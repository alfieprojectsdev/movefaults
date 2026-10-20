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
import os
from pathlib import Path

import pytest
from bernese_workflow.backends import BPEResult
from bernese_workflow.month_driver import DayOutcome, fin_banked, run_days, session_for

# A real HELMR1 failure: scope "session", so the breaker counts it rather than
# stopping at once. Failed days use it unless a test says otherwise.
HELMR1_PRT = Path(__file__).parent / "fixtures" / "bpe_errors" / "LZY250360_RP250360_513_000.PRT"


def _write_failed_step(sol_dir: Path, year: int, session: str, source: Path = HELMR1_PRT) -> None:
    """Leave a failed step's PRT in BPE/ as the real BPE would."""
    bpe = sol_dir / "BPE"
    bpe.mkdir(exist_ok=True)
    (bpe / f"RP{year % 100:02d}{session}_513_000.PRT").write_bytes(source.read_bytes())


@pytest.fixture(autouse=True)
def _bpe_dir(tmp_path: Path) -> None:
    """run_days refuses a BPE directory that does not exist, as a campaign's always does."""
    (tmp_path / "BPE").mkdir(exist_ok=True)


class FakeBackend:
    """Succeeds by writing FIN_<year><doy>0.NQ0.gz into sol_dir, unless told not to.

    A failed day leaves a HELMR1 PRT in sol_dir/BPE, so the circuit breaker sees
    a known session error and lets the run go on.
    """

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
        else:
            _write_failed_step(self.sol_dir, year, session)
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
    out = run_days(be, "LUZON", 2025, [3, 1, 2], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    assert be.calls == ["0010", "0020", "0030"]
    assert [o.doy for o in out] == [1, 2, 3]
    assert all(o.status == "ok" for o in out)


def test_banked_days_are_skipped_not_rerun(tmp_path):
    _bank(tmp_path, 2025, 2)
    be = FakeBackend(tmp_path)
    out = run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    assert be.calls == ["0010", "0030"]
    assert [o.status for o in out] == ["ok", "banked", "ok"]


def test_kill_then_rerun_redoes_only_the_killed_day(tmp_path):
    be = FakeBackend(tmp_path, kill_doy=2)
    with pytest.raises(KeyboardInterrupt):
        run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    day1_fin = tmp_path / "FIN_20250010.NQ0.gz"
    day1_marker = tmp_path / "FIN_20250010.done"
    assert day1_fin.exists()
    assert day1_marker.exists()
    before = day1_fin.stat().st_mtime_ns

    be2 = FakeBackend(tmp_path)
    out = run_days(be2, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    assert be2.calls == ["0020", "0030"]
    assert [o.status for o in out] == ["banked", "ok", "ok"]
    assert day1_fin.stat().st_mtime_ns == before


def test_a_failed_day_is_reported_and_the_run_continues(tmp_path):
    be = FakeBackend(tmp_path, fail_doys={2})
    out = run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    assert [o.status for o in out] == ["ok", "failed", "ok"]


def test_three_consecutive_identical_session_failures_stop_the_run(tmp_path):
    be = FakeBackend(tmp_path, fail_doys={2, 3, 4})
    out = run_days(be, "LUZON", 2025, [1, 2, 3, 4, 5], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    assert be.calls == ["0010", "0020", "0030", "0040"]
    assert [o.status for o in out] == ["ok", "failed", "failed", "failed", "not_run"]
    assert out[1].error == "HELMR1: NO_REDUNDANCY_NO_VERIFICATION_OF_SITES_POSSIBLE"
    assert "3 consecutive days" in out[4].note


def test_success_without_a_fin_file_counts_as_failed(tmp_path):
    class SaysOkWritesNothing(FakeBackend):
        def run(self, campaign_name, year, session):
            self.calls.append(session)
            return BPEResult(True, None, None, False, False)

    out = run_days(
        SaysOkWritesNothing(tmp_path),
        "LUZON",
        2025,
        [1],
        sol_dir=tmp_path,
        bpe_dir=tmp_path / "BPE",
    )
    assert out[0].status == "failed"
    assert "no valid FIN" in out[0].note


def test_outcome_carries_timing(tmp_path):
    out = run_days(
        FakeBackend(tmp_path), "LUZON", 2025, [1], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE"
    )
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
            _write_failed_step(self.sol_dir, year, session)
            return BPEResult(False, None, None, False, False)

    be = FailsButWritesFin(tmp_path)
    out = run_days(be, "LUZON", 2025, [1, 2], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    assert [o.status for o in out] == ["failed", "failed"]
    assert (tmp_path / "FIN_20250010.NQ0.gz").exists()
    assert not (tmp_path / "FIN_20250010.done").exists()

    # A real BPE day takes minutes; backdate the leftovers so the rerun's FINs
    # are distinguishable from them at filesystem mtime granularity.
    for leftover in tmp_path.glob("FIN_*.NQ0.gz"):
        os.utime(leftover, ns=(0, 0))
    be2 = FakeBackend(tmp_path)
    out2 = run_days(be2, "LUZON", 2025, [1, 2], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
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


def test_backend_exception_is_a_failed_day_and_stops_as_unknown(tmp_path):
    """The real backend raises on timeout and header validation.

    The day is recorded and the report returned, not an exception. No BPE step
    failed, so there is no diagnosis, and an unknown failure stops the run.
    """

    class RaisesOnDay2(FakeBackend):
        def run(self, campaign_name, year, session):
            if session == "0020":
                self.calls.append(session)
                raise RuntimeError("BPE timed out")
            return super().run(campaign_name, year, session)

    be = RaisesOnDay2(tmp_path)
    out = run_days(be, "LUZON", 2025, [1, 2, 3], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    assert [o.status for o in out] == ["ok", "failed", "not_run"]
    assert "RuntimeError" in out[1].note
    assert "unknown failure" in out[2].note


def test_corrupt_deflate_stream_not_banked_and_does_not_raise(tmp_path):
    good = tmp_path / "good.NQ0.gz"
    _write_valid_gz(good, b"SINEX data here" * 50)
    raw = bytearray(good.read_bytes())
    for i in range(12, len(raw) - 8):
        raw[i] ^= 0xFF
    (tmp_path / "FIN_20252000.NQ0.gz").write_bytes(bytes(raw))
    (tmp_path / "FIN_20252000.done").touch()
    assert not fin_banked(tmp_path, 2025, 200)


def test_stale_fin_from_an_earlier_attempt_is_not_banked(tmp_path):
    """Success without a new FIN must not bank a FIN left by a previous failed attempt."""
    _write_valid_gz(tmp_path / "FIN_20250010.NQ0.gz")

    class SaysOkWritesNothing(FakeBackend):
        def run(self, campaign_name, year, session):
            self.calls.append(session)
            return BPEResult(True, None, None, False, False)

    out = run_days(
        SaysOkWritesNothing(tmp_path),
        "LUZON",
        2025,
        [1],
        sol_dir=tmp_path,
        bpe_dir=tmp_path / "BPE",
    )
    assert out[0].status == "failed"
    assert "predates" in out[0].note
    assert not (tmp_path / "FIN_20250010.done").exists()


def test_doy_366_rejected_in_a_non_leap_year(tmp_path):
    with pytest.raises(ValueError):
        run_days(
            FakeBackend(tmp_path),
            "LUZON",
            2025,
            [365, 366],
            sol_dir=tmp_path,
            bpe_dir=tmp_path / "BPE",
        )
    assert (
        run_days(
            FakeBackend(tmp_path), "LUZON", 2024, [366], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE"
        )[0].status
        == "ok"
    )


def test_missing_bpe_dir_is_refused_before_any_day_runs(tmp_path):
    be = FakeBackend(tmp_path)
    with pytest.raises(ValueError, match="BPE directory"):
        run_days(be, "LUZON", 2025, [1], sol_dir=tmp_path, bpe_dir=tmp_path / "NOPE")
    assert be.calls == []


def test_unreadable_bpe_output_still_returns_the_report(tmp_path, monkeypatch):
    import bernese_workflow.month_driver as md

    def boom(*_a, **_k):
        raise PermissionError("denied")

    monkeypatch.setattr(md, "diagnose_day", boom)
    be = FakeBackend(tmp_path, fail_doys={1})
    out = run_days(be, "LUZON", 2025, [1, 2], sol_dir=tmp_path, bpe_dir=tmp_path / "BPE")
    assert [o.status for o in out] == ["failed", "not_run"]
    assert "unknown failure" in out[1].note
