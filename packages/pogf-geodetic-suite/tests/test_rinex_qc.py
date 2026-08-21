"""Tests for RinexQC / teqc +qc wrapper."""
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pogf_geodetic_suite.qc.rinex_qc import (
    QCToolTimeoutError,
    QCToolUnavailableError,
    RinexQC,
    RINEXQCResult,
    _parse_teqc_output,
)

# ---------------------------------------------------------------------------
# Fixture: representative teqc .S output (teqc 2019-era format)
# ---------------------------------------------------------------------------
SAMPLE_TEQC_OUTPUT = """\
Summary of Quality Checking:
  Version : teqc  2019Feb25

MARKER NAME             : ALGO

obs types   : L1  L2  P1  P2
# obs       :  85321  84000  85321  84000

-- Slips --
# slips  (all)    :    127

-- Multipath (in metres) --
MP1             :   0.352
MP2             :   0.413
"""

SAMPLE_ALT_FORMAT = """\
Total obs   : 42000
Slips       : 55
MP1 : 0.29
MP2 : 0.35
"""

SAMPLE_EMPTY_OUTPUT = "teqc processing complete\n"


# ---------------------------------------------------------------------------
# Parser unit tests (no subprocess, no filesystem)
# ---------------------------------------------------------------------------

def test_parse_standard_format():
    result = _parse_teqc_output(SAMPLE_TEQC_OUTPUT)
    assert result.obs_count == 85321
    assert result.cycle_slips == 127
    assert abs(result.mp1_rms - 0.352) < 1e-6
    assert abs(result.mp2_rms - 0.413) < 1e-6


def test_parse_alt_format():
    result = _parse_teqc_output(SAMPLE_ALT_FORMAT)
    assert result.obs_count == 42000
    assert result.cycle_slips == 55
    assert abs(result.mp1_rms - 0.29) < 1e-6


def test_parse_empty_output_returns_none_fields():
    result = _parse_teqc_output(SAMPLE_EMPTY_OUTPUT)
    assert result.obs_count is None
    assert result.cycle_slips is None
    assert result.mp1_rms is None
    assert result.mp2_rms is None


def test_parse_preserves_raw_output():
    result = _parse_teqc_output(SAMPLE_TEQC_OUTPUT)
    assert result.raw_output == SAMPLE_TEQC_OUTPUT


# ---------------------------------------------------------------------------
# Integration tests — subprocess mocked
# ---------------------------------------------------------------------------

def test_run_qc_file_not_found():
    qc = RinexQC()
    with pytest.raises(FileNotFoundError):
        qc.run_qc("/nonexistent/path/file.rnx")


def test_run_qc_reads_s_file(tmp_path):
    """run_qc() reads the .S output file written by teqc."""
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    def fake_run(cmd, **kwargs):
        # Simulate teqc writing a .S file
        s_file = Path(kwargs["cwd"]) / "ALGO0010.S"
        s_file.write_text(SAMPLE_TEQC_OUTPUT)
        result = MagicMock()
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
        return result

    with patch("pogf_geodetic_suite.qc.rinex_qc.subprocess.run", side_effect=fake_run):
        qc = RinexQC()
        result = qc.run_qc(str(rinex))

    assert result.obs_count == 85321
    assert result.cycle_slips == 127


def test_run_qc_falls_back_to_stderr(tmp_path):
    """When no .S file is written, parse stdout+stderr instead."""
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = SAMPLE_TEQC_OUTPUT

    with patch("pogf_geodetic_suite.qc.rinex_qc.subprocess.run", return_value=mock_proc):
        qc = RinexQC()
        result = qc.run_qc(str(rinex))

    assert result.obs_count == 85321


def test_run_qc_raises_when_teqc_not_found_and_fallback_disabled(tmp_path):
    """Missing teqc with no fallback → RuntimeError, as it always did.

    Behaviour change 2026-08-13: with `allow_fallback=True` (the default) a
    missing teqc now routes to gfzrnx instead of raising. This test pins the
    original contract for the explicit opt-out; the following test pins the
    new default.
    """
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.subprocess.run",
        side_effect=FileNotFoundError("teqc not found"),
    ):
        qc = RinexQC(allow_fallback=False)
        with pytest.raises(RuntimeError, match="teqc not found"):
            qc.run_qc(str(rinex))


