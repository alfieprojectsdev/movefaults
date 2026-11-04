"""Tests for the run worker: queue order, the BPE lock, stop, redo and recovery.

The fake backend stands in for BSW the way test_run_year's does: an ok session
leaves its results in the year directory (FIN/RED, CRD, TRO, PRC, as R2S_SAV
archives them) and a failed one leaves a real PRT from the fixtures in its
private campaign. It also records whether the machine's BPE lock was held
while it ran, which is the property the worker exists to guarantee.

No Bernese, no data, no gps3: everything is in a temporary directory.
"""

from __future__ import annotations

import datetime as dt
import gzip
import json
import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from bernese_workflow import bpe_processes
from bernese_workflow import redo as rd
from bernese_workflow.backends import SessionsResult, repr_campaign_name
from bernese_workflow.bpe_lock import BPELock, BPELockHeld
from bernese_workflow.ledger import Ledger, read_entries
from bernese_workflow.month_driver import fin_banked
from bernese_workflow.run_queue import (
    PREFLIGHT,
    REDO,
    START,
    STOP,
    InvalidRequest,
    Queue,
    make_request,
    read_json,
    validate,
)
from bernese_workflow.run_worker import Setup, Worker, WorkerRunning, main
from bernese_workflow.run_year import SimplePlan

FIXTURES = Path(__file__).parent / "fixtures" / "bpe_errors"
YEAR = 2025
USER = "observer1"


def stamp(doy: int) -> str:
    return f"{YEAR}{doy:03d}0"


@dataclass
class FakeBSW:
    campaign_dir: Path
    year_dir: Path
    lock_path: Path
    failing: set[int] = field(default_factory=set)
    calls: list[tuple[int, int]] = field(default_factory=list)
    lock_held: list[bool] = field(default_factory=list)
    during: Callable[[int], None] | None = None  # runs inside the BPE call

    def _held(self) -> bool:
        try:
            with BPELock(self.lock_path):
                return False
        except BPELockHeld:
            return True

    def run_sessions(self, campaign, year, first_session, n_sessions, *, maxsess, repr_prefix):
        first = int(first_session[:3])
        self.calls.append((first, n_sessions))
        self.lock_held.append(self._held())
        if self.during is not None:
            self.during(first)
        statuses = {}
        for doy in range(first, first + n_sessions):
            s = f"{doy:03d}0"
            tag = f"{year % 100:02d}{s}"
            camp = self.campaign_dir / repr_campaign_name(repr_prefix, year, s)
            shutil.rmtree(camp, ignore_errors=True)
            (camp / "BPE").mkdir(parents=True)
            if doy in self.failing:
                # A failed attempt still writes some results before the step that fails.
                write(self.year_dir / "OUT" / f"R2S_{stamp(doy)}.PRC", b"failed attempt")
                write(self.year_dir / "SOL" / f"RED_{stamp(doy)}.NQ0", b"failed attempt")
                dst = camp / "BPE" / f"RP{tag}_513_000"
                stem = FIXTURES / "LZY250360_RP250360_513_000"
                shutil.copyfile(stem.with_suffix(".PRT"), dst.with_suffix(".PRT"))
                shutil.copyfile(stem.with_suffix(".LOG"), dst.with_suffix(".LOG"))
                statuses[tag] = "error"
                continue
            for rel in ("OUT/R2S_{}.PRC", "STA/FIN_{}.CRD", "SOL/FIN_{}.SNX", "ATM/FIN_{}.TRO"):
                write(self.year_dir / rel.format(stamp(doy)), b"new " + rel.encode())
            write(self.year_dir / "SOL" / f"RED_{stamp(doy)}.NQ0", b"new red")
            with gzip.open(self.year_dir / "SOL" / f"FIN_{stamp(doy)}.NQ0.gz", "wb") as f:
                f.write(b"NEW NEQ " * 64)
            statuses[tag] = "finished"
        return SessionsResult(success=not self.failing, raw_log="", statuses=statuses)


def write(p: Path, data: bytes) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


