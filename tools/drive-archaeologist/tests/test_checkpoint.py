"""
Tests for checkpoint manager functionality.

DA-005b-1: storage is an append-only log (one JSON string per line) so that
multi-hour scans append O(1) per file instead of rewriting the full path set
every 1000 files. Public API is unchanged from the JSON era.
"""

import json
from pathlib import Path

from drive_archaeologist.utils.checkpoint import _BATCH_SIZE, CheckpointManager


def test_append_only_log_format(tmp_path):
    """Storage is one JSON string per line — appendable, greppable, wc -l-able."""
    cp = CheckpointManager("scan", checkpoint_dir=tmp_path)
    cp.mark_scanned(Path("/a/one.22o"))
    cp.mark_scanned(Path("/a/two.22o"))
    cp.save_checkpoint()
    lines = cp.checkpoint_file.read_text().splitlines()
    assert len(lines) == 2
    assert all(isinstance(json.loads(line), str) for line in lines)


def test_save_appends_instead_of_rewriting(tmp_path):
    """A later save must not rewrite earlier entries (the whole point)."""
    cp = CheckpointManager("scan", checkpoint_dir=tmp_path)
    cp.mark_scanned(Path("/a/one.22o"))
    cp.save_checkpoint()
    first_size = cp.checkpoint_file.stat().st_size
    cp.mark_scanned(Path("/a/two.22o"))
    cp.save_checkpoint()
    content = cp.checkpoint_file.read_text()
    assert cp.checkpoint_file.stat().st_size > first_size
    assert content.startswith(json.dumps(str(Path("/a/one.22o").absolute())))


def test_batch_autoflush_bounds_crash_loss(tmp_path):
    """Without any explicit save, a full batch is already durable — a crash
    loses at most one batch, which resume simply re-scans."""
    cp = CheckpointManager("scan", checkpoint_dir=tmp_path)
    for i in range(_BATCH_SIZE + 50):
        cp.mark_scanned(Path(f"/a/file{i:04}.22o"))
    # No save_checkpoint(): simulate crash by just reopening
    survivor = CheckpointManager("scan", checkpoint_dir=tmp_path)
    assert len(survivor.scanned_paths) == _BATCH_SIZE  # first batch flushed


def test_partial_last_line_after_crash_is_skipped(tmp_path):
    cp = CheckpointManager("scan", checkpoint_dir=tmp_path)
    cp.mark_scanned(Path("/a/good.22o"))
    cp.save_checkpoint()
    with open(cp.checkpoint_file, "a", encoding="utf-8") as f:
        f.write('"/a/trunc')  # torn write, no newline, invalid JSON
    survivor = CheckpointManager("scan", checkpoint_dir=tmp_path)
    assert survivor.is_scanned(Path("/a/good.22o"))
    assert len(survivor.scanned_paths) == 1


def test_path_with_newline_stays_one_line(tmp_path):
    """Corrupt-FS filenames can embed newlines; JSON escaping keeps the log
    line-oriented regardless."""
    cp = CheckpointManager("scan", checkpoint_dir=tmp_path)
    weird = Path("/a/evil\nname.22o")
    cp.mark_scanned(weird)
    cp.save_checkpoint()
    assert len(cp.checkpoint_file.read_text().splitlines()) == 1
    survivor = CheckpointManager("scan", checkpoint_dir=tmp_path)
    assert survivor.is_scanned(weird)


def test_legacy_json_checkpoint_migrates_once(tmp_path):
    legacy = tmp_path / "checkpoint_scan.json"
    legacy.write_text(
        json.dumps({"scan_id": "scan", "scanned_paths": ["/old/a.22o", "/old/b.22o"]})
    )
    cp = CheckpointManager("scan", checkpoint_dir=tmp_path)
    assert cp.is_scanned(Path("/old/a.22o"))
    assert not legacy.exists()  # converted and removed
    assert cp.checkpoint_file.exists()
    # Second open reads the log, no legacy left to re-migrate
    again = CheckpointManager("scan", checkpoint_dir=tmp_path)
    assert again.is_scanned(Path("/old/b.22o"))


def test_cleanup_removes_log_and_legacy(tmp_path):
    (tmp_path / "checkpoint_scan.json").write_text("not valid json {")
    cp = CheckpointManager("scan", checkpoint_dir=tmp_path)
    cp.mark_scanned(Path("/a/one.22o"))
    cp.save_checkpoint()
    cp.cleanup()
    assert not cp.checkpoint_file.exists()
    assert not (tmp_path / "checkpoint_scan.json").exists()


def test_checkpoint_save_load(tmp_path):
    """Test checkpoint save and load"""
    # Change to tmp directory to avoid polluting project
    import os

    original_dir = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Create checkpoint manager
        checkpoint = CheckpointManager("test_scan")

        # Mark some files as scanned
        test_file1 = Path("/test/file1.txt")
        test_file2 = Path("/test/file2.txt")
        checkpoint.mark_scanned(test_file1)
        checkpoint.mark_scanned(test_file2)

        # Save checkpoint
        checkpoint.save_checkpoint()

        # Create new manager with same scan_id (should load checkpoint)
        checkpoint2 = CheckpointManager("test_scan")

        # Verify files are marked as scanned
        assert checkpoint2.is_scanned(test_file1)
        assert checkpoint2.is_scanned(test_file2)
        assert not checkpoint2.is_scanned(Path("/test/file3.txt"))

        # Cleanup
        checkpoint2.cleanup()
    finally:
        os.chdir(original_dir)


def test_checkpoint_corrupted(tmp_path):
    """Test handling of corrupted checkpoint files"""
    import os

    original_dir = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Create corrupted checkpoint file
        checkpoint_file = Path("checkpoint_test_scan.json")
        checkpoint_file.write_text("not valid json {")

        # Create manager - should handle corruption gracefully
        checkpoint = CheckpointManager("test_scan")

        # Should start with empty scanned_paths
        assert len(checkpoint.scanned_paths) == 0

        # Cleanup
        checkpoint.cleanup()
    finally:
        os.chdir(original_dir)


def test_checkpoint_cleanup(tmp_path):
    """Test checkpoint cleanup"""
    import os

    original_dir = os.getcwd()
    os.chdir(tmp_path)

    try:
        # Create checkpoint manager
        checkpoint = CheckpointManager("test_scan")
        checkpoint.mark_scanned(Path("/test/file1.txt"))
        checkpoint.save_checkpoint()

        # Verify checkpoint file exists
        assert checkpoint.checkpoint_file.exists()

        # Cleanup
        checkpoint.cleanup()

        # Verify checkpoint file is removed
        assert not checkpoint.checkpoint_file.exists()
    finally:
        os.chdir(original_dir)


def test_checkpoint_no_duplicates(tmp_path):
    """Test that checkpoint prevents duplicate entries"""
    import os

    original_dir = os.getcwd()
    os.chdir(tmp_path)

    try:
        checkpoint = CheckpointManager("test_scan")

        # Mark same file multiple times
        test_file = Path("/test/file1.txt")
        checkpoint.mark_scanned(test_file)
        checkpoint.mark_scanned(test_file)
        checkpoint.mark_scanned(test_file)

        # Should only have one entry
        assert len(checkpoint.scanned_paths) == 1

        # Cleanup
        checkpoint.cleanup()
    finally:
        os.chdir(original_dir)
