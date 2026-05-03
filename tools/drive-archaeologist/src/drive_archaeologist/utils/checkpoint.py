"""
Checkpoint manager for resume capability.
Tracks which files have been scanned to enable resuming interrupted scans.
"""

import json
from pathlib import Path


class CheckpointManager:
    """
    Manages checkpoint files for scan resume capability.

    Saves progress periodically so scans can be resumed if interrupted.
    """

    def __init__(self, scan_id: str, checkpoint_dir: Path | None = None):
        """
        Initialize checkpoint manager.

        Args:
            scan_id: Unique identifier for this scan
            checkpoint_dir: Directory to store the checkpoint file. Defaults to CWD.
        """
        self.scan_id = scan_id
        base = Path(checkpoint_dir) if checkpoint_dir else Path(".")
        self.checkpoint_file = base / f"checkpoint_{scan_id}.json"
        self.scanned_paths: set[str] = set()

        if self.checkpoint_file.exists():
            self._load_checkpoint()

    def _load_checkpoint(self):
        """Load checkpoint from disk"""
        try:
            with open(self.checkpoint_file, encoding="utf-8") as f:
                data = json.load(f)
                self.scanned_paths = set(data.get("scanned_paths", []))
        except Exception:
            # If checkpoint is corrupted, start fresh
            self.scanned_paths = set()

    def mark_scanned(self, path: Path):
        """Mark a file as scanned"""
        self.scanned_paths.add(str(path.absolute()))

    def save_checkpoint(self):
        """Save current progress to disk"""
        data = {
            "scan_id": self.scan_id,
            "scanned_paths": list(self.scanned_paths),
            "total_files": len(self.scanned_paths),
        }

        with open(self.checkpoint_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def is_scanned(self, path: Path) -> bool:
        """Check if a file has already been scanned"""
        return str(path.absolute()) in self.scanned_paths

    def cleanup(self):
        """Remove checkpoint file"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
