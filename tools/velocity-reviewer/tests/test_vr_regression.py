"""Fit and suggestions: the fit must equal the legacy GUI's matrix solution."""

import numpy as np
import pytest
from velocity_reviewer.regression import fit_segment, iqr_outliers, process_site


def _legacy_model(t, d):
    """The normal-equations solve in `Outliers-input name.py`, for one component."""
    G = np.column_stack([np.ones(len(t)), t])
    g_inv = np.linalg.inv(G.T @ G)
    return g_inv @ G.T @ d


def _series(n=60, seed=1):
    rng = np.random.default_rng(seed)
    t = 2020.0 + np.arange(n) / 365.25
    e = 0.030 * (t - t[0]) + rng.normal(0, 0.002, n)  # 30 mm/yr east
    nn = -0.010 * (t - t[0]) + rng.normal(0, 0.002, n)  # -10 mm/yr north
    u = 0.002 * (t - t[0]) + rng.normal(0, 0.006, n)
    return t, e, nn, u


def test_fit_segment_recovers_a_line_in_mm_per_year():
    t = np.array([2020.0, 2020.5, 2021.0, 2021.5])
    d_cm = 1.0 + 2.5 * (t - 2020.0)  # 2.5 cm/yr
    predicted, v = fit_segment(t, d_cm)
    assert v == pytest.approx(25.0)
    np.testing.assert_allclose(predicted, d_cm)


def test_fit_segment_with_one_point_is_flat():
    predicted, v = fit_segment(np.array([2020.0]), np.array([3.0]))
    assert v == 0.0
    np.testing.assert_array_equal(predicted, [0.0])


def test_process_site_matches_the_legacy_gui():
    t, e, n, u = _series()
    out = process_site(t, e, n, u)
    for comp, key, raw in (("e", "ve", e), ("n", "vn", n), ("u", "vu", u)):
        d_cm = (raw - raw.mean()) * 100
        model = _legacy_model(t, d_cm)
        np.testing.assert_allclose(out[comp], d_cm)
        np.testing.assert_allclose(
            out[f"{comp}_fit"], np.column_stack([np.ones(len(t)), t]) @ model, atol=1e-8
        )
        assert out[key] == round(model[1] * 10, 1)


def test_process_site_flags_a_spike_and_nothing_else():
    t, e, n, u = _series()
    e = e.copy()
    e[30] += 0.05  # 5 cm spike
    out = process_site(t, e, n, u)
    assert out["iqr_outliers"] == [float(t[30])]


def test_iqr_outliers_needs_four_points():
    t = np.arange(3.0)
    assert iqr_outliers(t, np.array([0.0, 0.0, 9.0])) == []


def test_iqr_outliers_zero_spread_flags_nothing():
    t = np.arange(6.0)
    assert iqr_outliers(t, np.ones(6)) == []


def test_clean_noise_flags_nothing():
    """The old rule (|magnitude| > 3*IQR, no Q3) flagged 6 of these 60 points."""
    for seed in range(20):
        t, e, n, u = _series(seed=seed)
        assert process_site(t, e, n, u)["iqr_outliers"] == [], seed


def test_iqr_outliers_uses_tukey_fences():
    t = np.arange(8.0)
    # The test point stays the maximum, so the quartiles don't move with it.
    r = np.array([1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, 100.0])
    q1, q3 = np.percentile(r, [25, 75])
    iqr = q3 - q1
    # Inside the fences although larger than 3*IQR alone would allow.
    r[7] = q3 + 3 * iqr - 0.01
    assert r[7] > 3 * iqr
    assert iqr_outliers(t, r) == []
    r[7] = q3 + 3 * iqr + 0.5
    assert iqr_outliers(t, r) == [7.0]


def test_iqr_outliers_low_side_is_flagged_too():
    t = np.arange(8.0)
    r = np.array([1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 4.0, -20.0])
    assert iqr_outliers(t, r) == [7.0]


def test_iqr_outliers_any_column_flags_the_epoch():
    t = np.arange(8.0)
    quiet = np.array([1.0, 1.0, 2.0, 2.0, 3.0, 3.0, 2.0, 1.0])
    loud = quiet.copy()
    loud[2] = 50.0
    flat = np.zeros(8)  # zero spread: contributes no flags
    assert iqr_outliers(t, np.column_stack([quiet, loud, flat])) == [2.0]