@dataclass
class Env:
    root: Path
    queue: Queue
    bsw: FakeBSW
    year_dir: Path
    sol: Path
    lock_path: Path
    busiest: int | None = None
    running: list = field(default_factory=list)  # what the /proc scan reports

    def setup(self, req: dict) -> Setup:
        days = [req["doy"]] if req["kind"] == REDO else list(range(req["from"], req["to"] + 1))
        return Setup(
            backend=self.bsw,
            plan=SimplePlan(req["year"], days, busiest=self.busiest),
            sol_dir=self.sol,
            campaign_dir=self.bsw.campaign_dir,
            ledger=Ledger(self.year_dir / "ledger.jsonl"),
        )

    def worker(self, **kw) -> Worker:
        # The real /proc scan is tested on its own below. Here it is fixed, so a
        # BPE really running on the machine (gps3's local CI) cannot change a result.
        kw.setdefault("bpe_running", lambda: self.running)
        return Worker(self.queue, self.setup, lock_path=self.lock_path, **kw)

    def submit(self, kind: str, at: dt.datetime | None = None, **fields) -> dict:
        if kind != STOP:
            fields = {"campaign": "PHREF", "repr_prefix": "PHR", "year": YEAR, "pcf": "PHREF_DLY",
                      "maxsess": 2, **fields}  # fmt: skip
        if kind == REDO:
            fields.setdefault("reason", "new antenna record")
        req = make_request(kind, USER, at=at, **fields)
        self.queue.submit(req)
        return req

    def done(self, req: dict) -> dict:
        return read_json(self.queue.done / f"{req['id']}.json")


@pytest.fixture
def env(tmp_path: Path) -> Env:
    camp = tmp_path / "P"
    (camp / "PHREF" / "BPE").mkdir(parents=True)
    year_dir = tmp_path / "S" / "PHREF" / str(YEAR)
    sol = year_dir / "SOL"
    sol.mkdir(parents=True)
    lock = tmp_path / "bpe.lock"
    return Env(
        tmp_path, Queue(tmp_path / "state"), FakeBSW(camp, year_dir, lock), year_dir, sol, lock
    )


OLD = {
    "OUT/R2S_{}.PRC": b"old prc",
    "STA/FIN_{}.CRD": b"old crd",
    "SOL/FIN_{}.SNX": b"old snx",
    "SOL/RED_{}.NQ0": b"old red",
    "ATM/FIN_{}.TRP": b"old trp",
    "SOL/FIN_{}.done": b"",
}


def old_set(env: Env, doy: int) -> dict[str, bytes]:
    """A banked day's results, as an earlier run left them. Returns rel -> bytes."""
    out = {rel.format(stamp(doy)): data for rel, data in OLD.items()}
    for rel, data in out.items():
        write(env.year_dir / rel, data)
    fin = env.sol / f"FIN_{stamp(doy)}.NQ0.gz"
    with gzip.open(fin, "wb") as f:
        f.write(b"OLD NEQ " * 64)
    out[f"SOL/{fin.name}"] = fin.read_bytes()
    return out


def on_disk(env: Env, doy: int) -> dict[str, bytes]:
    return {r: (env.year_dir / r).read_bytes() for r in rd.present_results(env.year_dir, YEAR, doy)}


def manifests(env: Env) -> list[Path]:
    return sorted((env.year_dir / "SUPERSEDED").glob("*/MANIFEST_*.json"))


# --- requests and the queue -----------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        {"campaign": "../PHREF"},
        {"pcf": "PCF/PHREF_DLY"},
        {"repr_prefix": "PHREF"},
        {"from": 200, "to": 100},
        {"to": 366},  # 2025 has 365 days
        {"maxsess": 0},
        {"year": "2025"},
    ],
)
def test_a_request_that_could_carry_a_path_or_a_bad_range_is_refused(bad) -> None:
    fields = {"campaign": "PHREF", "repr_prefix": "PHR", "year": YEAR, "pcf": "PHREF_DLY",
              "from": 1, "to": 10, **bad}  # fmt: skip
    with pytest.raises(InvalidRequest):
        make_request(START, USER, **fields)


def test_a_redo_needs_a_reason_and_a_username_is_required() -> None:
    f = {"campaign": "PHREF", "repr_prefix": "PHR", "year": YEAR, "pcf": "X", "doy": 5}
    with pytest.raises(InvalidRequest, match="reason"):
        make_request(REDO, USER, **f)
    with pytest.raises(InvalidRequest, match="username"):
        make_request(REDO, "two words", reason="r", **f)


def test_requests_run_in_submission_order_one_at_a_time(env: Env) -> None:
    t0 = dt.datetime.now(dt.UTC)
    # Submitted out of order on disk: the id, which is the submission time, decides.
    c = env.submit(START, at=t0 + dt.timedelta(seconds=2), **{"from": 30, "to": 30})
    a = env.submit(START, at=t0, **{"from": 10, "to": 10})
    b = env.submit(START, at=t0 + dt.timedelta(seconds=1), **{"from": 20, "to": 20})
    with env.worker() as w:
        assert [w.step() for _ in range(4)] == ["ran", "ran", "ran", "idle"]
    assert [first for first, _ in env.bsw.calls] == [10, 20, 30]
    for r in (a, b, c):
        assert env.done(r)["outcome"] == "ok"
    assert read_json(env.queue.root / "status.json")["state"] == "idle"


