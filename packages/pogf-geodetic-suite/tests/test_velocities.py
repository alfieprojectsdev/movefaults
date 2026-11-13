"""`pogf-timeseries velocities` and `compare-velocities`.

Synthetic PLOT directories with known rates, a step at a catalogued epoch and
one planted outlier. The numbers checked here are the ones a processing staff
member would compare with their own MATLAB run, so the layout is checked as
closely as the values.
"""
from __future__ import annotations

import hashlib
import json

import numpy as np
import pytest
from click.testing import CliRunner
from pogf_geodetic_suite.timeseries.analysis import estimate_velocity
from pogf_geodetic_suite.timeseries.cli import group
from pogf_geodetic_suite.timeseries.velocities import (
    MANIFEST_NAME,
    OUTLIERS_NAME,
    TABLE_HEADER,
    TABLE_NAME,
    compare_velocity_tables,
    load_plot_file,
    parse_velocity_table,
)

STEP_EPOCH = 2020.5
OUTLIER_ROW = 40


def _series(rate_mm, t, step_m=(0.0, 0.0, 0.0), seed=0):
    rng = np.random.default_rng(seed)
    enu = np.outer(t - t[0], np.asarray(rate_mm) / 1000.0)
    enu += rng.normal(0, 0.002, enu.shape)
    enu[t >= STEP_EPOCH] += np.asarray(step_m)
    return enu


def _write_plot(path, t, enu):
    with path.open("w") as fh:
        for ti, (e, n, u) in zip(t, enu, strict=True):
            fh.write(f"{ti:.4f}  {e:13.4f}  {n:13.4f}  {u:13.4f}\n")


@pytest.fixture
def plots(tmp_path):
    """ALPH: two segments split by an EQ, one planted outlier.
    BRAV: one segment. GONE: listed, no file. TINY: two epochs."""
    d = tmp_path / "PLOTS"
    d.mkdir()
    t = np.round(np.arange(2019.0, 2022.0, 7 / 365.25), 4)
    a = _series((10.0, -5.0, 2.0), t, step_m=(0.03, -0.02, 0.0), seed=1)
    a[OUTLIER_ROW, 0] += 0.5
    _write_plot(d / "ALPH", t, a)
    _write_plot(d / "BRAV", t, _series((-3.0, 25.0, -1.0), t, seed=2))
    _write_plot(d / "TINY", t[:2], _series((1.0, 1.0, 1.0), t[:2], seed=3))
    (d / "123").write_text("ALPH\nBRAV\nGONE\nTINY\n")
    (d / "offsets").write_text(f"ALPH {STEP_EPOCH:.4f} EQ\n")
    return d


def _run(*args):
    return CliRunner().invoke(group, ["velocities", *map(str, args)])


def test_table_layout_and_segments(plots):
    res = _run(plots)
    assert res.exit_code == 0, res.output
    text = (plots / TABLE_NAME).read_text()
    assert text.startswith(TABLE_HEADER)
    body = text[len(TABLE_HEADER):].splitlines()
    assert [ln.split()[0] for ln in body] == ["ALPH", "ALPH", "BRAV"]
    # The MATLAB's own fprintf layout, column for column.
    for ln in body:
        name, rest = ln[:4], ln[4:]
        assert name.isalpha() and rest[0] == " "
        assert rest[11:15] == " +- " and rest[19:23] == "    "


def test_values_recover_the_rates(plots):
    _run(plots)
    rows = parse_velocity_table(plots / TABLE_NAME)
    last_b = rows["BRAV"][-1]
    assert last_b.ve == pytest.approx(-3.0, abs=0.5)
    assert last_b.vn == pytest.approx(25.0, abs=0.5)


def test_record_mode_is_estimate_velocity_unexcluded(plots):
    """The default must reproduce the MATLAB, i.e. fit with the outliers in."""
    _run(plots)
    t, enu = load_plot_file(plots / "ALPH")
    from pogf_geodetic_suite.timeseries.offsets_catalog import load_offsets_catalog
    ref = estimate_velocity(t, enu, offsets=load_offsets_catalog(plots / "offsets")["ALPH"],
                            exclude_outliers=False)
    got = parse_velocity_table(plots / TABLE_NAME)["ALPH"]
    for g, s in zip(got, ref.segments, strict=True):
        assert g.ve == pytest.approx(round(s.ve_mm_yr, 5), abs=1e-9)


def test_exclude_mode_changes_only_the_site_with_the_outlier(plots, tmp_path):
    _run(plots, "-o", tmp_path / "rec")
    _run(plots, "-o", tmp_path / "exc", "--outlier-mode", "exclude")
    rec = parse_velocity_table(tmp_path / "rec" / TABLE_NAME)
    exc = parse_velocity_table(tmp_path / "exc" / TABLE_NAME)
    assert rec["ALPH"][0].ve != exc["ALPH"][0].ve
    assert rec["BRAV"] == exc["BRAV"]


def test_outliers_file_lists_the_planted_epoch(plots):
    _run(plots)
    text = (plots / OUTLIERS_NAME).read_text()
    assert text.startswith("------------------\noutliers list\n------------------\nALPH\n")
    t, _ = load_plot_file(plots / "ALPH")
    assert f"{t[OUTLIER_ROW]:4.4f}\n" in text


