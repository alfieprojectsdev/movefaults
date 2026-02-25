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

MINIMAL_RINEX_HEADER = """\
     2.11           OBSERVATION DATA    G (GPS)             RINEX VERSION / TYPE
PBIS                                                        MARKER NAME
     5                                                      # / TYPES OF OBSERV
    30.000                                                  INTERVAL
  2023     1     1     0     0    0.0000000     GPS         TIME OF FIRST OBS
  2023     1     1    23    59   30.0000000     GPS         TIME OF LAST OBS
SN12345678901234567 TRIMBLE NETRS       4.23                REC # / TYPE / VERS
ANT001              TRM41249.00     NONE                    ANT # / TYPE
                                                            END OF HEADER
"""
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
    assert result == rinex_file


def test_validate_rinex_missing_file(tmp_dir):
    with pytest.raises(FileNotFoundError):
        _validate_rinex(os.path.join(tmp_dir, "nonexistent.rnx"))


def test_validate_rinex_invalid_header(tmp_dir):
    bad_file = Path(tmp_dir) / "not_rinex.txt"
    bad_file.write_text("This is not a RINEX file\n" * 10)
    with pytest.raises(ValueError, match="No RINEX VERSION"):
        _validate_rinex(str(bad_file))


def test_validate_rinex_skips_teqc_if_missing(rinex_file):
    """If teqc is not in PATH, _validate_rinex should still succeed."""
    with patch("ingestion_pipeline.tasks.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("teqc not found")
        result = _validate_rinex(rinex_file)
    assert result == rinex_file


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
