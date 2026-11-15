"""The 2-D profile model and bootstrap (modeling/profile2d.py).

Two kinds of test:

- synthetic: always run, checking each step against an independent
  calculation;
- parity with MATLAB: runs where a reference run is on disk (gps3), comparing
  every grid row with the MATLAB's parameters.txt. The reference files are
  PHIVOLCS data and are not in the repository. Point POGF_PROFILE2D_REFERENCE
  at a folder holding `*/*/profile2d_reference.json`; the default is gps3's.
"""

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from pogf_geodetic_suite.modeling.inversion import green_function
from pogf_geodetic_suite.modeling.profile2d import (
    PARAMETER_COLUMNS,
    Grid,
    Profile,
    ProfileData,
    bootstrap,
    drop_reference,
    green_table,
    legacy_picks,
    pick_line,
    project,
    read_velocities,
    solve_grid,
    write_parameters,
)


def _stations(rows):
    """A velocity table from (site, E m, N m, speed mm/yr, azimuth deg, sE, sN)."""
    return pd.DataFrame(
        [
            {
                "sites": s, "Ecoord": e, "Ncoord": n, "height": 0.0, "velocity": v,
                "azimuth": az, "Vu": 0.0, "hgt": 0.1, "erreast": se, "errnorth": sn,
            }
            for s, e, n, v, az, se, sn in rows
        ]
    )  # fmt: skip


SMALL = Grid(
    e1=np.array([-1.0, 0.0, 1.0]),
    depth=np.array([0.0, 5.0, 10.0]),
    width=np.array([0.0, 5.0, 15.0]),
    dip=np.array([70.0, 90.0]),
    rate=np.array([20.0, 30.0, 40.0]),
)


# ── projection ───────────────────────────────────────────────────────────────


def test_profile_normal_component_and_distance():
    # Profile pointing east (Az 90): distance is the east offset, and the
    # profile-normal component of a velocity due north is +v (MATLAB's -v sin(0 - 90)).
    prof = Profile(azimuth_deg=90.0, origin_en=(1000.0, 2000.0))
    df = _stations([("AAAA", 11000.0, 2000.0, 10.0, 0.0, 0.5, 0.5)])
    p = project(df, prof)
    assert p.x_km[0] == pytest.approx(10.0)
    assert p.v_orth[0] == pytest.approx(10.0)


def test_band_filter_and_stable_sort():
    prof = Profile(azimuth_deg=90.0, origin_en=(0.0, 0.0), halfwidth_km=5.0)
    df = _stations(
        [
            ("FARR", 0.0, 9000.0, 1.0, 0.0, 1.0, 1.0),  # 9 km off the line
            ("BBBB", 3000.0, 0.0, 1.0, 0.0, 1.0, 1.0),
            ("AAAA", -2000.0, 0.0, 1.0, 0.0, 1.0, 1.0),
            ("BBB2", 3000.0, 0.0, 2.0, 0.0, 1.0, 1.0),  # same distance: keeps input order
        ]
    )
    p = project(df, prof)
    assert list(p.sites) == ["AAAA", "BBBB", "BBB2"]


def test_legacy_sigma_scales_with_the_velocity_direction():
    prof = Profile(azimuth_deg=90.0, origin_en=(0.0, 0.0))
    df = _stations([("AAAA", 0.0, 0.0, 10.0, 60.0, 0.3, 0.4)])
    legacy = project(df, prof, sigma="legacy").err[0]
    assert legacy == pytest.approx(0.5 * abs(np.sin(np.radians(60.0 - 90.0))))


def test_propagated_sigma_is_the_normal_components_error():
    # Az 90: the normal component is the north velocity, so its sigma is sN,
    # whatever direction the station moves in.
    prof = Profile(azimuth_deg=90.0, origin_en=(0.0, 0.0))
    for az in (0.0, 45.0, 170.0):
        df = _stations([("AAAA", 0.0, 0.0, 10.0, az, 0.3, 0.4)])
        assert project(df, prof, sigma="propagated").err[0] == pytest.approx(0.4)


