"""The run worker: runs queued BPE requests one at a time, under the BPE lock.

WHY THIS EXISTS
The BSW console's Start, Stop, Redo and Queue preflight buttons need something
on gps3 that runs a BPE on a person's behalf, holds the machine's BPE lock
while it does, and leaves the results as they were if it dies. The console
must not do that itself: it is a web process and a BPE takes hours. The whole
design, including what happens on a crash, is in
docs/project_documentation/run_worker_design.md; this docstring is the map.

ONE STEP OF THE LOOP (Worker.step)
1. stop requests are applied first: a stop that waited its turn behind the job
   it was meant to stop would be useless;
2. the oldest valid run request is chosen (invalid ones are rejected, ones
   older than max_age expired);
3. the BPE lock is taken. If someone else holds it the request stays queued
   and the worker tries again next poll;
4. the request is claimed (queue/ -> active/), run, and finished (-> done/);
5. the lock is released. It is never held while idle.

WHAT EACH KIND RUNS
start      the planned range through run_year, busiest day first
preflight  the planned range's busiest day only
redo       redo.move_aside, run_year for the one day, redo.restore on failure

STOP
run_year asks ``stop`` before each BPE call. A stop therefore ends a run after
the block in progress (up to 2 x MAXSESS days), never inside one. SIGTERM and
SIGINT (and SIGHUP) do the same and then exit the loop; nothing here kills a BPE.

CRASH RECOVERY (Worker.recover)
A request left in active/ belongs to a dead worker, since worker.lock is held.
Under the BPE lock, a redo whose files had started moving is restored; any
other request is recorded interrupted and is NOT re-run automatically.

A BPE STILL RUNNING
Before recovering and before claiming each job, under the BPE lock, the worker
looks for BPE processes (bpe_processes.py). One found then has no lock holder
supervising it, typically an orphan of a SIGKILLed run, and the worker starts
nothing until it has gone. It never kills it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import getpass
import json
import logging
import os
import signal
import socket
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import FrameType
from typing import IO

from . import bpe_processes
from . import redo as rd
from .bpe_knowledge import KnowledgeBase
from .bpe_lock import BPELock, BPELockHeld
from .month_driver import DayOutcome
from .run_queue import (
    MAXSESS_DEFAULT,
    PREFLIGHT,
    REDO,
    RUN_KINDS,
    START,
    STOP,
    InvalidRequest,
    Queue,
    make_request,
    now_utc,
    read_json,
    validate,
    write_json_atomic,
)
from .run_year import PlanLike, SessionsBackend, SimplePlan, run_year

logger = logging.getLogger(__name__)

MAX_AGE_DEFAULT_S = 24 * 3600.0
POLL_DEFAULT_S = 5.0


@dataclass
class Setup:
    """What one request runs against. ``bsw_setup`` builds the real one; tests
    pass a factory that returns a fake backend and temporary directories."""

    backend: SessionsBackend
    plan: PlanLike
    sol_dir: Path  # <year dir>/SOL; the year directory is its parent
    campaign_dir: Path  # $P
    ledger: object | None = None  # ledger.Ledger, or anything with its methods
    config: str | None = None
    kb: KnowledgeBase | None = None
    # The PCF's V_ORB and its tier, recorded in run_start as bernese-run-year does.
    products: str | None = None
    product_tier: str | None = None


SetupFactory = Callable[[dict], Setup]


class WorkerRunning(RuntimeError):
    """Another worker holds this state directory."""


class _TaggedLedger:
    """A Ledger whose run_start also records who asked for the run, and why."""

    def __init__(self, inner: object, **tags: object) -> None:
        self._inner = inner
        self._tags = tags

    def run_start(self, **kw: object) -> str:
        return self._inner.run_start(**kw, **self._tags)  # type: ignore[attr-defined]

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def _ledger_event(ledger: object | None, event: str, **fields: object) -> None:
    if ledger is not None and hasattr(ledger, "event"):
        ledger.event(event, **fields)  # type: ignore[attr-defined]


def _days(req: dict) -> str:
    if req["kind"] == REDO:
        return f"DOY {req['doy']:03d}"
    return f"DOY {req['from']:03d}-{req['to']:03d}"


def describe(req: dict) -> str:
    """One line: what a request asks for and who asked."""
    if req.get("kind") == STOP:
        return f"stop {req.get('target') or 'the running request'} by {req.get('submitted_by')}"
    return (
        f"{req['kind']} {req['campaign']} {req['year']} {_days(req)} ({req['pcf']}) "
        f"by {req['submitted_by']}"
    )


class Worker:
    """Use as a context manager: entering takes worker.lock for the state directory."""

    def __init__(
        self,
        queue: Queue,
        setup: SetupFactory,
        *,
        lock_path: Path | None = None,
        max_age_s: float = MAX_AGE_DEFAULT_S,
        poll_s: float = POLL_DEFAULT_S,
        clock: Callable[[], dt.datetime] = now_utc,
        bpe_running: Callable[[], list[bpe_processes.BPEProcess]] = bpe_processes.find,
    ) -> None:
        self.queue = queue.ensure()
        self.bpe_running = bpe_running
        self.setup = setup
        self.lock_path = lock_path
        self.max_age_s = max_age_s
        self.poll_s = poll_s
        self.clock = clock
        self.halted_path = queue.root / "HALTED"
        self.status_path = queue.root / "status.json"
        self._fh: IO[str] | None = None
        self._active_id: str | None = None
        self._stop_reason: str | None = None
        self._signal_reason: str | None = None
        self.recovered = False

    # --- the worker's own lock -----------------------------------------------------------

    def __enter__(self) -> Worker:
        fh = open(self.queue.root / "worker.lock", "a+")  # noqa: SIM115 -- held while running
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            raise WorkerRunning(f"another worker is running on {self.queue.root}") from None
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({"pid": os.getpid(), "host": socket.gethostname()}) + "\n")
        fh.flush()
        self._fh = fh
        return self

    def __exit__(self, *exc: object) -> None:
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    # --- status ----------------------------------------------------------------------------

    def _status(self, state: str, **fields: object) -> None:
        write_json_atomic(
            self.status_path,
            {
                "state": state,
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "active": self._active_id,
                "updated": self.clock().isoformat(),
                **fields,
            },
            tmp_dir=self.queue.tmp,
        )

    def _halt(self, why: str) -> None:
        self.halted_path.write_text(
            f"{self.clock().isoformat()}\n{why}\n\n"
            "The worker claims no new run while this file exists. Put the day right,\n"
            "then delete this file.\n"
        )

    # --- signals ---------------------------------------------------------------------------

    def request_exit(self, why: str) -> None:
        """Stop the running request after its current BPE call, then leave the loop."""
        if self._signal_reason is None:
            self._signal_reason = why
            logger.warning("%s: stopping after the current BPE call, then exiting", why)
        else:
            logger.warning(
                "%s again: already stopping after the current BPE call. Only SIGKILL "
                "abandons a BPE mid-day, and the next start then recovers",
                why,
            )

    # --- reading the queue -----------------------------------------------------------------

    def _expired(self, req: dict) -> bool:
        submitted = dt.datetime.fromisoformat(req["submitted"])
        if submitted.tzinfo is None:
            submitted = submitted.replace(tzinfo=dt.UTC)
        return (self.clock() - submitted).total_seconds() > self.max_age_s

    def _read(self, path: Path) -> dict | None:
        """A valid, unexpired request from queue/, or None (rejected or expired)."""
        try:
            req = validate(read_json(path))
        except FileNotFoundError:
            return None
        except (InvalidRequest, ValueError, UnicodeDecodeError) as exc:
            logger.warning("rejected %s: %s", path.name, exc)
            self.queue.reject(path, str(exc))
            return None
        if path.stem != req["id"]:
            self.queue.reject(path, f"file name does not match its id {req['id']}")
            return None
        if self._expired(req):
            hours = self.max_age_s / 3600
            self.queue.finish(
                path, req, "expired",
                f"still queued more than {hours:g} h after it was submitted; not run. "
                "Submit it again if it is still wanted",
            )  # fmt: skip
            return None
        return req

    def _apply_stops(self) -> None:
        """Apply every queued stop request: stop the running one, or cancel a queued one."""
        for path in list(self.queue.pending()):
            try:
                raw = read_json(path)
                kind = raw.get("kind") if isinstance(raw, dict) else None
            except (OSError, ValueError, UnicodeDecodeError):
                kind = None  # _read rejects it below if it is still there
            if kind != STOP and kind is not None:
                continue
            req = self._read(path)
            if req is None:
                continue
            who = f"{req['submitted_by']} (request {req['id']})"
            target = req.get("target")
            if target is None or target == self._active_id:
                if self._active_id is None:
                    self.queue.finish(path, req, "nothing-to-stop", "no request was running")
                    continue
                if self._stop_reason is None:
                    self._stop_reason = f"stopped by {who}"
                self.queue.finish(
                    path, req, "applied", f"{self._active_id} stops after the current BPE call",
                    applied_to=self._active_id,
                )  # fmt: skip
                continue
            found = self.queue.find(target)
            # _read rejects or expires a victim that is not a valid request, so
            # nothing malformed can raise out of here into run_year's stop call.
            victim = self._read(found[1]) if found and found[0] == "queue" else None
            if victim is not None:
                self.queue.finish(found[1], victim, "cancelled", f"cancelled by {who}")
                self.queue.finish(path, req, "applied", f"cancelled {target}", applied_to=target)
            else:
                found = self.queue.find(target)
                where = found[0] if found else "nowhere"
                self.queue.finish(
                    path, req, "nothing-to-stop", f"{target} is {where}, not queued or running"
                )

    def _next(self) -> tuple[Path, dict] | None:
        for path in list(self.queue.pending()):
            req = self._read(path)
            if req is not None and req["kind"] in RUN_KINDS:
                return path, req
        return None

    def _should_stop(self) -> str | None:
        """run_year's stop callable: asked before every BPE call."""
        self._apply_stops()
        return self._stop_reason or self._signal_reason

    # --- the loop ----------------------------------------------------------------------------

    def _orphans(self, purpose: str) -> bool:
        """Under the BPE lock: is a BPE still running that nobody supervises?

        Every BPE runner takes the lock, so one found while we hold it was left
        by a run that died (a SIGKILLed worker or bernese-run-year). Starting
        another beside it, or restoring a redo under it, is what this prevents.
        Nothing is killed: that would be a kill mid-day. A person decides.
        """
        found = self.bpe_running()
        if not found:
            return False
        self._status(
            "blocked-by-running-bpe",
            reason=f"{purpose}: a BPE is running without the BPE lock; nothing is started "
            "until it has exited. If it is an orphan of a killed run, decide whether to "
            "let it finish or kill its process group",
            processes=[p.describe() for p in found],
        )
        logger.error("%s blocked: BPE processes running: %s", purpose,
                     "; ".join(p.describe() for p in found))  # fmt: skip
        return True

    def step(self) -> str:
        """One pass. Returns what it did:
        recovering | exiting | halted | idle | waiting | blocked | ran."""
        self.queue.clean_tmp()
        # Before recovery too: recovery can wait hours on a lock held elsewhere
        # or on an orphan BPE, and a SIGTERM must still end the loop meanwhile.
        if self._signal_reason:
            self._status("exiting", reason=self._signal_reason)
            return "exiting"
        if not self.recovered and not self.recover():
            return "recovering"
        self._apply_stops()
        if self._signal_reason:
            self._status("exiting", reason=self._signal_reason)
            return "exiting"
        if self.halted_path.exists():
            self._status("halted", reason=self.halted_path.read_text().strip())
            return "halted"
        nxt = self._next()
        if nxt is None:
            self._status("idle")
            return "idle"
        path, req = nxt
        lock = BPELock(self.lock_path, purpose=f"worker {req['id']} {describe(req)}")
        try:
            lock.__enter__()
        except BPELockHeld as exc:
            self._status("waiting-for-bpe-lock", next=req["id"], holder=str(exc))
            return "waiting"
        try:
            if self._orphans(f"next request {req['id']}"):
                return "blocked"
            if self._signal_reason:  # arrived while choosing: leave the request queued
                self._status("exiting", reason=self._signal_reason)
                return "exiting"
            try:
                active = self.queue.claim(path)
            except FileNotFoundError:
                return "idle"  # cancelled between choosing and claiming
            self._run(active, req)
        finally:
            lock.__exit__()
        return "ran"

    def run_forever(self) -> None:
        while True:
            what = self.step()
            if what == "exiting":
                return
            if what != "ran":
                time.sleep(self.poll_s)

    # --- running a request ---------------------------------------------------------------

    def _run(self, active: Path, req: dict) -> None:
        self._active_id = req["id"]
        self._stop_reason = None
        req["started"] = self.clock().isoformat()
        req["worker"] = {"pid": os.getpid(), "host": socket.gethostname()}
        self.queue.update_active(active, req)
        self._status("running", request=describe(req))
        logger.info("running %s: %s", req["id"], describe(req))
        fields: dict = {}
        # Inherited by the BPE driver and everything it starts, so a BPE this job
        # leaves behind can be found by the next start (bpe_processes).
        os.environ[bpe_processes.WORKER_MARKER] = req["id"]
        try:
            if req["kind"] == REDO:
                outcome, detail, fields = self._redo(active, req)
            else:
                outcome, detail, fields = self._range(req)
        except rd.RestoreFailed as exc:
            outcome, detail = "restore-failed", str(exc)
            self._halt(f"request {req['id']} ({describe(req)}): {exc}")
        except Exception as exc:  # noqa: BLE001 -- recorded as the request's outcome
            logger.exception("request %s raised", req["id"])
            outcome, detail = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            os.environ.pop(bpe_processes.WORKER_MARKER, None)
        self.queue.finish(active, req, outcome, detail, **fields)
        logger.info("%s: %s %s", req["id"], outcome, detail)
        self._active_id = None
        self._stop_reason = None

    def _run_year(
        self, s: Setup, req: dict, plan: PlanLike, *, preflight: bool
    ) -> list[DayOutcome]:
        ledger = None
        if s.ledger is not None:
            ledger = _TaggedLedger(
                s.ledger, request=req["id"], kind=req["kind"],
                submitted_by=req["submitted_by"], reason=req.get("reason", ""),
            )  # fmt: skip
        counts = getattr(s.plan, "station_counts", None)
        return run_year(
            s.backend, plan,
            campaign=req["campaign"], repr_prefix=req["repr_prefix"],
            campaign_dir=s.campaign_dir, sol_dir=s.sol_dir, maxsess=req["maxsess"],
            kb=s.kb, preflight=preflight, ledger=ledger, config=s.config,
            station_counts=counts, stop=self._should_stop,
            pcf=req["pcf"], products=s.products, product_tier=s.product_tier,
        )  # fmt: skip

    def _summary(self, out: list[DayOutcome]) -> tuple[str, str, dict]:
        days = {f"{o.doy:03d}": o.status for o in out}
        failed = [o for o in out if o.status == "failed"]
        not_run = [o for o in out if o.status == "not_run"]
        detail = "; ".join(f"DOY {o.doy:03d} {o.error or o.note}" for o in failed)
        stopped = self._stop_reason or self._signal_reason
        # Stopped only if the stop is what left days not run: a SIGTERM that
        # arrives during a block the breaker then halts must not hide the halt.
        if stopped and any(o.note == f"stopped: {stopped}" for o in not_run):
            return "stopped", "; ".join(x for x in (stopped, detail) if x), {"days": days}
        if failed or not_run:
            if not_run:
                detail = "; ".join(x for x in (detail, not_run[0].note) if x)
            return "failed", detail, {"days": days}
        return "ok", f"{len(out)} days ok or already banked", {"days": days}

    def _range(self, req: dict) -> tuple[str, str, dict]:
        s = self.setup(req)
        if s.plan.problems:
            return "refused", "the plan has problems: " + "; ".join(s.plan.problems), {}
        if req["kind"] == PREFLIGHT:
            busiest = s.plan.busiest
            if busiest is None:
                return "refused", "the plan names no busiest day (no station counts)", {}
            plan: PlanLike = SimplePlan(s.plan.year, [busiest])
            preflight = False
        else:
            plan, preflight = s.plan, True
        if not plan.todo:
            return (
                "ok",
                "nothing to run: every day in the range is solved or excluded",
                {"days": {}},
            )
        out = self._run_year(s, req, plan, preflight=preflight)
        outcome, detail, fields = self._summary(out)
        if req["kind"] == PREFLIGHT:
            fields["preflight_day"] = plan.todo[0]
        return outcome, detail, fields

    def _redo(self, active: Path, req: dict) -> tuple[str, str, dict]:
        year, doy = req["year"], req["doy"]
        s = self.setup(req)
        if s.plan.problems:
            return "refused", "the plan has problems: " + "; ".join(s.plan.problems), {}
        excluded = {e.doy: e for e in getattr(s.plan, "excluded", [])}
        if doy not in s.plan.todo and doy in excluded and excluded[doy].reason != "solved":
            e = excluded[doy]
            return "refused", f"the plan excludes DOY {doy:03d}: {e.reason} {e.detail}".strip(), {}
        year_dir = s.sol_dir.parent
        if not rd.present_results(year_dir, year, doy):
            return (
                "refused",
                f"DOY {doy:03d} has no results to move aside; submit a start for that day instead",
                {},
            )
        mpath = rd.manifest_path(year_dir, year, doy)
        # The manifest's path is recorded before the manifest exists, so recovery
        # always knows where to look.
        req["manifest"] = str(mpath)
        self.queue.update_active(active, req)
        m = rd.move_aside(year_dir, year, doy, mpath, request=req["id"])
        aside = {"manifest": str(mpath), "superseded": str(m.aside)}
        # From here until the day is judged, any way out restores the old set.
        try:
            _ledger_event(
                s.ledger, "superseded", doy=doy, session=m.data["session"], request=req["id"],
                submitted_by=req["submitted_by"], reason=req.get("reason", ""),
                to=str(m.aside), files=[f["path"] for f in m.files],
            )  # fmt: skip
            out = self._run_year(s, req, SimplePlan(year, [doy]), preflight=False)
        except Exception as exc:  # noqa: BLE001 -- the day is restored, then recorded
            removed = self._restore(s.ledger, m, req)
            return (
                "failed",
                f"{type(exc).__name__}: {exc}; the old set is back in place",
                {**aside, "removed": removed},
            )
        except BaseException:
            self._restore(s.ledger, m, req)
            raise
        day = next((o for o in out if o.doy == doy), None)
        if day is not None and day.status == "ok":
            m.set_state(rd.SUCCEEDED)
            return (
                "ok",
                f"DOY {doy:03d} redone; the old set is in {m.aside}",
                {
                    **aside,
                    "days": {f"{doy:03d}": "ok"},
                },
            )
        removed = self._restore(s.ledger, m, req)
        why = (day.error or day.note) if day else "run_year did not report the day"
        stopped = self._stop_reason or self._signal_reason
        outcome = "stopped" if day and day.status == "not_run" and stopped else "failed"
        return (
            outcome,
            f"{why}; the old set is back in place",
            {
                **aside,
                "removed": removed,
                "days": {f"{doy:03d}": day.status if day else "unknown"},
            },
        )

    def _restore(self, ledger: object | None, m: rd.Manifest, req: dict) -> list[str]:
        removed = rd.restore(m)
        _ledger_event(
            ledger, "restored", doy=m.data["doy"],
            session=m.data["session"], request=req.get("id"), source=str(m.aside),
            files=[f["path"] for f in m.files], removed=removed,
        )  # fmt: skip
        return removed

    # --- crash recovery ----------------------------------------------------------------

    def recover(self) -> bool:
        """Finish whatever a dead worker left in active/. False if the BPE lock is
        held elsewhere: nothing new is claimed until recovery has run."""
        files = self.queue.active_files()
        if not files:
            self.recovered = True
            return True
        lock = BPELock(self.lock_path, purpose="worker crash recovery")
        try:
            lock.__enter__()
        except BPELockHeld as exc:
            self._status("waiting-for-bpe-lock", reason="crash recovery", holder=str(exc))
            return False
        try:
            if self._orphans("crash recovery"):
                return False
            for path in files:
                self._recover_one(path)
        finally:
            lock.__exit__()
        self.recovered = True
        return True

    def _recover_one(self, path: Path) -> None:
        try:
            req = read_json(path)
        except (OSError, ValueError, UnicodeDecodeError) as exc:
            self.queue.reject(path, f"unreadable after a crash: {exc}")
            return
        died = "the worker died while this was running"
        mfile = Path(req["manifest"]) if req.get("kind") == REDO and req.get("manifest") else None
        if req.get("kind") != REDO:
            self.queue.finish(
                path, req, "interrupted",
                f"{died}. Nothing is re-run automatically; days banked before then stay "
                "banked, so submitting the range again resumes it",
            )  # fmt: skip
            return
        if mfile is None or not mfile.exists():
            self.queue.finish(path, req, "interrupted", f"{died}; nothing had been moved aside")
            return
        m = rd.Manifest.load(mfile)
        fields = {"manifest": str(mfile), "superseded": str(m.aside)}
        if m.state in (rd.MOVING, rd.MOVED):
            from .ledger import Ledger
            from .run_year import default_ledger_path

            ledger = Ledger(default_ledger_path(req["campaign"], req["year"], m.year_dir / "SOL"))
            try:
                removed = self._restore(ledger, m, req)
            except rd.RestoreFailed as exc:
                self._halt(f"request {req['id']} ({describe(req)}): {exc}")
                self.queue.finish(path, req, "restore-failed", f"{died}; {exc}", **fields)
                return
            self.queue.finish(
                path, req, "interrupted", f"{died}; the old set is back in place",
                removed=removed, **fields,
            )  # fmt: skip
        elif m.state == rd.SUCCEEDED:
            self.queue.finish(
                path, req, "ok", "the redo had finished before the worker died", **fields
            )
        elif m.state == rd.RESTORED:
            self.queue.finish(
                path, req, "failed", "the redo failed and the old set had been restored", **fields
            )
        else:
            why = "; ".join(m.data.get("problems", [])) or m.state
            self._halt(f"request {req['id']} ({describe(req)}): {why}")
            self.queue.finish(path, req, "restore-failed", why, **fields)


