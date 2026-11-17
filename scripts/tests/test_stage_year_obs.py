"""scripts/stage_year_obs.py: one link per station-day, for any year, and nothing else touched."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "stage_year_obs.py"
spec = importlib.util.spec_from_file_location("stage_year_obs", SCRIPT)
stage = importlib.util.module_from_spec(spec)
sys.modules["stage_year_obs"] = stage
spec.loader.exec_module(stage)


@pytest.fixture
def tree(tmp_path, monkeypatch):
    src2, src3, pool = tmp_path / "archive", tmp_path / "pool" / "RINEX3", tmp_path / "pool"
    src2.mkdir()
    src3.mkdir(parents=True)
    monkeypatch.setenv("D", str(pool))

    def touch(folder: Path, *names: str) -> None:
        for n in names:
            (folder / n).write_text(n)

    touch(src2,
          "AAAA0010.24o", "AAAA0020.24d.gz",           # one file each
          "bbbb0010.24o",                              # lower-case code
          "CCCC0010.24o", "CCCC0010.24d.gz",           # a file and its compressed copy
          "DDDD0010.24o",                              # also has RINEX 3
          "AAAA0011.24o",                              # an hourly/sub-daily session: not daily
          "AAAA0010.23o",                              # another year
          "AAAA0010.24n", "notes.txt")
    touch(src3,
          "DDDD00PHL_R_20240010000_01D_30S_MO.crx.gz",
          "EEEE00AUS_R_20240020000_01D_30S_MO.crx.gz",
          "EEEE00AUS_R_20230020000_01D_30S_MO.crx.gz",  # another year
          "EEEE00AUS_R_20240020000_01H_30S_MO.crx.gz",  # hourly
          "EEEE00AUS_R_20240020000_01D_MN.rnx.gz")      # navigation
    return src2, src3, pool


def run(src2, *extra):
    return stage.main(["--year", "2024", "--campaign", "CAMP", "--rinex2", str(src2), *extra])


def test_dry_run_reports_and_writes_nothing(tree, capsys):
    src2, _, pool = tree
    assert run(src2) == 0
    out = capsys.readouterr().out
    assert "6 station-days, 5 stations, 2 days" in out
    assert "Dry run" in out
    assert not (pool / "CAMP").exists()


def test_apply_links_one_file_per_station_day(tree):
    src2, src3, pool = tree
    assert run(src2, "--apply") == 0
    links = {p.name: p.resolve() for p in (pool / "CAMP").iterdir()}
    assert sorted(links) == [
        "AAAA0010.24o", "AAAA0020.24d.gz", "BBBB0010.24o", "CCCC0010.24o",
        "DDDD00PHL_R_20240010000_01D_30S_MO.crx.gz", "EEEE00AUS_R_20240020000_01D_30S_MO.crx.gz",
    ]
    assert links["BBBB0010.24o"] == (src2 / "bbbb0010.24o").resolve(), "upper-case link, source untouched"
    assert links["CCCC0010.24o"] == (src2 / "CCCC0010.24o").resolve(), "the observation file, not its copy"
    assert links["DDDD00PHL_R_20240010000_01D_30S_MO.crx.gz"].parent == src3.resolve(), "RINEX 3 wins"
    assert all(p.is_symlink() for p in (pool / "CAMP").iterdir())


def test_counts_say_what_was_left_out(tree, capsys):
    src2, _, _ = tree
    run(src2)
    out = capsys.readouterr().out
    assert "1  other packings of a staged file left out" in out
    assert "1  RINEX 2 left out for a RINEX 3 file" in out
    assert "4  RINEX 2" in out and "2  RINEX 3" in out


def test_exclude_and_day_range(tree, capsys):
    src2, _, pool = tree
    assert run(src2, "--exclude", "aaaa", "--from", "1", "--to", "1", "--apply") == 0
    assert sorted(p.name for p in (pool / "CAMP").iterdir()) == [
        "BBBB0010.24o", "CCCC0010.24o", "DDDD00PHL_R_20240010000_01D_30S_MO.crx.gz",
    ]
    assert "excluded: AAAA" in capsys.readouterr().out


def test_ambiguous_station_day_is_refused(tree, capsys):
    src2, _, pool = tree
    (src2 / "aaaa0010.24o").write_text("a second file for AAAA day 1")
    assert run(src2, "--apply") == 1
    captured = capsys.readouterr()
    assert "AMBIGUOUS AAAA DOY 001" in captured.out and "refusing" in captured.err
    assert not (pool / "CAMP").exists()


def test_packings_are_ranked(tree):
    src2, _, pool = tree
    (src2 / "ffff0030.24d.gz").write_text("hatanaka")
    (src2 / "ffff0030.24o.gz").write_text("gzipped observation")
    (src2 / "GGGG0030.24o.gz").write_text("only packing there is")
    assert run(src2, "--apply") == 0
    dest = pool / "CAMP"
    assert (dest / "FFFF0030.24d.gz").is_symlink() and not (dest / "FFFF0030.24o.gz").exists()
    assert (dest / "GGGG0030.24o.gz").is_symlink()


def test_rerun_is_idempotent(tree, capsys):
    src2, _, _ = tree
    assert run(src2, "--apply") == 0
    capsys.readouterr()
    assert run(src2, "--apply") == 0
    assert "0 links made (0 repointed), 6 already there, 0 removed" in capsys.readouterr().out


def test_a_changed_choice_is_refused_until_pruned(tree, capsys):
    """A link the staging no longer chooses would run beside its replacement."""
    src2, src3, pool = tree
    dest = pool / "CAMP"
    assert run(src2, "--apply") == 0
    (src3 / "AAAA00PHL_R_20240010000_01D_30S_MO.crx.gz").write_text("RINEX 3 arrives for AAAA day 1")
    capsys.readouterr()
    for extra in ((), ("--apply",)):  # the dry run refuses as --apply would
        assert run(src2, *extra) == 1
        assert "not in this staging and would run too" in capsys.readouterr().err
    assert (dest / "AAAA0010.24o").is_symlink(), "nothing was changed by the refusals"
    assert not (dest / "AAAA00PHL_R_20240010000_01D_30S_MO.crx.gz").exists()

    assert run(src2, "--prune") == 0
    assert "would remove 1 links" in capsys.readouterr().out
    assert run(src2, "--apply", "--prune") == 0
    assert "1 removed" in capsys.readouterr().out
    assert not (dest / "AAAA0010.24o").exists()
    assert (dest / "AAAA00PHL_R_20240010000_01D_30S_MO.crx.gz").is_symlink()
    assert (dest / "AAAA0020.24d.gz").is_symlink(), "other days are untouched"


def test_prune_takes_a_newly_excluded_station_and_only_links(tree, capsys):
    src2, _, pool = tree
    dest = pool / "CAMP"
    assert run(src2, "--apply") == 0
    assert run(src2, "--exclude", "AAAA", "--apply", "--prune") == 0
    assert not (dest / "AAAA0010.24o").exists() and not (dest / "AAAA0020.24d.gz").exists()
    assert (dest / "BBBB0010.24o").is_symlink()
    # A regular file for the year is never removed: the run is refused instead.
    (dest / "ZZZZ0010.24o").write_text("copied in by hand")
    capsys.readouterr()
    assert run(src2, "--exclude", "AAAA", "--apply", "--prune") == 1
    assert "regular files" in capsys.readouterr().err
    assert (dest / "ZZZZ0010.24o").read_text() == "copied in by hand"


def test_a_mistyped_exclude_or_range_is_refused(tree, capsys):
    src2, _, pool = tree
    assert run(src2, "--exclude", "AAAB", "--apply") == 1
    assert "names no station" in capsys.readouterr().err and not (pool / "CAMP").exists()
    with pytest.raises(SystemExit):
        run(src2, "--from", "200", "--to", "100")


def test_rinex3_stations_are_named(tree, capsys):
    src2, _, _ = tree
    run(src2)
    assert "RINEX 3 taken for: DDDD EEEE" in capsys.readouterr().out


def test_existing_files_of_other_years_and_campaigns_are_left_alone(tree):
    src2, _, pool = tree
    dest = pool / "CAMP"
    dest.mkdir()
    (dest / "AAAA0010.25o").write_text("last year's staging")
    (dest / "PHSUP.note").write_text("x")
    assert run(src2, "--apply") == 0
    assert (dest / "AAAA0010.25o").read_text() == "last year's staging"
    assert (dest / "PHSUP.note").exists()


def test_a_regular_file_where_a_link_would_go_is_refused(tree, capsys):
    src2, _, pool = tree
    dest = pool / "CAMP"
    dest.mkdir()
    (dest / "AAAA0010.24o").write_text("a real file")
    assert run(src2, "--apply") == 1
    assert "regular files" in capsys.readouterr().err
    assert (dest / "AAAA0010.24o").read_text() == "a real file"
    assert len(list(dest.iterdir())) == 1


def test_refuses_without_the_datapool_or_any_file(tree, monkeypatch, tmp_path, capsys):
    src2, _, _ = tree
    empty = tmp_path / "empty"
    empty.mkdir()
    assert stage.main(["--year", "2019", "--campaign", "CAMP", "--rinex2", str(empty)]) == 1
    assert "no 2019 daily files" in capsys.readouterr().err
    monkeypatch.delenv("D")
    assert run(src2) == 1
    assert "$D is not set" in capsys.readouterr().err