def test_propagated_sigma_against_monte_carlo():
    az = 73.0
    prof = Profile(azimuth_deg=az, origin_en=(0.0, 0.0))
    se, sn = 0.3, 0.7
    df = _stations([("AAAA", 0.0, 0.0, 10.0, 20.0, se, sn)])
    rng = np.random.default_rng(0)
    ve = 10 * np.sin(np.radians(20.0)) + rng.normal(0, se, 200_000)
    vn = 10 * np.cos(np.radians(20.0)) + rng.normal(0, sn, 200_000)
    a = np.radians(az)
    normal = -ve * np.cos(a) + vn * np.sin(a)
    assert project(df, prof, sigma="propagated").err[0] == pytest.approx(normal.std(), rel=0.01)
    assert project(df, prof).v_orth[0] == pytest.approx(normal.mean(), abs=0.01)


def test_unknown_sigma_is_refused():
    df = _stations([("AAAA", 0.0, 0.0, 1.0, 0.0, 1.0, 1.0)])
    with pytest.raises(ValueError, match="sigma"):
        project(df, Profile(90.0, (0.0, 0.0)), sigma="other")  # type: ignore[arg-type]


def test_read_velocities_takes_tab_or_comma(tmp_path):
    df = _stations([("AAAA", 1.0, 2.0, 3.0, 4.0, 0.5, 0.6)])
    df.to_csv(tmp_path / "a.csv", index=False)
    df.to_csv(tmp_path / "a.txt", sep="\t", index=False)
    for name in ("a.csv", "a.txt"):
        assert read_velocities(tmp_path / name)["erreast"].iloc[0] == 0.5
    pd.DataFrame({"sites": ["X"]}).to_csv(tmp_path / "bad.csv", index=False)
    with pytest.raises(ValueError, match="missing columns"):
        read_velocities(tmp_path / "bad.csv")


# ── dropping the reference ───────────────────────────────────────────────────


def _profile(sites, x):
    n = len(sites)
    return ProfileData(np.array(sites), np.array(x, float), np.zeros(n), np.ones(n))


def test_drop_first_is_the_matlab_rule():
    p = _profile(["REFS", "AAAA", "BBBB"], [-50, -10, 5])
    assert list(drop_reference(p).sites) == ["AAAA", "BBBB"]


def test_drop_first_and_by_name_agree_when_reference_is_westernmost():
    p = _profile(["REFS", "AAAA", "BBBB"], [-50, -10, 5])
    assert list(drop_reference(p, drop="reference", reference="REFS").sites) == ["AAAA", "BBBB"]


def test_drop_first_removes_the_wrong_station_when_one_lies_beyond_the_reference():
    p = _profile(["WEST", "REFS", "AAAA"], [-80, -50, 5])
    assert list(drop_reference(p).sites) == ["REFS", "AAAA"]  # the legacy defect
    assert list(drop_reference(p, drop="reference", reference="REFS").sites) == ["WEST", "AAAA"]


def test_drop_by_name_needs_a_reference_on_the_profile():
    p = _profile(["AAAA"], [1])
    with pytest.raises(ValueError, match="needs"):
        drop_reference(p, drop="reference")
    with pytest.raises(ValueError, match="not on the profile"):
        drop_reference(p, drop="reference", reference="ZZZZ")


# ── Green's functions ────────────────────────────────────────────────────────


def test_green_table_matches_the_older_port_at_e1_zero():
    x = np.array([-30.0, -5.0, 2.0, 40.0])
    G = green_table(x, SMALL)
    a = 1  # e1 == 0
    for b, d in enumerate(SMALL.depth):
        for c, w in enumerate(SMALL.width):
            for k, dip in enumerate(SMALL.dip):
                expected = np.zeros(4) if w == 0 else green_function(d, w, dip, x)
                np.testing.assert_allclose(G[a, b, c, k], expected, atol=1e-12)