# --- the real setup ---------------------------------------------------------------------


def bsw_setup(req: dict) -> Setup:
    """Plan the request from the environment LOADGPS.setvar exports, as
    ``bernese-run-year --run`` does, and build the real BSW backend."""
    from .backends import LinuxBPEBackend
    from .ledger import Ledger
    from .run_plan import plan_from_env, product_tier
    from .run_year import default_ledger_path, run_config_hash

    env = {}
    for name in ("P", "U", "C", "S", "D"):
        if not os.environ.get(name):
            raise RuntimeError(
                f"${name} is not set: start the worker after sourcing LOADGPS.setvar"
            )
        env[name] = Path(os.environ[name])
    redo = req["kind"] == REDO
    a, b = (req["doy"], req["doy"]) if redo else (req["from"], req["to"])
    # A redo's day is solved by definition; planned as solved it would skip the
    # reference-coverage and station-file checks that every other run gets.
    planned = plan_from_env(
        campaign=req["campaign"], year=req["year"], pcf=req["pcf"],
        doy_from=a, doy_to=b, done_mode="none" if redo else "fin",
    )  # fmt: skip
    products, tier = product_tier(planned.pcf_text)
    backend = LinuxBPEBackend(
        env["C"], env["U"], env["P"], pcf_file=req["pcf"],
        rinex_source_dir=planned.rinex_dir, sta_file=planned.sta_file,
        preflight_required=True,
    )  # fmt: skip
    return Setup(
        backend=backend,
        plan=planned.plan,
        sol_dir=planned.sol_dir,
        campaign_dir=env["P"],
        ledger=Ledger(default_ledger_path(req["campaign"], req["year"], planned.sol_dir)),
        config=run_config_hash(env["U"], planned.pcf_path, planned.pcf_text),
        products=products,
        product_tier=tier,
    )


