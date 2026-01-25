"""
Tests for checkpoint manager functionality.
"""

from pathlib import Path

from drive_archaeologist.utils.checkpoint import CheckpointManager


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
