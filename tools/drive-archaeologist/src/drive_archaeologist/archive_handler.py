"""
Handles archive extraction for nested scanning.
Uses a combination of standard library and third-party modules.
"""

import tarfile
import zipfile
import tempfile
from pathlib import Path
from typing import List, Optional

import py7zr
import rarfile

# Supported archive extensions
SUPPORTED_ARCHIVES = [
    ".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".xz", ".txz", ".7z", ".rar"
]


class ArchiveHandler:
    """
    Detects and extracts various archive formats to a temporary directory.
    """

    def __init__(self, temp_base_dir: Optional[Path] = None):
        """
        Initializes the handler.

        Args:
            temp_base_dir: An optional base directory for temporary extraction folders.
                           If None, the system's default temporary directory is used.
        """
        self.temp_base_dir = temp_base_dir

    def is_archive(self, filepath: Path) -> bool:
        """
        Check if a file is a supported archive format based on its extension.
        """
        # Handle multi-part extensions like .tar.gz
        for ext in SUPPORTED_ARCHIVES:
            if str(filepath).lower().endswith(ext):
                return True
        return False

    def extract(self, filepath: Path) -> Optional[Path]:
        """
        Extracts an archive to a new temporary directory.

        Args:
            filepath: The path to the archive file.

        Returns:
            The path to the temporary directory where files were extracted, or None on failure.
        """
        if not self.is_archive(filepath):
            return None

        # Create a unique temporary directory for this archive's contents
        try:
            temp_dir = tempfile.mkdtemp(prefix=f"da_{filepath.name}_", dir=self.temp_base_dir)
            temp_path = Path(temp_dir)
        except Exception:
            return None # Could not create temp directory

        try:
            lower_path = str(filepath).lower()
            if lower_path.endswith(".zip"):
                with zipfile.ZipFile(filepath, 'r') as zf:
                    zf.extractall(temp_path)
            elif lower_path.endswith(".rar"):
                # rarfile requires the 'unrar' command-line utility.
                # It will raise an exception if it's not found.
                with rarfile.RarFile(filepath, 'r') as rf:
                    rf.extractall(temp_path)
            elif lower_path.endswith(".7z"):
                with py7zr.SevenZipFile(filepath, 'r') as szf:
                    szf.extractall(temp_path)
            elif ".tar" in lower_path or lower_path.endswith(("tgz", "tbz2", "txz")):
                # The tarfile module can handle most common tar compressions
                with tarfile.open(filepath, 'r:*') as tf:
                    tf.extractall(temp_path)
            else:
                # Simple compression formats like .gz that aren't tarballs.
                # This logic is more complex as they usually wrap a single file.
                # For now, we are focusing on multi-file archives.
                return None

            return temp_path

        except Exception:
            # This can fail for many reasons: corrupt file, password protected,
            # missing backend (like unrar), etc.
            # We will log this in the scanner, for now, just clean up and return None.
            self._cleanup(temp_path)
            return None

    def _cleanup(self, temp_path: Path):
        """
        Recursively remove the temporary extraction directory.
        """
        if not temp_path or not temp_path.is_dir():
            return
        try:
            for item in temp_path.iterdir():
                if item.is_dir():
                    self._cleanup(item)
                else:
                    item.unlink()
            temp_path.rmdir()
        except Exception:
            # Log this error from the scanner
            pass