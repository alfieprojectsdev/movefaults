"""
DA-002 scanner-hardening tests: corrupt-FAT gates, symlink non-traversal,
exclude globs, archive depth cap, clobber guard, skip itemization.
"""

import json
import os
import zipfile
from pathlib import Path

import pytest
from drive_archaeologist.classifier import Classifier
from drive_archaeologist.scanner import CORRUPT_CATEGORY, SYMLINK_CATEGORY, DeepScanner
from drive_archaeologist.utils.paths import is_suspect_name, sanitize_for_json, should_skip_path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_scan(root: Path, out: Path, **kwargs) -> DeepScanner:
    scanner = DeepScanner(root, output_file=out, **kwargs)
    scanner.scan()
    return scanner


# --- capacity sanity gate (finding #1) ---------------------------------------


def test_oversize_direntry_classified_corrupt_and_not_extracted(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    # a zip whose claimed size exceeds the injected fs capacity — must be
    # flagged corrupt and never opened
    bomb = root / "huge.zip"
    with zipfile.ZipFile(bomb, "w") as zf:
        zf.writestr("inner.txt", "x" * 2048)
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out, fs_capacity_bytes=100)
    records = {r["name"]: r for r in read_jsonl(out)}
    assert records["huge.zip"]["category"] == CORRUPT_CATEGORY
    assert records["huge.zip"]["corrupt_reason"] == "oversize_direntry"
    assert "inner.txt" not in records  # never extracted
    assert scanner.stats.corrupt_entries == 1
    assert scanner.stats.archives_extracted == 0


def test_claimed_sum_over_capacity_sets_inconsistent_flag(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "a.bin").write_bytes(b"x" * 600)
    (root / "b.bin").write_bytes(b"y" * 600)
    out = tmp_path / "out.jsonl"
    # each file fits capacity, the sum does not
    scanner = run_scan(root, out, fs_capacity_bytes=1000)
    assert scanner.stats.metadata_inconsistent is True


def test_sane_tree_not_flagged(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "a.txt").write_text("hello")
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out)
    assert scanner.stats.metadata_inconsistent is False
    assert scanner.stats.corrupt_entries == 0


# --- mojibake / undecodable names (finding #2) --------------------------------


def test_is_suspect_name():
    assert is_suspect_name("bad\x01name.txt")
    assert is_suspect_name("bad\udcffname")  # lone surrogate from undecodable bytes
    assert not is_suspect_name("ALGO0010.22O")
    assert not is_suspect_name("normál-ünïcode.txt")


def test_undecodable_filename_recorded_not_opened(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    fd = os.open(os.path.join(str(root).encode(), b"bad\xff.zip"), os.O_CREAT | os.O_WRONLY)
    os.write(fd, b"not really a zip")
    os.close(fd)
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out)
    records = read_jsonl(out)  # must not crash on the surrogate path
    assert len(records) == 1
    assert records[0]["category"] == CORRUPT_CATEGORY
    assert records[0]["corrupt_reason"] == "undecodable_name"
    assert scanner.stats.archives_seen == 0  # suspect entries are never opened


def test_sanitize_for_json_handles_surrogates():
    out = sanitize_for_json("bad\udcffname")
    assert "\\udcff" in out  # byte value preserved, string now UTF-8-safe
    out.encode("utf-8")  # must not raise
    assert sanitize_for_json("clean") == "clean"


# --- symlink gate (finding #8) -------------------------------------------------


def test_symlink_recorded_never_traversed(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("host filesystem file")
    root = tmp_path / "drive"
    root.mkdir()
    (root / "escape").symlink_to(outside)
    (root / "normal.txt").write_text("ok")
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out)
    records = {r["name"]: r for r in read_jsonl(out)}
    assert "secret.txt" not in records  # did NOT walk through the link
    assert records["escape"]["category"] == SYMLINK_CATEGORY
    assert records["escape"]["symlink_target"] == str(outside)
    assert scanner.stats.symlinks == 1


def test_symlink_loop_is_harmless(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "loop").symlink_to(root)
    (root / "file.txt").write_text("data")
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out)
    names = [r["name"] for r in read_jsonl(out)]
    assert names.count("file.txt") == 1  # no re-walk through the loop
    assert scanner.stats.symlinks == 1


# --- exclude globs (finding #5) ------------------------------------------------


