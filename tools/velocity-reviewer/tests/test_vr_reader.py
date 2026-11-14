"""File handling: the 123 list, PLOT files, offsets, OUTLIERS.txt and the in-place strip."""

from pathlib import Path

import numpy as np
import pytest
from velocity_reviewer.reader import (
    previously_stripped,
    read_123,
    read_offsets,
    read_plot,
    write_cleaned_plots,
    write_outliers_txt,
)

PLOT_ROWS = [
    "2020.0014  0.010000  0.020000  0.030000",
    "2020.0041  0.011000  0.021000  0.031000",
    "2020.0068  0.012000  0.022000  0.032000",
    "2020.0096  0.013000  0.023000  0.033000",
]


def _write_plot(plots_dir: Path, site: str, rows: list[str]) -> Path:
    path = plots_dir / site
    path.write_text("\n".join(rows) + "\n")
    return path


def _rows(path: Path) -> list[str]:
    return [line for line in path.read_text().splitlines() if line.strip()]


# ── readers ───────────────────────────────────────────────────────────────────


def test_read_123_keeps_order_skips_blanks_and_normalises(tmp_path):
    (tmp_path / "123").write_text("bbbb\n\n  AAAA  \nCCCCX\n")
    assert read_123(tmp_path) == ["BBBB", "AAAA", "CCCC"]


def test_read_123_accepts_crlf(tmp_path):
    (tmp_path / "123").write_bytes(b"AAAA\r\nBBBB\r\n")
    assert read_123(tmp_path) == ["AAAA", "BBBB"]


def test_read_plot_returns_columns_in_metres(tmp_path):
    _write_plot(tmp_path, "AAAA", PLOT_ROWS + [""])
    t, e, n, u = read_plot(tmp_path, "AAAA")
    np.testing.assert_allclose(t, [2020.0014, 2020.0041, 2020.0068, 2020.0096])
    np.testing.assert_allclose(e, [0.010, 0.011, 0.012, 0.013])
    np.testing.assert_allclose(n, [0.020, 0.021, 0.022, 0.023])
    np.testing.assert_allclose(u, [0.030, 0.031, 0.032, 0.033])


def test_read_offsets_groups_by_site_and_ignores_short_lines(tmp_path):
    (tmp_path / "offsets").write_text(
        "aaaa 2019.5000 eq\nAAAA 2021.2500 CE\nBBBB 2020.1000 UK\nbroken line\n"
    )
    assert read_offsets(tmp_path) == {
        "AAAA": [(2019.5, "EQ"), (2021.25, "CE")],
        "BBBB": [(2020.1, "UK")],
    }


def test_read_offsets_missing_file_is_empty(tmp_path):
    assert read_offsets(tmp_path) == {}


# ── OUTLIERS.txt ──────────────────────────────────────────────────────────────


def test_write_outliers_txt_sorted_by_site_then_epoch(tmp_path):
    path = write_outliers_txt(tmp_path, {"BBBB": [2020.5, 2020.25], "AAAA": [2021.0]})
    assert path == tmp_path / "OUTLIERS.txt"
    assert path.read_text() == "AAAA 2021.0000\nBBBB 2020.2500\nBBBB 2020.5000\n"


def test_write_outliers_txt_overwrites_rather_than_appends(tmp_path):
    write_outliers_txt(tmp_path, {"AAAA": [2021.0]})
    write_outliers_txt(tmp_path, {"BBBB": [2020.0]})
    assert (tmp_path / "OUTLIERS.txt").read_text() == "BBBB 2020.0000\n"


# ── in-place strip ────────────────────────────────────────────────────────────


def test_strip_removes_selected_rows_and_keeps_a_backup(tmp_path):
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS)

    removed = write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})

    assert removed == 1
    assert _rows(plot) == [PLOT_ROWS[0], PLOT_ROWS[2], PLOT_ROWS[3]]
    assert _rows(tmp_path / "AAAA.bak") == PLOT_ROWS


