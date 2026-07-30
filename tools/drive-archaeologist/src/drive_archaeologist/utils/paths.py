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


def should_skip_path(path: Path, include_hidden: bool = False) -> bool:
    """
    Determine if a path should be skipped during scanning.

    Args:
        path: Path to check
        include_hidden: When True, do not skip hidden (dot-prefixed) or
            system entries. Skipping them silently hides real content —
            a drive whose only files live in .Trash-1000 would otherwise
            survey as empty (DA-002 finding #7).

    Returns:
        True if path should be skipped, False otherwise
    """
    if include_hidden:
        return False

    # Skip system directories
    for part in path.parts:
        if part in SYSTEM_DIRECTORIES:
            return True

    # Skip hidden files on Unix (starting with .)
    # But don't skip . and .. for directory traversal
    if path.name.startswith(".") and path.name not in {".", ".."}:
        return True

    return False


def is_suspect_name(name: str) -> bool:
    """
    Detect filenames that indicate filesystem corruption (DA-002 finding #2).

    Corrupt FAT directory entries surface as mojibake: bytes that do not
    decode as UTF-8 (Python exposes them as lone surrogates) or embedded
    C0 control characters. Such entries must never be opened or extracted.
    """
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return True
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in name)


def sanitize_for_json(text: str) -> str:
    """
    Sanitize a string so it can be written to a UTF-8 JSONL stream.

    Paths from corrupt filesystems can contain lone surrogates (undecodable
    bytes); writing those to a UTF-8 file raises UnicodeEncodeError and the
    record is lost. backslashreplace keeps the raw byte values visible
    (e.g. ``\\udcff``) so corrupt names stay forensically identifiable.
    """
    return text.encode("utf-8", errors="backslashreplace").decode("utf-8")


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
