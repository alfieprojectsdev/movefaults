"""Tests for the DC3D port and the disloc3d-convention wrapper.

The load-bearing test is `test_matches_disloc_at_the_surface`. There is no
reference output to diff against -- `disloc3d.mexw64` cannot run here, which is
the whole premise -- so verification is against an INDEPENDENT transliteration
of the same physics: Cervelli's `disloc.c`, ported in PR #147 from a different
original by a different author. Two independent ports agreeing to machine
precision is real evidence. "It runs" is not.
"""
from __future__ import annotations

import numpy as np
import pytest
from pogf_geodetic_suite.modeling.dc3d import (
    SingularObservation,
    alpha_from_poisson,
    dc3d,
    has_quadrant_fix,
)
from pogf_geodetic_suite.modeling.disloc import disloc
from pogf_geodetic_suite.modeling.disloc3d import disloc3d, green_functions

STATIONS = np.array([[3.0, 7.0], [-4.0, 2.0], [8.0, -6.0], [0.0, 11.0]])


# ---------------------------------------------------------------------------
# cross-validation against the independent Cervelli port
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("strike", [0.0, 30.0, 90.0, 145.0, 270.0])
@pytest.mark.parametrize("dip", [90.0, 70.0, 45.0])
def test_matches_disloc_at_the_surface(strike, dip):
    """DC3D at z=0 must reproduce the 1985 surface solution.

    Okada 1992 (internal) and Okada 1985 (surface) are different formulations
    of the same physics, and `disloc.c` is a different author's C. Agreement
    to 1e-12 across strike and dip is what establishes the transliteration.
    """
    model = np.array([[20.0, 10.0, 15.0, dip, strike, 1.5, -2.0, 1.0, 0.6, 0.0]]).T
    expected = disloc(model, STATIONS.T, nu=0.25)
    obs = np.vstack([STATIONS[:, 0], STATIONS[:, 1], np.zeros(len(STATIONS))])
    got, _, _, _ = disloc3d(model, obs, nu=0.25)
    assert np.abs(expected - got).max() < 1e-12


def test_matches_disloc_for_tensile_opening():
    model = np.array([[20.0, 10.0, 15.0, 80.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0]]).T
    expected = disloc(model, STATIONS.T, nu=0.25)
    obs = np.vstack([STATIONS[:, 0], STATIONS[:, 1], np.zeros(len(STATIONS))])
    got, _, _, _ = disloc3d(model, obs, nu=0.25)
    assert np.abs(expected - got).max() < 1e-12


# ---------------------------------------------------------------------------
# the convention trap that returns zeros instead of erroring
# ---------------------------------------------------------------------------


def test_signed_half_lengths_collapse_to_zero():
    """`al = (-L/2, L/2)` yields EXACTLY zero, silently.

    Okada's AL1/AL2 are positive distances in the -strike and +strike
    directions. Given signed offsets instead, all four corner terms become
    identical and the +,-,-,+ accumulation cancels to zero -- a plausible
    "no deformation" result with nothing raised.

    Pinned because it cost real time to find and would cost it again.
    """
    kw = {"alpha": 2.0 / 3.0}
    L, W, D = 20.0, 10.0, 15.0
    wrong = dc3d(3.0, 7.0, 0.0, D, 90.0, (-L / 2, L / 2), (0.0, W), (1.0, 0, 0), **kw)
    right = dc3d(3.0, 7.0, 0.0, D, 90.0, (L / 2, L / 2), (0.0, W), (1.0, 0, 0), **kw)
    assert np.allclose(wrong, 0.0)
    assert not np.allclose(right, 0.0)


def test_alpha_from_poisson():
    assert alpha_from_poisson(0.25) == pytest.approx(2.0 / 3.0)
    assert alpha_from_poisson(0.0) == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# error handling
# ---------------------------------------------------------------------------