# --- command line ---------------------------------------------------------------------


def _list(q: Queue, n_done: int) -> None:
    def line(where: str, p: Path) -> str:
        try:
            r = read_json(p)
        except (OSError, ValueError):
            return f"  {where:7} {p.name}  (unreadable)"
        if not isinstance(r, dict):
            return f"  {where:7} {p.name}  (not a valid request)"
        try:
            what = describe(r) if r.get("kind") else r.get("detail", "")
        except (KeyError, TypeError, AttributeError):
            what = "(not a valid request)"
        tail = f"  -> {r['outcome']}: {r.get('detail', '')}" if "outcome" in r else ""
        return f"  {where:7} {r.get('id', p.stem)}  {what}{tail}"

    status = q.root / "status.json"
    if status.exists():
        print(f"worker:  {status.read_text().strip()}")
    if (q.root / "HALTED").exists():
        print(f"HALTED:  {(q.root / 'HALTED').read_text().strip()}")
    for p in q.active_files():
        print(line("active", p))
    for p in q.pending():
        print(line("queued", p))
    done = sorted(q.done.glob("*.json"))[-n_done:] if q.done.is_dir() and n_done > 0 else []
    for p in done:
        print(line("done", p))


def _login() -> str | None:
    """The submitting account; None (refused by validate) rather than a crash
    of every subcommand when there is no login name, as ledger.started_by."""
    try:
        return getpass.getuser()
    except (OSError, KeyError):
        return None


