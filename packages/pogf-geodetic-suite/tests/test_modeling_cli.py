"""pogf-modeling: the profile, grid and bootstrap commands (modeling/cli.py).

Synthetic data throughout. What the numbers should be is profile2d's business
(test_profile2d.py); these check that the commands pass settings through, write
the files the MATLAB workflow expects, and can repeat a run from its record.
"""

import json

import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner
from pogf_geodetic_suite.modeling.cli import SETTINGS_NAME, group, parse_axis
from pogf_geodetic_suite.modeling.profile2d import (
    PARAMETER_COLUMNS,
    Grid,
    Profile,
    bootstrap,
    drop_reference,
    green_table,
    legacy_picks,
    pick_line,
    project,
    read_velocities,
    solve_grid,
)

GRID_ARGS = ["--e1", "-1:1:1", "--depth", "0:10:5", "--width", "0:15:5", "--dip", "70:90:20", "--rate", "20:40:10"]
PROFILE_ARGS = ["--azimuth", "90", "--origin", "0", "0"]
GRID = Grid(
    e1=np.array([-1.0, 0.0, 1.0]), depth=np.array([0.0, 5.0, 10.0]), width=np.array([0.0, 5.0, 10.0, 15.0]),
    dip=np.array([70.0, 90.0]), rate=np.array([20.0, 30.0, 40.0]),
)  # fmt: skip
PROFILE = Profile(90.0, (0.0, 0.0), 200.0)


@pytest.fixture
def table(tmp_path):
    """A PHm.csv: the reference first, then stations across a locked fault at x = 0."""
    rows = [("REFS", -50_000.0, 0.0, 0.0, 0.0)]
    for i, x in enumerate([-35, -20, -10, -4, 3, 8, 15, 30, 60]):
        rows.append((f"S{i:03d}", x * 1000.0, 0.0, 30.0 / np.pi * np.arctan(x / 8.0) + 15.0, 0.0))
    df = pd.DataFrame(
        [{"sites": s, "Ecoord": e, "Ncoord": n, "height": 0.0, "velocity": v, "azimuth": az,
          "Vu": 0.0, "hgt": 0.1, "erreast": 0.5, "errnorth": 0.5} for s, e, n, v, az in rows]
    )  # fmt: skip
    path = tmp_path / "PHm.csv"
    df.to_csv(path, index=False)
    return path


def run(*args):
    return CliRunner().invoke(group, [str(a) for a in args], catch_exceptions=False)


# ── axes and settings ────────────────────────────────────────────────────────


def test_axis_includes_both_ends_like_matlab():
    np.testing.assert_array_equal(parse_axis("0:15:5", "depth"), [0, 5, 10, 15])
    np.testing.assert_allclose(parse_axis("-1:1:0.5", "e1"), [-1, -0.5, 0, 0.5, 1])
    np.testing.assert_array_equal(parse_axis("90:90:1", "dip"), [90])
    np.testing.assert_array_equal(parse_axis([3, 1, 2], "rate"), [3, 1, 2])


@pytest.mark.parametrize("bad", ["0:15", "a:b:c", "0:15:0", "15:0:1", []])
def test_a_bad_axis_is_refused_by_name(bad):
    import click

    with pytest.raises(click.ClickException, match="depth"):
        parse_axis(bad, "depth")


def test_missing_settings_are_named(table, tmp_path):
    r = run("grid", table, "-o", tmp_path / "out", *GRID_ARGS)
    assert r.exit_code != 0 and "--azimuth" in r.output and "--origin" in r.output
    r = run("grid", table, "-o", tmp_path / "out", *PROFILE_ARGS, "--depth", "0:5:5")
    assert r.exit_code != 0 and "--e1" in r.output and "--rate" in r.output
    r = run("bootstrap", table, "-o", tmp_path / "out", *PROFILE_ARGS, *GRID_ARGS)
    assert r.exit_code != 0 and "--samples" in r.output
    assert not (tmp_path / "out").exists(), "nothing is written when the settings are incomplete"


# ── profile ──────────────────────────────────────────────────────────────────