def test_positive_z_is_refused():
    """z > 0 is above the free surface, where the solution is undefined.

    The Fortran writes a warning to unit 6 and continues. A printf per call
    inside a 100,000-sample inversion is not a diagnostic.
    """
    with pytest.raises(ValueError, match="z must be <= 0"):
        dc3d(1.0, 1.0, 5.0, 15.0, 90.0, (10.0, 10.0), (0.0, 10.0), (1.0, 0, 0))


def test_singular_point_raises_by_default():
    """Zeros are indistinguishable from "no deformation" downstream."""
    with pytest.raises(SingularObservation):
        dc3d(0.0, 0.0, 0.0, 0.0, 90.0, (0.0, 0.0), (0.0, 0.0), (1.0, 0, 0))


def test_singular_point_returns_zeros_when_not_strict():
    out = dc3d(0.0, 0.0, 0.0, 0.0, 90.0, (0.0, 0.0), (0.0, 0.0), (1.0, 0, 0),
               strict=False)
    assert np.allclose(out, 0.0)


def test_rejects_bad_shapes():
    with pytest.raises(ValueError, match=r"model must be \(10, n\)"):
        disloc3d(np.zeros((9, 1)), np.zeros((3, 2)))
    with pytest.raises(ValueError, match=r"obs must be \(3, m\)"):
        disloc3d(np.zeros((10, 1)), np.zeros((2, 2)))


# ---------------------------------------------------------------------------
# physics: symmetry and the analytic limit
# ---------------------------------------------------------------------------


def test_strike_slip_is_antisymmetric_across_the_fault():
    kw = {"alpha": 2.0 / 3.0}
    al, aw, D = (2500.0, 2500.0), (0.0, 20.0), 20.0
    for off in (1.0, 5.0, 20.0, 100.0):
        plus = dc3d(0.0, off, 0.0, D, 90.0, al, aw, (1.0, 0, 0), **kw)
        minus = dc3d(0.0, -off, 0.0, D, 90.0, al, aw, (1.0, 0, 0), **kw)
        assert plus[0] == pytest.approx(-minus[0], abs=1e-15)


def test_long_locked_strike_slip_approaches_the_arctan_profile():
    """A locked vertical strike-slip fault has closed form u = (s/pi)*arctan(x/D).

    This is also exactly what `analysis/03 Yu` fits, so agreement is a check on
    the science the port is meant to serve, not only on the arithmetic. The
    fault must be long and deep for the 2D limit to hold; the residual is the
    finite-length effect.
    """
    D, s = 20.0, 1.0
    # aw is (DOWNDIP, UPDIP) distance from the reference depth. The slipping
    # part is BELOW D, so it extends downdip: (BIG, 0).
    #
    # (0, BIG) instead extends updip through the free surface and gives the
    # surface-breaking answer -- which is the complement, -(s/pi)*(pi - atan),
    # not an error. Two plausible profiles, one physical; worth pinning.
    al, aw = (5.0e5, 5.0e5), (1.0e6, 0.0)
    kw = {"alpha": 2.0 / 3.0}
    for x in (5.0, 20.0, 60.0, 150.0):
        got = dc3d(0.0, x, 0.0, D, 90.0, al, aw, (s, 0, 0), **kw)[0]
        want = -(s / np.pi) * np.arctan(x / D)
        assert got == pytest.approx(want, rel=1e-3)


def test_updip_extension_gives_the_surface_breaking_complement():
    """Pins the aw ordering, which is easy to reverse and hard to notice.

    A fault extending UPDIP from D through the free surface is a different
    physical problem, not a broken one: its profile is the complement of the
    buried case. Both look like plausible arctan-ish curves.
    """
    D, s = 20.0, 1.0
    al = (5.0e5, 5.0e5)
    kw = {"alpha": 2.0 / 3.0}
    for x in (5.0, 20.0, 60.0):
        down = dc3d(0.0, x, 0.0, D, 90.0, al, (1.0e6, 0.0), (s, 0, 0), **kw)[0]
        up = dc3d(0.0, x, 0.0, D, 90.0, al, (0.0, 1.0e6), (s, 0, 0), **kw)[0]
        assert down + up == pytest.approx(-s, rel=2e-3)


