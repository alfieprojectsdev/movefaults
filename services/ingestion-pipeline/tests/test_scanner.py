"""
Tests for FileScanner — directory walking, hashing, idempotency.

All DB and Celery interactions are mocked so tests run without PostgreSQL or Redis.
"""

import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from ingestion_pipeline.scanner import FileScanner, _is_rinex_file, _sha256


# ---------------------------------------------------------------------------
# _is_rinex_file
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name, expected", [
    ("PBIS001a.23o", True),    # RINEX 2.x observation
    ("PBIS001a.23d", True),    # RINEX 2.x Hatanaka
    ("PBIS001a.rnx", True),    # RINEX 3.x
    ("PBIS001a.crx", True),    # RINEX 3.x Hatanaka
    ("PBIS001a.rnx.gz", True), # gzip wrapper
    ("PBIS001a.zip", True),    # zip wrapper
    ("README.txt", False),
    ("photo.jpg", False),
    ("config.yml", False),
    ("PBIS001a.23n", False),   # navigation file — not observation
])
def test_is_rinex_file(name, expected):
    assert _is_rinex_file(name) == expected


# ---------------------------------------------------------------------------
# _sha256
# ---------------------------------------------------------------------------

def test_sha256_consistent(tmp_path):
    f = tmp_path / "test.rnx"
    f.write_bytes(b"RINEX content")
    h1 = _sha256(str(f))
    h2 = _sha256(str(f))
    assert h1 == h2
    assert len(h1) == 64


def test_sha256_different_content(tmp_path):
    f1 = tmp_path / "a.rnx"
    f2 = tmp_path / "b.rnx"
    f1.write_bytes(b"content A")
    f2.write_bytes(b"content B")
    assert _sha256(str(f1)) != _sha256(str(f2))


def test_sha256_missing_file():
    assert _sha256("/no/such/file.rnx") is None


# ---------------------------------------------------------------------------
# FileScanner
# ---------------------------------------------------------------------------

MINIMAL_RINEX = """\
     2.11           OBSERVATION DATA    G (GPS)             RINEX VERSION / TYPE
PBIS                                                        MARKER NAME
                                                            END OF HEADER
"""


@pytest.fixture
def scan_dir(tmp_path):
    """Temporary directory with two RINEX files."""
    (tmp_path / "PBIS001a.23o").write_text(MINIMAL_RINEX)
    (tmp_path / "BOST001a.23o").write_text(MINIMAL_RINEX)
    (tmp_path / "ignore.txt").write_text("not a rinex file")
    return tmp_path


def _mock_session_factory(existing_log=None):
    """Return a mock SessionLocal that mimics the DB session interface."""
    session = MagicMock()
    session.get.return_value = existing_log
    # Make it usable as a context manager (not used, but defensive)
    session.__enter__ = lambda s: s
    session.__exit__ = MagicMock(return_value=False)
    return session


def test_scanner_queues_new_files(scan_dir):
    """New files should be queued and trigger_ingest should be called."""
    mock_session = _mock_session_factory(existing_log=None)

    with patch("ingestion_pipeline.scanner.SessionLocal", return_value=mock_session), \
         patch("ingestion_pipeline.scanner.trigger_ingest") as mock_trigger:

        scanner = FileScanner(str(scan_dir))
        result = scanner.scan()

    assert result["queued"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == 0
    assert mock_trigger.call_count == 2


def test_scanner_skips_already_ingested(scan_dir):
    """Files with status='success' should be skipped."""
    success_log = MagicMock()
    success_log.status = "success"
    mock_session = _mock_session_factory(existing_log=success_log)

    with patch("ingestion_pipeline.scanner.SessionLocal", return_value=mock_session), \
         patch("ingestion_pipeline.scanner.trigger_ingest") as mock_trigger:

        scanner = FileScanner(str(scan_dir))
        result = scanner.scan()

    assert result["skipped"] == 2
    assert result["queued"] == 0
    mock_trigger.assert_not_called()


def test_scanner_requeues_failed_files(scan_dir):
    """Files with status='failed' should be re-queued."""
    failed_log = MagicMock()
    failed_log.status = "failed"
    mock_session = _mock_session_factory(existing_log=failed_log)

    with patch("ingestion_pipeline.scanner.SessionLocal", return_value=mock_session), \
         patch("ingestion_pipeline.scanner.trigger_ingest") as mock_trigger:

        scanner = FileScanner(str(scan_dir))
        result = scanner.scan()

    assert result["queued"] == 2
    # status should be reset to 'pending'
    assert failed_log.status == "pending"


def test_scanner_ignores_non_rinex(scan_dir):
    """Non-RINEX files (ignore.txt) should not appear in counts."""
    mock_session = _mock_session_factory(existing_log=None)

    with patch("ingestion_pipeline.scanner.SessionLocal", return_value=mock_session), \
         patch("ingestion_pipeline.scanner.trigger_ingest"):

        scanner = FileScanner(str(scan_dir))
        result = scanner.scan()

    # Only 2 .23o files — ignore.txt excluded
    assert result["queued"] + result["skipped"] == 2
