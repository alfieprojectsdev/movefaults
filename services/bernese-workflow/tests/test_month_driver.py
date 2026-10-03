"""Day-level resume for multi-day runs through the service.

The scripts/ wrappers skip any day whose FIN_*.NQ0 exists, so a killed run costs
one session. The service had no such driver, so its kill cost was "whatever you
re-invoke by hand" (SETTLED.md §4). These tests pin the resume behaviour without
running Bernese: a fake backend writes the FIN file on success, the way the
real BPE's save step does.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bernese_workflow.backends import BPEResult
from bernese_workflow.month_driver import DayOutcome, fin_banked, run_days, session_for


class FakeBackend:
    """Succeeds by writing FIN_<year><doy>0.NQ0.gz into sol_dir, unless told not to."""

    def __init__(self, sol_dir: Path, fail_doys=(), kill_doy=None):
        self.sol_dir = sol_dir
        self.fail_doys = set(fail_doys)
        self.kill_doy = kill_doy
        self.calls: list[str] = []

    def run(self, campaign_name: str, year: int, session: str) -> BPEResult:
        self.calls.append(session)
        doy = int(session[:3])
        if doy == self.kill_doy:
            raise KeyboardInterrupt("simulated kill mid-day")
        ok = doy not in self.fail_doys
        if ok:
            (self.sol_dir / f"FIN_{year}{session}.NQ0.gz").write_bytes(b"x")
        return BPEResult(ok, None, None, False, False)


def test_session_is_three_digit_doy_plus_session_char():
    assert session_for(1) == "0010"
    assert session_for(200) == "2000"
    with pytest.raises(ValueError):
        session_for(0)
    with pytest.raises(ValueError):
        session_for(367)


def test_fin_banked_accepts_compressed_and_plain(tmp_path):
    assert not fin_banked(tmp_path, 2025, 200)
    (tmp_path / "FIN_20252000.NQ0").write_bytes(b"x")
    assert fin_banked(tmp_path, 2025, 200)
    (tmp_path / "FIN_20252010.NQ0.gz").write_bytes(b"x")
    assert fin_banked(tmp_path, 2025, 201)


def test_runs_every_day_in_order_and_reports_each(tmp_path):
    be = FakeBackend(tmp_path)
    out = run_days(be, "LUZON", 2025, [3, 1, 2], sol_dir=tmp_path)
    assert be.calls == ["0010", "0020", "0030"]
    assert [o.doy for o in out] == [1, 2, 3]
    assert all(o.status == "ok" for o in out)


def test_banked_days_are_skipped_not_rerun(tmp_path):
    (tmp_path / "FIN_20250020.NQ0.gz").write_bytes(b"x")
    be = FakeBackend(tmp_path)
    out = run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path)
    assert be.calls == ["0010", "0030"]
    assert [o.status for o in out] == ["ok", "banked", "ok"]


def test_kill_then_rerun_redoes_only_the_killed_day(tmp_path):
    # The Wednesday dry-run spec, in miniature: kill mid day 2, rerun, and day 1
    # must be skipped with its FIN untouched while day 2 is redone.
    be = FakeBackend(tmp_path, kill_doy=2)
    with pytest.raises(KeyboardInterrupt):
        run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path)
    day1 = tmp_path / "FIN_20250010.NQ0.gz"
    before = day1.stat().st_mtime_ns

    be2 = FakeBackend(tmp_path)
    out = run_days(be2, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path)
    assert be2.calls == ["0020", "0030"]
    assert [o.status for o in out] == ["banked", "ok", "ok"]
    assert day1.stat().st_mtime_ns == before


def test_a_failed_day_is_reported_and_the_run_continues(tmp_path):
    be = FakeBackend(tmp_path, fail_doys={2})
    out = run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path)
    assert [o.status for o in out] == ["ok", "failed", "ok"]


def test_two_consecutive_failures_stop_the_run(tmp_path):
    # Weekend rule: a BPE that fails twice means stop and write it up, not
    # work around it. Two in a row is the signal; isolated failures are not.
    be = FakeBackend(tmp_path, fail_doys={2, 3})
    out = run_days(be, "LUZON", 2025, [1, 2, 3, 4, 5], sol_dir=tmp_path)
    assert be.calls == ["0010", "0020", "0030"]
    assert [o.status for o in out] == ["ok", "failed", "failed", "not_run", "not_run"]


def test_success_without_a_fin_file_counts_as_failed(tmp_path):
    # A BPE can report success and save nothing; the FIN file is the evidence
    # a later resume relies on, so a missing one must not read as done.
    class SaysOkWritesNothing(FakeBackend):
        def run(self, campaign_name, year, session):
            self.calls.append(session)
            return BPEResult(True, None, None, False, False)

    out = run_days(SaysOkWritesNothing(tmp_path), "LUZON", 2025, [1], sol_dir=tmp_path)
    assert out[0].status == "failed"
    assert "no FIN" in out[0].note


def test_outcome_carries_timing(tmp_path):
    out = run_days(FakeBackend(tmp_path), "LUZON", 2025, [1], sol_dir=tmp_path)
    assert isinstance(out[0], DayOutcome)
    assert out[0].seconds >= 0
