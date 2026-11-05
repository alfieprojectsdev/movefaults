"""What the console shows, read from the processing service's own records.

Nothing here decides anything or writes anything. Each number comes from the
same code the command line uses: the ledger (bernese_workflow.ledger), the
scanner and known-errors list (bpe_scanner, bpe_knowledge), the diagnosis
(circuit_breaker.diagnose_day) and the BPE lock record (bpe_lock). Where the
service records nothing, the result says so instead of guessing.
"""

from __future__ import annotations

import datetime as dt
import gzip
import os
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from bernese_workflow import bpe_knowledge, ledger
from bernese_workflow.bpe_lock import BPELock
from bernese_workflow.bpe_lock import default_path as default_lock_path
from bernese_workflow.circuit_breaker import K_DEFAULT, MAX_FAILURES_DEFAULT, diagnose_day
from bernese_workflow.run_plan import fin_present, result_dir

from .settings import Campaign, Settings

GPS_EPOCH = dt.date(1980, 1, 6)

# PCF steps grouped by hundreds, the way the PCF's own comments group them.
GROUPS = [
    ("0xx", "copy"),
    ("1xx", "orbits"),
    ("2xx", "RINEX, CODSPP"),
    ("3xx", "baselines"),
    ("4xx", "ambiguities"),
    ("5xx", "ADDNEQ2, HELMCHK"),
    ("9xx", "R2S_SAV"),
]
_GROUP_OF = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 9: 6}

# Where each archived result lives and what it is. Order is the Day screen's.
RESULT_KINDS = [
    ("OUT", "R2S_", ".PRC", "BPE processing summary"),
    ("STA", "FIN_", ".CRD", "Final coordinates (the target output)"),
    ("SOL", "FIN_", ".SNX", "SINEX, one-session solution"),
    ("SOL", "FIN_", ".NQ0", "Normal equations, final"),
    ("SOL", "RED_", ".NQ0", "Normal equations, reduced"),
    ("ATM", "FIN_", ".TRO", "Troposphere, SINEX format"),
    ("ATM", "FIN_", ".TRP", "Troposphere, Bernese format"),
]
_V52_PREFIX = {"FIN_": "F1_", "RED_": "R1_", "R2S_": "R2S"}


# --------------------------------------------------------------------------- dates


def doy_date(year: int, doy: int) -> dt.date:
    return dt.date(year, 1, 1) + dt.timedelta(days=doy - 1)


def gps_week(day: dt.date) -> tuple[int, int]:
    n = (day - GPS_EPOCH).days
    return n // 7, n % 7


def day_info(year: int, doy: int, session_char: str = "0") -> dict:
    d = doy_date(year, doy)
    week, dow = gps_week(d)
    return {
        "year": year,
        "doy": doy,
        "date": d.isoformat(),
        "gps_week": week,
        "gps_day": dow,
        "session": f"{doy:03d}{session_char}",
    }


def days_in_year(year: int) -> int:
    return 366 if (year % 4 == 0 and year % 100 != 0) or year % 400 == 0 else 365


# --------------------------------------------------------------------------- paths


def _pcf_text(s: Settings, pcf: str) -> str | None:
    try:
        return (s.gpsuser / "PCF" / f"{pcf}.PCF").read_text(errors="replace")
    except OSError:
        return None


def year_dir(s: Settings, pcf: str, campaign: str, year: int) -> Path:
    """V_RESULT for that year, as run_plan reads it."""
    text = _pcf_text(s, pcf) or ""
    path, _ = result_dir(text, s.env, year, fallback=s.savedisk / campaign / str(year))
    return path


def campaign_years(s: Settings, c: Campaign) -> list[int]:
    this = dt.date.today().year
    return [y for y in range(this + 1, 2009, -1) if year_dir(s, c.pcf, c.name, y).is_dir()]


def ledger_path(s: Settings, c: Campaign, year: int) -> Path:
    return year_dir(s, c.pcf, c.name, year) / "ledger.jsonl"


def bpe_dirs(s: Settings, c: Campaign, year: int, session: str) -> list[Path]:
    """Where a day's BPE protocol files can be: its own campaign, then the shared one."""
    out = []
    if c.prefix:
        out.append(s.campaigns_dir / f"{c.prefix}{year % 100:02d}{session}" / "BPE")
    out.append(s.campaigns_dir / c.name / "BPE")
    return [p for p in out if p.is_dir()]


