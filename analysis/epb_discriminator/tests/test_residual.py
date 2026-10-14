"""The residual test's statistics, checked against theory before anything uses them.

Every later number in the spike (power, cost on true quakes, blind spots) is a
rate measured against a threshold set from chi2(N-4). If the null distribution
is off, all of them are off together, so this is the first thing that must hold.
"""

from __future__ import annotations

import numpy as np
from epb.geometry import design_matrix, los_enu, make_sky, weights
from epb.residual import chi2_norm, leakage, mdb, normalized_resid, wls
from scipy import stats

SIGMA0 = 0.003  # m/s, placeholder (see README)


def _geom(n_sat: int, seed: int):
    rng = np.random.default_rng(seed)
    az, el = make_sky(n_sat, rng)
    H = design_matrix(los_enu(az, el))
    W = weights(el, SIGMA0)
    return H, W, rng


def test_noise_only_chi2_matches_theory():
    n_sat, n_epochs = 9, 20_000
    H, W, rng = _geom(n_sat, seed=1)
    sigma = 1 / np.sqrt(W)
    y = rng.standard_normal((n_epochs, n_sat)) * sigma
    _, r, _ = wls(H, W, y)
    dof = n_sat - 4
    c = chi2_norm(r, W, dof)
    assert abs(c.mean() - 1.0) < 0.02
    # false-reject rate at alpha = 1 % must be 1 % (binomial sd ~ 0.07 %)
    thr = stats.chi2.ppf(0.99, dof) / dof
    assert abs((c > thr).mean() - 0.01) < 0.003


def test_bias_in_column_space_of_H_is_invisible():
    # Constraint 1 of the brief: d = H @ theta looks exactly like motion + clock.
    H, W, rng = _geom(8, seed=2)
    y = rng.standard_normal(8) * 1e-3
    theta = np.array([0.02, -0.01, 0.03, 0.005])
    _, r0, _ = wls(H, W, y)
    _, r1, _ = wls(H, W, y + H @ theta)
    np.testing.assert_allclose(r1, r0, atol=1e-12)


def test_wls_recovers_motion_and_clock_without_noise():
    H, W, _ = _geom(7, seed=3)
    x = np.array([0.05, 0.03, 0.01, 0.002])
    x_hat, r, _ = wls(H, W, H @ x)
    np.testing.assert_allclose(x_hat, x, atol=1e-12)
    np.testing.assert_allclose(r, 0, atol=1e-12)


def test_normalized_residuals_are_unit_normal_under_the_null():
    n_sat = 10
    H, W, rng = _geom(n_sat, seed=4)
    y = rng.standard_normal((20_000, n_sat)) / np.sqrt(W)
    _, r, _ = wls(H, W, y)
    w = normalized_resid(H, W, r)
    np.testing.assert_allclose(w.std(axis=0), 1.0, atol=0.03)


def test_bias_at_mdb_is_detected_at_roughly_the_stated_power():
    # Baarda: a bias of size MDB_i on satellite i is found by the 1-dof w-test
    # with probability `power` at significance `alpha`.
    n_sat, alpha, power = 10, 0.001, 0.8
    H, W, rng = _geom(n_sat, seed=5)
    m = mdb(H, W, alpha=alpha, power=power)
    i = int(np.argmin(m))
    crit = stats.norm.ppf(1 - alpha / 2)
    trials = 20_000
    y = rng.standard_normal((trials, n_sat)) / np.sqrt(W)
    y[:, i] += m[i]
    _, r, _ = wls(H, W, y)
    hit = np.abs(normalized_resid(H, W, r)[:, i]) > crit
    assert abs(hit.mean() - power) < 0.02


def test_leakage_maps_a_unit_bias_to_the_solution_error():
    H, W, _ = _geom(8, seed=6)
    L = leakage(H, W)
    assert L.shape == (8, 4)
    d = np.zeros(8)
    d[3] = 0.01
    x_hat, _, _ = wls(H, W, d)
    np.testing.assert_allclose(x_hat, 0.01 * L[3], atol=1e-12)