def test_the_ledger_records_who_asked_for_the_run(env: Env) -> None:
    env.submit(START, reason="monthly", **{"from": 10, "to": 11})
    with env.worker() as w:
        w.step()
    entries, _ = read_entries(env.year_dir / "ledger.jsonl")
    start = next(e for e in entries if e["event"] == "run_start")
    assert start["submitted_by"] == USER
    assert start["kind"] == START
    assert start["reason"] == "monthly"


def test_a_malformed_file_is_rejected_and_kept_not_run(env: Env) -> None:
    env.queue.ensure()
    (env.queue.queue / "20260101T000000.000000Z-00000000.json").write_text("{not json")
    with env.worker() as w:
        assert w.step() == "idle"
    rec = read_json(env.queue.done / "20260101T000000.000000Z-00000000.json")
    assert rec["outcome"] == "rejected"
    assert (env.queue.done / rec["raw"]).read_text() == "{not json"
    assert env.bsw.calls == []


def test_a_request_queued_longer_than_max_age_expires_instead_of_running(env: Env) -> None:
    old = env.submit(
        START, at=dt.datetime.now(dt.UTC) - dt.timedelta(hours=30), **{"from": 1, "to": 1}
    )
    with env.worker() as w:
        assert w.step() == "idle"
    assert env.done(old)["outcome"] == "expired"
    assert env.bsw.calls == []


def test_a_second_worker_on_the_same_state_directory_is_refused(env: Env) -> None:
    with env.worker(), pytest.raises(WorkerRunning), env.worker():
        pass


def test_validate_is_applied_to_what_is_read_not_only_to_what_is_submitted(env: Env) -> None:
    req = env.submit(START, **{"from": 1, "to": 1})
    path = env.queue.queue / f"{req['id']}.json"
    path.write_text(json.dumps({**req, "campaign": "../../etc"}))
    with env.worker() as w:
        w.step()
    assert env.done(req)["outcome"] == "rejected"
    assert env.bsw.calls == []
    with pytest.raises(InvalidRequest):
        validate({**req, "campaign": "../../etc"})


# --- the BPE lock -----------------------------------------------------------------------


def test_the_bpe_lock_is_held_for_the_whole_job_and_released_after(env: Env) -> None:
    env.submit(START, **{"from": 10, "to": 15})
    with env.worker() as w:
        w.step()
    assert len(env.bsw.calls) == 2  # 6 days, chunks of 2 x maxsess = 4
    assert env.bsw.lock_held == [True, True]
    with BPELock(env.lock_path):  # free again: the worker does not hold it while idle
        pass


def test_a_redo_moves_files_only_while_holding_the_lock(env: Env, monkeypatch) -> None:
    old_set(env, 40)
    seen: list[bool] = []
    real = rd.move_aside

    def spy(*a, **k):
        seen.append(env.bsw._held())
        return real(*a, **k)

    monkeypatch.setattr(rd, "move_aside", spy)
    env.submit(REDO, doy=40)
    with env.worker() as w:
        w.step()
    assert seen == [True]


def test_a_request_waits_while_someone_else_holds_the_lock(env: Env) -> None:
    req = env.submit(START, **{"from": 10, "to": 10})
    with env.worker() as w:
        with BPELock(env.lock_path, purpose="a maintainer's bernese-run-year"):
            assert w.step() == "waiting"
            status = read_json(env.queue.root / "status.json")
            assert status["state"] == "waiting-for-bpe-lock"
            assert "maintainer" in status["holder"]
            assert (env.queue.queue / f"{req['id']}.json").exists(), "still queued, not failed"
        assert w.step() == "ran"
    assert env.done(req)["outcome"] == "ok"


# --- stop -------------------------------------------------------------------------------


def test_stop_ends_the_run_after_the_block_in_progress_never_inside_it(env: Env) -> None:
    run = env.submit(START, **{"from": 10, "to": 19})
    stops: list[dict] = []
    env.bsw.during = lambda first: stops.append(env.submit(STOP)) if first == 10 else None
    with env.worker() as w:
        w.step()
    rec = env.done(run)
    assert env.bsw.calls == [(10, 4)], "no BPE call after the stop, and the first was not cut"
    assert rec["outcome"] == "stopped"
    assert USER in rec["detail"]
    assert all(rec["days"][f"{d:03d}"] == "ok" for d in range(10, 14))
    assert all(rec["days"][f"{d:03d}"] == "not_run" for d in range(14, 20))
    assert env.done(stops[0])["outcome"] == "applied"
    entries, _ = read_entries(env.year_dir / "ledger.jsonl")
    assert "stopped by" in next(e for e in entries if e["event"] == "run_end")["halt"]


