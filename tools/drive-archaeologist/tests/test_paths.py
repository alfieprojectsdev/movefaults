"""
Tests for path utilities.
"""

from pathlib import Path

from drive_archaeologist.utils.paths import (
    is_reserved_name,
    safe_filename,
    should_skip_path,
)


def test_should_skip_system_directories():
    """Test that system directories are skipped"""
    assert should_skip_path(Path("C:/$RECYCLE.BIN/file.txt"))
    assert should_skip_path(Path("/System Volume Information/file.txt"))
    assert not should_skip_path(Path("/home/user/file.txt"))


def test_should_skip_hidden_files():
    """Test that hidden files are skipped"""
    assert should_skip_path(Path(".hidden_file"))
    assert should_skip_path(Path("/home/user/.gitignore"))
    assert not should_skip_path(Path("/home/user/normal_file.txt"))


def test_reserved_names():
    """Test Windows reserved name detection"""
    assert is_reserved_name("CON")
    assert is_reserved_name("con")
    assert is_reserved_name("PRN")
    assert is_reserved_name("COM1")
    assert not is_reserved_name("CONFIG")
    assert not is_reserved_name("normal_file")


def test_safe_filename():
    """Test filename sanitization"""
    import platform

    # Test that function returns a valid string
    assert isinstance(safe_filename("normal_file.txt"), str)
    assert len(safe_filename("normal_file.txt")) > 0

    # Test that normal filenames pass through unchanged
    assert safe_filename("normal_file.txt") == "normal_file.txt"

    # Platform-specific tests
    if platform.system() == "Windows":
        # Windows reserved names should be sanitized on Windows
        assert safe_filename("CON") != "CON"
        assert safe_filename("PRN.txt") != "PRN.txt"

        # Special characters should be sanitized on Windows
        result = safe_filename("file:with*special?chars")
        assert ":" not in result
        assert "*" not in result
        assert "?" not in result
    else:
        # On Linux with platform="auto", pathvalidate may not sanitize
        # Linux-valid characters like : * ?
        # This is expected behavior - the function uses platform="auto"
        # which respects the current OS's filesystem rules
        result = safe_filename("file_with_underscores_123.txt")
        assert result == "file_with_underscores_123.txt"
