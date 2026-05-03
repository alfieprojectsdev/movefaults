"""Tests for RinexQC / teqc +qc wrapper."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pogf_geodetic_suite.qc.rinex_qc import RinexQC, RINEXQCResult, _parse_teqc_output

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

    def fake_run(cmd, capture_output, text, cwd):
        # Simulate teqc writing a .S file
        s_file = Path(cwd) / "ALGO0010.S"
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


def test_run_qc_raises_when_teqc_not_found(tmp_path):
    """FileNotFoundError from subprocess (teqc binary missing) → RuntimeError."""
    rinex = tmp_path / "ALGO0010.22O"
    rinex.write_text("dummy rinex content")

    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.subprocess.run",
        side_effect=FileNotFoundError("teqc not found"),
    ):
        qc = RinexQC()
        with pytest.raises(RuntimeError, match="teqc not found"):
            qc.run_qc(str(rinex))


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


def test_rinex_qc_result_dataclass_fields():
    r = RINEXQCResult(obs_count=1000, cycle_slips=5, mp1_rms=0.3, mp2_rms=0.4, raw_output="")
    assert r.obs_count == 1000
    assert r.cycle_slips == 5
    assert r.mp1_rms == 0.3
    assert r.mp2_rms == 0.4