def test_green_table_e1_shifts_the_fault():
    # A vertical fault moved 1 km east gives the same field moved 1 km east.
    x = np.array([-10.0, -3.0, 4.0, 12.0])
    G = green_table(x, SMALL)
    G_shifted = green_table(x + 1.0, SMALL)
    k90 = 1
    np.testing.assert_allclose(G_shifted[2, :, :, k90], G[1, :, :, k90], atol=1e-10)


# ── the grid ─────────────────────────────────────────────────────────────────


def _data(n=9, seed=3):
    rng = np.random.default_rng(seed)
    x = np.sort(rng.uniform(-40, 40, n))
    return ProfileData(
        np.array([f"S{i:03d}" for i in range(n)]), x, rng.normal(10, 5, n), rng.uniform(0.3, 2, n)
    )


def test_solve_grid_equals_weighted_lstsq_for_every_model():
    data = _data()
    G = green_table(data.x_km, SMALL)
    r = solve_grid(G, data, SMALL)
    w = 1 / data.err
    east = data.x_km >= 0
    for idx in np.ndindex(SMALL.shape):
        g = G[idx[:4]]
        d = data.v_orth - SMALL.rate[idx[4]] * east
        if not g.any():
            s = 0.0  # MATLAB's backslash on a zero column
        else:
            s = np.linalg.lstsq((g * w)[:, None], d * w, rcond=None)[0][0]
        resid = d - s * g
        chi2 = np.sum(resid**2 / data.err**2)
        assert r.slip[idx] == pytest.approx(s, abs=1e-9)
        assert r.chi2[idx] == pytest.approx(chi2, rel=1e-9, abs=1e-9)
        assert r.reduced_chi2[idx] == pytest.approx(chi2 / len(data.x_km), rel=1e-9, abs=1e-9)
        assert r.wrms[idx] == pytest.approx(
            np.sqrt(chi2 / np.sum(1 / data.err**2)), rel=1e-9, abs=1e-9
        )


def test_solve_grid_checks_its_inputs():
    data = _data()
    G = green_table(data.x_km, SMALL)
    with pytest.raises(ValueError, match="stations"):
        solve_grid(G[..., :-1], data, SMALL)
    bad = ProfileData(data.sites, data.x_km, data.v_orth, np.zeros_like(data.err))
    with pytest.raises(ValueError, match="positive error"):
        solve_grid(G, bad, SMALL)


def test_table_is_in_the_matlab_loop_order():
    data = _data()
    t = solve_grid(green_table(data.x_km, SMALL), data, SMALL).table()
    assert list(t.columns) == PARAMETER_COLUMNS
    assert len(t) == SMALL.size
    # Rate innermost, then dip, width, depth, E1 outermost.
    assert list(t["Rate"][:3]) == [20.0, 30.0, 40.0]
    assert list(t["Dip"][:4]) == [70.0, 70.0, 70.0, 90.0]
    assert t["East"].iloc[0] == -1.0 and t["East"].iloc[-1] == 1.0


# ── picks ────────────────────────────────────────────────────────────────────


def test_legacy_picks_filter_slip_and_choose_closest_to_one():
    data = _data()
    r = solve_grid(green_table(data.x_km, SMALL), data, SMALL)
    t = r.table()
    ok = t[(t.Slip >= 0) & (t.Slip <= t.Rate)]
    i_r, i_w = legacy_picks(r)
    assert i_r == (ok["Reduced chi2"] - 1).abs().idxmin()
    assert set(i_w) == set(ok.index[ok.Residual == ok.Residual.min()])


def test_legacy_picks_return_every_wrms_tie():
    data = _data()
    r = solve_grid(green_table(data.x_km, SMALL), data, SMALL)
    # Zero-width faults give slip 0 and the same misfit at every depth: force a tie.
    r.wrms[...] = 5.0
    r.wrms[:, :, 0, :, 1] = 1.0
    _, i_w = legacy_picks(r)
    assert len(i_w) == 3 * 3 * 2  # every E1, depth and dip at width 0, rate 30


