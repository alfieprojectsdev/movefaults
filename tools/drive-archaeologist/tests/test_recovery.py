"""
DA-006 recovery tests: $I metadata parsing, $R/$I pairing into a recovery
manifest, and the idempotent manifest-copy executor. Fixtures build synthetic
$RECYCLE.BIN trees in tmp_path — no real drives, nothing destructive.
"""

import json
import struct
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner
from drive_archaeologist.cli import main
from drive_archaeologist.recovery import (
    RecycleBinError,
    copy_from_manifest,
    pair_recycle_bin,
    parse_dollar_i,
    windows_path_to_rel,
)

FILETIME_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)


def make_dollar_i(original_path: str, version: int = 2, size: int = 1234) -> bytes:
    """Build a synthetic $I blob (version 1: Vista/7 fixed path; 2: Win10+)."""
    deleted = datetime(2021, 8, 13, 11, 22, 43, tzinfo=UTC)
    filetime = int((deleted - FILETIME_EPOCH).total_seconds() * 10_000_000)
    head = struct.pack("<qqq", version, size, filetime)
    encoded = original_path.encode("utf-16-le")
    if version == 1:
        return head + encoded + b"\x00" * (520 - len(encoded))
    return head + struct.pack("<i", len(original_path) + 1) + encoded + b"\x00\x00"


class TestParseDollarI:
    @pytest.mark.parametrize("version", [1, 2])
    def test_roundtrip(self, tmp_path, version):
        original = "D:\\2021June_NorthLuzon_cGPS_IESAS\\BLNA_20210629\\BLNA1800.21o"
        blob = tmp_path / "$IABC123.21o"
        blob.write_bytes(make_dollar_i(original, version=version))
        got_path, got_deleted = parse_dollar_i(blob)
        assert got_path == original
        assert got_deleted.year == 2021 and got_deleted.month == 8

    def test_truncated_raises(self, tmp_path):
        blob = tmp_path / "$Ishort"
        blob.write_bytes(b"\x02\x00\x00")
        with pytest.raises(RecycleBinError):
            parse_dollar_i(blob)

    def test_unknown_version_raises(self, tmp_path):
        blob = tmp_path / "$Ibad"
        blob.write_bytes(struct.pack("<qqq", 99, 0, 0) + b"\x00" * 32)
        with pytest.raises(RecycleBinError):
            parse_dollar_i(blob)


class TestWindowsPathToRel:
    @pytest.mark.parametrize(
        ("win", "rel"),
        [
            ("D:\\Backups\\SITE0010.22o", "D/Backups/SITE0010.22o"),
            ("c:\\lower\\drive.dat", "C/lower/drive.dat"),
            ("\\\\server\\share\\f.22o", "server/share/f.22o"),
            ("relative\\odd.22o", "relative/odd.22o"),
        ],
    )
    def test_conversion(self, win, rel):
        assert windows_path_to_rel(win) == rel


def build_bin_tree(root: Path) -> Path:
    """Drive root with one deleted file + one deleted directory + one orphan."""
    sid = root / "$RECYCLE.BIN" / "S-1-5-21-1111-2222-3333-1001"
    sid.mkdir(parents=True)
    # Deleted single file
    (sid / "$RFILE01.22o").write_bytes(b"obs data")
    (sid / "$IFILE01.22o").write_bytes(make_dollar_i("D:\\OBS\\PPPP0010.22o", size=8))
    # Deleted directory: files keep real names underneath
    campaign = sid / "$RDIR001"
    (campaign / "BLNA_20210629").mkdir(parents=True)
    (campaign / "BLNA_20210629" / "BLNA1800.21o").write_bytes(b"x" * 16)
    (sid / "$IDIR001").write_bytes(make_dollar_i("D:\\Campaign2021", size=0))
    # Orphan $R (its $I is gone)
    (sid / "$RORPHAN.dat").write_bytes(b"trimble")
    return root


def catalog_for(root: Path, dest: Path) -> Path:
    """JSONL catalog rows for the payload files in the synthetic bin tree."""
    sid = root / "$RECYCLE.BIN" / "S-1-5-21-1111-2222-3333-1001"
    rows = [
        {"path": str(sid / "$RFILE01.22o"), "category": "GNSS Data", "size_bytes": 8},
        {
            "path": str(sid / "$RDIR001" / "BLNA_20210629" / "BLNA1800.21o"),
            "category": "GNSS Data",
            "size_bytes": 16,
        },
        {"path": str(sid / "$RORPHAN.dat"), "category": "GNSS Raw (Trimble)", "size_bytes": 7},
        {"path": str(sid / "$IFILE01.22o"), "category": "GNSS Data", "size_bytes": 544},
        {"path": str(root / "live" / "keep.mp3"), "category": "Audio", "size_bytes": 3},
    ]
    cat = dest / "catalog.jsonl"
    cat.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return cat