def test_exclude_glob_skips_subtree(tmp_path):
    root = tmp_path / "drive"
    (root / "keep").mkdir(parents=True)
    (root / "junk").mkdir()
    (root / "keep" / "a.txt").write_text("a")
    (root / "junk" / "b.txt").write_text("b")
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out, excludes=["junk"])
    names = [r["name"] for r in read_jsonl(out)]
    assert "a.txt" in names
    assert "b.txt" not in names
    assert scanner.stats.excluded_count == 1
    assert scanner.stats.excluded_roots  # itemized


# --- hidden/system skip visibility (finding #7) --------------------------------


def test_hidden_skipped_by_default_but_itemized(tmp_path):
    root = tmp_path / "drive"
    (root / ".Trash-1000").mkdir(parents=True)
    (root / ".Trash-1000" / "movie.mkv").write_text("x")
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out)
    assert read_jsonl(out) == []
    assert scanner.skipped_count == 1
    assert any(".Trash-1000" in r for r in scanner.stats.skipped_roots)


def test_include_hidden_scans_trash(tmp_path):
    root = tmp_path / "drive"
    (root / ".Trash-1000").mkdir(parents=True)
    (root / ".Trash-1000" / "movie.mkv").write_text("x")
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out, include_hidden=True)
    names = [r["name"] for r in read_jsonl(out)]
    assert "movie.mkv" in names
    assert scanner.skipped_count == 0


def test_should_skip_path_include_hidden_flag():
    assert should_skip_path(Path("/d/.hidden"))
    assert not should_skip_path(Path("/d/.hidden"), include_hidden=True)
    assert should_skip_path(Path("/d/$RECYCLE.BIN/f"))
    assert not should_skip_path(Path("/d/$RECYCLE.BIN/f"), include_hidden=True)


# --- archive depth cap (finding #9) ---------------------------------------------


def _nested_zip(root: Path) -> Path:
    inner = root / "inner.zip"
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr("deep.txt", "bottom")
    outer = root / "outer.zip"
    with zipfile.ZipFile(outer, "w") as zf:
        zf.write(inner, "inner.zip")
    inner.unlink()
    return outer


def test_archive_depth_cap(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    _nested_zip(root)
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out, max_archive_depth=1)
    names = [r["name"] for r in read_jsonl(out)]
    assert "inner.zip" in names  # cataloged
    assert "deep.txt" not in names  # but not extracted past the cap
    assert scanner.stats.archives_depth_capped == 1


def test_archive_depth_zero_never_extracts(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    zip_path = root / "top.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("member.txt", "x")
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out, max_archive_depth=0)
    names = [r["name"] for r in read_jsonl(out)]
    assert "top.zip" in names
    assert "member.txt" not in names
    assert scanner.stats.archives_extracted == 0


# --- clobber guard (finding #10) -------------------------------------------------


def test_existing_output_refused_without_force(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "a.txt").write_text("a")
    out = tmp_path / "out.jsonl"
    out.write_text("precious previous survey\n")
    with pytest.raises(FileExistsError):
        DeepScanner(root, output_file=out).scan()
    assert out.read_text() == "precious previous survey\n"  # untouched


def test_existing_output_overwritten_with_force(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "a.txt").write_text("a")
    out = tmp_path / "out.jsonl"
    out.write_text("old\n")
    run_scan(root, out, force=True)
    assert [r["name"] for r in read_jsonl(out)] == ["a.txt"]


# --- cross-link / hardlink duplicates (finding #3) --------------------------------


def test_hardlink_duplicate_marked_not_reextracted(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    first = root / "a_data.zip"
    with zipfile.ZipFile(first, "w") as zf:
        zf.writestr("member.txt", "x")
    os.link(first, root / "b_link.zip")
    out = tmp_path / "out.jsonl"
    scanner = run_scan(root, out)
    records = read_jsonl(out)
    dups = [r for r in records if r.get("hardlink_dup")]
    assert len(dups) == 1
    assert scanner.stats.hardlink_dups == 1
    # the shared inode was extracted exactly once
    assert sum(1 for r in records if r["name"] == "member.txt") == 1


# --- classifier RINEX fallback -----------------------------------------------------


def test_classifier_rinex_regex_fallback():
    c = Classifier()
    assert c.classify(Path("PPPP0010.23o")) == "GNSS Data"  # year past profile list
    assert c.classify(Path("algo1150.05d")) == "GNSS Data"  # Hatanaka, legacy year
    assert c.classify(Path("site001a.99n")) == "GNSS Data"
    assert c.classify(Path("ALGO0010.22O")) == "GNSS Data"  # still via ext map
    assert c.classify(Path("notrinex.23x")) is None
    assert c.classify(Path("toolongname0010.23o")) is None