def test_strip_matches_epochs_to_four_decimals(tmp_path):
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    # The browser sends back the float it was given; a tiny representation
    # difference must still match the row.
    write_cleaned_plots(tmp_path, {"AAAA": [2020.00410000001]})
    assert PLOT_ROWS[1] not in _rows(plot)


def test_re_export_is_idempotent(tmp_path):
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})
    first = plot.read_text()
    removed = write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})
    assert removed == 1
    assert plot.read_text() == first


def test_changing_the_selection_restores_previously_removed_rows(tmp_path):
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0068]})
    assert _rows(plot) == [PLOT_ROWS[0], PLOT_ROWS[1], PLOT_ROWS[3]]


def test_clearing_the_selection_restores_the_original(tmp_path):
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})

    removed = write_cleaned_plots(tmp_path, {"AAAA": []})

    assert removed == 0
    assert _rows(plot) == PLOT_ROWS


def test_empty_selection_without_backup_leaves_file_untouched(tmp_path):
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    before = plot.read_bytes()
    assert write_cleaned_plots(tmp_path, {"AAAA": []}) == 0
    assert plot.read_bytes() == before
    assert not (tmp_path / "AAAA.bak").exists()


def test_regenerated_plot_file_replaces_a_stale_backup(tmp_path):
    """PLOT files rebuilt after an export (new epochs) must not lose the new rows."""
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})

    new_row = "2020.0123  0.014000  0.024000  0.034000"
    _write_plot(tmp_path, "AAAA", PLOT_ROWS + [new_row])  # regenerated from CRDs

    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})

    assert _rows(plot) == [PLOT_ROWS[0], PLOT_ROWS[2], PLOT_ROWS[3], new_row]
    assert _rows(tmp_path / "AAAA.bak") == PLOT_ROWS + [new_row]


def test_reprocessed_values_replace_a_stale_backup(tmp_path):
    """Same epochs, new coordinates (a reprocessing) also count as regenerated."""
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})

    reprocessed = [r.replace("  0.01", "  0.51", 1) for r in PLOT_ROWS]  # east moves
    assert [r.split()[0] for r in reprocessed] == [r.split()[0] for r in PLOT_ROWS]
    _write_plot(tmp_path, "AAAA", reprocessed)
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})

    assert _rows(plot) == [reprocessed[0], reprocessed[2], reprocessed[3]]


def test_sites_without_a_plot_file_are_skipped(tmp_path):
    assert write_cleaned_plots(tmp_path, {"ZZZZ": [2020.0]}) == 0
    assert not (tmp_path / "ZZZZ").exists()


def test_last_row_removed_leaves_an_empty_file(tmp_path):
    plot = _write_plot(tmp_path, "AAAA", PLOT_ROWS[:1])
    assert write_cleaned_plots(tmp_path, {"AAAA": [2020.0014]}) == 1
    assert plot.read_text() == ""


@pytest.mark.parametrize("site", ["AAAA", "A1B2"])
def test_backup_name_is_site_dot_bak(tmp_path, site):
    _write_plot(tmp_path, site, PLOT_ROWS)
    write_cleaned_plots(tmp_path, {site: [2020.0014]})
    assert (tmp_path / f"{site}.bak").exists()


def test_previously_stripped_reports_what_an_export_removed(tmp_path):
    _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    assert previously_stripped(tmp_path, "AAAA") is None  # no backup yet
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})
    assert previously_stripped(tmp_path, "AAAA") == [2020.0041]
    _t, *_ = read_plot(tmp_path, "AAAA", from_backup=True)
    assert len(_t) == len(PLOT_ROWS)


def test_previously_stripped_is_none_after_regeneration(tmp_path):
    _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})
    _write_plot(tmp_path, "AAAA", PLOT_ROWS + ["2020.0123  0.014000  0.024000  0.034000"])
    assert previously_stripped(tmp_path, "AAAA") is None


def test_strip_leaves_no_temporary_file(tmp_path):
    _write_plot(tmp_path, "AAAA", PLOT_ROWS)
    write_cleaned_plots(tmp_path, {"AAAA": [2020.0041]})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["AAAA", "AAAA.bak"]