def test_failures_are_reported_not_dropped(plots):
    res = _run(plots)
    assert "NOT FITTED GONE: no PLOT file" in res.output
    assert "NOT FITTED TINY" in res.output
    assert "fitted    : 2 of 4 sites" in res.output


def test_manifest_records_the_catalog_and_outputs(plots):
    _run(plots, "-r", "REFR")
    m = json.loads((plots / MANIFEST_NAME).read_text())
    assert m["offsets"]["sha256"] == hashlib.sha256((plots / "offsets").read_bytes()).hexdigest()
    assert m["outlier_mode"] == "record" and m["reference"] == "REFR"
    assert m["sites_listed"] == 4 and m["sites_fitted"] == 2
    assert {f["site"] for f in m["failures"]} == {"GONE", "TINY"}
    for name, digest in m["outputs"].items():
        assert hashlib.sha256((plots / name).read_bytes()).hexdigest() == digest


def test_missing_catalog_is_never_silent(plots):
    (plots / "offsets").unlink()
    res = _run(plots)
    assert res.exit_code == 2 and "--no-offsets" in res.output
    res = _run(plots, "--no-offsets")
    assert res.exit_code == 0
    assert len(parse_velocity_table(plots / TABLE_NAME)["ALPH"]) == 1
    assert json.loads((plots / MANIFEST_NAME).read_text())["offsets"] is None


def test_crd_needs_a_reference(plots, tmp_path):
    crd = tmp_path / "X.CRD"
    crd.write_text("")
    res = _run(plots, "--crd", crd)
    assert res.exit_code == 2 and "--reference" in res.output


# ---------------------------------------------------------------------------
# compare-velocities
# ---------------------------------------------------------------------------


def _table(path, lines):
    path.write_text(TABLE_HEADER + "".join(ln + "\n" for ln in lines))
    return path


L1 = "ALPH   10.00000 +-  0.1      -5.00000 +-  0.1       2.00000 +-  0.3"
L2 = "BRAV   -3.00000 +-  0.1      25.00000 +-  0.1      -1.00000 +-  0.3"


def test_identical_tables_match(tmp_path):
    a = _table(tmp_path / "a", [L1, L2])
    b = _table(tmp_path / "b", [L1, L2])
    assert {r.status for r in compare_velocity_tables(a, b)} == {"match"}
    assert CliRunner().invoke(group, ["compare-velocities", str(a), str(b)]).exit_code == 0


def test_last_decimal_difference_is_reported(tmp_path):
    a = _table(tmp_path / "a", [L1, L2])
    b = _table(tmp_path / "b", [L1.replace("10.00000", "10.00001"), L2])
    rows = {r.site: r for r in compare_velocity_tables(a, b)}
    assert rows["ALPH"].status == "differ" and rows["BRAV"].status == "match"
    assert CliRunner().invoke(group, ["compare-velocities", str(a), str(b)]).exit_code == 1


def test_nan_is_a_difference(tmp_path):
    a = _table(tmp_path / "a", [L1])
    b = _table(tmp_path / "b", [L1.replace("+-  0.1      -5", "+-  NaN      -5")])
    assert compare_velocity_tables(a, b)[0].status == "differ"


def test_segment_count_and_missing_sites(tmp_path):
    a = _table(tmp_path / "a", [L1, L1, L2])
    b = _table(tmp_path / "b", [L1])
    rows = {r.site: r.status for r in compare_velocity_tables(a, b)}
    assert rows == {"ALPH": "segments", "BRAV": "only-ours"}


def test_dropped_trailing_segment_is_named_and_withheld_from_the_map(plots, tmp_path):
    """An offset leaving fewer than 3 epochs after it: estimate_velocity skips
    that segment, so the last table line is the PRE-offset rate. It must be
    reported, and kept off the map rather than drawn as the current rate."""
    t, _ = load_plot_file(plots / "BRAV")
    (plots / "offsets").write_text(
        f"ALPH {STEP_EPOCH:.4f} EQ\nBRAV {t[-2] - 1e-4:.4f} EQ\n"
    )
    crd = tmp_path / "X.CRD"
    crd.write_text(
        "TEST\n----\n\nLOCAL GEODETIC DATUM: IGS20\n\n"
        "NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG\n\n"
        "  1  ALPH 00000M001  -3000000.0000   5500000.0000   1600000.0000    A\n"
        "  2  BRAV 00000M002  -3010000.0000   5490000.0000   1610000.0000    A\n"
    )
    res = _run(plots, "--crd", crd, "-r", "ALPH")
    assert res.exit_code == 0, res.output
    assert "SHORT SEGMENT BRAV" in res.output and "NOT the current rate" in res.output
    m = json.loads((plots / MANIFEST_NAME).read_text())
    assert [f["site"] for f in m["short_segments"]] == ["BRAV"]
    psvelo = (plots / "velocities.psvelo").read_text()
    brav = [ln for ln in psvelo.splitlines() if ln.rstrip().endswith("BRAV")]
    assert brav and all(ln.startswith("#") for ln in brav)


def test_python_nan_is_parsed_not_dropped(tmp_path):
    a = _table(tmp_path / "a", [L1])
    b = _table(tmp_path / "b", [L1.replace("10.00000", "     nan")])
    rows = compare_velocity_tables(a, b)
    assert [r.status for r in rows] == ["differ"]
