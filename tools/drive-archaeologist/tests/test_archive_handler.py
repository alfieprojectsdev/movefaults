import zipfile
from pathlib import Path

from drive_archaeologist.archive_handler import ArchiveHandler


def test_extract_zip(tmp_path):
    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("hello.txt", "content")
    handler = ArchiveHandler()
    result = handler.extract(zip_path)
    assert result is not None
    assert (result / "hello.txt").exists()


def test_rar_missing_dep_returns_none_not_raises(tmp_path):
    # If rarfile not installed, must return None rather than raising ImportError
    fake_rar = tmp_path / "test.rar"
    fake_rar.write_bytes(b"Rar!\x1a\x07\x00")
    handler = ArchiveHandler()
    import sys
    original = sys.modules.get("rarfile", "NOT_SET")
    sys.modules["rarfile"] = None  # simulate missing package
    try:
        result = handler.extract(fake_rar)
        assert result is None, "extract() must return None when rarfile dep is missing"
    except ImportError as exc:
        raise AssertionError("extract() must not propagate ImportError for missing rarfile") from exc
    finally:
        if original == "NOT_SET":
            del sys.modules["rarfile"]
        else:
            sys.modules["rarfile"] = original


def test_7z_missing_dep_returns_none_not_raises(tmp_path):
    fake_7z = tmp_path / "test.7z"
    fake_7z.write_bytes(b"7z\xbc\xaf'\x1c")
    handler = ArchiveHandler()
    import sys
    original = sys.modules.get("py7zr", "NOT_SET")
    sys.modules["py7zr"] = None
    try:
        result = handler.extract(fake_7z)
        assert result is None, "extract() must return None when py7zr dep is missing"
    except ImportError as exc:
        raise AssertionError("extract() must not propagate ImportError for missing py7zr") from exc
    finally:
        if original == "NOT_SET":
            del sys.modules["py7zr"]
        else:
            sys.modules["py7zr"] = original


def test_is_archive_detection():
    h = ArchiveHandler()
    assert h.is_archive(Path("file.zip")) is True
    assert h.is_archive(Path("file.tar.gz")) is True
    assert h.is_archive(Path("file.7z")) is True
    assert h.is_archive(Path("file.rar")) is True
    assert h.is_archive(Path("file.txt")) is False
    assert h.is_archive(Path("file.rnx")) is False
