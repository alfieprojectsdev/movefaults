"""Day-level resume for multi-day runs through the service.

The scripts/ wrappers skip any day whose FIN_*.NQ0 exists, so a killed run costs
one session. The service had no such driver, so its kill cost was "whatever you
re-invoke by hand" (SETTLED.md §4). These tests pin the resume behaviour without
running Bernese: a fake backend writes the FIN file on success, the way the
real BPE's save step does. The driver writes a .done marker after success, and
resume only skips days with both a valid FIN and the marker.
"""

from __future__ import annotations

import gzip
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
            _write_valid_gz(self.sol_dir / f"FIN_{year}{session}.NQ0.gz")
        return BPEResult(ok, None, None, False, False)


def _write_valid_gz(path: Path, content: bytes = b"SINEX placeholder") -> None:
    """Write a valid gzip file (unlike the old b'x' which is not valid gzip)."""
    with gzip.open(path, "wb") as f:
        f.write(content)


def _bank(sol_dir: Path, year: int, doy: int, session_char: str = "0") -> None:
    """Create a banked day: valid FIN + session-keyed .done marker."""
    _write_valid_gz(sol_dir / f"FIN_{year}{doy:03d}{session_char}.NQ0.gz")
    (sol_dir / f"FIN_{year}{doy:03d}{session_char}.done").touch()


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
    (tmp_path / "FIN_20252000.done").touch()
    assert fin_banked(tmp_path, 2025, 200)
    _write_valid_gz(tmp_path / "FIN_20252010.NQ0.gz")
    (tmp_path / "FIN_20252010.done").touch()
    assert fin_banked(tmp_path, 2025, 201)


def test_runs_every_day_in_order_and_reports_each(tmp_path):
    be = FakeBackend(tmp_path)
    out = run_days(be, "LUZON", 2025, [3, 1, 2], sol_dir=tmp_path)
    assert be.calls == ["0010", "0020", "0030"]
    assert [o.doy for o in out] == [1, 2, 3]
    assert all(o.status == "ok" for o in out)


def test_banked_days_are_skipped_not_rerun(tmp_path):
    _bank(tmp_path, 2025, 2)
    be = FakeBackend(tmp_path)
    out = run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path)
    assert be.calls == ["0010", "0030"]
    assert [o.status for o in out] == ["ok", "banked", "ok"]


def test_kill_then_rerun_redoes_only_the_killed_day(tmp_path):
    be = FakeBackend(tmp_path, kill_doy=2)
    with pytest.raises(KeyboardInterrupt):
        run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path)
    day1_fin = tmp_path / "FIN_20250010.NQ0.gz"
    day1_marker = tmp_path / "FIN_20250010.done"
    assert day1_fin.exists()
    assert day1_marker.exists()
    before = day1_fin.stat().st_mtime_ns

    be2 = FakeBackend(tmp_path)
    out = run_days(be2, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path)
    assert be2.calls == ["0020", "0030"]
    assert [o.status for o in out] == ["banked", "ok", "ok"]
    assert day1_fin.stat().st_mtime_ns == before


def test_a_failed_day_is_reported_and_the_run_continues(tmp_path):
    be = FakeBackend(tmp_path, fail_doys={2})
    out = run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path)
    assert [o.status for o in out] == ["ok", "failed", "ok"]


def test_two_consecutive_failures_stop_the_run(tmp_path):
    be = FakeBackend(tmp_path, fail_doys={2, 3})
    out = run_days(be, "LUZON", 2025, [1, 2, 3, 4, 5], sol_dir=tmp_path)
    assert be.calls == ["0010", "0020", "0030"]
    assert [o.status for o in out] == ["ok", "failed", "failed", "not_run", "not_run"]


def test_success_without_a_fin_file_counts_as_failed(tmp_path):
    class SaysOkWritesNothing(FakeBackend):
        def run(self, campaign_name, year, session):
            self.calls.append(session)
            return BPEResult(True, None, None, False, False)

    out = run_days(SaysOkWritesNothing(tmp_path), "LUZON", 2025, [1], sol_dir=tmp_path)
    assert out[0].status == "failed"
    assert "no valid FIN" in out[0].note


def test_outcome_carries_timing(tmp_path):
    out = run_days(FakeBackend(tmp_path), "LUZON", 2025, [1], sol_dir=tmp_path)
    assert isinstance(out[0], DayOutcome)
    assert out[0].seconds >= 0


# --- finch review: three failure-path tests that must each catch a mutant ---


def test_zero_byte_fin_not_banked(tmp_path):
    """A zero-byte FIN from a crash mid-write must not count as banked."""
    (tmp_path / "FIN_20252000.NQ0").write_bytes(b"")
    (tmp_path / "FIN_20252000.done").touch()
    assert not fin_banked(tmp_path, 2025, 200)
    (tmp_path / "FIN_20252010.NQ0.gz").write_bytes(b"")
    (tmp_path / "FIN_20252010.done").touch()
    assert not fin_banked(tmp_path, 2025, 201)


def test_failed_run_leaving_fin_is_rerun_on_resume(tmp_path):
    """A BPE that writes the FIN then fails at a later job must be rerun, not banked."""

    class FailsButWritesFin(FakeBackend):
        def run(self, campaign_name, year, session):
            self.calls.append(session)
            _write_valid_gz(self.sol_dir / f"FIN_{year}{session}.NQ0.gz")
            return BPEResult(False, None, None, False, False)

    be = FailsButWritesFin(tmp_path)
    out = run_days(be, "LUZON", 2025, [1, 2], sol_dir=tmp_path)
    assert [o.status for o in out] == ["failed", "failed"]
    assert (tmp_path / "FIN_20250010.NQ0.gz").exists()
    assert not (tmp_path / "FIN_20250010.done").exists()

    be2 = FakeBackend(tmp_path)
    out2 = run_days(be2, "LUZON", 2025, [1, 2], sol_dir=tmp_path)
    assert be2.calls == ["0010", "0020"]
    assert [o.status for o in out2] == ["ok", "ok"]


def test_marker_survives_compress_decompress(tmp_path):
    """Compressing or decompressing a FIN after banking must not break the match."""
    _bank(tmp_path, 2025, 200)
    assert fin_banked(tmp_path, 2025, 200)
    gz = tmp_path / "FIN_20252000.NQ0.gz"
    plain = tmp_path / "FIN_20252000.NQ0"
    gz.rename(plain)
    plain.write_bytes(b"decompressed content")
    assert fin_banked(tmp_path, 2025, 200)


def test_truncated_gz_not_banked(tmp_path):
    """A truncated .gz (power loss during compression) must not count as banked."""
    good = tmp_path / "good.NQ0.gz"
    _write_valid_gz(good, b"SINEX data here")
    raw = good.read_bytes()
    truncated = raw[: len(raw) // 2]

    p = tmp_path / "FIN_20252000.NQ0.gz"
    p.write_bytes(truncated)
    (tmp_path / "FIN_20252000.done").touch()
    assert not fin_banked(tmp_path, 2025, 200)