def test_a_stop_naming_a_queued_request_cancels_it_ahead_of_its_turn(env: Env) -> None:
    a = env.submit(START, **{"from": 10, "to": 10})
    b = env.submit(START, **{"from": 20, "to": 20})
    stop = env.submit(STOP, target=b["id"])
    with env.worker() as w:
        assert w.step() == "ran"
        assert w.step() == "idle"
    assert env.done(a)["outcome"] == "ok"
    assert env.done(b)["outcome"] == "cancelled"
    assert env.done(stop)["outcome"] == "applied"
    assert [f for f, _ in env.bsw.calls] == [10]


def test_a_stop_with_nothing_running_is_recorded_as_such(env: Env) -> None:
    stop = env.submit(STOP)
    with env.worker() as w:
        assert w.step() == "idle"
    assert env.done(stop)["outcome"] == "nothing-to-stop"


def test_sigterm_stops_after_the_current_block_then_the_loop_exits(env: Env) -> None:
    run = env.submit(START, **{"from": 10, "to": 19})
    later = env.submit(START, **{"from": 30, "to": 30})
    with env.worker() as w:
        env.bsw.during = lambda first: w.request_exit("SIGTERM")
        assert w.step() == "ran"
        assert w.step() == "exiting"
    assert env.done(run)["outcome"] == "stopped"
    assert len(env.bsw.calls) == 1
    assert (env.queue.queue / f"{later['id']}.json").exists(), "the next request waits"


# --- preflight --------------------------------------------------------------------------


def test_preflight_runs_only_the_busiest_day(env: Env) -> None:
    env.busiest = 17
    req = env.submit(PREFLIGHT, **{"from": 10, "to": 20})
    with env.worker() as w:
        w.step()
    assert env.bsw.calls == [(17, 1)]
    rec = env.done(req)
    assert rec["outcome"] == "ok"
    assert rec["preflight_day"] == 17


def test_preflight_without_a_busiest_day_is_refused(env: Env) -> None:
    req = env.submit(PREFLIGHT, **{"from": 10, "to": 20})
    with env.worker() as w:
        w.step()
    assert env.done(req)["outcome"] == "refused"
    assert env.bsw.calls == []


# --- redo -------------------------------------------------------------------------------


def test_redo_success_moves_the_whole_old_set_aside_and_keeps_the_new_one(env: Env) -> None:
    old = old_set(env, 40)
    req = env.submit(REDO, doy=40)
    with env.worker() as w:
        w.step()
    rec = env.done(req)
    assert rec["outcome"] == "ok", rec["detail"]

    [mfile] = manifests(env)
    assert mfile.parent.parent == env.year_dir / "SUPERSEDED"
    assert len(mfile.parent.name) == len("20261104-1015")
    m = rd.Manifest.load(mfile)
    assert m.state == rd.SUCCEEDED
    assert [h["state"] for h in m.data["history"]] == ["moving", "moved", "succeeded"]
    assert {f["path"] for f in m.files} == set(old)
    for rel, data in old.items():  # every old file aside, byte for byte, in its folder
        assert (mfile.parent / rel).read_bytes() == data
        assert next(f for f in m.files if f["path"] == rel)["sha256"] == rd.sha256(
            mfile.parent / rel
        )

    now = on_disk(env, 40)
    assert now[f"STA/FIN_{stamp(40)}.CRD"].startswith(b"new")
    assert f"ATM/FIN_{stamp(40)}.TRP" not in now, (
        "the old TRP is aside, not left beside the new set"
    )
    assert fin_banked(env.sol, YEAR, 40), "the new FIN carries a fresh marker"

    entries, _ = read_entries(env.year_dir / "ledger.jsonl")
    sup = next(e for e in entries if e["event"] == "superseded")
    assert sup["reason"] == "new antenna record"
    assert sup["submitted_by"] == USER