class TestPairRecycleBin:
    def test_pairing_manifest(self, tmp_path):
        root = build_bin_tree(tmp_path / "drive")
        catalog = catalog_for(root, tmp_path)
        dest_root = tmp_path / "out"
        result = pair_recycle_bin(catalog, dest_root)

        by_src = {r.src_path.name: r for r in result.rows}
        # Deleted single file restores its original name
        single = by_src["$RFILE01.22o"]
        assert single.status == "ok"
        assert single.dest_path == dest_root / "D/OBS/PPPP0010.22o"
        assert single.original_path == "D:\\OBS\\PPPP0010.22o"
        # File inside deleted directory: original dir + real subpath
        nested = by_src["BLNA1800.21o"]
        assert nested.dest_path == dest_root / "D/Campaign2021/BLNA_20210629/BLNA1800.21o"
        # Orphan lands under _orphaned, still recovered
        orphan = by_src["$RORPHAN.dat"]
        assert orphan.status == "orphan"
        assert orphan.dest_path == dest_root / "_orphaned/$RORPHAN.dat"

    def test_dollar_i_stubs_not_treated_as_payload(self, tmp_path):
        root = build_bin_tree(tmp_path / "drive")
        catalog = catalog_for(root, tmp_path)
        result = pair_recycle_bin(catalog, tmp_path / "out")
        names = [r.src_path.name for r in result.rows]
        assert "$IFILE01.22o" not in names  # metadata stub, not content

    def test_category_filter(self, tmp_path):
        root = build_bin_tree(tmp_path / "drive")
        catalog = catalog_for(root, tmp_path)
        result = pair_recycle_bin(catalog, tmp_path / "out", categories={"GNSS Raw (Trimble)"})
        assert [r.src_path.name for r in result.rows] == ["$RORPHAN.dat"]

    def test_no_dest_collisions_reported(self, tmp_path):
        root = build_bin_tree(tmp_path / "drive")
        catalog = catalog_for(root, tmp_path)
        result = pair_recycle_bin(catalog, tmp_path / "out")
        assert result.dest_collisions == 0


class TestCopyFromManifest:
    def _paired(self, tmp_path):
        root = build_bin_tree(tmp_path / "drive")
        catalog = catalog_for(root, tmp_path)
        dest_root = tmp_path / "out"
        result = pair_recycle_bin(catalog, dest_root)
        manifest = tmp_path / "manifest.tsv"
        result.write_manifest(manifest)
        return manifest, dest_root

    def test_copy_verifies_and_is_idempotent(self, tmp_path):
        manifest, dest_root = self._paired(tmp_path)
        stats = copy_from_manifest(manifest, dest_root)
        assert (stats.copied, stats.failed) == (3, 0)
        assert (dest_root / "D/OBS/PPPP0010.22o").read_bytes() == b"obs data"
        again = copy_from_manifest(manifest, dest_root)
        assert (again.copied, again.skipped) == (0, 3)

    def test_dest_outside_root_refused(self, tmp_path):
        manifest, dest_root = self._paired(tmp_path)
        rogue = tmp_path / "rogue.tsv"
        lines = manifest.read_text().splitlines()
        lines[1] = lines[1].replace(str(dest_root), str(tmp_path / "elsewhere"))
        rogue.write_text("\n".join(lines) + "\n")
        stats = copy_from_manifest(rogue, dest_root)
        assert stats.failed == 1
        assert not (tmp_path / "elsewhere").exists()

    def test_size_mismatch_flagged(self, tmp_path):
        manifest, dest_root = self._paired(tmp_path)
        src = tmp_path / "drive/$RECYCLE.BIN/S-1-5-21-1111-2222-3333-1001/$RFILE01.22o"
        src.write_bytes(b"changed since catalog!!")  # size no longer matches manifest
        stats = copy_from_manifest(manifest, dest_root)
        assert stats.failed == 1


class TestRecoverCli:
    def test_pair_then_copy_end_to_end(self, tmp_path):
        root = build_bin_tree(tmp_path / "drive")
        catalog = catalog_for(root, tmp_path)
        dest_root = tmp_path / "recovered"
        manifest = tmp_path / "manifest.tsv"
        runner = CliRunner()

        r1 = runner.invoke(
            main,
            ["recover", "pair", str(catalog), "--dest-root", str(dest_root), "-o", str(manifest)],
        )
        assert r1.exit_code == 0, r1.output
        assert "orphan" in r1.output.lower()

        r2 = runner.invoke(main, ["recover", "copy", str(manifest), "--dest-root", str(dest_root)])
        assert r2.exit_code == 0, r2.output
        assert (dest_root / "D/OBS/PPPP0010.22o").is_file()
        assert (dest_root / "_orphaned/$RORPHAN.dat").is_file()
