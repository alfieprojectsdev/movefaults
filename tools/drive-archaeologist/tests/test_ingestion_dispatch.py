"""
Tests for ingestion_dispatch.make_dispatch_callback.

All tests run without a live DB or Celery broker — the ingestion_pipeline
package is fully mocked out via unittest.mock.patch.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from drive_archaeologist.ingestion_dispatch import make_dispatch_callback

# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

GNSS_ARTIFACT = {
    "path": "/data/SITE0010.24O",
    "name": "SITE0010.24O",
    "extension": ".24o",
    "category": "GNSS Data",
    "size_bytes": 1024,
    "in_archive": False,
    "archive_path": None,
}

NON_GNSS_ARTIFACT = {
    "path": "/data/report.pdf",
    "name": "report.pdf",
    "extension": ".pdf",
    "category": "Document",
    "size_bytes": 512,
    "in_archive": False,
    "archive_path": None,
}

ARCHIVE_ARTIFACT = {
    "path": "/tmp/extracted/SITE0010.24O",
    "name": "SITE0010.24O",
    "extension": ".24o",
    "category": "GNSS Data",
    "size_bytes": 1024,
    "in_archive": True,
    "archive_path": "/data/archive.zip",
}


# ---------------------------------------------------------------------------
# Module-level mock for ingestion_pipeline so imports inside the callback
# can be controlled per-test without requiring the package to be installed.
# ---------------------------------------------------------------------------

def _make_pipeline_mocks(existing_log=None):
    """Return (mock_sessionlocal, mock_ingest_log_cls, mock_trigger_ingest) triple."""
    mock_session = MagicMock()
    mock_session.get.return_value = existing_log
    mock_session_local = MagicMock(return_value=mock_session)

    mock_ingest_log_cls = MagicMock()
    mock_trigger_ingest = MagicMock(return_value="fake-task-id")

    return mock_session_local, mock_ingest_log_cls, mock_trigger_ingest, mock_session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestDispatchSkipsNonGnssFiles:
    def test_dispatch_skips_non_gnss_files(self):
        """Non-GNSS category → trigger_ingest never called."""
        callback = make_dispatch_callback(dry_run=False)

        mock_session_local, mock_log_cls, mock_trigger, _ = _make_pipeline_mocks()

        with (
            patch.dict(
                sys.modules,
                {
                    "ingestion_pipeline": MagicMock(),
                    "ingestion_pipeline.database": MagicMock(SessionLocal=mock_session_local),
                    "ingestion_pipeline.models": MagicMock(IngestionLog=mock_log_cls),
                    "ingestion_pipeline.pipeline": MagicMock(trigger_ingest=mock_trigger),
                },
            )
        ):
            callback(NON_GNSS_ARTIFACT)

        mock_trigger.assert_not_called()


class TestDispatchSkipsArchiveExtractedFiles:
    def test_dispatch_skips_archive_extracted_files(self):
        """in_archive=True → trigger_ingest never called, even for GNSS category."""
        callback = make_dispatch_callback(dry_run=False)

        mock_session_local, mock_log_cls, mock_trigger, _ = _make_pipeline_mocks()

        with (
            patch.dict(
                sys.modules,
                {
                    "ingestion_pipeline": MagicMock(),
                    "ingestion_pipeline.database": MagicMock(SessionLocal=mock_session_local),
                    "ingestion_pipeline.models": MagicMock(IngestionLog=mock_log_cls),
                    "ingestion_pipeline.pipeline": MagicMock(trigger_ingest=mock_trigger),
                },
            )
        ):
            callback(ARCHIVE_ARTIFACT)

        mock_trigger.assert_not_called()


class TestDispatchCallsTriggerIngestForGnssFile:
    def test_dispatch_calls_trigger_ingest_for_gnss_file(self, tmp_path):
        """GNSS file, in_archive=False → trigger_ingest called with correct args."""
        # Write a real file so _sha256 can read it.
        gnss_file = tmp_path / "SITE0010.24O"
        gnss_file.write_bytes(b"RINEX OBSERVATION DATA" * 10)

        artifact = {**GNSS_ARTIFACT, "path": str(gnss_file), "name": gnss_file.name}
        callback = make_dispatch_callback(dry_run=False)

        mock_session_local, mock_log_cls, mock_trigger, mock_session = _make_pipeline_mocks(
            existing_log=None
        )

        with (
            patch.dict(
                sys.modules,
                {
                    "ingestion_pipeline": MagicMock(),
                    "ingestion_pipeline.database": MagicMock(SessionLocal=mock_session_local),
                    "ingestion_pipeline.models": MagicMock(IngestionLog=mock_log_cls),
                    "ingestion_pipeline.pipeline": MagicMock(trigger_ingest=mock_trigger),
                },
            )
        ):
            callback(artifact)

        mock_trigger.assert_called_once()
        call_args = mock_trigger.call_args
        assert call_args[0][0] == str(gnss_file)
        # Second argument is the SHA-256 hex string (64 chars).
        assert len(call_args[0][1]) == 64


class TestDispatchSkipsAlreadyIngested:
    def test_dispatch_skips_already_ingested(self, tmp_path):
        """IngestionLog row with status='success' → trigger_ingest not called."""
        gnss_file = tmp_path / "SITE0010.24O"
        gnss_file.write_bytes(b"RINEX" * 20)

        artifact = {**GNSS_ARTIFACT, "path": str(gnss_file), "name": gnss_file.name}
        callback = make_dispatch_callback(dry_run=False)

        existing_log = MagicMock()
        existing_log.status = "success"

        mock_session_local, mock_log_cls, mock_trigger, _ = _make_pipeline_mocks(
            existing_log=existing_log
        )

        with (
            patch.dict(
                sys.modules,
                {
                    "ingestion_pipeline": MagicMock(),
                    "ingestion_pipeline.database": MagicMock(SessionLocal=mock_session_local),
                    "ingestion_pipeline.models": MagicMock(IngestionLog=mock_log_cls),
                    "ingestion_pipeline.pipeline": MagicMock(trigger_ingest=mock_trigger),
                },
            )
        ):
            callback(artifact)

        mock_trigger.assert_not_called()


class TestDispatchDryRunDoesNotCallTriggerIngest:
    def test_dispatch_dry_run_does_not_call_trigger_ingest(self, tmp_path):
        """dry_run=True → trigger_ingest never called regardless of file type."""
        gnss_file = tmp_path / "SITE0010.24O"
        gnss_file.write_bytes(b"RINEX" * 20)

        artifact = {**GNSS_ARTIFACT, "path": str(gnss_file), "name": gnss_file.name}
        callback = make_dispatch_callback(dry_run=True)

        mock_session_local, mock_log_cls, mock_trigger, _ = _make_pipeline_mocks()

        with (
            patch.dict(
                sys.modules,
                {
                    "ingestion_pipeline": MagicMock(),
                    "ingestion_pipeline.database": MagicMock(SessionLocal=mock_session_local),
                    "ingestion_pipeline.models": MagicMock(IngestionLog=mock_log_cls),
                    "ingestion_pipeline.pipeline": MagicMock(trigger_ingest=mock_trigger),
                },
            )
        ):
            callback(artifact)

        mock_trigger.assert_not_called()
        # Session should not be opened either — dry_run exits before lazy import.
        mock_session_local.assert_not_called()


class TestDispatchHandlesMissingIngestionPackage:
    def test_dispatch_handles_missing_ingestion_package(self, tmp_path):
        """ImportError from ingestion_pipeline → no exception propagates, trigger_ingest not called."""
        gnss_file = tmp_path / "SITE0010.24O"
        gnss_file.write_bytes(b"RINEX" * 20)

        artifact = {**GNSS_ARTIFACT, "path": str(gnss_file), "name": gnss_file.name}
        callback = make_dispatch_callback(dry_run=False)

        # Remove any cached ingestion_pipeline modules to force ImportError.
        modules_to_remove = [k for k in sys.modules if k.startswith("ingestion_pipeline")]
        saved = {k: sys.modules.pop(k) for k in modules_to_remove}

        try:
            import builtins

            real_import = builtins.__import__

            def mock_import(name, *args, **kwargs):
                if name.startswith("ingestion_pipeline"):
                    raise ImportError(f"No module named '{name}'")
                return real_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=mock_import):
                # Should not raise.
                callback(artifact)

        finally:
            sys.modules.update(saved)