def test_redo_failure_removes_the_attempt_and_puts_the_old_set_back(env: Env) -> None:
    old = old_set(env, 40)
    env.bsw.failing = {40}
    req = env.submit(REDO, doy=40)
    with env.worker() as w:
        w.step()
    rec = env.done(req)
    assert rec["outcome"] == "failed"
    assert "HELMR1" in rec["detail"]
    assert "old set is back" in rec["detail"]

    assert on_disk(env, 40) == old, "exactly the old set, byte for byte, and nothing else"
    assert fin_banked(env.sol, YEAR, 40), "the day is banked again, marker and all"
    assert set(rec["removed"]) == {f"OUT/R2S_{stamp(40)}.PRC", f"SOL/RED_{stamp(40)}.NQ0"}
    [mfile] = manifests(env)
    assert rd.Manifest.load(mfile).state == rd.RESTORED
    assert (env.bsw.campaign_dir / "PHR250400" / "BPE").is_dir(), "kept for autopsy"
    entries, _ = read_entries(env.year_dir / "ledger.jsonl")
    assert any(e["event"] == "restored" and e["doy"] == 40 for e in entries)


def test_redo_restores_when_the_backend_raises(env: Env) -> None:
    old = old_set(env, 40)

    def boom(first):
        write(env.year_dir / "OUT" / f"R2S_{stamp(40)}.PRC", b"half written")
        raise RuntimeError("BPE timed out after 7200s")

    env.bsw.during = boom
    req = env.submit(REDO, doy=40)
    with env.worker() as w:
        w.step()
    assert env.done(req)["outcome"] == "failed"
    assert on_disk(env, 40) == old


def test_a_redo_of_a_day_with_nothing_to_move_is_refused(env: Env) -> None:
    req = env.submit(REDO, doy=40)
    with env.worker() as w:
        w.step()
    assert env.done(req)["outcome"] == "refused"
    assert env.bsw.calls == []
    assert not (env.year_dir / "SUPERSEDED").exists()


def test_a_restore_that_cannot_verify_touches_nothing_and_halts_the_worker(env: Env) -> None:
    old_set(env, 40)

    def tamper(first):
        [mfile] = manifests(env)
        (mfile.parent / f"STA/FIN_{stamp(40)}.CRD").write_bytes(b"changed while aside")

    env.bsw.failing = {40}
    env.bsw.during = tamper
    req = env.submit(REDO, doy=40)
    nxt = env.submit(START, **{"from": 50, "to": 50})
    with env.worker() as w:
        w.step()
        assert w.step() == "halted"
    rec = env.done(req)
    assert rec["outcome"] == "restore-failed"
    assert "FIN_2025040" in rec["detail"]
    assert (env.queue.root / "HALTED").exists()
    # Nothing was touched: the failed attempt's files are still where it left them.
    assert (env.year_dir / "OUT" / f"R2S_{stamp(40)}.PRC").read_bytes() == b"failed attempt"
    assert rd.Manifest.load(manifests(env)[0]).state == rd.RESTORE_FAILED
    assert (env.queue.queue / f"{nxt['id']}.json").exists(), "nothing new is claimed"


def test_two_redos_of_the_same_day_in_one_minute_get_separate_directories(env: Env) -> None:
    at = dt.datetime(2026, 11, 4, 10, 15)
    a = rd.manifest_path(env.year_dir, YEAR, 40, at=at)
    a.parent.mkdir(parents=True)
    a.write_text("{}")
    b = rd.manifest_path(env.year_dir, YEAR, 40, at=at)
    assert a.parent.name == "20261104-1015"
    assert b.parent.name == "20261104-1015-2"
    assert rd.manifest_path(env.year_dir, YEAR, 41, at=at).parent == a.parent


# --- crash recovery ---------------------------------------------------------------------


def crashed(env: Env, req: dict, **fields) -> Path:
    """Put a request in active/ as a worker that died would have left it."""
    path = env.queue.ensure().queue / f"{req['id']}.json"
    active = env.queue.claim(path)
    env.queue.update_active(active, {**req, "started": "2026-11-04T00:00:00+00:00", **fields})
    return active


def test_an_interrupted_start_is_recorded_and_not_rerun(env: Env) -> None:
    req = env.submit(START, **{"from": 10, "to": 20})
    crashed(env, req)
    nxt = env.submit(START, **{"from": 30, "to": 30})
    with env.worker() as w:
        assert w.step() == "ran"
    assert env.done(req)["outcome"] == "interrupted"
    assert "resumes" in env.done(req)["detail"]
    assert [f for f, _ in env.bsw.calls] == [30], "only the next request ran"
    assert env.done(nxt)["outcome"] == "ok"