def _add_run_fields(sp: argparse.ArgumentParser, *, redo: bool) -> None:
    sp.add_argument("--campaign", required=True, help="base campaign under $P, e.g. PHREF")
    sp.add_argument("--repr-prefix", required=True, help="per-session campaign prefix, e.g. PHR")
    sp.add_argument("--year", type=int, required=True)
    if redo:
        sp.add_argument("--doy", type=int, required=True)
    else:
        sp.add_argument("--from", dest="doy_from", type=int, required=True)
        sp.add_argument("--to", dest="doy_to", type=int, required=True)
    sp.add_argument("--pcf", required=True)
    sp.add_argument("--maxsess", type=int, default=MAXSESS_DEFAULT)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Run queued BPE requests one at a time under the BPE lock, or queue one."
    )
    ap.add_argument(
        "--state-dir", type=Path, default=None,
        help="the queue; default $BERNESE_WORKER_STATE or ~/.local/state/bernese-workflow/worker",
    )  # fmt: skip
    sub = ap.add_subparsers(dest="cmd", required=True)

    run = sub.add_parser("run", help="run the worker loop (source LOADGPS.setvar first)")
    run.add_argument("--poll", type=float, default=POLL_DEFAULT_S, help="seconds between looks")
    run.add_argument("--max-age-hours", type=float, default=MAX_AGE_DEFAULT_S / 3600)
    run.add_argument("--once", action="store_true", help="one pass, then exit")

    submit = sub.add_parser("submit", help="queue a request")
    kinds = submit.add_subparsers(dest="kind", required=True)
    for kind, redo in ((START, False), (PREFLIGHT, False), (REDO, True)):
        sp = kinds.add_parser(kind)
        _add_run_fields(sp, redo=redo)
    stop = kinds.add_parser("stop", help="stop the running request after its current BPE call")
    stop.add_argument("--target", help="a request id: cancels it if queued, stops it if running")
    for sp in kinds.choices.values():
        sp.add_argument("--by", default=_login(), help="who is asking (default: you)")
        sp.add_argument("--reason", default="", help="why; required for a redo")

    ls = sub.add_parser("list", help="the queue, the running request and recent results")
    ls.add_argument("-n", type=int, default=10, help="how many finished requests to show")

    args = ap.parse_args(argv)
    q = Queue(args.state_dir)

    if args.cmd == "list":
        _list(q, args.n)
        return 0

    if args.cmd == "submit":
        kind = STOP if args.kind == "stop" else args.kind
        fields: dict[str, object] = {"reason": args.reason}
        if kind == STOP:
            fields["target"] = args.target
        else:
            fields.update(
                campaign=args.campaign, repr_prefix=args.repr_prefix, year=args.year,
                pcf=args.pcf, maxsess=args.maxsess,
            )  # fmt: skip
            if kind == REDO:
                fields["doy"] = args.doy
            else:
                fields.update({"from": args.doy_from, "to": args.doy_to})
        try:
            path = q.submit(make_request(kind, args.by, **fields))
        except InvalidRequest as exc:
            print(f"refused: {exc}", file=sys.stderr)
            return 2
        print(path)
        return 0

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    missing = [v for v in ("P", "U", "C", "S", "D") if not os.environ.get(v)]
    if missing:
        print(
            f"refused: ${', $'.join(missing)} not set: source LOADGPS.setvar first", file=sys.stderr
        )
        return 2
    worker = Worker(q, bsw_setup, max_age_s=args.max_age_hours * 3600, poll_s=args.poll)

    def on_signal(signum: int, _frame: FrameType | None) -> None:
        worker.request_exit(signal.Signals(signum).name)

    # SIGHUP too, as bernese-run-year does: a closed terminal or a dropped ssh
    # session must stop after the BPE call, not kill the worker mid-redo.
    old = {s: signal.signal(s, on_signal) for s in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        with worker:
            if args.once:
                print(worker.step())
            else:
                worker.run_forever()
    except WorkerRunning as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 3
    finally:
        for s, h in old.items():
            signal.signal(s, h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