# --------------------------------------------------------------------------- ledger


@dataclass
class Attempt:
    run: str
    doy: int
    session: str
    started: float
    ended: float | None
    outcome: str | None  # ok | failed | not_run | None while open
    seconds: float | None
    error: str
    note: str
    stations: int | None
    mode: str

    def as_dict(self) -> dict:
        return {
            "run": self.run,
            "doy": self.doy,
            "session": self.session,
            "started": self.started,
            "ended": self.ended,
            "outcome": self.outcome or "running",
            "seconds": self.seconds,
            "error": self.error,
            "note": self.note,
            "stations": self.stations,
            "mode": self.mode,
        }


def attempts(entries: Iterable[dict]) -> list[Attempt]:
    """Pair every attempt_start with its attempt_end, in ledger order."""
    out: list[Attempt] = []
    open_: dict[tuple[str, int], Attempt] = {}
    for e in entries:
        ev = e.get("event")
        key = (e.get("run", ""), e.get("doy", -1))
        if ev == "attempt_start":
            a = Attempt(
                key[0],
                key[1],
                e.get("session", ""),
                e["ts"],
                None,
                None,
                None,
                "",
                "",
                None,
                e.get("mode", "day"),
            )
            open_[key] = a
            out.append(a)
        elif ev == "attempt_end":
            a = open_.pop(key, None)
            if a is None:  # closed without a start: a day the queue never began
                a = Attempt(
                    key[0],
                    key[1],
                    e.get("session", ""),
                    e["ts"],
                    None,
                    None,
                    None,
                    "",
                    "",
                    None,
                    e.get("mode", "day"),
                )
                out.append(a)
            a.ended = e["ts"]
            a.outcome = e.get("outcome")
            a.seconds = e.get("seconds")
            a.error = e.get("error") or ""
            a.note = e.get("note") or ""
            a.stations = e.get("stations")
    return out


def read_ledger(path: Path) -> list[dict]:
    entries, _ = ledger.read_entries(path)
    return entries


def run_provenance(start: dict | None) -> dict:
    """What a run's run_start says produced it: who, the command, the code, the
    PCF and products (recorded since #318, bernese_workflow/ledger.py).

    A run_start written before #318 has none of user, code or pcf: the same
    test ``ledger._provenance_line`` uses. Its fields are None and ``recorded``
    is False, so the page says "not recorded" for that run only. The config
    hash is older than #318 and is given either way.
    """
    out = {
        "recorded": False,
        "started_by": None,
        "command": None,
        "code_version": None,
        "pcf": None,
        "products": None,
        "product_tier": None,
        "config_hash": (start or {}).get("config"),
    }
    if not start or not any(k in start for k in ("user", "code", "pcf")):
        return out
    who = str(start.get("user") or "unknown")
    if start.get("sudo_user"):
        who += f" (sudo from {start['sudo_user']})"
    if start.get("submitted_by"):
        # bernese-worker runs as the service account and tags run_start with
        # the request (run_worker._TaggedLedger): the person who asked started it.
        who = f"{start['submitted_by']} (through the run worker as {who}"
        who += f", request {start['request']})" if start.get("request") else ")"
    command = start.get("command")
    if isinstance(command, list):
        command = " ".join(str(a) for a in command)
    elif command is not None and not isinstance(command, str):
        command = str(command)
    code = start.get("code")
    code = code if isinstance(code, dict) else {}
    commit = str(code.get("commit") or "unknown")
    version = commit if commit == "unknown" else commit[:10]
    if commit != "unknown":
        # As the ledger's status line: a bare sha would read as "clean".
        if code.get("dirty"):
            version += " (dirty)"
        elif code.get("dirty") is None:
            version += " (dirty unknown)"
    out.update(
        recorded=True,
        started_by=who,
        command=command or None,
        code_version=version,
        pcf=start.get("pcf"),
        products=start.get("products"),
        product_tier=start.get("product_tier"),
    )
    return out


def runs_in(entries: list[dict]) -> list[dict]:
    """One record per run, newest first, with the status the CLI would print."""
    starts = [e for e in entries if e["event"] == "run_start"]
    out = []
    for st in reversed(starts):
        mine = [e for e in entries if e.get("run") == st["run"]]
        # run_status reads the most recent run_start; give it this run alone.
        status = ledger.run_status(mine)
        end = next((e for e in mine if e["event"] == "run_end"), None)
        out.append(
            {
                "run": st["run"],
                "started": st["ts"],
                "ended": end["ts"] if end else None,
                "host": st.get("host"),
                "pid": st.get("pid"),
                "doys": st.get("doys") or [],
                "banked": st.get("banked") or [],
                "config": st.get("config"),
                "provenance": run_provenance(st),
                "state": status.state,
                "halt": end.get("halt") if end else None,
                "status_lines": status.lines,
            }
        )
    return out