def test_a_redo_that_died_mid_move_is_restored_on_restart(env: Env) -> None:
    old = old_set(env, 40)
    req = env.submit(REDO, doy=40)
    mpath = rd.manifest_path(env.year_dir, YEAR, 40)
    m = rd.move_aside(env.year_dir, YEAR, 40, mpath, request=req["id"])
    # As if the worker died after moving all but one file: put one back, state moving.
    first = m.files[0]["path"]
    (m.aside / first).rename(env.year_dir / first)
    m.data["state"] = rd.MOVING
    rd.write_json_atomic(mpath, m.data)
    crashed(env, req, manifest=str(mpath))

    with env.worker() as w:
        w.step()
    rec = env.done(req)
    assert rec["outcome"] == "interrupted"
    assert "old set is back" in rec["detail"]
    assert on_disk(env, 40) == old
    assert env.bsw.calls == []


def test_a_redo_that_died_during_its_bpe_is_restored_and_its_output_removed(env: Env) -> None:
    old = old_set(env, 40)
    req = env.submit(REDO, doy=40)
    mpath = rd.manifest_path(env.year_dir, YEAR, 40)
    rd.move_aside(env.year_dir, YEAR, 40, mpath, request=req["id"])
    write(env.year_dir / "SOL" / f"FIN_{stamp(40)}.SNX", b"half a new solution")
    write(env.year_dir / "ATM" / f"FIN_{stamp(40)}.TRO", b"half a new troposphere")
    crashed(env, req, manifest=str(mpath))

    with env.worker() as w:
        w.step()
    assert env.done(req)["outcome"] == "interrupted"
    assert on_disk(env, 40) == old
    entries, _ = read_entries(env.year_dir / "ledger.jsonl")
    restored = next(e for e in entries if e["event"] == "restored")
    assert set(restored["removed"]) == {f"SOL/FIN_{stamp(40)}.SNX", f"ATM/FIN_{stamp(40)}.TRO"}


def test_a_redo_that_died_before_writing_its_manifest_moved_nothing(env: Env) -> None:
    old = old_set(env, 40)
    req = env.submit(REDO, doy=40)
    crashed(env, req, manifest=str(rd.manifest_path(env.year_dir, YEAR, 40)))
    with env.worker() as w:
        w.step()
    assert env.done(req)["outcome"] == "interrupted"
    assert "nothing had been moved" in env.done(req)["detail"]
    assert on_disk(env, 40) == old


def test_a_redo_that_succeeded_just_before_the_crash_is_recorded_ok(env: Env) -> None:
    old_set(env, 40)
    req = env.submit(REDO, doy=40)
    mpath = rd.manifest_path(env.year_dir, YEAR, 40)
    m = rd.move_aside(env.year_dir, YEAR, 40, mpath, request=req["id"])
    write(env.year_dir / "STA" / f"FIN_{stamp(40)}.CRD", b"the new coordinates")
    m.set_state(rd.SUCCEEDED)
    crashed(env, req, manifest=str(mpath))
    with env.worker() as w:
        w.step()
    assert env.done(req)["outcome"] == "ok"
    assert (env.year_dir / "STA" / f"FIN_{stamp(40)}.CRD").read_bytes() == b"the new coordinates"


def test_recovery_waits_for_the_bpe_lock_and_claims_nothing_meanwhile(env: Env) -> None:
    old = old_set(env, 40)
    req = env.submit(REDO, doy=40)
    mpath = rd.manifest_path(env.year_dir, YEAR, 40)
    rd.move_aside(env.year_dir, YEAR, 40, mpath, request=req["id"])
    crashed(env, req, manifest=str(mpath))
    nxt = env.submit(START, **{"from": 50, "to": 50})
    with env.worker() as w:
        with BPELock(env.lock_path):
            assert w.step() == "recovering"
            assert (env.queue.active / f"{req['id']}.json").exists()
            assert (env.queue.queue / f"{nxt['id']}.json").exists()
        assert w.step() == "ran"
    assert on_disk(env, 40) == old
    assert env.done(nxt)["outcome"] == "ok"


# --- restore on its own ----------------------------------------------------------------


def test_move_aside_rolls_back_if_a_move_fails(env: Env, monkeypatch) -> None:
    old = old_set(env, 40)
    real, n = rd._move, {"calls": 0}

    def flaky(src, dst):
        n["calls"] += 1
        if n["calls"] == 3:
            raise OSError("EXDEV: SUPERSEDED is on another filesystem")
        real(src, dst)

    monkeypatch.setattr(rd, "_move", flaky)
    with pytest.raises(OSError, match="EXDEV"):
        rd.move_aside(env.year_dir, YEAR, 40, rd.manifest_path(env.year_dir, YEAR, 40))
    assert on_disk(env, 40) == old


# --- command line -----------------------------------------------------------------------


