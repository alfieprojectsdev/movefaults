import logging
import shutil
import os
from datetime import datetime

logger = logging.getLogger(__name__)

ARCHIVE_DIR = os.getenv("ARCHIVE_DIR", "/data/archive")

def load_rinex_file(file_path: str, file_hash: str) -> str:
    """
    Load file to archive and update DB.
    Returns new path in archive.
    """
    if not os.path.exists(ARCHIVE_DIR):
        os.makedirs(ARCHIVE_DIR, exist_ok=True)

    filename = os.path.basename(file_path)
    dest_path = os.path.join(ARCHIVE_DIR, filename)

    # Check if dest already exists, if so overwrite or skip?
    # Idempotency check should have prevented this, but let's be safe.
    if os.path.exists(dest_path):
        logger.warning(f"File {dest_path} already exists, overwriting.")

    shutil.move(file_path, dest_path)
    logger.info(f"Moved {file_path} to {dest_path}")

    return dest_path