def test_profile_prints_the_projection(table, tmp_path):
    r = run("profile", table, *PROFILE_ARGS, "-o", tmp_path / "profile.txt")
    assert r.exit_code == 0, r.output
    data = project(read_velocities(table), PROFILE)
    rows = [ln.split() for ln in r.output.splitlines() if not ln.startswith("#")]
    assert [row[0] for row in rows] == [s.strip() for s in data.sites]
    np.testing.assert_allclose([float(row[1]) for row in rows], data.x_km, atol=1e-3)
    np.testing.assert_allclose([float(row[2]) for row in rows], data.v_orth, atol=1e-5)
    assert "sigma legacy" in r.output.splitlines()[0]
    assert (tmp_path / "profile.txt").read_text() == r.output


def test_profile_sigma_option_changes_the_errors(table):
    legacy = run("profile", table, *PROFILE_ARGS).output
    fixed = run("profile", table, *PROFILE_ARGS, "--sigma", "propagated").output
    assert "sigma propagated" in fixed and legacy != fixed


# ── grid ─────────────────────────────────────────────────────────────────────


def test_grid_writes_the_matlabs_files_and_the_library_picks(table, tmp_path):
    out = tmp_path / "run"
    r = run("grid", table, "-o", out, *PROFILE_ARGS, *GRID_ARGS)
    assert r.exit_code == 0, r.output
    data = drop_reference(project(read_velocities(table), PROFILE))
    result = solve_grid(green_table(data.x_km, GRID), data, GRID)
    i_r, i_w = legacy_picks(result)
    assert (out / "parameters_rchi.txt").read_text() == pick_line(result.model(i_r)) + "\n"
    assert (out / "parameters_wrms.txt").read_text().splitlines() == [pick_line(result.model(int(i))) for i in i_w]
    params = pd.read_csv(out / "parameters.txt", sep=" ")
    assert list(params.columns) == PARAMETER_COLUMNS and len(params) == GRID.size
    assert f"{GRID.size:,} models on 9 stations" in r.output
    assert "reference station: REFS" in r.output, "the default reference is announced"


def test_grid_no_table_skips_the_big_file(table, tmp_path):
    out = tmp_path / "run"
    assert run("grid", table, "-o", out, *PROFILE_ARGS, *GRID_ARGS, "--no-table").exit_code == 0
    assert not (out / "parameters.txt").exists()
    assert (out / "parameters_rchi.txt").exists()


def test_grid_refuses_to_replace_results_unless_told(table, tmp_path):
    out = tmp_path / "run"
    args = ["grid", table, "-o", out, *PROFILE_ARGS, *GRID_ARGS, "--no-table"]
    assert run(*args).exit_code == 0
    before = (out / "parameters_rchi.txt").read_text()
    r = run(*args, "--rate", "20:30:10")
    assert r.exit_code != 0 and "already holds" in r.output
    assert (out / "parameters_rchi.txt").read_text() == before
    assert run(*args, "--rate", "20:30:10", "--overwrite").exit_code == 0


def test_grid_reference_by_name_and_drop(table, tmp_path):
    r = run("grid", table, "-o", tmp_path / "a", *PROFILE_ARGS, *GRID_ARGS, "--no-table",
            "--reference", "refs", "--drop", "reference")  # fmt: skip
    assert r.exit_code == 0, r.output
    record = json.loads((tmp_path / "a" / SETTINGS_NAME).read_text())
    assert record["reference"] == "REFS" and record["drop"] == "reference"
    assert "REFS" not in record["stations"] and len(record["stations"]) == 9
    r = run("grid", table, "-o", tmp_path / "b", *PROFILE_ARGS, *GRID_ARGS, "--reference", "NOPE")
    assert r.exit_code != 0 and "NOPE" in r.output and not (tmp_path / "b").exists()


