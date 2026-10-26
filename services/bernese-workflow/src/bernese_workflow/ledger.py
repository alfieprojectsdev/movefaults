"""Append-only record of every attempt at a day, and the run status read from it.

WHY THIS EXISTS
Status today is inferred from files on disk: scripts/luzon_status.sh counts
FIN_*.SNX.gz and calls a run STALLED when that count has not moved for 45
minutes. From the count alone a slow day, a dead driver and a run that keeps
failing look the same, so the script needs a state file to remember the last
count and still cannot say which day is in progress, for how long, or why
earlier days failed. The ledger records those directly.

WHAT IS WRITTEN
One JSON object per line, appended and fsynced, never rewritten:

  run_start      a run_days call began: run id, host, pid, campaign, year, the
                 days asked for, the days already banked, and the config hash
  attempt_start  a day was handed to the backend
  attempt_end    that day finished: outcome ok | failed, seconds, error, note,
                 station count
  run_end        the call returned; ``halt`` is the circuit breaker's reason,
                 or null when every day was attempted

A run with a run_start and no run_end was interrupted, or is still running.
Which one is decided from the pid: alive on this host means running.

THE .done MARKERS STAY
month_driver still writes and checks FIN_*.done. The ledger records what
happened; the marker is the evidence next to the file that a day finished.
Whether to retire the markers is an open decision (cutover plan 2.7), and
keeping both is the choice that can be undone.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import statistics
import sys
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

LEDGER_VERSION = 1
SLOW_FACTOR_DEFAULT = 2.0


def config_hash(paths: Iterable[Path]) -> str:
    """12 hex digits over the names and contents of the files that define a run.

    Pass the PCF and the option-directory panels. Two attempts with the same
    hash ran the same configuration; a changed hash between two attempts at one
    day is the first thing to look at when their outcomes differ.

    Each file is named by its directory and name (R2S_FIN/ADDNEQ2.INP): option
    directories reuse panel names, and the absolute path would differ by host.
    """
    h = hashlib.sha256()
    for p in sorted(Path(p) for p in paths):
        h.update(f"{p.parent.name}/{p.name}".encode() + b"\0")
        h.update(p.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:12]


class Ledger:
    """Writer for one ledger file. Each entry is one fsynced line."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.run_id: str | None = None

    def _append(self, event: str, **fields: object) -> None:
        entry = {"v": LEDGER_VERSION, "ts": round(time.time(), 3), "event": event}
        if self.run_id is not None:
            entry["run"] = self.run_id
        entry.update(fields)
        line = json.dumps(entry, separators=(",", ":")) + "\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # O_APPEND makes each write land at the end even with two writers; one
        # line per write keeps entries whole.
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def run_start(
        self,
        *,
        campaign: str,
        year: int,
        doys: list[int],
        banked: list[int],
        config: str | None = None,
    ) -> str:
        self.run_id = uuid.uuid4().hex[:8]
        self._append(
            "run_start",
            host=socket.gethostname(),
            pid=os.getpid(),
            campaign=campaign,
            year=year,
            doys=doys,
            banked=banked,
            config=config,
        )
        return self.run_id

    def attempt_start(self, *, doy: int, session: str, **extra: object) -> None:
        """``extra`` is written as is: step F tags parallel runs mode="block", block=[a, b]."""
        self._append("attempt_start", doy=doy, session=session, **extra)

    def attempt_end(
        self,
        *,
        doy: int,
        session: str,
        outcome: str,
        seconds: float,
        error: str = "",
        note: str = "",
        stations: int | None = None,
        **extra: object,
    ) -> None:
        """``outcome`` is ok, failed or not_run (a day a stopped queue never started)."""
        self._append(
            "attempt_end",
            doy=doy,
            session=session,
            outcome=outcome,
            seconds=round(seconds, 1),
            error=error,
            note=note,
            stations=stations,
            **extra,
        )

    def run_end(self, *, halt: str | None) -> None:
        self._append("run_end", halt=halt)


def read_entries(path: Path) -> tuple[list[dict], int]:
    """All entries, and how many lines could not be read.

    A torn last line (power loss mid-write) is skipped and counted, not fatal:
    every earlier line is still a complete record.
    """
    entries: list[dict] = []
    bad = 0
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return [], 0
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            bad += 1
            continue
        if isinstance(entry, dict) and "event" in entry:
            entries.append(entry)
        else:
            bad += 1
    return entries, bad


def _pid_alive(host: str, pid: int) -> bool | None:
    """True or False on this host; None when the run is on another host."""
    if host != socket.gethostname():
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _doys(attempts: list[dict]) -> str:
    """'DOY 004', or 'DOY 008-010' for a span, or a comma list when not contiguous."""
    ds = sorted({e["doy"] for e in attempts})
    if len(ds) == 1:
        return f"DOY {ds[0]:03d}"
    if ds == list(range(ds[0], ds[-1] + 1)):
        return f"DOY {ds[0]:03d}-{ds[-1]:03d}"
    return "DOY " + ", ".join(f"{d:03d}" for d in ds)


