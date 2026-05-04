"""
Factory for the on_classified callback that dispatches GNSS files to the ingestion pipeline.

This module has NO top-level imports from ingestion_pipeline — all pipeline imports are
lazy (inside the callback closure) so that drive-archaeologist remains installable without
the ingestion_pipeline package present.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# The single category string used by drive_archaeologist.profiles for GNSS files.
# Verified against profiles.py: all RINEX, SP3, CLK, SNX, etc. extensions map here.
GNSS_CATEGORIES: frozenset[str] = frozenset({"GNSS Data"})


def _sha256(file_path: str) -> str | None:
    """SHA-256 of file contents, chunked for large files. Returns None on read error."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError as exc:
        logger.warning("Cannot hash %s: %s", file_path, exc)
        return None


def make_dispatch_callback(dry_run: bool = False) -> Callable[[dict], None]:
    """
    Return an on_classified callback that dispatches GNSS files to the
    ingestion pipeline Celery chain.

    dry_run=True logs what would be dispatched without calling trigger_ingest.
    Handles a missing ingestion_pipeline package gracefully (logs a warning, skips).
    """

    def _dispatch(artifact: dict) -> None:
        # 1. Skip files extracted from archives — temp paths are transient.
        if artifact.get("in_archive"):
            logger.debug("Skipping archive-extracted file: %s", artifact.get("path"))
            return

        # 2. Skip non-GNSS categories.
        category = artifact.get("category")
        if category not in GNSS_CATEGORIES:
            logger.debug("Skipping non-GNSS file (category=%r): %s", category, artifact.get("path"))
            return

        file_path: str = artifact["path"]

        # 3. Compute SHA-256 using stdlib hashlib directly (no pipeline import needed).
        file_hash = _sha256(file_path)
        if file_hash is None:
            logger.warning("Could not hash %s — skipping dispatch", file_path)
            return

        # 4. Dry-run: log and return without touching Celery or the DB.
        if dry_run:
            logger.info("[dry-run] Would dispatch %s (hash=%s)", file_path, file_hash)
            return

        # 5. Lazy-import ingestion_pipeline. Gracefully degrade if not installed.
        try:
            from ingestion_pipeline.database import SessionLocal  # type: ignore[import-not-found]
            from ingestion_pipeline.models import IngestionLog  # type: ignore[import-not-found]
            from ingestion_pipeline.pipeline import trigger_ingest  # type: ignore[import-not-found]
        except ImportError:
            logger.warning(
                "ingestion_pipeline package not available — cannot dispatch %s", file_path
            )
            return

        try:
            session = SessionLocal()
            try:
                # 6. Idempotency check: skip files already successfully ingested.
                existing = session.get(IngestionLog, file_hash)
                if existing and existing.status == "success":
                    logger.debug("Already ingested (hash=%s): %s", file_hash, file_path)
                    return

                # 7. Upsert IngestionLog row with status="pending".
                if existing:
                    existing.status = "pending"
                    existing.filename = artifact.get("name", existing.filename)
                    existing.filepath = file_path
                    existing.error_message = None
                    existing.ingested_at = None
                else:
                    session.add(
                        IngestionLog(
                            file_hash=file_hash,
                            filename=artifact.get("name", ""),
                            filepath=file_path,
                            status="pending",
                        )
                    )
                session.commit()

                trigger_ingest(file_path, file_hash)
                logger.info("Dispatched %s (hash=%s)", file_path, file_hash)

            finally:
                session.close()

        except Exception as exc:
            logger.error("Dispatch failed for %s: %s", file_path, exc)
            raise

    return _dispatch