def test_a_bad_velocity_table_is_explained(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("sites,Ecoord\nAAAA,1\n")
    r = run("grid", bad, "-o", tmp_path / "out", *PROFILE_ARGS, *GRID_ARGS)
    assert r.exit_code != 0 and "missing columns" in r.output
    assert "Traceback" not in r.output


# ── bootstrap ────────────────────────────────────────────────────────────────


def _boot(table, out, *extra):
    return run("bootstrap", table, "-o", out, *PROFILE_ARGS, *GRID_ARGS, "--samples", "6", *extra)


def test_bootstrap_matches_the_library_for_the_same_seed(table, tmp_path):
    out = tmp_path / "boot"
    r = _boot(table, out, "--seed", "7")
    assert r.exit_code == 0, r.output
    df = read_velocities(table)
    expected = bootstrap(df.iloc[1:].reset_index(drop=True), df.iloc[[0]].reset_index(drop=True),
                         PROFILE, GRID, n_samples=6, sample_size=9, seed=7)  # fmt: skip
    assert (out / "parameters_rchi.txt").read_text().splitlines() == [pick_line(m) for m in expected.rchi_picks]
    assert (out / "parameters_wrms.txt").read_text().splitlines() == [
        pick_line(m) for ties in expected.wrms_picks for m in ties
    ]
    assert "95% interval of the picks, reduced chi2 closest to 1" in r.output
    assert (out / "intervals.txt").read_text() in r.output
    rate = expected.intervals().loc["Rate"]
    line = next(ln for ln in r.output.splitlines() if ln.strip().startswith("Rate"))
    assert [float(v) for v in line.split()[1:]] == pytest.approx([rate["low"], rate["median"], rate["high"]], abs=1e-3)


def test_bootstrap_records_its_seed_and_repeats_from_its_record(table, tmp_path):
    first = tmp_path / "first"
    assert _boot(table, first).exit_code == 0  # no --seed: one is drawn
    record = json.loads((first / SETTINGS_NAME).read_text())
    assert isinstance(record["seed"], int) and record["n_samples"] == 6 and record["sample_size"] == 9
    assert record["sigma"] == "legacy" and record["drop"] == "first" and record["reference"] == "REFS"
    assert len(record["population_sha256"]) == 64
    again = tmp_path / "again"
    r = run("bootstrap", table, "-o", again, "--settings", first / SETTINGS_NAME)
    assert r.exit_code == 0, r.output
    for name in ("parameters_rchi.txt", "parameters_wrms.txt", "intervals.txt"):
        assert (again / name).read_text() == (first / name).read_text(), name


def test_two_unseeded_runs_differ(table, tmp_path):
    assert _boot(table, tmp_path / "a").exit_code == 0
    assert _boot(table, tmp_path / "b").exit_code == 0
    seeds = [json.loads((tmp_path / d / SETTINGS_NAME).read_text())["seed"] for d in "ab"]
    assert seeds[0] != seeds[1]


def test_an_option_overrides_the_settings_file(table, tmp_path):
    settings = tmp_path / "s.json"
    settings.write_text(json.dumps({
        "profile": {"azimuth_deg": 90, "origin_en": [0, 0]},
        "grid": {"e1": "-1:1:1", "depth": "0:10:5", "width": "0:15:5", "dip": "70:90:20", "rate": [20, 30, 40]},
        "n_samples": 3, "seed": 1, "sigma": "propagated",
    }))  # fmt: skip
    out = tmp_path / "o"
    r = run("bootstrap", table, "-o", out, "--settings", settings, "--samples", "5", "--sigma", "legacy")
    assert r.exit_code == 0, r.output
    record = json.loads((out / SETTINGS_NAME).read_text())
    assert record["n_samples"] == 5 and record["sigma"] == "legacy" and record["seed"] == 1
    assert record["profile"]["halfwidth_km"] == 200.0, "the default half-width is recorded"
    assert len((out / "parameters_rchi.txt").read_text().splitlines()) == 5


def test_bad_settings_are_refused(table, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    r = run("bootstrap", table, "-o", tmp_path / "o", "--settings", bad)
    assert r.exit_code != 0 and "bad.json" in r.output
    bad.write_text(json.dumps({"sigma": "other", "profile": {"azimuth_deg": 90, "origin_en": [0, 0]}}))
    r = run("profile", table, "--settings", bad)
    assert r.exit_code != 0 and "sigma is one of" in r.output