@dataclass
class RunStatus:
    state: str  # none | running | slow | finished | halted | dead | unknown
    exit_code: int
    lines: list[str] = field(default_factory=list)


# Exit codes, so the status can drive cron or mail as luzon_status.sh's did.
EXIT = {"running": 0, "finished": 1, "slow": 2, "dead": 3, "halted": 4, "unknown": 5, "none": 5}


def run_status(
    entries: list[dict],
    *,
    now: float | None = None,
    slow_factor: float = SLOW_FACTOR_DEFAULT,
    alive=_pid_alive,
) -> RunStatus:
    """Status of the most recent run in the ledger.

    Slow and broken are different answers. Slow: a day is in progress and has
    taken more than ``slow_factor`` times the median of this ledger's successful
    days. Broken: the circuit breaker halted the run (halted), or the driver
    is gone without a run_end (dead).
    """
    now = time.time() if now is None else now
    starts = [e for e in entries if e["event"] == "run_start"]
    if not starts:
        return RunStatus("none", EXIT["none"], ["no run recorded"])
    start = starts[-1]
    run = start.get("run")
    mine = [e for e in entries if e.get("run") == run]
    ends = [e for e in mine if e["event"] == "attempt_end"]
    ok = [e for e in ends if e.get("outcome") == "ok"]
    failed = [e for e in ends if e.get("outcome") == "failed"]
    not_run = [e for e in ends if e.get("outcome") == "not_run"]
    asked = start.get("doys") or []
    banked = start.get("banked") or []
    done_doys = {e["doy"] for e in ends}
    left = [d for d in asked if d not in done_doys and d not in banked]

    lines = [
        f"run {run}  {start.get('campaign')} {start.get('year')}  host {start.get('host')} "
        f"pid {start.get('pid')}  config {start.get('config') or '-'}",
        f"  started {time.strftime('%Y-%m-%d %H:%M', time.localtime(start['ts']))}; "
        f"{len(asked)} days asked, {len(banked)} already banked",
        f"  ok {len(ok)}   failed {len(failed)}   not run {len(not_run)}   "
        f"not yet attempted {len(left)}",
    ]
    for e in failed[-5:]:
        lines.append(f"  failed DOY {e['doy']:03d}: {e.get('error') or e.get('note')}")

    open_attempts = [e for e in mine if e["event"] == "attempt_start" and e["doy"] not in done_doys]
    # Days run one at a time and days run as a parallel block take different
    # wall times; judge the attempts in flight against earlier ones run the same way.
    mode = open_attempts[-1].get("mode", "day") if open_attempts else "day"
    durations = [
        e["seconds"]
        for e in entries
        if e["event"] == "attempt_end" and e.get("outcome") == "ok" and e.get("mode", "day") == mode
    ]
    typical = statistics.median(durations) if durations else None
    if typical is not None:
        what = "day" if mode == "day" else f"{mode} run"
        lines.append(f"  typical {what}: {typical / 60:.1f} min (median of {len(durations)})")

    end = next((e for e in mine if e["event"] == "run_end"), None)
    if end is not None:
        if end.get("halt"):
            lines.append(f"  HALTED: {end['halt']}")
            return RunStatus("halted", EXIT["halted"], lines)
        lines.append("  finished")
        return RunStatus("finished", EXIT["finished"], lines)

    living = alive(start.get("host", ""), int(start.get("pid", -1)))
    if living is False:
        where = f" during {_doys(open_attempts)}" if open_attempts else ""
        lines.append(f"  DEAD: the driver is gone{where}, with {len(left)} days outstanding")
        return RunStatus("dead", EXIT["dead"], lines)
    if not open_attempts:
        lines.append("  running, between days")
        return RunStatus(
            "running" if living else "unknown", EXIT["running" if living else "unknown"], lines
        )
    elapsed = now - min(e["ts"] for e in open_attempts)
    if len(open_attempts) == 1:
        lines.append(f"  {_doys(open_attempts)} in progress for {elapsed / 60:.1f} min")
    else:
        lines.append(
            f"  {len(open_attempts)} days in progress ({_doys(open_attempts)}), "
            f"the oldest for {elapsed / 60:.1f} min"
        )
    if living is None:
        lines.append("  (run is on another host: cannot tell running from dead)")
        return RunStatus("unknown", EXIT["unknown"], lines)
    if typical is not None and elapsed > slow_factor * typical:
        lines.append(f"  SLOW: more than {slow_factor:g} x the typical day")
        return RunStatus("slow", EXIT["slow"], lines)
    return RunStatus("running", EXIT["running"], lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Status of a run, read from its ledger.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="print the latest run's status; exit code carries the state")
    st.add_argument("ledger", type=Path)
    st.add_argument("--slow-factor", type=float, default=SLOW_FACTOR_DEFAULT)
    args = ap.parse_args(argv)

    entries, bad = read_entries(args.ledger)
    status = run_status(entries, slow_factor=args.slow_factor)
    print(f"{status.state.upper()}  ({args.ledger})")
    print("\n".join(status.lines))
    if bad:
        print(f"  note: {bad} unreadable line(s) skipped")
    return status.exit_code


if __name__ == "__main__":
    sys.exit(main())