def test_missing_teqc_falls_back_and_records_why(tmp_path):
    """Default path: teqc absent → gfzrnx runs, and the result says so.

    The substitution must never be silent. `tool` and `fallback_reason` are
    what make a result reproducible after the fact.
    """
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "teqc" in str(cmd[0]):
            raise FileNotFoundError("teqc not found")
        return SimpleNamespace(
            returncode=0,
            stdout="STP AIRA E TYP   C1X" + chr(10) + "STO AIRA E E02  1272" + chr(10),
            stderr="",
        )

    with patch("pogf_geodetic_suite.qc.rinex_qc.subprocess.run", side_effect=fake_run):
        result = RinexQC().run_qc(str(rinex))

    assert result.tool == "gfzrnx"
    assert "not installed" in result.fallback_reason
    assert result.obs_count == 1272
    assert any("stk_obs" in str(c) for c in calls)


def test_both_tools_missing_names_both(tmp_path):
    """If neither binary exists, the error must name both, not just gfzrnx."""
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.subprocess.run",
        side_effect=FileNotFoundError("nothing here"),
    ):
        with pytest.raises(RuntimeError) as exc:
            RinexQC().run_qc(str(rinex))
    msg = str(exc.value)
    assert "teqc" in msg and "gfzrnx" in msg


def test_run_qc_raises_on_fatal_exit_code(tmp_path):
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy")

    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.stderr = "fatal error"
    mock_proc.stdout = ""

    with patch("pogf_geodetic_suite.qc.rinex_qc.subprocess.run", return_value=mock_proc):
        qc = RinexQC()
        with pytest.raises(RuntimeError):
            qc.run_qc(str(rinex))


def test_run_qc_raises_on_timeout(tmp_path):
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="teqc", timeout=30),
    ):
        qc = RinexQC(timeout_sec=30)
        with pytest.raises(RuntimeError, match="timed out after 30s"):
            qc.run_qc(str(rinex))


def test_rinex_qc_custom_timeout():
    qc = RinexQC(timeout_sec=30)
    assert qc.timeout_sec == 30


def test_rinex_qc_result_dataclass_fields():
    r = RINEXQCResult(obs_count=1000, cycle_slips=5, mp1_rms=0.3, mp2_rms=0.4, raw_output="")
    assert r.obs_count == 1000
    assert r.cycle_slips == 5
    assert r.mp1_rms == 0.3
    assert r.mp2_rms == 0.4


# ---------------------------------------------------------------------------
# gfzrnx fallback (added 2026-08-13)
#
# teqc was discontinued in 2019 and cannot read RINEX 3 at all, while every
# IGS fiducial this project uses is RINEX 3. These cover the routing decision,
# not the tools themselves.
# ---------------------------------------------------------------------------

def test_teqc_rinex3_refusal_is_recognised():
    """The trigger matches teqc's actual wording, verbatim from a real run."""
    from pogf_geodetic_suite.qc.rinex_qc import _TEQC_RINEX3_REFUSAL
    real = ("teqc: failure to read '     3.04           OBSERVATION DATA    M"
            "                   RINEX VERSION / TYPE'\n"
            "        on line 1 of 'CUSV00THA_R_20260870000_01D_30S_MO.rnx'\n"
            "        (unaccepted RINEX version or non-RINEX file; must be "
            "RINEX Version <= 2.11) ... exiting")
    assert _TEQC_RINEX3_REFUSAL.search(real)


def test_normal_teqc_output_does_not_trigger_fallback():
    """A successful teqc run must never be routed to gfzrnx."""
    from pogf_geodetic_suite.qc.rinex_qc import _TEQC_RINEX3_REFUSAL
    assert not _TEQC_RINEX3_REFUSAL.search(
        "SUM  Total satellites w/ obs : 31\nmoving average MP1 : 0.35 m"
    )


def test_gfzrnx_parser_leaves_unreported_fields_none():
    """gfzrnx -stk_obs reports observation counts but not multipath or slips.

    Those stay None rather than 0: a zero would be compared against teqc's
    multipath RMS by someone who did not notice the tool differed.
    """
    from pogf_geodetic_suite.qc.rinex_qc import _parse_gfzrnx_output
    out = ("STP AIRA E TYP   C1X   C5X\n"
           "STO AIRA E E02  1272  1272\n"
           "STO AIRA E E03  1137  1137\n")
    r = _parse_gfzrnx_output(out)
    assert r.tool == "gfzrnx"
    assert r.obs_count == 1272 + 1272 + 1137 + 1137
    assert r.cycle_slips is None
    assert r.mp1_rms is None and r.mp2_rms is None


def test_result_defaults_to_teqc_provenance():
    """An unlabelled result must claim teqc, never an ambiguous blank."""
    from pogf_geodetic_suite.qc.rinex_qc import RINEXQCResult
    r = RINEXQCResult(obs_count=1, cycle_slips=0, mp1_rms=0.1, mp2_rms=0.2,
                      raw_output="")
    assert r.tool == "teqc"
    assert r.fallback_reason is None


