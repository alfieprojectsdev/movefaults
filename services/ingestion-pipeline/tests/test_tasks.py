"""
Tests for ingestion_pipeline tasks.

Uses temporary files and mocks — no Celery worker, no PostgreSQL connection.
Tests cover the core logic: header validation, compression handling, header parsing.
"""

import gzip
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from ingestion_pipeline.tasks import (
    _parse_rinex_header,
    _parse_rinex_time,
    _standardize_format,
    _validate_rinex,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _rec(data: str, label: str) -> str:
    """One RINEX 2.x header record: data in columns 1-60, label in 61-80.

    Built rather than typed because the fixed-width layout is the point: the
    hand-typed version had every label starting near column 59, and teqc read
    the stray characters as an observable code (issue #243).
    """
    assert len(data) <= 60, f"data overflows into the label columns: {data!r}"
    return f"{data:<60}{label:<20}"


def _epoch(minute: int, second: float, sats: list[str]) -> list[str]:
    """One RINEX 2.11 epoch: header line, then one 5-observable line per satellite."""
    head = f" 23  1  1  0{minute:3d}{second:11.7f}  0{len(sats):3d}" + "".join(sats)
    obs = [
        "".join(f"{v:14.3f}  " for v in (1.1e8 + i, 8.6e7 + i, 2.1e7 + i, 2.1e7 + i, 2.1e7 + i))
        for i, _ in enumerate(sats)
    ]
    return [head, *obs]


# A header teqc accepts, with every record RINEX 2.11 marks mandatory, plus two
# epochs of data because gfzrnx rejects a header-only file ("no observations
# got/left"). The "valid" test must pass on BOTH tools, or it asserts a fact
# about whichever tool the machine happens to have.
MINIMAL_RINEX_HEADER = (
    "\n".join(
        [
            _rec("     2.11           OBSERVATION DATA    G (GPS)", "RINEX VERSION / TYPE"),
            _rec("pogf-test           PHIVOLCS            20230101 000000 UTC", "PGM / RUN BY / DATE"),
            _rec("PBIS", "MARKER NAME"),
            _rec("pogf                PHIVOLCS", "OBSERVER / AGENCY"),
            _rec("SN12345678901234567 TRIMBLE NETRS       4.23", "REC # / TYPE / VERS"),
            _rec("ANT001              TRM41249.00     NONE", "ANT # / TYPE"),
            _rec(" -3499087.8994  5191752.4907  1214049.9581", "APPROX POSITION XYZ"),
            _rec("        0.0000        0.0000        0.0000", "ANTENNA: DELTA H/E/N"),
            _rec("     1     1", "WAVELENGTH FACT L1/2"),
            _rec("     5    L1    L2    C1    P1    P2", "# / TYPES OF OBSERV"),
            _rec("    30.000", "INTERVAL"),
            _rec("  2023     1     1     0     0    0.0000000     GPS", "TIME OF FIRST OBS"),
            _rec("  2023     1     1     0     0   30.0000000     GPS", "TIME OF LAST OBS"),
            _rec("", "END OF HEADER"),
            *_epoch(0, 0.0, ["G05", "G12"]),
            *_epoch(0, 30.0, ["G05", "G12"]),
        ]
    )
    + "\n"
)
# REC # / TYPE / VERS field layout (RINEX 2.x, fixed-width 80 chars):
#   cols  1-20 (0-indexed  0-19): receiver serial number  → "SN12345678901234567 "
#   cols 21-40 (0-indexed 20-39): receiver type           → "TRIMBLE NETRS       "
#   cols 41-60 (0-indexed 40-59): firmware version        → "4.23                "
# ANT # / TYPE field layout:
#   cols  1-20: antenna serial  → "ANT001              "
#   cols 21-40: antenna type    → "TRM41249.00     NONE"


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def rinex_file(tmp_dir):
    """A minimal valid RINEX observation file."""
    path = Path(tmp_dir) / "PBIS001a.23o"
    path.write_text(MINIMAL_RINEX_HEADER, encoding="ascii")
    return str(path)


@pytest.fixture
def gz_rinex_file(tmp_dir):
    """A gzip-compressed RINEX file."""
    rinex_path = Path(tmp_dir) / "PBIS001a.23o"
    rinex_path.write_text(MINIMAL_RINEX_HEADER, encoding="ascii")
    gz_path = Path(tmp_dir) / "PBIS001a.23o.gz"
    with open(rinex_path, "rb") as f_in, gzip.open(gz_path, "wb") as f_out:
        shutil.copyfileobj(f_in, f_out)
    return str(gz_path)


# ---------------------------------------------------------------------------
# _parse_rinex_header
# ---------------------------------------------------------------------------

def test_parse_rinex_header_extracts_station(rinex_file):
    meta = _parse_rinex_header(rinex_file)
    assert meta["station_code"] == "PBIS"


def test_parse_rinex_header_extracts_interval(rinex_file):
    meta = _parse_rinex_header(rinex_file)
    assert meta["sampling_interval"] == pytest.approx(30.0)


def test_parse_rinex_header_extracts_receiver(rinex_file):
    meta = _parse_rinex_header(rinex_file)
    assert "TRIMBLE" in meta.get("receiver_type", "") or "NETRS" in meta.get("receiver_type", "")


def test_parse_rinex_header_missing_file():
    meta = _parse_rinex_header("/nonexistent/path.rnx")
    assert meta == {}


# ---------------------------------------------------------------------------
# _parse_rinex_time
# ---------------------------------------------------------------------------

def test_parse_rinex_time_valid():
    raw = "  2023     1     1     0     0    0.0000000     GPS"
    dt = _parse_rinex_time(raw)
    assert dt is not None
    assert dt.year == 2023
    assert dt.month == 1
    assert dt.day == 1


def test_parse_rinex_time_invalid():
    assert _parse_rinex_time("not a time") is None
    assert _parse_rinex_time("") is None


# ---------------------------------------------------------------------------
# validate_rinex
# ---------------------------------------------------------------------------

def test_validate_rinex_valid_header(rinex_file):
    result = _validate_rinex(rinex_file)
    assert result["file_path"] == rinex_file


def test_validate_rinex_missing_file(tmp_dir):
    with pytest.raises(FileNotFoundError):
        _validate_rinex(os.path.join(tmp_dir, "nonexistent.rnx"))


def test_validate_rinex_invalid_header(tmp_dir):
    bad_file = Path(tmp_dir) / "not_rinex.txt"
    bad_file.write_text("This is not a RINEX file\n" * 10)
    with pytest.raises(ValueError, match="No RINEX VERSION"):
        _validate_rinex(str(bad_file))


def test_validate_rinex_skips_teqc_if_missing(rinex_file):
    """If teqc is not in PATH, _validate_rinex should still succeed with None QC fields."""
    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.subprocess.run",
        side_effect=FileNotFoundError("teqc not found"),
    ):
        result = _validate_rinex(rinex_file)
    assert result["file_path"] == rinex_file
    assert result["qc_obs_count"] is None
    assert result["qc_cycle_slips"] is None