def test_cli_submit_and_list(env: Env, capsys) -> None:
    state = ["--state-dir", str(env.queue.root)]
    assert main([*state, "submit", "start", "--campaign", "PHREF", "--repr-prefix", "PHR",
                 "--year", "2025", "--from", "152", "--to", "181", "--pcf", "PHREF_DLY",
                 "--by", USER]) == 0  # fmt: skip
    assert main([*state, "submit", "redo", "--campaign", "PHREF", "--repr-prefix", "PHR",
                 "--year", "2025", "--doy", "152", "--pcf", "PHREF_DLY", "--by", USER]) == 2  # fmt: skip
    assert "reason" in capsys.readouterr().err
    assert main([*state, "submit", "stop", "--by", USER]) == 0
    capsys.readouterr()
    assert main([*state, "list"]) == 0
    out = capsys.readouterr().out
    assert "start PHREF 2025 DOY 152-181 (PHREF_DLY) by observer1" in out
    assert "stop the running request by observer1" in out
    [first, second] = sorted(p.name for p in env.queue.queue.glob("*.json"))
    assert read_json(env.queue.queue / first)["kind"] == START
    assert read_json(env.queue.queue / second)["kind"] == STOP


def test_cli_run_refuses_without_the_bernese_environment(env: Env, monkeypatch, capsys) -> None:
    for v in ("P", "U", "C", "S", "D"):
        monkeypatch.delenv(v, raising=False)
    assert main(["--state-dir", str(env.queue.root), "run", "--once"]) == 2
    assert "LOADGPS.setvar" in capsys.readouterr().err


def test_a_redo_whose_ledger_write_fails_still_restores(env: Env, monkeypatch) -> None:
    old = old_set(env, 40)

    def full(self, event, **fields):
        raise OSError("No space left on device")

    monkeypatch.setattr(Ledger, "event", full)
    req = env.submit(REDO, doy=40)
    with env.worker() as w:
        w.step()
    assert env.done(req)["outcome"] == "failed"
    assert on_disk(env, 40) == old


# --- a BPE left running by a killed run ------------------------------------------------

ORPHAN = bpe_processes.BPEProcess(4242, "perl RUNBPE.pm gps3 5000 1 2", "PHR250400", "")


def test_a_bpe_running_without_the_lock_blocks_the_next_request(env: Env) -> None:
    req = env.submit(START, **{"from": 10, "to": 10})
    env.running = [ORPHAN]
    with env.worker() as w:
        assert w.step() == "blocked"
        status = read_json(env.queue.root / "status.json")
        assert status["state"] == "blocked-by-running-bpe"
        assert "pid 4242" in status["processes"][0]
        assert (env.queue.queue / f"{req['id']}.json").exists(), "still queued, not claimed"
        with BPELock(env.lock_path):  # and the lock was let go
            pass
        env.running = []
        assert w.step() == "ran"
    assert env.bsw.calls == [(10, 1)]


def test_recovery_does_not_restore_a_redo_under_a_bpe_still_running(env: Env) -> None:
    old = old_set(env, 40)
    req = env.submit(REDO, doy=40)
    mpath = rd.manifest_path(env.year_dir, YEAR, 40)
    rd.move_aside(env.year_dir, YEAR, 40, mpath, request=req["id"])
    crashed(env, req, manifest=str(mpath))
    env.running = [bpe_processes.BPEProcess(4242, "sh -c GPSEST", "PHR250400", req["id"])]
    with env.worker() as w:
        assert w.step() == "recovering"
        assert rd.Manifest.load(mpath).state == rd.MOVED, "nothing moved back under it"
        assert (env.queue.active / f"{req['id']}.json").exists()
        env.running = []
        w.step()
    assert on_disk(env, 40) == old
    assert env.done(req)["outcome"] == "interrupted"


def test_the_job_marker_is_in_the_environment_only_while_the_job_runs(env: Env) -> None:
    req = env.submit(START, **{"from": 10, "to": 10})
    seen: list[str | None] = []
    env.bsw.during = lambda first: seen.append(os.environ.get(bpe_processes.WORKER_MARKER))
    with env.worker() as w:
        w.step()
    assert seen == [req["id"]]
    assert bpe_processes.WORKER_MARKER not in os.environ


def _proc(root: Path, pid: int, argv: list[str], env: dict[str, str] | None = None) -> None:
    d = root / str(pid)
    d.mkdir(parents=True)
    (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
    if env is not None:
        (d / "environ").write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in env.items()))


