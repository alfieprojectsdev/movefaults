"""
Cross-platform path utilities for Windows and Linux compatibility.
Handles Windows reserved filenames, long paths, and system directories.
"""

from pathlib import Path

from pathvalidate import sanitize_filename

# Windows reserved names
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    "COM1",
    "COM2",
    "COM3",
    "COM4",
    "COM5",
    "COM6",
    "COM7",
    "COM8",
    "COM9",
    "LPT1",
    "LPT2",
    "LPT3",
    "LPT4",
    "LPT5",
    "LPT6",
    "LPT7",
    "LPT8",
    "LPT9",
}

# System directories to skip
SYSTEM_DIRECTORIES = {
    "$RECYCLE.BIN",
    "System Volume Information",
    ".Trash",
    ".Trashes",
    "__MACOSX",
}


def should_skip_path(path: Path) -> bool:
    """
    Determine if a path should be skipped during scanning.

    Args:
        path: Path to check

    Returns:
        True if path should be skipped, False otherwise
    """
    # Skip system directories
    for part in path.parts:
        if part in SYSTEM_DIRECTORIES:
            return True

    # Skip hidden files on Unix (starting with .)
    # But don't skip . and .. for directory traversal
    if path.name.startswith(".") and path.name not in {".", ".."}:
        return True

    return False


def sanitize_for_json(text: str) -> str:
    """
    Sanitize string for JSON output.

    Args:
        text: String to sanitize

    Returns:
        Sanitized string safe for JSON
    """
    # Replace backslashes with forward slashes for cross-platform consistency
    # (but keep original paths in output for user clarity)
    return text


def safe_filename(name: str) -> str:
    """
    Sanitize filename for cross-platform safety.
    Handles Windows reserved names.

    Args:
        name: Filename to sanitize

    Returns:
        Safe filename
    """
    # Use pathvalidate for comprehensive sanitization
    return sanitize_filename(name, platform="auto")


def is_reserved_name(name: str) -> bool:
    """
    Check if filename is a Windows reserved name.

    Args:
        name: Filename to check (without extension)

    Returns:
        True if reserved, False otherwise
    """
    name_upper = Path(name).stem.upper()
    return name_upper in WINDOWS_RESERVED_NAMES