def test_validate_rinex_captures_qc_metrics(rinex_file):
    """When teqc succeeds, QC metrics are returned in the dict."""
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.stdout = ""
    mock_proc.stderr = "# obs       :  85321\n# slips  (all)    :    10\nMP1 : 0.30\nMP2 : 0.41\n"
    with patch("pogf_geodetic_suite.qc.rinex_qc.subprocess.run", return_value=mock_proc):
        result = _validate_rinex(rinex_file)
    assert result["file_path"] == rinex_file
    assert result["qc_obs_count"] == 85321
    assert result["qc_cycle_slips"] == 10
    assert abs(result["qc_mp1_rms"] - 0.30) < 1e-6
    assert abs(result["qc_mp2_rms"] - 0.41) < 1e-6


# ---------------------------------------------------------------------------
# _standardize_format
# ---------------------------------------------------------------------------

def test_standardize_format_passthrough_plain(rinex_file):
    """Plain RINEX file should be copied to temp and returned."""
    out = _standardize_format(rinex_file)
    assert Path(out).exists()
    assert Path(out).read_text(encoding="ascii").startswith(" ")


def test_standardize_format_decompresses_gz(gz_rinex_file):
    """Gzip-compressed RINEX file should be decompressed."""
    out = _standardize_format(gz_rinex_file)
    out_path = Path(out)
    assert out_path.exists()
    assert out_path.suffix.lower() != ".gz"
    content = out_path.read_text(encoding="ascii")
    assert "RINEX VERSION" in content


def test_validate_rinex_degrades_when_no_qc_binary_exists(rinex_file):
    """No QC binary at all -> ingestion proceeds with null metrics.

    Regression guard. `_validate_rinex` used to decide this by substring-
    matching the exception message for "not found". When the gfzrnx fallback
    landed, the no-binary message became "...teqc not installed... and the
    gfzrnx fallback is not available...", the substring stopped matching, and
    every ingestion on a machine without teqc raised instead of degrading.
    Nothing caught it because no CI ran the suite.

    This asserts on the real exception type raised by the QC layer, with a
    message deliberately containing NEITHER "not found" NOR "timed out".
    """
    from pogf_geodetic_suite.qc.rinex_qc import QCToolUnavailableError

    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.RinexQC.run_qc",
        side_effect=QCToolUnavailableError(
            "teqc not installed at 'teqc' and the gfzrnx fallback "
            "is not available at 'gfzrnx'."
        ),
    ):
        result = _validate_rinex(rinex_file)

    assert result["file_path"] == rinex_file
    assert result["qc_obs_count"] is None
    assert result["qc_cycle_slips"] is None


def test_validate_rinex_propagates_real_qc_failure(rinex_file):
    """A QC tool that RAN and failed is a data problem -- it must NOT degrade."""
    with patch(
        "pogf_geodetic_suite.qc.rinex_qc.RinexQC.run_qc",
        side_effect=RuntimeError("teqc exited 2: corrupt observation block"),
    ):
        with pytest.raises(RuntimeError, match="corrupt observation block"):
            _validate_rinex(rinex_file)


def test_validate_rinex_degrades_when_qc_package_is_not_importable(rinex_file):
    """A missing pogf-geodetic-suite must degrade, not raise a NameError.

    Regression guard. The QC import is lazy. When it lived INSIDE the same try
    block whose `except` names QCToolUnavailableError/QCToolTimeoutError, an
    ImportError could not be handled: Python evaluates the except expression
    at exception time, the names were never bound, and the real ImportError
    was masked by `UnboundLocalError: cannot access local variable
    'QCToolUnavailableError'`.
    """
    import builtins

    real_import = builtins.__import__

    def _fail_qc_import(name, *args, **kwargs):
        if name.startswith("pogf_geodetic_suite"):
            raise ImportError("no module named pogf_geodetic_suite (simulated)")
        return real_import(name, *args, **kwargs)

    with patch.object(builtins, "__import__", _fail_qc_import):
        result = _validate_rinex(rinex_file)

    assert result["file_path"] == rinex_file
    assert result["qc_obs_count"] is None
    assert result["qc_mp1_rms"] is None
