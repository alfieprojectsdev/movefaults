"""Run a range of days as blocks of parallel sessions, each in its own campaign.

WHY THIS EXISTS
scripts/run_phref_year.sh and run_luzon_year.sh process a year in parallel by
calling a Perl driver once per block of consecutive days. This is the service's
version of them (cutover step F), built on what month_driver already does for
single sessions: a day counts as done only when its FIN is on disk and banked,
a failed day is diagnosed from its own step output and the known-errors list,
and the circuit breaker decides whether the run goes on.

HOW BSW RUNS A BLOCK (MENU/bpe.cpp, server.cpp; config/.../sessions_pcs.pl)
One BPE call runs NUM_SESS consecutive sessions, at most MAXSESS at a time.
With REPR_MODE each session gets a private campaign ${P}/<prefix><yy><ssss>,
which is what makes parallel sessions safe (with one shared campaign, 4 of 5
failed on 2026-08-12, each consuming the others' staged RINEX). With NEXTSESS=0
the server starts no new session after the first error; the ones already
running finish, then the BPE ends.

WHAT A BLOCK LEAVES, AND WHAT THIS DOES WITH IT
After each call every day of the block is judged by what is on disk:
  a fresh, intact FIN           banked (.done written and fsynced), and only
                                THEN its private campaign is deleted
  no fresh FIN, but the server  failed: diagnosed from that campaign's own BPE/
  ran it (status or campaign)   (private, so no other session's PRT is in it);
                                the campaign is kept for autopsy
  neither                       not started: queued behind the error
The breaker hears the started days in day order. If it does not halt, the
block resumes from its first day not yet run, as the shell drivers' resume loop
does; if it halts, every day not yet run is reported not_run.

Blocks are cut into chunks of at most ``chunk_days`` (default 2 x maxsess):
successful campaigns are kept until their day is banked, so a chunk bounds how
many exist at once (~283 MB each).

PREFLIGHT
With ``preflight=True`` and a plan that names its busiest day, that day runs
alone first, so a configuration error such as a too-small MAXPAR stops the run
after one session instead of failing a block.

WHAT IT DOES NOT DO
It never retries a failed day within a run and never deletes anything but a
banked day's private campaign. The base campaign is never touched. A run is
started for an explicit range: it never defaults to a whole year.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import shutil
import signal
import sys
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import FrameType
from typing import Protocol

from .backends import SessionsResult, repr_campaign_name
from .bpe_knowledge import DEFAULT_PATH, KnowledgeBase, load
from .circuit_breaker import (
    K_DEFAULT,
    MAX_FAILURES_DEFAULT,
    CircuitBreaker,
    Diagnosis,
    diagnose_day,
)
from .month_driver import (
    DayOutcome,
    _done_marker,
    _fin_mtimes,
    _fresh_fin,
    _write_marker,
    fin_banked,
    session_for,
)

logger = logging.getLogger(__name__)


# --- what this module needs from its collaborators, without importing them -------------


class SessionsBackend(Protocol):
    def run_sessions(
        self,
        campaign_name: str,
        year: int,
        first_session: str,
        n_sessions: int,
        *,
        maxsess: int,
        repr_prefix: str,
    ) -> SessionsResult: ...


class PlanLike(Protocol):
    """What run_year reads from a plan: run_plan.RunPlan has this shape."""

    year: int
    todo: list[int]
    problems: list[str]

    @property
    def blocks(self) -> list[tuple[int, int]]: ...

    @property
    def busiest(self) -> int | None: ...


class RunLedger(Protocol):
    """What run_year writes to a ledger: ledger.Ledger has this shape."""

    def run_start(
        self,
        *,
        campaign: str,
        year: int,
        doys: list[int],
        banked: list[int],
        config: str | None = None,
    ) -> str: ...

    def attempt_start(self, *, doy: int, session: str, **extra: object) -> None: ...

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
    ) -> None: ...

    def run_end(self, *, halt: str | None) -> None: ...


def contiguous_blocks(days: Iterable[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for d in sorted(set(days)):
        if out and d == out[-1][1] + 1:
            out[-1] = (out[-1][0], d)
        else:
            out.append((d, d))
    return out


@dataclass
class SimplePlan:
    """A plan when none is supplied: the days to run, nothing more."""

    year: int
    todo: list[int]
    problems: list[str] = field(default_factory=list)
    busiest: int | None = None

    @property
    def blocks(self) -> list[tuple[int, int]]:
        return contiguous_blocks(self.todo)


def chunks(blocks: Iterable[tuple[int, int]], size: int) -> list[tuple[int, int]]:
    """Cut each block into pieces of at most ``size`` days, in order."""
    if size < 1:
        raise ValueError(f"chunk size must be >= 1, got {size}")
    out: list[tuple[int, int]] = []
    for a, b in blocks:
        for s in range(a, b + 1, size):
            out.append((s, min(s + size - 1, b)))
    return out


def _segments(plan: PlanLike, todo: list[int], preflight: bool) -> list[tuple[int, int]]:
    blocks = contiguous_blocks(todo)
    first = plan.busiest if preflight else None
    if first is None or first not in todo:
        return blocks
    rest = contiguous_blocks(d for d in todo if d != first)
    return [(first, first), *rest]


# <yy><ddd><session char>, e.g. 251520 in PHR251520
_REPR_SUFFIX = re.compile(r"^\d{5}[A-Za-z0-9]$")


def _built_since(path: Path, since: float) -> bool:
    """A directory created (or rebuilt) at or after ``since``."""
    try:
        return path.stat().st_mtime >= since - 1
    except FileNotFoundError:
        return False


def _remove_private_campaign(campaign_dir: Path, name: str, base: str, prefix: str) -> None:
    """Delete one session's private campaign, refusing anything that is not one:
    it must be <prefix><yy><ssss>, directly under the campaign directory, and not
    the base campaign."""
    path = campaign_dir / name
    if (
        name == base
        or not name.startswith(prefix)
        or not _REPR_SUFFIX.match(name[len(prefix) :])
        or path.resolve().parent != campaign_dir.resolve()
    ):
        raise RuntimeError(f"refusing to delete {path}: not a private session campaign")
    if path.is_dir():
        shutil.rmtree(path)


def run_year(
    backend: SessionsBackend,
    plan: PlanLike,
    *,
    campaign: str,
    repr_prefix: str,
    campaign_dir: Path,
    sol_dir: Path,
    maxsess: int,
    kb: KnowledgeBase | None = None,
    k: int = K_DEFAULT,
    max_failures: int = MAX_FAILURES_DEFAULT,
    session_char: str = "0",
    preflight: bool = True,
    chunk_days: int | None = None,
    ledger: RunLedger | None = None,
    config: str | None = None,
    station_counts: Mapping[int, int] | None = None,
) -> list[DayOutcome]:
    """Run ``plan.todo`` in parallel blocks. See the module docstring."""
    if plan.problems:
        raise ValueError("the plan has problems, nothing was run: " + "; ".join(plan.problems))
    if maxsess < 1:
        raise ValueError(f"maxsess must be >= 1, got {maxsess}")
    if repr_prefix == campaign:
        raise ValueError("repr_prefix must differ from the campaign name")
    if not sol_dir.is_dir():
        raise ValueError(f"SOL directory does not exist: {sol_dir}")
    if not (campaign_dir / campaign).is_dir():
        raise ValueError(f"campaign does not exist: {campaign_dir / campaign}")
    if kb is None:
        kb = load(DEFAULT_PATH)
    year = plan.year
    counts = station_counts or {}
    days = sorted(set(plan.todo))
    banked = [d for d in days if fin_banked(sol_dir, year, d, session_char)]
    todo = [d for d in days if d not in banked]
    queue = chunks(_segments(plan, todo, preflight), chunk_days or 2 * maxsess)

    out: dict[int, DayOutcome] = {
        d: DayOutcome(d, session_for(d, session_char), "banked") for d in banked
    }
    breaker = CircuitBreaker(k, max_failures)
    halt: str | None = None
    if ledger is not None:
        ledger.run_start(campaign=campaign, year=year, doys=days, banked=banked, config=config)
    try:
        while queue and halt is None:
            a, b = queue.pop(0)
            halt, resume_from = _run_chunk(
                backend, a, b, out,
                year=year, campaign=campaign, repr_prefix=repr_prefix,
                campaign_dir=campaign_dir, sol_dir=sol_dir, maxsess=maxsess,
                kb=kb, breaker=breaker, session_char=session_char,
                ledger=ledger, counts=counts,
            )  # fmt: skip
            if halt is None and resume_from is not None:
                queue.insert(0, (resume_from, b))
        for d in todo:
            if d not in out:
                out[d] = DayOutcome(
                    d, session_for(d, session_char), "not_run", note=f"stopped: {halt}"
                )
    except BaseException as exc:
        halt = halt or f"interrupted: {type(exc).__name__}"
        raise
    finally:
        if ledger is not None:
            ledger.run_end(halt=halt)
    return [out[d] for d in sorted(out)]


def _run_chunk(
    backend: SessionsBackend,
    a: int,
    b: int,
    out: dict[int, DayOutcome],
    *,
    year: int,
    campaign: str,
    repr_prefix: str,
    campaign_dir: Path,
    sol_dir: Path,
    maxsess: int,
    kb: KnowledgeBase,
    breaker: CircuitBreaker,
    session_char: str,
    ledger: RunLedger | None,
    counts: Mapping[int, int],
) -> tuple[str | None, int | None]:
    """One BPE call for days a..b. Returns (halt reason, day to resume from)."""
    days = list(range(a, b + 1))
    sessions = {d: session_for(d, session_char) for d in days}
    block = [a, b]
    for d in days:
        # This attempt replaces whatever a marker vouched for (month_driver docstring).
        _done_marker(sol_dir, year, d, session_char).unlink(missing_ok=True)
    before = {d: _fin_mtimes(sol_dir, year, d, session_char) for d in days}
    if ledger is not None:
        for d in days:
            ledger.attempt_start(doy=d, session=sessions[d], mode="block", block=block)
    started = time.time()
    t0 = time.monotonic()
    raised: str | None = None
    result: SessionsResult | None = None
    try:
        result = backend.run_sessions(
            campaign, year, sessions[a], len(days), maxsess=maxsess, repr_prefix=repr_prefix
        )
    except Exception as exc:  # noqa: BLE001 -- recorded as this block's failure
        raised = f"{type(exc).__name__}: {exc}"
    seconds = time.monotonic() - t0
    statuses = result.statuses if result is not None else {}

    # Judge every day by what is on disk, then tell the breaker in day order.
    judged: list[tuple[int, str, Diagnosis | None, str]] = []
    for d in days:
        s = sessions[d]
        name = repr_campaign_name(repr_prefix, year, s)
        state = statuses.get(f"{year % 100:02d}{s}")
        fin = _fresh_fin(sol_dir, year, d, session_char, before[d])
        if fin is not None:
            _write_marker(_done_marker(sol_dir, year, d, session_char), fin)
            _remove_private_campaign(campaign_dir, name, campaign, repr_prefix)
            judged.append((d, "ok", None, ""))
        elif state in ("error", "finished") or (
            # A session the server did not report on (or reported "running" when the
            # BPE was killed) started if its campaign was built during this call.
            # The server rebuilds the campaign when a session starts, so an older
            # one is left from an earlier run, and "waiting" means never started.
            state != "waiting" and _built_since(campaign_dir / name, started)
        ):
            note = (
                f"backend raised {raised}"
                if raised
                else f"session {state or 'unknown'} and no fresh FIN"
            )
            try:
                diag = diagnose_day(campaign_dir / name / "BPE", year, s, started, kb)
            except OSError as exc:
                diag = Diagnosis(None, None, None, unreadable=f"{type(exc).__name__}: {exc}")
            judged.append((d, "failed", diag, note))
        else:
            judged.append((d, "not_started", None, ""))

    # BSW starts sessions in order, so the days that did not start are a suffix of
    # the chunk. Resuming re-runs from the first of them; if a later day ran,
    # re-queuing would unbank it, so stop instead.
    order = [v for _, v, _, _ in judged]
    out_of_order = next(
        (
            judged[i][0]
            for i in range(len(order))
            if order[i] != "not_started" and "not_started" in order[:i]
        ),
        None,
    )

    halt: str | None = None
    first_not_started: int | None = None
    for d, verdict, found, note in judged:
        s = sessions[d]
        if verdict == "ok":
            out[d] = DayOutcome(d, s, "ok", seconds)
            if ledger is not None:
                ledger.attempt_end(
                    doy=d, session=s, outcome="ok", seconds=seconds,
                    stations=counts.get(d), mode="block", block=block,
                )  # fmt: skip
            if halt is None:
                breaker.success()
            continue
        if verdict == "failed":
            assert found is not None
            explanation = found.explanation(kb)
            out[d] = DayOutcome(d, s, "failed", seconds, note, found.label, explanation)
            if ledger is not None:
                ledger.attempt_end(
                    doy=d, session=s, outcome="failed", seconds=seconds, error=found.label,
                    note=note, stations=counts.get(d), mode="block", block=block,
                )  # fmt: skip
            logger.warning("DOY %03d failed: %s; %s", d, note, found.label)
            if halt is None:
                halt = breaker.failure(found)
                if halt is not None:
                    logger.error("stopping: %s\n%s", halt, explanation)
            continue
        if first_not_started is None:
            first_not_started = d
    if halt is None and raised is not None:
        # A raise (timeout, refused pre-flight) is unknown whatever a step left
        # behind, as in month_driver: another block would cost another timeout.
        halt = f"unknown failure (backend raised {raised}); no remedy on file"
    if halt is None and out_of_order is not None:
        halt = (
            f"sessions finished out of order: DOY {first_not_started:03d} did not start but "
            f"DOY {out_of_order:03d} ran; not resuming, so nothing banked is re-run"
        )
    if halt is not None or first_not_started is None:
        if halt is not None and ledger is not None:
            for d, verdict, _, _ in judged:
                if verdict == "not_started":
                    ledger.attempt_end(
                        doy=d, session=sessions[d], outcome="not_run", seconds=0.0,
                        note=f"not started: {halt}", mode="block", block=block,
                    )  # fmt: skip
        return halt, None
    if ledger is not None:
        for d, verdict, _, _ in judged:
            if verdict == "not_started":
                ledger.attempt_end(
                    doy=d, session=sessions[d], outcome="not_run", seconds=0.0,
                    note="not started: the queue stopped at an earlier failure; resumed",
                    mode="block", block=block,
                )  # fmt: skip
    if not any(v != "not_started" for _, v, _, _ in judged):
        return "no session of the block started", None
    return None, first_not_started


# --- command line ---------------------------------------------------------------------


class Interrupted(BaseException):
    """SIGTERM or SIGHUP, turned into an exception so cleanup runs on the way out."""


def _raise_interrupted(signum: int, _frame: FrameType | None) -> None:
    raise Interrupted(signal.Signals(signum).name)


def _env_path(name: str) -> Path:
    v = os.environ.get(name)
    if not v:
        raise SystemExit(f"{name} is not set: source LOADGPS.setvar first")
    return Path(v)


def default_ledger_path(campaign: str, year: int, sol_dir: Path) -> Path:
    """The ledger beside the results it describes: <V_RESULT>/ledger.jsonl, the
    parent of SOL/. It is their provenance, so it is backed up and found with
    them. $BPE_LEDGER_DIR/<campaign>-<year>.jsonl overrides."""
    root = os.environ.get("BPE_LEDGER_DIR")
    if root:
        return Path(root) / f"{campaign}-{year}.jsonl"
    return sol_dir.parent / "ledger.jsonl"


def run_config_hash(u: Path, pcf_path: Path, pcf_text: str) -> str:
    """ledger.config_hash over the PCF and every panel in the option directories it uses."""
    from .ledger import config_hash
    from .run_plan import pcf_option_dirs

    panels = [p for d in pcf_option_dirs(pcf_text) for p in sorted((u / "OPT" / d).glob("*.INP"))]
    return config_hash([pcf_path, *panels])


def main(argv: list[str] | None = None) -> int:
    from .backends import LinuxBPEBackend
    from .bpe_lock import BPELock, BPELockHeld
    from .ledger import Ledger
    from .run_plan import format_plan, parse_excludes, plan_from_env

    ap = argparse.ArgumentParser(
        description="Run a range of days as parallel BPE blocks, one campaign per session."
    )
    ap.add_argument("--campaign", required=True, help="base campaign under $P, e.g. PHREF")
    ap.add_argument("--repr-prefix", required=True, help="per-session campaign prefix, e.g. PHR")
    ap.add_argument("--year", type=int, required=True)
    ap.add_argument("--from", dest="doy_from", type=int, required=True)
    ap.add_argument("--to", dest="doy_to", type=int, required=True)
    ap.add_argument("--pcf", required=True)
    ap.add_argument("--maxsess", type=int, default=6)
    ap.add_argument(
        "--exclude",
        action="extend",
        nargs="+",
        default=[],
        metavar="DOY[:REASON]",
        help="days never to attempt, each with an optional reason",
    )
    ap.add_argument("--no-preflight", action="store_true")
    ap.add_argument(
        "--sol-dir",
        type=Path,
        help="where R2S_SAV archives FIN files; default the PCF's V_RESULT + /SOL",
    )
    ap.add_argument(
        "--ledger",
        type=Path,
        help="the run ledger (JSONL); default <V_RESULT>/ledger.jsonl, beside SOL/, "
        "or $BPE_LEDGER_DIR/<campaign>-<year>.jsonl when that is set",
    )
    ap.add_argument(
        "--done",
        choices=("fin", "banked"),
        default="fin",
        help="fin (default): a day with any FIN_* file is left alone, as scripts/ "
        "decides, so days scripts/ solved are never re-run by accident. banked: only "
        "a FIN with the service's .done marker counts; redoing scripts/' days is then "
        "a deliberate choice",
    )
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan", action="store_true", help="print what would run, run nothing")
    mode.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # LOADGPS.setvar exports the Bernese root as $C (there is no $X).
    P, U, C, S = (_env_path(v) for v in ("P", "U", "C", "S"))
    listed = parse_excludes(args.exclude)

    def make_plan():
        try:
            return plan_from_env(
                campaign=args.campaign, year=args.year, pcf=args.pcf,
                doy_from=args.doy_from, doy_to=args.doy_to,
                listed=listed, sol_dir=args.sol_dir, done_mode=args.done,
            )  # fmt: skip
        except OSError as e:  # the PCF itself: nothing to plan from
            print(f"refused: {e}", file=sys.stderr)
            raise SystemExit(2) from e

    def show(planned) -> None:
        for line in planned.sources:
            print(line)
        print(format_plan(planned.plan, label=f"{planned.label}   MAXSESS {args.maxsess}"))

    if args.plan:
        planned = make_plan()
        show(planned)
        return 0 if planned.plan.ok else 1

    backend = LinuxBPEBackend(C, U, P, pcf_file=args.pcf)
    purpose = f"{args.campaign} {args.year} {args.doy_from:03d}-{args.doy_to:03d} ({args.pcf})"
    old = {s: signal.signal(s, _raise_interrupted) for s in (signal.SIGTERM, signal.SIGHUP)}
    try:
        with BPELock(purpose=purpose):
            # Planned under the lock: which days are banked can change until
            # no other run can be banking them.
            planned = make_plan()
            show(planned)
            if not planned.plan.ok:
                print("refused: the plan has problems, nothing was run", file=sys.stderr)
                return 2
            ledger_path = args.ledger or default_ledger_path(
                args.campaign, args.year, planned.sol_dir
            )
            print(f"ledger:   {ledger_path}")
            out = run_year(
                backend, planned.plan,
                campaign=args.campaign, repr_prefix=args.repr_prefix,
                campaign_dir=P, sol_dir=planned.sol_dir, maxsess=args.maxsess,
                preflight=not args.no_preflight,
                ledger=Ledger(ledger_path),
                config=run_config_hash(U, planned.pcf_path, planned.pcf_text),
                station_counts=planned.plan.station_counts,
            )  # fmt: skip
    except BPELockHeld as e:
        print(f"refused: {e}", file=sys.stderr)
        return 3
    except Interrupted as e:
        print(f"stopped by {e}; the BPE's process group was cleaned up", file=sys.stderr)
        return 130
    finally:
        for s, h in old.items():
            signal.signal(s, h)
    for o in out:
        line = f"  DOY {o.doy:03d}  {o.status:8}"
        if o.status == "failed":
            line += f"  {o.error}  ({o.note})"
        print(line)
    failed = [o for o in out if o.status in ("failed", "not_run")]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
