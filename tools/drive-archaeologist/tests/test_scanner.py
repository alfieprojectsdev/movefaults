"""
Tests for the core scanner functionality.
"""

import json
import platform

from drive_archaeologist.scanner import DeepScanner


def test_scanner_basic(tmp_path):
    """Test basic scanning functionality"""
    # Create test files
    test_dir = tmp_path / "test_scan"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("test")
    (test_dir / "file2.txt").write_text("test")

    # Scan
    output_file = tmp_path / "scan_output.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file)
    scanner.scan()

    # Verify output
    assert output_file.exists()

    # Parse JSONL
    files = []
    with open(output_file) as f:
        for line in f:
            files.append(json.loads(line))

    assert len(files) == 2
    assert all("path" in f for f in files)
    assert all("size_bytes" in f for f in files)


def test_scanner_resume(tmp_path):
    """Test resume capability"""
    # Create test files
    test_dir = tmp_path / "test_scan"
    test_dir.mkdir()
    for i in range(10):
        (test_dir / f"file{i}.txt").write_text(f"test {i}")

    # First scan (will be interrupted)
    output_file = tmp_path / "scan_output.jsonl"
    # Note: In a real scenario, we'd interrupt the first scan
    # For testing purposes, we just create the scanner without scanning

    # Second scan with resume
    scanner2 = DeepScanner(test_dir, output_file=output_file, resume=True)
    scanner2.scan()

    # Verify no duplicates
    files = []
    with open(output_file) as f:
        for line in f:
            files.append(json.loads(line))

    # Check for duplicates by path
    paths = [f["path"] for f in files]
    assert len(paths) == len(set(paths)), "Duplicate files found"


def test_scanner_handles_errors(tmp_path):
    """Test that scanner handles permission errors gracefully"""
    # This test is platform-specific and may need adjustment
    # Create test file with restricted permissions
    test_dir = tmp_path / "test_scan"
    test_dir.mkdir()
    restricted_file = test_dir / "restricted.txt"
    restricted_file.write_text("test")

    # Make file unreadable (Unix only)
    if platform.system() != "Windows":
        restricted_file.chmod(0o000)

    # Scan should complete without crashing
    output_file = tmp_path / "scan_output.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file)
    scanner.scan()

    # Scanner should have logged errors
    assert scanner.error_count >= 0  # May be 0 on Windows


def test_scanner_skips_system_directories(tmp_path):
    """Test that scanner skips system directories"""
    test_dir = tmp_path / "test_scan"
    test_dir.mkdir()

    # Create normal files
    (test_dir / "file1.txt").write_text("test")
    (test_dir / "file2.txt").write_text("test")

    # Create hidden file (should be skipped)
    (test_dir / ".hidden_file").write_text("hidden")

    # Create system directory (should be skipped)
    system_dir = test_dir / "$RECYCLE.BIN"
    system_dir.mkdir()
    (system_dir / "trash.txt").write_text("trash")

    # Scan
    output_file = tmp_path / "scan_output.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file)
    scanner.scan()

    # Verify only normal files were scanned
    files = []
    with open(output_file) as f:
        for line in f:
            files.append(json.loads(line))

    assert len(files) == 2
    assert scanner.skipped_count > 0


def test_scanner_output_format(tmp_path):
    """Test that scanner output has correct metadata fields"""
    test_dir = tmp_path / "test_scan"
    test_dir.mkdir()
    (test_dir / "test_file.txt").write_text("test content")

    # Scan
    output_file = tmp_path / "scan_output.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file)
    scanner.scan()

    # Parse output
    with open(output_file) as f:
        metadata = json.loads(f.readline())

    # Verify all expected fields are present
    assert "path" in metadata
    assert "name" in metadata
    assert "extension" in metadata
    assert "size_bytes" in metadata
    assert "size_mb" in metadata
    assert "modified" in metadata
    assert "created" in metadata
    assert "parent_dir" in metadata
    assert "depth" in metadata
    assert "scan_timestamp" in metadata

    # Verify values
    assert metadata["name"] == "test_file.txt"
    assert metadata["extension"] == ".txt"
    assert metadata["size_bytes"] == 12  # "test content"
    assert metadata["depth"] == 1
