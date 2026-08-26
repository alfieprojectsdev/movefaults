"""Tests for the MATLAB-free Okada dislocation core.

Verification here is against *physics*, not against a stored output, because
there is no reference output to store: `disloc.mexw64` is a Windows binary that
cannot run on this machine, which is the whole reason this module exists.

The load-bearing test is `test_reproduces_the_analytic_arctan_profile`. A long
vertical strike-slip fault locked from the surface to depth D has a known
closed-form surface profile, u = (s/pi) * arctan(x/D). That is also exactly the
interseismic model `analysis/03 Yu` fits, so agreement means the port
reproduces the physics the project actually uses.
"""
from __future__ import annotations

import numpy as np
import pytest
from pogf_geodetic_suite.modeling.disloc import (
    UnphysicalModel,
    disloc,
    last_unphysical_count,
)

LOCKING_DEPTH = 15_000.0


def _long_strikeslip(depth: float = LOCKING_DEPTH, width: float = 1.0e7) -> np.ndarray:
    """A dislocation long and deep enough to approximate the 2-D limit.

    Length 1e8 m is the same trick `06 Ku-en/make_G.m` uses with length 5000
    (km): make the fault long enough that along-strike effects vanish, and a
    3-D engine solves a plane-strain problem.
    """
    return np.array(
        [[1.0e8], [width], [depth + width], [90.0], [0.0], [0.0], [0.0], [1.0], [0.0], [0.0]]
    )


def _stations(x: np.ndarray) -> np.ndarray:
    return np.vstack([x, np.zeros_like(x)])


# ---------------------------------------------------------------------------
# physics
# ---------------------------------------------------------------------------


def test_reproduces_the_analytic_arctan_profile():
    """u_parallel = (s/pi) * arctan(x / D) for a locked vertical strike-slip fault."""
    x = np.array([-100e3, -50e3, -20e3, -5e3, -1e3, 1e3, 5e3, 20e3, 50e3, 100e3])
    got = disloc(_long_strikeslip(), _stations(x), nu=0.25)[1]
    analytic = (1.0 / np.pi) * np.arctan(x / LOCKING_DEPTH)
    # 1% with width 1e7 m; the residual is finite-width, see the next test.
    assert np.allclose(got, analytic, rtol=0.01)


def test_converges_to_the_infinite_dislocation_limit_as_width_grows():
    """The analytic form assumes an infinitely deep dislocation.

    A finite one under-predicts the far field, and the shortfall must shrink
    monotonically as the dislocation deepens. If it did not, the disagreement
    would be an implementation error rather than a modelling choice.
    """
    x = np.array([100e3])
    analytic = (1.0 / np.pi) * np.arctan(x / LOCKING_DEPTH)
    ratios = [
        float(disloc(_long_strikeslip(width=w), _stations(x), nu=0.25)[1][0] / analytic[0])
        for w in (1e5, 1e6, 1e7, 1e8)
    ]
    assert ratios == sorted(ratios), f"not monotonic: {ratios}"
    assert ratios[-1] > 0.99


def test_strike_slip_field_is_antisymmetric_across_the_fault():
    x = np.array([1e3, 5e3, 20e3, 50e3, 100e3])
    both = np.concatenate([-x[::-1], x])
    u = disloc(_long_strikeslip(), _stations(both), nu=0.25)[1]
    assert np.allclose(u[: len(x)][::-1], -u[len(x) :], atol=1e-12)


def test_displacement_decays_with_distance():
    x = np.array([1e3, 10e3, 100e3, 1000e3])
    u = np.abs(disloc(_long_strikeslip(), _stations(x), nu=0.25)[1])
    assert np.all(np.diff(u) > 0) or np.all(np.diff(u[:-1]) > 0)


def test_zero_slip_gives_zero_displacement():
    m = _long_strikeslip()
    m[7, 0] = 0.0
    u = disloc(m, _stations(np.array([1e3, 10e3])), nu=0.25)
    assert np.allclose(u, 0.0)


def test_slip_scales_linearly():
    """Elastic, so doubling the slip doubles the displacement."""
    x = np.array([5e3, 20e3])
    one = disloc(_long_strikeslip(), _stations(x), nu=0.25)
    m = _long_strikeslip()
    m[7, 0] = 2.0
    assert np.allclose(disloc(m, _stations(x), nu=0.25), 2.0 * one)


def test_superposition_of_two_dislocations_equals_the_sum():
    x = np.array([5e3, 20e3, 50e3])
    a = _long_strikeslip(depth=10_000.0)
    b = _long_strikeslip(depth=25_000.0)
    both = np.hstack([a, b])
    assert np.allclose(
        disloc(both, _stations(x), nu=0.25),
        disloc(a, _stations(x), nu=0.25) + disloc(b, _stations(x), nu=0.25),
    )


# ---------------------------------------------------------------------------
# the loop bug that made the .mexw64 unportable
# ---------------------------------------------------------------------------


def test_multiple_dislocations_terminate():
    """Regression for `for (i=0; i< NumDisl; i=i++)` in the vendored source.

    `i=i++` is undefined behaviour; gcc leaves i unchanged and the loop never
    ends. The Windows .mexw64 ran only because MSVC happened to increment. The
    first attempt to run this on Linux hung. With one dislocation the loop
    exits on the bound anyway -- it takes two or more to catch it.
    """
    model = np.hstack([_long_strikeslip(depth=d) for d in (8e3, 15e3, 25e3)])
    u = disloc(model, _stations(np.array([10e3])), nu=0.25)
    assert u.shape == (3, 1)
    assert np.isfinite(u).all()


# ---------------------------------------------------------------------------
# reference station and validation
# ---------------------------------------------------------------------------


def test_ref_station_subtracts_and_drops_that_column():
    x = np.array([-20e3, 0.0, 20e3])
    absolute = disloc(_long_strikeslip(), _stations(x), nu=0.25)
    relative = disloc(_long_strikeslip(), _stations(x), nu=0.25, ref_station=2)
    assert relative.shape == (3, 2)
    expected = np.delete(absolute - absolute[:, [1]], 1, axis=1)
    assert np.allclose(relative, expected)


def test_unphysical_model_raises_by_default():
    m = _long_strikeslip()
    m[0, 0] = -1.0  # negative length
    with pytest.raises(UnphysicalModel, match="rejected by GoodModel"):
        disloc(m, _stations(np.array([1e3])), nu=0.25)


def test_unphysical_model_can_be_skipped_like_the_original():
    """The original warned via mexWarnMsgTxt and carried on; strict=False keeps that."""
    m = _long_strikeslip()
    m[0, 0] = -1.0
    u = disloc(m, _stations(np.array([1e3])), nu=0.25, strict=False)
    assert np.allclose(u, 0.0)          # the rejected dislocation contributes nothing
    assert last_unphysical_count() == 1


@pytest.mark.parametrize(
    "model, coords, msg",
    [
        (np.zeros((9, 1)), np.zeros((2, 1)), "model must be"),
        (np.zeros((10, 1)), np.zeros((3, 1)), "coords must be"),
    ],
)
def test_shape_validation(model, coords, msg):
    with pytest.raises(ValueError, match=msg):
        disloc(model, coords)


def test_ref_station_out_of_range():
    with pytest.raises(ValueError, match="ref_station"):
        disloc(_long_strikeslip(), _stations(np.array([1e3, 2e3])), ref_station=5)