# --------------------------------------------------------------------------- day states


def _solved(sol_dir: Path, year: int, doy: int) -> bool:
    return fin_present(sol_dir, year, doy)


def day_states(s: Settings, c: Campaign, year: int) -> dict:
    """Every day of the year, with a state the calendar colours by.

    solved fixed / float from the FIN files in SAVEDISK (float: solved only by
    the float PCF); failed, running and queued from the ledger. ``excluded`` is
    a plan's decision and the ledger does not record plans, so it is never
    reported from here.
    """
    sol = year_dir(s, c.pcf, c.name, year) / "SOL"
    fsol = year_dir(s, c.float_pcf, c.name, year) / "SOL" if c.float_pcf else None
    entries = read_ledger(ledger_path(s, c, year))
    atts = attempts(entries)
    latest: dict[int, Attempt] = {}
    for a in atts:
        latest[a.doy] = a
    runs = runs_in(entries)
    live = runs[0] if runs and runs[0]["state"] in ("running", "slow", "unknown") else None
    live_doys = set(live["doys"]) if live else set()

    days = []
    counts = dict.fromkeys(("fixed", "float", "failed", "running", "queued", "excluded", "none"), 0)
    for doy in range(1, days_in_year(year) + 1):
        a = latest.get(doy)
        if sol.is_dir() and _solved(sol, year, doy):
            state = "fixed"
        elif fsol is not None and fsol.is_dir() and _solved(fsol, year, doy):
            state = "float"
        elif a is not None and a.outcome is None and live and a.run == live["run"]:
            state = "running"
        elif a is not None and a.outcome == "failed":
            state = "failed"
        elif doy in live_doys and not (a is not None and a.run == live["run"] and a.outcome):
            state = "queued"
        else:
            state = "none"
        counts[state] += 1
        note = ""
        if a is not None and state in ("failed", "running"):
            note = a.error or a.note
        days.append({**day_info(year, doy), "state": state, "note": note})
    return {"campaign": c.name, "year": year, "counts": counts, "days": days}


# --------------------------------------------------------------------------- lock


def flock_held(path: Path, proc_locks: Path = Path("/proc/locks")) -> bool:
    """Whether any process holds an flock on ``path``, read from /proc/locks.

    Testing by taking the lock would, for that instant, make its real owner
    find it held and refuse to start. False when the file does not exist.
    """
    try:
        st = path.stat()
        want = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
        for line in proc_locks.read_text().splitlines():
            f = line.split()
            if "FLOCK" in f and "->" not in f and want in f:
                return True
    except OSError:
        pass
    return False


def lock_status(s: Settings, proc_locks: Path = Path("/proc/locks")) -> dict:
    """Who holds the BPE lock, read without taking it.

    Taking the lock to test it would, for that instant, make a BPE starting on
    the machine find it held and refuse (scripts/local_ci.py reads it the same
    way, for the same reason).
    """
    path = s.lock_path or default_lock_path()
    held = flock_held(path, proc_locks)
    holder = BPELock.describe_holder(path) if path.exists() else ""
    return {
        "held": held,
        "holder": holder if held else "",
        "last_holder": holder,
        "path": str(path),
    }


# --------------------------------------------------------------------------- run grid


def _pid_of(path: Path) -> int | None:
    m = re.search(r"_(\d{3})_\d{3}$", path.stem)
    return int(m[1]) if m else None