def test_find_recognises_bpe_scripts_and_the_worker_marker_and_nothing_else(tmp_path) -> None:
    _proc(
        tmp_path,
        10,
        ["perl", "/u/SCRIPT/sessions_pcs.pl", "2025", "0400"],
        {"BPE_CAMPAIGN": "PHREF"},
    )
    _proc(tmp_path, 11, ["/usr/bin/perl", "/bsw/BPE/RUNBPE.pm", "gps3", "5000"])
    _proc(tmp_path, 12, ["/bsw/EXE_GNU/GPSEST"], {bpe_processes.WORKER_MARKER: "req-1"})
    _proc(tmp_path, 13, ["vim", "/bsw/BPE/RUNBPE.pm"])  # editing it is not running it
    _proc(tmp_path, 14, ["grep", "-r", "startBPE.pm", "."])
    _proc(tmp_path, 15, ["perl", "sessions_pcs.pl"])  # excluded below: "this process"
    (tmp_path / "self").mkdir()
    (tmp_path / "16").mkdir()  # exited between listing and reading: no cmdline
    found = bpe_processes.find(tmp_path, exclude={15})
    assert [p.pid for p in found] == [10, 11, 12]
    assert found[0].campaign == "PHREF"
    assert found[2].request == "req-1"


def test_find_sees_a_real_child_that_inherited_the_marker() -> None:
    proc = subprocess.Popen(
        ["sleep", "30"], env={**os.environ, bpe_processes.WORKER_MARKER: "req-real"}
    )
    try:
        found = [p for p in bpe_processes.find() if p.pid == proc.pid]
        assert found and found[0].request == "req-real"
    finally:
        proc.kill()
        proc.wait()


# --- review fixes ------------------------------------------------------------------------


def test_a_restore_that_dies_part_way_halts_the_worker_instead_of_failing_quietly(
    env: Env, monkeypatch
) -> None:
    old_set(env, 40)
    env.bsw.failing = {40}
    req = env.submit(REDO, doy=40)
    real, n = rd._move, {"calls": 0}

    def flaky(src, dst):
        n["calls"] += 1
        if n["calls"] == len(OLD) + 2:  # every move aside, then the second move back
            raise OSError("EIO")
        real(src, dst)

    monkeypatch.setattr(rd, "_move", flaky)
    with env.worker() as w:
        w.step()
        assert w.step() == "halted"
    rec = env.done(req)
    assert rec["outcome"] == "restore-failed"
    assert "EIO" in rec["detail"]
    [mfile] = manifests(env)
    assert rd.Manifest.load(mfile).state == rd.RESTORE_FAILED


def test_a_request_carrying_the_workers_own_fields_is_refused(env: Env) -> None:
    req = make_request(START, USER, campaign="PHREF", repr_prefix="PHR", year=YEAR,
                       pcf="PHREF_DLY", **{"from": 10, "to": 10})  # fmt: skip
    with pytest.raises(InvalidRequest, match="manifest"):
        validate({**req, "manifest": "/elsewhere/SUPERSEDED/x/MANIFEST_20250400.json"})


def test_sigterm_ends_the_loop_while_recovery_is_waiting(env: Env) -> None:
    req = env.submit(START, **{"from": 10, "to": 10})
    crashed(env, req)
    with env.worker() as w:
        with BPELock(env.lock_path):
            assert w.step() == "recovering"
            w.request_exit("SIGTERM")
            assert w.step() == "exiting"


def test_a_stop_naming_a_malformed_queued_file_does_not_fail_the_running_job(env: Env) -> None:
    from bernese_workflow.run_queue import new_id

    run = env.submit(START, **{"from": 10, "to": 19})
    bad = new_id()

    def during(first: int) -> None:
        if first == 10:
            (env.queue.queue / f"{bad}.json").write_text("[1, 2]")
            env.submit(STOP, target=bad)

    env.bsw.during = during
    with env.worker() as w:
        w.step()
    assert env.done(run)["outcome"] == "ok", "the run went on past the stop's check"
    assert [f for f, _ in env.bsw.calls] == [10, 14, 18]


def test_cli_list_survives_a_malformed_queued_request_and_n_0_shows_none(env: Env, capsys) -> None:
    from bernese_workflow.run_queue import new_id

    env.submit(START, **{"from": 10, "to": 10})
    with env.worker() as w:
        w.step()
    env.queue.ensure()
    (env.queue.queue / f"{new_id()}.json").write_text('{"kind": "start"}')
    capsys.readouterr()
    assert main(["--state-dir", str(env.queue.root), "list", "-n", "0"]) == 0
    out = capsys.readouterr().out
    assert "(not a valid request)" in out
    assert not any(line.startswith("  done") for line in out.splitlines())
