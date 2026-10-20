"""Tests for the circuit breaker and its wiring into month_driver.run_days.

The plan's exit check for week 1 is the first test: a replay of 29 August, when
ADDNEQ2's MAXPAR failed 24 days in a row, must stop early and print the MAXPAR
remedy. No Bernese runs here: a fake backend leaves the failed step's PRT in
BPE/ the way the real BPE does.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from bernese_workflow.backends import BPEResult
from bernese_workflow.bpe_knowledge import DEFAULT_PATH, load, loads
from bernese_workflow.circuit_breaker import CircuitBreaker, Diagnosis, diagnose_day
from bernese_workflow.month_driver import run_days

FIXTURES = Path(__file__).parent / "fixtures" / "bpe_errors"
MAXPAR_PRT = FIXTURES / "MXPREP_MX230100_511_000.PRT"
MAXPAR_LOG = FIXTURES / "MXPREP_MX230100_511_000.LOG"
HELMR1_PRT = FIXTURES / "LZY250360_RP250360_513_000.PRT"

_ERR = " 01-JAN-2026  00:00:00  00:00:01  00:00:00  ERR GPSEST    ERROR IN MAIN PROGRAM\n"
GETPOL = " *** SR GETPOL: NO SUITABLE EPOCHS IN POLE FILE\n" + _ERR
UNKNOWN = " *** SR NOSUCH: SOMETHING NEW\n" + _ERR


def _step(bpe: Path, year: int, session: str, content: str | Path, pid: str = "511_000") -> Path:
    bpe.mkdir(parents=True, exist_ok=True)
    path = bpe / f"RP{year % 100:02d}{session}_{pid}.PRT"
    if isinstance(content, Path):
        path.write_bytes(content.read_bytes())
    else:
        path.write_text(content)
    return path


class ReplayBackend:
    """Fails every day listed in ``failures`` with that day's PRT content."""

    def __init__(self, bpe_dir: Path, sol_dir: Path, failures: dict[int, str | Path]):
        self.bpe_dir = bpe_dir
        self.sol_dir = sol_dir
        self.failures = failures
        self.calls: list[str] = []

    def run(self, campaign_name: str, year: int, session: str) -> BPEResult:
        self.calls.append(session)
        doy = int(session[:3])
        if doy in self.failures:
            _step(self.bpe_dir, year, session, self.failures[doy])
            return BPEResult(False, None, None, False, False)
        (self.sol_dir / f"FIN_{year}{session}.NQ0").write_bytes(b"x")
        return BPEResult(True, None, None, False, False)


def _replay(tmp_path: Path, failures: dict[int, str | Path], doys, kb=None):
    (tmp_path / "BPE").mkdir(exist_ok=True)
    be = ReplayBackend(tmp_path / "BPE", tmp_path, failures)
    kb = kb if kb is not None else load(DEFAULT_PATH)
    out = run_days(be, "PHREF", 2025, doys, sol_dir=tmp_path, bpe_dir=tmp_path / "BPE", kb=kb)
    return be, out


# --- the exit check ----------------------------------------------------------


def test_replay_of_29_august_stops_at_once_with_the_maxpar_remedy(tmp_path):
    """24 days of neqckdim. It is scope: configuration, so the first one stops the run."""
    days = list(range(1, 25))
    be, out = _replay(tmp_path, dict.fromkeys(days, MAXPAR_PRT), days)
    assert len(be.calls) == 1
    assert [o.status for o in out] == ["failed"] + ["not_run"] * 23
    assert out[0].error == "neqckdim: DIMENSION_TOO_SMALL"
    assert "Raise MAXPAR" in out[0].explanation
    assert "configuration error" in out[1].note


def test_replay_with_the_row_as_session_scope_stops_after_three(tmp_path):
    """The plan's literal check: K = 3 identical failures stop the run."""
    text = DEFAULT_PATH.read_text().replace(
        "  - emitter: neqckdim\n    message: DIMENSION TOO SMALL\n    scope: configuration",
        "  - emitter: neqckdim\n    message: DIMENSION TOO SMALL\n    scope: session",
    )
    kb = loads(text)
    days = list(range(1, 25))
    be, out = _replay(tmp_path, dict.fromkeys(days, MAXPAR_PRT), days, kb=kb)
    assert len(be.calls) == 3
    assert [o.status for o in out[:4]] == ["failed", "failed", "failed", "not_run"]
    assert "3 consecutive days failed with neqckdim" in out[3].note
    assert "Raise MAXPAR" in out[2].explanation


# --- the breaker's rules, through the driver ---------------------------------


def test_unknown_error_stops_at_once(tmp_path):
    be, out = _replay(tmp_path, {1: UNKNOWN}, [1, 2])
    assert be.calls == ["0010"]
    assert "UNKNOWN" in out[0].explanation
    assert "*** SR NOSUCH: SOMETHING NEW" in out[0].explanation
    assert "unknown failure" in out[1].note