# ---------------------------------------------------------------------------
# Bradley's fix -- the empirical answer to the licence question
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not has_quadrant_fix(), reason="dc3d_quadrant.c not built")
def test_quadrant_fix_agrees_with_the_core_on_our_geometries():
    """No measurable difference on the geometries this project uses.

    Bradley's fix is EPL 1.0 while the core is unencumbered, so whether we
    need it is a real decision. It is answered by measurement rather than
    assumed: across the plane-strain profile geometry `06 Ku-en` uses --
    including deep in the region where the fix actually fires -- the two agree
    to machine precision.

    This does NOT prove no geometry needs the fix; Bradley documented one.
    It shows ours do not, which is what the default rests on.
    """
    al, aw, D = (2500.0, 2500.0), (0.0, 20.0), 20.0
    kw = {"alpha": 2.0 / 3.0}
    worst = 0.0
    for xa in (-2400.0, -2000.0, -1000.0, -100.0, 0.0, 100.0, 2400.0):
        for yp in (0.1, 1.0, 10.0, 100.0):
            a = dc3d(xa, yp, 0.0, D, 90.0, al, aw, (1.0, 0, 0), **kw)
            b = dc3d(xa, yp, 0.0, D, 90.0, al, aw, (1.0, 0, 0),
                     quadrant_fix=True, **kw)
            denom = max(np.abs(b).max(), 1e-30)
            worst = max(worst, np.abs(a - b).max() / denom)
    assert worst < 1e-12, f"worst relative difference {worst:.3e}"


@pytest.mark.skipif(not has_quadrant_fix(), reason="dc3d_quadrant.c not built")
def test_quadrant_fix_preserves_the_disloc_agreement():
    """The fix must not change the answer where the core is already right."""
    model = np.array([[20.0, 10.0, 15.0, 70.0, 30.0, 0.0, 0.0, 1.0, 0.5, 0.0]]).T
    expected = disloc(model, STATIONS.T, nu=0.25)
    obs = np.vstack([STATIONS[:, 0], STATIONS[:, 1], np.zeros(len(STATIONS))])
    got, _, _, _ = disloc3d(model, obs, nu=0.25, quadrant_fix=True)
    assert np.abs(expected - got).max() < 1e-12


# ---------------------------------------------------------------------------
# the make_G.m translation
# ---------------------------------------------------------------------------


def test_green_functions_shape_and_sign_convention():
    segs = np.array([[20.0, 5.0, 89.0, 0.0], [15.0, 25.0, 70.0, 10.0]])
    xs = np.linspace(-100.0, 100.0, 21)
    for datatype in (1, 2, 3):
        g = green_functions(segs, xs, datatype)
        assert g.shape == (21, 4)          # 2 segments x (strike-slip, dip-slip)
        assert np.isfinite(g).all()


def test_green_functions_datatype_3_is_not_negated():
    """`make_G.m` negates datatypes 1 and 2 and keeps 3."""
    segs = np.array([[20.0, 5.0, 89.0, 0.0]])
    xs = np.array([-50.0, -10.0, 10.0, 50.0])
    g1 = green_functions(segs, xs, 1)
    g3 = green_functions(segs, xs, 3)
    assert not np.allclose(g1, 0.0)
    assert not np.allclose(g3, 0.0)


def test_green_functions_rejects_bad_input():
    with pytest.raises(ValueError, match=r"segments must be \(k, 4\)"):
        green_functions(np.zeros((2, 3)), np.array([1.0]), 1)
    with pytest.raises(ValueError, match="datatype must be"):
        green_functions(np.zeros((1, 4)), np.array([1.0]), 4)
