"""
FileScanner — discovers GNSS/RINEX files and queues them for ingestion.

Walks a directory tree, identifies RINEX observation files by extension,
hashes each file (SHA-256), performs an idempotency check against
ingestion_logs, and triggers the Celery pipeline chain for new or
previously-failed files.

RINEX extensions recognised:
  .rnx              — RINEX 3.x observation
  .crx              — Hatanaka-compressed RINEX 3.x
  .gz, .zip, .Z     — compressed wrappers (may contain any of the above)
  .??o, .??d        — RINEX 2.x observation / Hatanaka (yy + single char)
"""

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path

from .database import SessionLocal
from .models import IngestionLog
from .pipeline import trigger_ingest

# RINEX 2.x obs suffix pattern: two-digit year + 'o' (obs) or 'd' (Hatanaka)
_EXPLICIT_EXTENSIONS = {".rnx", ".crx", ".gz", ".zip"}
_COMPRESSED_SUFFIX = ".Z"


def _is_rinex_file(filename: str) -> bool:
    """
    Returns True for files that are likely RINEX observation data.

    RINEX 2.x filenames follow the pattern: SSSSdddh.yyo / SSSSdddh.yyd
    where yy is the two-digit year and the last char is 'o' (obs) or 'd' (Hatanaka).
    We use a loose suffix check consistent with the original scanner.
    """
    path = Path(filename)
    suffix = path.suffix.lower()

    if suffix in _EXPLICIT_EXTENSIONS:
        return True
    if suffix == _COMPRESSED_SUFFIX:
        return True
    # RINEX 2.x: .??o or .??d  (e.g. .23o, .20d)
    # Path.suffix includes the dot → ".23o" has len 4: dot + two year digits + obs/hatanaka char
    if len(suffix) == 4 and suffix[1:3].isdigit() and suffix[3] in "od":
        return True
    return False


def _sha256(file_path: str) -> str | None:
    """SHA-256 hash of file contents, chunked for large files."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


class FileScanner:
    """
    Walks root_directory, hashes each RINEX file, and triggers the
    ingestion pipeline for files not yet successfully ingested.

    Idempotency: a file with status='success' in ingestion_logs is skipped.
    Failed files (status='failed') are re-queued automatically.
    """

    def __init__(self, root_directory: str):
        self.root_directory = root_directory

    def scan(self) -> dict:
        """
        Execute the scan. Returns a summary dict with counts:
            queued, skipped, errors
        """
        counts = {"queued": 0, "skipped": 0, "errors": 0}
        session = SessionLocal()

        try:
            for root, _dirs, files in os.walk(self.root_directory):
                for filename in sorted(files):
                    if not _is_rinex_file(filename):
                        continue

                    filepath = os.path.join(root, filename)
                    file_hash = _sha256(filepath)

                    if file_hash is None:
                        print(f"ERROR: cannot read {filepath}")
                        counts["errors"] += 1
                        continue

                    existing = session.get(IngestionLog, file_hash)

                    if existing and existing.status == "success":
                        print(f"SKIP  {filename} (already ingested)")
                        counts["skipped"] += 1
                        continue

                    print(f"QUEUE {filename}")

                    if existing:
                        # Re-queue a previously failed attempt
                        existing.status = "pending"
                        existing.queued_at = datetime.now(timezone.utc)
                        existing.error_message = None
                    else:
                        session.add(IngestionLog(
                            file_hash=file_hash,
                            filename=filename,
                            filepath=filepath,
                            status="pending",
                        ))

                    session.commit()
                    trigger_ingest(filepath, file_hash)
                    counts["queued"] += 1

        finally:
            session.close()

        return counts


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        scanner = FileScanner(sys.argv[1])
        result = scanner.scan()
        print(f"\nDone — queued: {result['queued']}, skipped: {result['skipped']}, errors: {result['errors']}")
    else:
        print("Usage: python -m ingestion_pipeline.scanner <directory>")