def test_failure_without_any_failed_step_stops_at_once(tmp_path):
    """BPE reports failure but no step says ERR: nothing to look up."""
    be, out = _replay(tmp_path, {1: " nothing here\n"}, [1, 2])
    assert be.calls == ["0010"]
    assert out[0].error == "no failed BPE step"
    assert "unknown failure" in out[1].note


def test_different_session_errors_do_not_trip_k(tmp_path):
    failures = {1: HELMR1_PRT, 2: GETPOL, 3: HELMR1_PRT, 4: GETPOL}
    be, out = _replay(tmp_path, failures, [1, 2, 3, 4, 5])
    assert len(be.calls) == 5
    assert [o.status for o in out] == ["failed"] * 4 + ["ok"]


def test_five_failures_in_a_row_stop_the_run_whatever_the_errors(tmp_path):
    """Review finding: alternating session errors restart K every day and never stop."""
    failures = {d: (HELMR1_PRT if d % 2 else GETPOL) for d in range(1, 8)}
    be, out = _replay(tmp_path, failures, range(1, 8))
    assert len(be.calls) == 5
    assert [o.status for o in out] == ["failed"] * 5 + ["not_run"] * 2
    assert "5 consecutive days failed, with different errors" in out[5].note


def test_only_a_success_resets_the_cap(tmp_path):
    failures = {d: (HELMR1_PRT if d % 2 else GETPOL) for d in (1, 2, 3, 4, 6, 7, 8, 9)}
    be, out = _replay(tmp_path, failures, range(1, 10))
    assert len(be.calls) == 9
    assert out[4].status == "ok"


def test_a_success_restarts_the_count(tmp_path):
    failures = {1: HELMR1_PRT, 2: HELMR1_PRT, 4: HELMR1_PRT, 5: HELMR1_PRT}
    be, out = _replay(tmp_path, failures, [1, 2, 3, 4, 5])
    assert len(be.calls) == 5
    assert [o.status for o in out] == ["failed", "failed", "ok", "failed", "failed"]


# --- finding the failed step -------------------------------------------------


def test_diagnosis_reads_the_lowest_failed_step(tmp_path):
    kb = load(DEFAULT_PATH)
    _step(tmp_path, 2025, "2000", GETPOL, pid="322_017")
    _step(tmp_path, 2025, "2000", HELMR1_PRT, pid="513_000")
    d = diagnose_day(tmp_path, 2025, "2000", 0.0, kb)
    assert d.step is not None and d.step.name == "RP252000_322_017.PRT"
    assert d.label == "GETPOL: NO_SUITABLE_EPOCHS_IN_POLE_FILE"
    assert d.entry is not None and d.entry.scope == "session"


def test_diagnosis_ignores_an_earlier_attempt_and_other_days(tmp_path):
    kb = load(DEFAULT_PATH)
    old = _step(tmp_path, 2025, "2000", UNKNOWN, pid="322_017")
    os.utime(old, (0, 0))
    _step(tmp_path, 2025, "2010", UNKNOWN, pid="322_017")
    _step(tmp_path, 2024, "2000", UNKNOWN, pid="322_017")
    d = diagnose_day(tmp_path, 2025, "2000", 1000.0, kb)
    assert d.step is None and d.key is None


def test_diagnosis_from_a_log_when_there_is_no_prt(tmp_path):
    kb = load(DEFAULT_PATH)
    (tmp_path / "MX230100_511_000.LOG").write_bytes(MAXPAR_LOG.read_bytes())
    d = diagnose_day(tmp_path, 2023, "0100", 0.0, kb)
    assert d.step is not None and d.step.suffix == ".LOG"
    assert d.label == "neqckdim: DIMENSION_TOO_SMALL"


def test_diagnosis_prefers_the_prt_of_a_pair(tmp_path):
    kb = load(DEFAULT_PATH)
    (tmp_path / "MX230100_511_000.PRT").write_bytes(MAXPAR_PRT.read_bytes())
    (tmp_path / "MX230100_511_000.LOG").write_bytes(MAXPAR_LOG.read_bytes())
    d = diagnose_day(tmp_path, 2023, "0100", 0.0, kb)
    assert d.step is not None and d.step.suffix == ".PRT"


def test_breaker_rejects_k_below_one():
    with pytest.raises(ValueError):
        CircuitBreaker(0)


def test_breaker_rejects_a_cap_below_k():
    with pytest.raises(ValueError, match="max_failures"):
        CircuitBreaker(k=3, max_failures=2)


def test_breaker_with_k_one_stops_on_the_first_session_error(tmp_path):
    kb = load(DEFAULT_PATH)
    _step(tmp_path, 2025, "2000", HELMR1_PRT)
    breaker = CircuitBreaker(1)
    assert breaker.failure(diagnose_day(tmp_path, 2025, "2000", 0.0, kb)) is not None


def test_empty_diagnosis_is_unknown():
    reason = CircuitBreaker().failure(Diagnosis(None, None, None))
    assert reason is not None and "unknown" in reason