def _group(pid: int) -> int:
    return _GROUP_OF.get(pid // 100, 6)


def _latest_pid(bpe: Path, year: int, session: str, since: float) -> int | None:
    pids = [
        p
        for p in bpe.glob(f"*{year % 100:02d}{session}_[0-9][0-9][0-9]_[0-9][0-9][0-9].PRT")
        if p.stat().st_mtime >= since - 1
    ]
    found = [_pid_of(p) for p in pids]
    found = [f for f in found if f is not None]
    return max(found) if found else None


def run_detail(s: Settings, c: Campaign, year: int, run_id: str | None = None) -> dict:
    """Days x PCF step groups for one run (the latest if ``run_id`` is None)."""
    entries = read_ledger(ledger_path(s, c, year))
    runs = runs_in(entries)
    if not runs:
        return {"campaign": c.name, "year": year, "run": None, "runs": []}
    run = next((r for r in runs if r["run"] == run_id), None) if run_id else runs[0]
    if run is None:
        raise KeyError(run_id)
    mine = [e for e in entries if e.get("run") == run["run"]]
    atts = attempts(mine)
    latest = {a.doy: a for a in atts}

    rows = []
    for doy in run["doys"]:
        a = latest.get(doy)
        info = day_info(year, doy)
        cells = ["wait"] * len(GROUPS)
        pid: int | None = None
        if doy in run["banked"]:
            outcome = "already solved"
            cells = ["done"] * len(GROUPS)
        elif a is None:
            outcome = "not started (halted)" if run["halt"] else "queued"
        elif a.outcome == "ok":
            outcome = "solved"
            cells = ["done"] * len(GROUPS)
        elif a.outcome == "not_run":
            outcome = "not started"
        elif a.outcome == "failed":
            outcome = "failed"
            pid = _failed_pid(s, c, year, a)
            g = _group(pid) if pid is not None else None
            if g is not None:
                cells = ["done"] * g + ["failed"] + ["wait"] * (len(GROUPS) - g - 1)
        else:
            outcome = "running"
            for bpe in bpe_dirs(s, c, year, a.session):
                pid = _latest_pid(bpe, year, a.session, a.started)
                if pid is not None:
                    break
            g = _group(pid) if pid is not None else 0
            cells = ["done"] * g + ["running"] + ["wait"] * (len(GROUPS) - g - 1)
        secs = (
            a.seconds
            if a and a.seconds is not None
            else (time.time() - a.started if a and a.outcome is None else None)
        )
        rows.append(
            {
                **info,
                "outcome": outcome,
                "error": a.error if a else "",
                "note": a.note if a else "",
                "pid": pid,
                "cells": cells,
                "seconds": secs,
            }
        )

    # The circuit breaker's counters, recomputed from the run's attempt order.
    same = anyf = 0
    last_key = None
    for a in sorted((a for a in atts if a.outcome in ("ok", "failed")), key=lambda a: a.ended or 0):
        if a.outcome == "ok":
            same = anyf = 0
            last_key = None
            continue
        same = same + 1 if a.error == last_key else 1
        last_key = a.error
        anyf += 1
    oks = [a.seconds for a in atts if a.outcome == "ok" and a.seconds]
    median = sorted(oks)[len(oks) // 2] if oks else None
    return {
        "campaign": c.name,
        "year": year,
        "run": run,
        "runs": [
            {k: r[k] for k in ("run", "started", "ended", "state", "halt", "doys")} for r in runs
        ],
        "groups": [{"key": k, "name": n} for k, n in GROUPS],
        "rows": rows,
        "breaker": {
            "identical": same,
            "identical_limit": K_DEFAULT,
            "any": anyf,
            "any_limit": MAX_FAILURES_DEFAULT,
            "last_error": last_key or "",
        },
        "median_seconds": median,
    }


def _failed_pid(s: Settings, c: Campaign, year: int, a: Attempt) -> int | None:
    d = _diagnosis(s, c, year, a)
    return _pid_of(d.step) if d is not None and d.step is not None else None


# --------------------------------------------------------------------------- diagnosis


def _kb(s: Settings) -> bpe_knowledge.KnowledgeBase:
    return bpe_knowledge.load(s.kb_path) if s.kb_path else bpe_knowledge.load()


def _diagnosis(s: Settings, c: Campaign, year: int, a: Attempt):
    kb = _kb(s)
    for bpe in bpe_dirs(s, c, year, a.session):
        d = diagnose_day(bpe, year, a.session, a.started, kb)
        if d.step is not None:
            return d
    return None


def entry_dict(e: bpe_knowledge.Entry | None) -> dict | None:
    if e is None:
        return None
    return {
        "emitter": e.emitter,
        "message": e.message,
        "scope": e.scope,
        "status": e.status,
        "diagnosis": e.diagnosis,
        "remedy": e.remedy,
        "source": e.source,
        "confirm": e.confirm,
        "number": e.number,
    }


def entry_for_label(kb: bpe_knowledge.KnowledgeBase, label: str) -> bpe_knowledge.Entry | None:
    """The entry a ledger error label names: Diagnosis.label is 'emitter: KIND'."""
    if ": " not in label:
        return None
    emitter, kind = label.split(": ", 1)
    return next((e for e in kb.entries if e.key == (emitter.lower(), kind)), None)


def _verdict(entry: bpe_knowledge.Entry | None, label: str) -> dict:
    if entry is None:
        return {
            "kind": "unknown",
            "text": "Stopped for a person.",
            "detail": "The message is not in the known-errors list. An unknown failure always stops the run.",
        }
    if entry.scope == "configuration":
        return {
            "kind": "configuration",
            "text": "Stopped at once.",
            "detail": "Configuration-scope error: every remaining day would fail the same way.",
        }
    return {
        "kind": "session",
        "text": "Counted, and the run continued.",
        "detail": f"Session-scope error: {K_DEFAULT} identical failures in a row stop the run.",
    }


def failure(s: Settings, c: Campaign, year: int, doy: int) -> dict:
    """The latest failed attempt at a day, its raw lines and the known-errors entry."""
    entries = read_ledger(ledger_path(s, c, year))
    failed = [a for a in attempts(entries) if a.doy == doy and a.outcome == "failed"]
    if not failed:
        raise KeyError(f"no failed attempt at DOY {doy:03d}")
    a = failed[-1]
    kb = _kb(s)
    d = _diagnosis(s, c, year, a)
    out = {
        **day_info(year, doy),
        "campaign": c.name,
        "attempt": a.as_dict(),
        "attempt_number": len([x for x in attempts(entries) if x.doy == doy and x.outcome]),
        "label": a.error,
        "file": None,
        "pid": None,
        "script": None,
        "program": None,
        "cause": None,
        "lines": [],
        "first_current_line": 0,
    }
    entry = None
    if d is not None and d.step is not None and d.report is not None:
        text = d.step.read_text(errors="replace").splitlines()
        cause = d.report.cause
        entry = d.entry
        pid = _pid_of(d.step)
        out.update(
            file=f"BPE/{d.step.name}",
            pid=pid,
            script=_script_for(s, c, pid),
            program=d.report.failed_program,
            cause=None
            if cause is None
            else {
                "emitter": cause.emitter,
                "emitter_type": cause.emitter_type,
                "program": cause.program,
                "headline": cause.headline,
                "kind": cause.kind,
                "detail": list(cause.detail),
                "params": cause.params,
                "line": cause.line,
            },
            lines=text,
            first_current_line=_last_attempt_start(text),
        )
    else:
        entry = entry_for_label(kb, a.error)
    out["entry"] = entry_dict(entry)
    out["verdict"] = _verdict(entry, a.error)
    return out


_ATTEMPT_RE = re.compile(r"^\s*PROTOCOL FILE FOR BPE SCRIPT\s*$")


def _last_attempt_start(lines: list[str]) -> int:
    """Index of the last attempt's first line; earlier attempts are history."""
    idx = [i for i, t in enumerate(lines) if _ATTEMPT_RE.match(t)]
    return idx[-1] if idx else 0


def _script_for(s: Settings, c: Campaign, pid: int | None) -> str | None:
    if pid is None:
        return None
    text = _pcf_text(s, c.pcf) or ""
    m = re.search(rf"^{pid:03d}\s+(\S+)", text, re.MULTILINE)
    return m[1] if m else None


# --------------------------------------------------------------------------- day


def _v52_name(name: str, year: int) -> str:
    for new, old in _V52_PREFIX.items():
        if name.startswith(new):
            rest = name[len(new) :].replace(f"{year}", f"{year % 100:02d}", 1)
            return (old + rest).removesuffix(".gz")
    return name


def day_results(
    s: Settings, c: Campaign, year: int, doy: int, session_char: str = "0"
) -> list[dict]:
    base = year_dir(s, c.pcf, c.name, year)
    stamp = f"{year}{doy:03d}{session_char}"
    out = []
    for folder, prefix, ext, what in RESULT_KINDS:
        name = f"{prefix}{stamp}{ext}"
        for cand in (name, name + ".gz"):
            p = base / folder / cand
            if p.is_file():
                st = p.stat()
                out.append(
                    {
                        "name": cand,
                        "v52": _v52_name(cand, year),
                        "folder": folder,
                        "what": what,
                        "size": st.st_size,
                        "written": st.st_mtime,
                        "path": f"{folder}/{cand}",
                    }
                )
                break
        else:
            out.append(
                {
                    "name": name,
                    "v52": _v52_name(name, year),
                    "folder": folder,
                    "what": what,
                    "size": None,
                    "written": None,
                    "path": None,
                }
            )
    return out


def _open_text(p: Path) -> list[str]:
    if p.suffix == ".gz":
        with gzip.open(p, "rt", errors="replace") as fh:
            return fh.read().splitlines()
    return p.read_text(errors="replace").splitlines()


def _snx_sites(p: Path) -> set[str]:
    sites: set[str] = set()
    on = False
    for line in _open_text(p):
        if line.startswith("+SITE/ID"):
            on = True
        elif line.startswith("-SITE/ID"):
            break
        elif on and line.startswith(" ") and len(line) > 5:
            sites.add(line[1:5])
    return sites


_HELM_RMS = re.compile(r"RMS OF TRANSFORMATION\s*:\s*([\d.]+)\s*MM")


def day_quality(s: Settings, c: Campaign, year: int, doy: int) -> dict:
    """Stations in the solution (and those dropped since the day before), HELMCHK RMS."""
    base = year_dir(s, c.pcf, c.name, year)

    def snx(d: int) -> Path | None:
        for n in (f"FIN_{year}{d:03d}0.SNX.gz", f"FIN_{year}{d:03d}0.SNX"):
            if (base / "SOL" / n).is_file():
                return base / "SOL" / n
        return None

    q: dict = {
        "stations": None,
        "dropped": [],
        "helmert_rms_mm": None,
        "ambiguity_rate": None,
        "sources": {},
    }
    now = snx(doy)
    if now:
        sites = _snx_sites(now)
        q["stations"] = len(sites)
        q["sources"]["stations"] = f"SOL/{now.name}"
        before = snx(doy - 1) if doy > 1 else None
        if before:
            q["dropped"] = sorted(_snx_sites(before) - sites)
    prc = base / "OUT" / f"R2S_{year}{doy:03d}0.PRC"
    if prc.is_file():
        for i, line in enumerate(_open_text(prc)):
            m = _HELM_RMS.search(line)
            if m:
                q["helmert_rms_mm"] = float(m[1])
                q["sources"]["helmert_rms_mm"] = f"OUT/{prc.name}:{i + 1}"
    # The ambiguity fixing rate is in the AMB_*.SUM listings, which the archive
    # step does not keep. Not reported rather than estimated.
    return q


def day_detail(s: Settings, c: Campaign, year: int, doy: int) -> dict:
    entries = read_ledger(ledger_path(s, c, year))
    atts = [a for a in attempts(entries) if a.doy == doy]
    runs = {r["run"]: r for r in runs_in(entries)}
    results = day_results(s, c, year, doy)
    states = day_states(s, c, year)["days"][doy - 1]

    def prov(run: str) -> dict:
        return runs[run]["provenance"] if run in runs else run_provenance(None)

    # The day block describes the latest attempt's run: that attempt made, or
    # failed to make, the results listed below.
    latest_run = atts[-1].run if atts else None
    latest = prov(latest_run) if latest_run else run_provenance(None)
    return {
        **day_info(year, doy),
        "campaign": c.name,
        "state": states["state"],
        "attempts": [
            {
                **a.as_dict(),
                "config": runs.get(a.run, {}).get("config"),
                "host": runs.get(a.run, {}).get("host"),
                "provenance": prov(a.run),
            }
            for a in reversed(atts)
        ],
        "results": results,
        "present": sum(1 for r in results if r["path"]),
        "quality": day_quality(s, c, year, doy),
        "provenance": {
            # The PCF the run recorded; before #318, the campaign's configured one.
            "pcf": f"{latest['pcf'] or c.pcf}.PCF",
            "ambiguities": {"fixed": "fixed", "float": "float"}.get(states["state"], "—"),
            "campaign_dir": f"${{P}}/{c.prefix}{year % 100:02d}{doy:03d}0"
            if c.prefix
            else f"${{P}}/{c.name}",
            # From the latest attempt's run_start. A run before #318 did not
            # record them: None, shown as "not recorded", never guessed.
            "run": latest_run,
            "recorded": latest["recorded"],
            "started_by": latest["started_by"],
            "command": latest["command"],
            "code_version": latest["code_version"],
            "products": latest["products"],
            "product_tier": latest["product_tier"],
            "config_hash": next(
                (runs[a.run]["config"] for a in reversed(atts) if a.run in runs), None
            ),
        },
    }


def read_day_file(
    s: Settings, c: Campaign, year: int, doy: int, name: str, max_lines: int = 50000
) -> dict:
    """A day's file by its listed name: an archived result, or a BPE protocol file.

    The name must be one this server listed for the day; anything else is
    refused, so no path from the browser ever reaches the filesystem.
    """
    allowed: dict[str, Path] = {}
    base = year_dir(s, c.pcf, c.name, year)
    for r in day_results(s, c, year, doy):
        if r["path"]:
            allowed[r["path"]] = base / r["path"]
    session = f"{doy:03d}0"
    for bpe in bpe_dirs(s, c, year, session):
        for p in bpe.glob(f"*{year % 100:02d}{session}_[0-9][0-9][0-9]_[0-9][0-9][0-9].*"):
            if p.suffix in (".PRT", ".LOG"):
                allowed[f"BPE/{p.name}"] = p
    if name not in allowed:
        raise KeyError(name)
    lines = _open_text(allowed[name])
    return {
        "name": name,
        "lines": lines[:max_lines],
        "truncated": len(lines) > max_lines,
        "total": len(lines),
    }


# --------------------------------------------------------------------------- campaigns


def campaign_summary(s: Settings, c: Campaign) -> dict:
    years = []
    last_run = None
    for y in campaign_years(s, c):
        st = day_states(s, c, y)
        n = st["counts"]
        years.append(
            {
                "year": y,
                "fixed": n["fixed"],
                "float": n["float"],
                "failed": n["failed"],
                "not_run": n["none"] + n["queued"] + n["running"],
            }
        )
        runs = runs_in(read_ledger(ledger_path(s, c, y)))
        if runs and (last_run is None or runs[0]["started"] > last_run["started"]):
            last_run = {**runs[0], "year": y}
    return {
        "name": c.name,
        "pcf": c.pcf,
        "float_pcf": c.float_pcf,
        "prefix": c.prefix,
        "years": years,
        "last_run": last_run,
    }


def activity(s: Settings, limit: int = 20) -> list[dict]:
    """Recent events from every campaign's ledger, newest first."""
    out = []
    for c in s.campaigns:
        for y in campaign_years(s, c):
            for e in read_ledger(ledger_path(s, c, y)):
                ev = e["event"]
                if ev == "run_start":
                    n = len(e.get("doys") or [])
                    text = f"Run {e.get('run')} started: {n} day(s), {len(e.get('banked') or [])} already solved."
                elif ev == "run_end":
                    text = (
                        f"Run {e.get('run')} halted: {e['halt']}"
                        if e.get("halt")
                        else f"Run {e.get('run')} finished."
                    )
                elif ev == "attempt_end" and e.get("outcome") == "failed":
                    text = f"DOY {e['doy']:03d} failed: {e.get('error') or e.get('note')}"
                else:
                    continue
                out.append(
                    {
                        "ts": e["ts"],
                        "who": e.get("host") or "service",
                        "campaign": c.name,
                        "year": y,
                        "doy": e.get("doy"),
                        "event": ev,
                        "text": text,
                    }
                )
    out.sort(key=lambda r: r["ts"], reverse=True)
    return out[:limit]


# --------------------------------------------------------------------------- known errors


def known_errors(s: Settings, days: int = 30) -> dict:
    kb = _kb(s)
    since = time.time() - days * 86400
    fired: dict[tuple[str, str], list[dict]] = {}
    unknown = []
    for c in s.campaigns:
        for y in campaign_years(s, c):
            for a in attempts(read_ledger(ledger_path(s, c, y))):
                if a.outcome != "failed" or (a.ended or 0) < since:
                    continue
                e = entry_for_label(kb, a.error)
                where = {"campaign": c.name, "year": y, "doy": a.doy, "ts": a.ended}
                if e is None:
                    unknown.append({**where, "label": a.error})
                else:
                    fired.setdefault(e.key, []).append(where)
    rows = []
    for e in kb.entries:
        hits = sorted(fired.get(e.key, []), key=lambda w: w["ts"] or 0)
        rows.append({**entry_dict(e), "fired": len(hits), "last": hits[-1] if hits else None})
    path = s.kb_path or bpe_knowledge.DEFAULT_PATH
    return {"path": str(path), "days": days, "entries": rows, "unknown": unknown}
