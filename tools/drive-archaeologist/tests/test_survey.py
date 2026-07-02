"""
DA-003 survey-mode tests: stats-only walk, wipe/keep verdict, disclosures.
"""

import zipfile

from click.testing import CliRunner
from drive_archaeologist.cli import main
from drive_archaeologist.scanner import DeepScanner


def make_media_tree(root):
    (root / "Movies").mkdir(parents=True)
    (root / "Movies" / "film.mkv").write_bytes(b"m" * 100)
    (root / "Movies" / "film.srt").write_text("subs")
    (root / "song.mp3").write_bytes(b"a" * 50)


def test_stats_only_writes_nothing(tmp_path, monkeypatch):
    root = tmp_path / "drive"
    root.mkdir()
    make_media_tree(root)
    monkeypatch.chdir(tmp_path)  # any accidental default output would land here
    scanner = DeepScanner(root, stats_only=True)
    scanner.scan()
    assert scanner.output_file is None
    leftovers = [p for p in tmp_path.iterdir() if p.name != "drive"]
    assert leftovers == []  # no jsonl, no log, no checkpoint
    assert scanner.file_count == 3
    assert scanner.stats.categories["Video"] == 1
    assert scanner.stats.categories["Audio"] == 1


def test_verdict_safe_on_pure_media(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    make_media_tree(root)
    scanner = DeepScanner(root, stats_only=True, include_hidden=True)
    scanner.scan()
    verdict, warnings = scanner.survey_verdict()
    assert "safe-to-wipe candidate" in verdict
    assert scanner.stats.gnss_files == 0


def test_verdict_do_not_wipe_on_gnss(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    make_media_tree(root)
    (root / "PPPP0010.23o").write_text("rinex obs")  # only the regex fallback catches .23o
    scanner = DeepScanner(root, stats_only=True, include_hidden=True)
    scanner.scan()
    verdict, _ = scanner.survey_verdict()
    assert "DO NOT wipe" in verdict
    assert scanner.stats.gnss_files == 1


def test_verdict_unreliable_on_corrupt_fs(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "a.bin").write_bytes(b"x" * 600)
    (root / "b.bin").write_bytes(b"y" * 600)
    scanner = DeepScanner(root, stats_only=True, fs_capacity_bytes=1000)
    scanner.scan()
    verdict, warnings = scanner.survey_verdict()
    assert "verdict unreliable" in verdict
    assert any("inconsistent" in w for w in warnings)


def test_verdict_disclosures(tmp_path):
    root = tmp_path / "drive"
    (root / ".Trash-1000").mkdir(parents=True)
    (root / ".Trash-1000" / "hidden.mkv").write_text("x")
    (root / "visible.txt").write_text("v")
    with zipfile.ZipFile(root / "bundle.zip", "w") as zf:
        zf.writestr("member.txt", "m")
    (root / "link").symlink_to(root / "visible.txt")

    scanner = DeepScanner(root, stats_only=True, include_hidden=False, max_archive_depth=0)
    scanner.scan()
    _, warnings = scanner.survey_verdict()
    joined = " | ".join(warnings)
    assert "NOT surveyed" in joined  # hidden skip disclosed
    assert "symlinks" in joined
    assert "archives present but not opened" in joined


def test_survey_cli_end_to_end(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    make_media_tree(root)
    runner = CliRunner()
    result = runner.invoke(main, ["survey", str(root)])
    assert result.exit_code == 0, result.output
    assert "Verdict:" in result.output
    assert "safe-to-wipe candidate" in result.output


def test_survey_cli_gnss_verdict(tmp_path):
    root = tmp_path / "drive"
    root.mkdir()
    (root / "ALGO0010.22O").write_text("obs")
    runner = CliRunner()
    result = runner.invoke(main, ["survey", str(root)])
    assert result.exit_code == 0, result.output
    assert "DO NOT wipe" in result.output