def test_legacy_picks_refuse_when_nothing_passes():
    data = _data()
    r = solve_grid(green_table(data.x_km, SMALL), data, SMALL)
    r.slip[...] = -1.0
    with pytest.raises(ValueError, match="no model"):
        legacy_picks(r)


# ── output formats ───────────────────────────────────────────────────────────


def test_write_parameters_reads_back_like_the_matlabs(tmp_path):
    data = _data()
    r = solve_grid(green_table(data.x_km, SMALL), data, SMALL)
    path = tmp_path / "parameters.txt"
    write_parameters(r, path)
    assert path.read_text().splitlines()[0] == (
        'East Depth Width Dip Residual Rate Slip "Reduced chi2" Chi2'
    )
    back = pd.read_csv(path, sep=" ")
    pd.testing.assert_frame_equal(back.astype(float), r.table().astype(float), rtol=1e-14)


def test_pick_line_is_tab_separated_in_column_order():
    m = dict(
        zip(PARAMETER_COLUMNS, [-1.0, 0.0, 1.0, 90.0, 0.42, 39.0, 4.85, 168.8, 2025.6], strict=True)
    )
    assert pick_line(m) == "-1\t0\t1\t90\t0.42\t39\t4.85\t168.8\t2025.6"


# ── the bootstrap ────────────────────────────────────────────────────────────


def _population():
    # A synthetic locked fault at x = 0: stations west near 0, east near the block rate.
    xs = [-35, -20, -10, -4, 3, 8, 15, 30, 60]
    rows = []
    for i, x in enumerate(xs):
        normal = 30.0 / np.pi * np.arctan(x / 8.0) + 15.0  # 0 .. 30 across the fault
        # Velocity due north on an Az-90 profile is all normal component.
        rows.append((f"S{i:03d}", x * 1000.0, 0.0, normal, 0.0, 0.5, 0.5))
    return _stations(rows)


def _reference_row():
    return _stations([("REFS", -50_000.0, 0.0, 0.0, 0.0, 0.5, 0.5)])


def test_bootstrap_is_reproducible_with_a_seed():
    prof = Profile(azimuth_deg=90.0, origin_en=(0.0, 0.0))
    kw = {"n_samples": 5, "sample_size": 9, "sigma": "propagated"}
    a = bootstrap(_population(), _reference_row(), prof, SMALL, seed=7, **kw)
    b = bootstrap(_population(), _reference_row(), prof, SMALL, seed=7, **kw)
    c = bootstrap(_population(), _reference_row(), prof, SMALL, seed=8, **kw)
    assert a.rchi_picks == b.rchi_picks
    assert a.rchi_picks != c.rchi_picks
    assert a.settings["seed"] == 7 and a.settings["population_sha256"]


def test_bootstrap_iteration_equals_the_pipeline_run_by_hand():
    """One iteration = project the resample + reference, drop, grid, pick."""
    prof = Profile(azimuth_deg=90.0, origin_en=(0.0, 0.0))
    pop, ref = _population(), _reference_row()
    run = bootstrap(pop, ref, prof, SMALL, n_samples=1, sample_size=9, seed=11)
    draw = np.random.default_rng(11).choice(len(pop), size=9, replace=True)
    sample = pd.concat([pop.iloc[draw], ref], ignore_index=True)
    data = drop_reference(project(sample, prof))
    r = solve_grid(green_table(data.x_km, SMALL), data, SMALL)
    i_r, i_w = legacy_picks(r)
    # Same models; values to the last few bits (summation order differs).
    assert run.rchi_picks[0] == pytest.approx(r.model(i_r), rel=1e-12)
    assert len(run.wrms_picks[0]) == len(i_w)
    for got, i in zip(run.wrms_picks[0], i_w, strict=True):
        assert got == pytest.approx(r.model(int(i)), rel=1e-12)


