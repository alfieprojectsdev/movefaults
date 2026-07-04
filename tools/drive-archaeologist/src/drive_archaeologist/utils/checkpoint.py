"""
Checkpoint manager for resume capability.
Tracks which files have been scanned to enable resuming interrupted scans.

Storage (DA-005b-1) is an append-only log — `checkpoint_<scan_id>.log`, one
JSON-encoded path per line — so checkpointing costs O(1) per file. The old
format rewrote the entire path set as JSON on every save: at NAS scale
(millions of files) that rewrite dominates the scan itself. JSON-encoding
each line keeps the log line-oriented even when corrupt filesystems produce
filenames containing newlines.

Durability model: paths are appended in batches of _BATCH_SIZE; a crash loses
at most one unflushed batch, which a resumed scan simply re-walks. A torn
final line (crash mid-write) is skipped on load.
"""

import json
from pathlib import Path

# Paths buffered before an append+flush. Small enough that a crash re-scans
# a negligible tail; large enough that open/append cost is amortized.
_BATCH_SIZE = 100


class CheckpointManager:
    """
    Manages checkpoint files for scan resume capability.

    Saves progress incrementally so scans can be resumed if interrupted.
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
        self.checkpoint_file = base / f"checkpoint_{scan_id}.log"
        self._legacy_file = base / f"checkpoint_{scan_id}.json"
        self.scanned_paths: set[str] = set()
        self._pending: list[str] = []

        if self.checkpoint_file.exists():
            self._load_log()
        if self._legacy_file.exists():
            self._migrate_legacy()

    def _load_log(self):
        """Load the append-only log; skip torn/corrupt lines instead of dying."""
        try:
            with open(self.checkpoint_file, encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        self.scanned_paths.add(json.loads(line))
                    except json.JSONDecodeError:
                        # Torn write from a crash — the path wasn't durably
                        # recorded, so resume will just re-scan it
                        continue
        except OSError:
            self.scanned_paths = set()

    def _migrate_legacy(self):
        """One-time conversion of a pre-DA-005b-1 JSON checkpoint."""
        try:
            with open(self._legacy_file, encoding="utf-8") as f:
                legacy_paths = set(json.load(f).get("scanned_paths", []))
        except Exception:
            # Corrupted legacy checkpoint: same behavior as before — start fresh
            return
        new = legacy_paths - self.scanned_paths
        if new:
            self.scanned_paths |= new
            self._append(sorted(new))
        self._legacy_file.unlink(missing_ok=True)

    def _append(self, paths: list[str]):
        with open(self.checkpoint_file, "a", encoding="utf-8") as f:
            for path in paths:
                f.write(json.dumps(path, ensure_ascii=False) + "\n")
            f.flush()

    def mark_scanned(self, path: Path):
        """Mark a file as scanned"""
        key = str(path.absolute())
        if key in self.scanned_paths:
            return
        self.scanned_paths.add(key)
        self._pending.append(key)
        if len(self._pending) >= _BATCH_SIZE:
            self.save_checkpoint()

    def save_checkpoint(self):
        """Flush buffered paths to the log (appends; never rewrites)."""
        if not self._pending:
            return
        self._append(self._pending)
        self._pending.clear()

    def is_scanned(self, path: Path) -> bool:
        """Check if a file has already been scanned"""
        return str(path.absolute()) in self.scanned_paths

    def cleanup(self):
        """Remove checkpoint files (log and any legacy JSON)"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
        self._legacy_file.unlink(missing_ok=True)
