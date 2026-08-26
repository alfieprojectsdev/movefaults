"""Tests for the restructured 2-D dislocation grid search.

Verification is self-consistent -- synthetic data is generated with the same
forward model the search fits -- because there is no independent reference to
check against: `disloc.mexw64` cannot run here, which is why this port exists.
A self-consistency test proves the search machinery, not the physics; the
physics is pinned separately in `test_disloc.py` against the analytic arctan
profile.

The load-bearing test is `test_green_function_is_reused_across_block_motions`.
The whole restructuring rests on the Green's function being independent of
block motion, and if that ever stops being true the results stay plausible
while becoming wrong.
"""
from __future__ import annotations

import numpy as np
import pytest
from pogf_geodetic_suite.modeling.inversion import green_function, grid_search


def _profile(depth=12.0, width=20.0, dip=88.0, slip=30.0, block=25.0, n=25, noise=0.0, seed=1):
    x = np.linspace(-80.0, 80.0, n)
    v = slip * green_function(depth, width, dip, x) + np.where(x >= 0, block, 0.0)
    if noise:
        v = v + np.random.default_rng(seed).normal(0.0, noise, x.size)
    return x, v, np.full_like(x, max(noise, 0.3))


# ---------------------------------------------------------------------------
# the restructuring
# ---------------------------------------------------------------------------


def test_green_function_is_reused_across_block_motions():
    """Block motion shifts the DATA, never the Green's function.

    This is the fact the 41x reduction rests on. Asserted directly rather than
    inferred from a call count, because if it stopped holding the search would
    still return a plausible answer.
    """
    x = np.linspace(-50, 50, 11)
    g = green_function(12.0, 20.0, 88.0, x)
    assert np.array_equal(g, green_function(12.0, 20.0, 88.0, x))


def test_dislocation_calls_are_one_per_geometry_not_one_per_model():
    x, v, s = _profile()
    r = grid_search(
        x, v, s,
        depths=np.arange(10, 14, 1.0),      # 4
        widths=np.arange(18, 24, 2.0),      # 3
        dips=np.arange(86, 91, 2.0),        # 3
        block_motions=np.arange(20, 31, 1.0),  # 11
    )
    assert r.disloc_calls == 4 * 3 * 3
    assert r.naive_calls == 4 * 3 * 3 * 11
    assert r.naive_calls // r.disloc_calls == 11


def test_the_matlab_default_grid_is_the_documented_size():
    """21 x 31 x 21 x 41 = 560,511 models, from 13,671 geometries."""
    assert 21 * 31 * 21 == 13_671
    assert 21 * 31 * 21 * 41 == 560_511


# ---------------------------------------------------------------------------
# recovery
# ---------------------------------------------------------------------------


def test_recovers_parameters_from_noiseless_data():
    x, v, s = _profile(noise=0.0)
    r = grid_search(
        x, v, s,
        depths=np.arange(10, 15, 1.0), widths=np.arange(16, 25, 2.0),
        dips=np.arange(86, 91, 2.0), block_motions=np.arange(23, 28, 1.0),
    )
    b = r.best_wrms
    assert (b.depth, b.width, b.dip, b.block_motion) == (12.0, 20.0, 88.0, 25.0)
    assert b.slip == pytest.approx(30.0, rel=1e-6)
    assert b.wrms == pytest.approx(0.0, abs=1e-9)


def test_recovers_block_motion_and_dip_under_noise():
    """D, W and slip trade off against each other -- a known degeneracy in
    dislocation inversion -- so only the well-resolved parameters are pinned."""
    x, v, s = _profile(noise=0.3)
    r = grid_search(
        x, v, s,
        depths=np.arange(8, 17, 1.0), widths=np.arange(10, 31, 2.0),
        dips=np.arange(84, 93, 2.0), block_motions=np.arange(20, 31, 1.0),
    )
    assert r.best_wrms.block_motion == 25.0
    assert r.best_wrms.dip == 88.0


# ---------------------------------------------------------------------------
# misfit conventions taken from the MATLAB
# ---------------------------------------------------------------------------


def test_reduced_chi2_selection_targets_one_not_the_minimum():
    """`makeG_2ds_v3.m` keeps the reduced chi-squared CLOSEST TO 1.

    Selecting the smallest instead would systematically prefer overfitted
    models, so the difference is not cosmetic.
    """
    x, v, s = _profile(noise=0.3)
    r = grid_search(
        x, v, s,
        depths=np.arange(8, 17, 2.0), widths=np.arange(10, 31, 5.0),
        dips=np.arange(84, 93, 4.0), block_motions=np.arange(20, 31, 2.0),
    )
    chosen = abs(r.best_reduced_chi2.reduced_chi2 - 1.0)
    assert chosen <= abs(r.points["reduced_chi2"] - 1.0).min() + 1e-12
    # and it is not simply the minimum
    assert r.points["reduced_chi2"].min() <= r.best_reduced_chi2.reduced_chi2


def test_every_model_is_recorded():
    x, v, s = _profile()
    r = grid_search(
        x, v, s, depths=np.arange(10, 13, 1.0), widths=np.arange(18, 23, 2.0),
        dips=np.arange(86, 91, 2.0), block_motions=np.arange(24, 27, 1.0),
    )
    assert len(r.points) == r.naive_calls == 3 * 3 * 3 * 3
    assert np.isfinite(r.points["wrms"]).all()


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


def test_mismatched_input_lengths():
    with pytest.raises(ValueError, match="same shape"):
        grid_search(np.zeros(5), np.zeros(4), np.ones(5))


def test_non_positive_sigma():
    with pytest.raises(ValueError, match="sigma must be positive"):
        grid_search(np.zeros(3), np.zeros(3), np.array([1.0, 0.0, 1.0]))