def test_bootstrap_intervals_are_quantiles_of_the_picks():
    prof = Profile(azimuth_deg=90.0, origin_en=(0.0, 0.0))
    run = bootstrap(
        _population(), _reference_row(), prof, SMALL, n_samples=20, sample_size=9, seed=1
    )
    iv = run.intervals()
    rates = pd.Series([m["Rate"] for m in run.rchi_picks])
    assert iv.loc["Rate", "median"] == rates.quantile(0.5)
    assert list(iv.columns) == ["low", "median", "high"]


def test_bootstrap_refuses_a_reference_off_the_profile():
    prof = Profile(azimuth_deg=90.0, origin_en=(0.0, 0.0), halfwidth_km=5.0)
    far = _stations([("REFS", 0.0, 50_000.0, 0.0, 0.0, 0.5, 0.5)])
    with pytest.raises(ValueError, match="outside the profile band"):
        bootstrap(_population(), far, prof, SMALL, n_samples=1, sample_size=3, seed=0)


# ── parity with the MATLAB (where the reference run is on disk) ──────────────

REFERENCE_ROOT = Path(
    os.environ.get("POGF_PROFILE2D_REFERENCE", Path.home() / "leyte_bootstrap_20261112" / "snap")
)
REFERENCES = sorted(REFERENCE_ROOT.glob("*/*/profile2d_reference.json"))


def _axis(lo_hi_step):
    lo, hi, step = lo_hi_step
    return np.arange(lo, hi + step / 2, step, dtype=float)


@pytest.mark.skipif(not REFERENCES, reason=f"no MATLAB reference runs under {REFERENCE_ROOT}")
@pytest.mark.parametrize("cfg_path", REFERENCES, ids=lambda p: p.parent.parent.name)
def test_matches_the_matlab_run(cfg_path):
    from scipy.io import loadmat

    cfg = json.loads(cfg_path.read_text())
    d = cfg_path.parent
    prof = Profile(
        cfg["profile"]["azimuth_deg"],
        tuple(cfg["profile"]["origin_en"]),
        cfg["profile"]["halfwidth_km"],
    )
    grid = Grid(**{k: _axis(v) for k, v in cfg["grid"].items()})

    # velproj_loop.m: the same stations, distances, velocities and errors.
    p = project(read_velocities(d / cfg["velocities"]), prof)
    m = loadmat(d / cfg["projected"])
    assert [s.strip() for s in p.sites] == [s.strip() for s in m["sites"]]
    np.testing.assert_allclose(p.x_km, m["dis0"].ravel(), atol=1e-9)
    np.testing.assert_allclose(p.v_orth, m["Vorth"].ravel(), atol=1e-12)
    np.testing.assert_allclose(p.err, m["err"].ravel(), atol=1e-12)
    assert p.sites[0].strip() == cfg["reference"]

    # makeG_2ds_v3_loop.m: every row of parameters.txt.
    data = drop_reference(p)
    r = solve_grid(green_table(data.x_km, grid), data, grid)
    ours = r.table()
    theirs = pd.read_csv(d / cfg["parameters"], sep=" ")
    assert len(ours) == len(theirs) == grid.size
    for col in ("East", "Depth", "Width", "Dip", "Rate"):
        np.testing.assert_array_equal(ours[col].to_numpy(float), theirs[col].to_numpy(float))
    for col, rel in (("Residual", 1e-9), ("Slip", 1e-6), ("Reduced chi2", 1e-9), ("Chi2", 1e-9)):
        np.testing.assert_allclose(ours[col], theirs[col], rtol=rel, atol=1e-8, err_msg=col)

    # bootstrap_v2.py's picks, applied to their table and to ours: the same models.
    ok = theirs[(theirs.Slip >= 0) & (theirs.Slip <= theirs.Rate)]
    their_rchi = (ok["Reduced chi2"] - 1).abs().idxmin()
    their_wrms = set(ok.index[ok.Residual == ok.Residual.min()])
    i_r, i_w = legacy_picks(r)
    assert i_r == their_rchi
    assert set(i_w) == their_wrms