# ---------------------------------------------------------------------------
# SUM-row parsing (added 2026-08-13)
#
# teqc 2019Feb25 reports #have / mp1 / mp2 / o-slps as COLUMNS of a SUM row,
# not as "key : value" pairs. The original patterns never matched it, and the
# mismatch was invisible for as long as teqc was not installed on the machine.
# Fixture below is verbatim from a real run on ALAB1210.25o.
# ---------------------------------------------------------------------------

REAL_TEQC_SUM = (
    "Total satellites w/ obs : 55\n"
    "IOD slips               :    147\n"
    "      first epoch    last epoch    hrs   dt  #expt  #have   %   mp1   mp2 o/slps\n"
    "SUM 25  5  1 00:00 25  5  1 23:59 24.00  30     -   46370  -   0.74  0.49    284\n"
)


def test_sum_row_yields_all_four_metrics():
    r = _parse_teqc_output(REAL_TEQC_SUM)
    assert r.obs_count == 46370
    assert r.cycle_slips == 284
    assert r.mp1_rms == 0.74
    assert r.mp2_rms == 0.49
    assert r.tool == "teqc"


def test_sum_row_tolerates_dash_columns():
    """teqc writes '-' where a value is unavailable; that must not become 0."""
    text = (
        "      first epoch    last epoch    hrs   dt  #expt  #have   %   mp1   mp2 o/slps\n"
        "SUM 25  5  1 00:00 25  5  1 23:59 24.00  30     -       -  -      -     -      0\n"
    )
    r = _parse_teqc_output(text)
    assert r.obs_count is None
    assert r.mp1_rms is None and r.mp2_rms is None
    assert r.cycle_slips == 0


def test_keyvalue_fallback_still_works_for_other_versions():
    """Older/other teqc builds using 'key : value' must still parse."""
    r = _parse_teqc_output("total obs : 12345\nMP1 : 0.31\nMP2 : 0.22\nslips : 7\n")
    assert r.obs_count == 12345
    assert r.mp1_rms == 0.31
    assert r.cycle_slips == 7


# ---------------------------------------------------------------------------
# Typed failure contract
#
# Callers must be able to distinguish "no QC binary exists" from "QC ran and
# the data is bad" WITHOUT reading the message text. The ingestion pipeline
# once matched on prose ("not found"); the gfzrnx fallback reworded the
# message to "not installed"/"not available", the match silently stopped
# firing, and every ingestion on a teqc-less machine failed instead of
# degrading. These tests pin the types so that cannot recur.
# ---------------------------------------------------------------------------

def test_missing_binaries_raise_unavailable_not_bare_runtime(tmp_path):
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.subprocess.run",
        side_effect=FileNotFoundError("nothing here"),
    ):
        with pytest.raises(QCToolUnavailableError):
            RinexQC().run_qc(str(rinex))


def test_missing_teqc_with_fallback_disabled_raises_unavailable(tmp_path):
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.subprocess.run",
        side_effect=FileNotFoundError("no teqc"),
    ):
        with pytest.raises(QCToolUnavailableError):
            RinexQC(allow_fallback=False).run_qc(str(rinex))


def test_timeout_raises_timeout_type_not_unavailable(tmp_path):
    """A tool that ran and hung is NOT the same as a tool that is absent."""
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="teqc", timeout=30),
    ):
        with pytest.raises(QCToolTimeoutError):
            RinexQC(timeout_sec=30).run_qc(str(rinex))
    assert not issubclass(QCToolTimeoutError, QCToolUnavailableError)


def test_bad_exit_code_is_NOT_unavailable(tmp_path):
    """teqc ran and rejected the file. That is a data problem, and callers that
    degrade on unavailability must NOT degrade on this."""
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy")

    mock_proc = MagicMock()
    mock_proc.returncode = 2
    mock_proc.stderr = "fatal error"
    mock_proc.stdout = ""

    with patch("pogf_geodetic_suite.qc.rinex_qc.subprocess.run", return_value=mock_proc):
        with pytest.raises(RuntimeError) as exc:
            RinexQC().run_qc(str(rinex))
    assert not isinstance(exc.value, (QCToolUnavailableError, QCToolTimeoutError))


def test_typed_errors_remain_runtimeerror_subclasses():
    """Pre-existing `except RuntimeError` handlers must keep working."""
    assert issubclass(QCToolUnavailableError, RuntimeError)
    assert issubclass(QCToolTimeoutError, RuntimeError)
