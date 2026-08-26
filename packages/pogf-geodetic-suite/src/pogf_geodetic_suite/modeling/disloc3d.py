"""
`disloc3d` without MATLAB -- the calling convention `06 Ku-en` expects.

WHY
---
`analysis/06 Ku-en Dislocation Model/` calls ``disloc3d`` through
``disloc3d.mexw64``, a Windows binary with no source in this tree. It is the
last MATLAB dependency in the modelling chain, and it sits on the code path
behind the newest published Philippine results -- `inversion and monte carlo`
at 900,000 samples for Central Luzon, Masbate and Northern Leyte.

:mod:`dc3d` provides the Okada 1992 kernel. This module is the wrapper around
it: the coordinate rotations, the fault-parameter packing, and the strain and
stress that ``disloc3d`` returns and ``dc3d`` does not.

THE CONVENTION WAS MEASURED, NOT ASSUMED
----------------------------------------
The mapping between this convention and Okada's was determined by fitting
against :mod:`disloc` -- the independent Cervelli transliteration already in
this package -- and confirmed to 1.5e-16 at the surface. Three parts of it are
not guessable and one of them silently returns zeros when wrong:

* ``al = (L/2, L/2)`` -- Okada's ``AL1, AL2`` are **positive distances** in the
  -strike and +strike directions, not signed offsets. Passing ``(-L/2, L/2)``
  makes all four corner terms identical, and they cancel to **exactly zero**:
  a plausible "no deformation" answer with no error raised. That cost an hour.
* ``aw = (0, W)`` -- width measured updip from the reference depth.
* Okada's frame is x along strike, ``y_hat = z_hat x x_hat``, z up. For strike
  0 that puts Okada's +y along **-East**.

WHAT ``make_G.m`` PASSES
------------------------
::

    [U,D,S,flag] = disloc3d(m, [x_m; 0*x_m; 0*x_m], 1, .25)
    fault(k,:)   = [5000, seg(1:2), abs(dip)+180, str, seg(4), 0]
    m            = [fault(i,:), ss, ds, opening]'

so ``mu = 1``, ``nu = 0.25`` at every one of the twelve call sites, the
observation points lie on the free surface, and the length is 5000 -- a fault
long enough that along-strike effects vanish, which is how a 3D engine is used
for a plane-strain problem. **Only ``U`` is ever consumed**; ``D`` and ``S``
are computed and discarded at all twelve.
"""
from __future__ import annotations

import numpy as np

from .dc3d import dc3d

_DEG = np.pi / 180.0


def _rotate_in(de: np.ndarray, dn: np.ndarray, strike_deg: float):
    """Station offsets (East, North) -> Okada's (x along strike, y)."""
    s, c = np.sin(strike_deg * _DEG), np.cos(strike_deg * _DEG)
    return de * s + dn * c, -de * c + dn * s


def _rotate_out(ux: float, uy: float, strike_deg: float):
    """Okada's (ux, uy) -> (East, North)."""
    s, c = np.sin(strike_deg * _DEG), np.cos(strike_deg * _DEG)
    return ux * s - uy * c, ux * c + uy * s


def disloc3d(
    model: np.ndarray,
    obs: np.ndarray,
    mu: float = 1.0,
    nu: float = 0.25,
    *,
    quadrant_fix: bool = False,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Displacement, gradient and stress from rectangular dislocations.

    Args:
        model: ``(10, n)`` -- one dislocation per column::

            [length, width, depth, dip, strike, east, north, ss, ds, opening]

        obs:   ``(3, m)`` -- one station per column, ``[east; north; up]``.
               ``up`` must be <= 0.
        mu:    Shear modulus. Scales stress only; displacement is independent
               of it. Every call site in ``make_G.m`` passes 1.
        nu:    Poisson's ratio. Every call site passes 0.25.
        quadrant_fix: use Bradley's EPL-licensed fix; see :mod:`dc3d`.

    Returns:
        ``(U, D, S, flag)``

        * ``U`` ``(3, m)`` -- displacement ``[E; N; U]``
        * ``D`` ``(9, m)`` -- displacement gradient
        * ``S`` ``(6, m)`` -- stress, ``[xx, xy, xz, yy, yz, zz]``
        * ``flag`` ``(m,)`` -- non-zero where a dislocation was rejected

    Note:
        Contributions from multiple dislocations are summed, matching the
        original. ``flag`` is per station, not per dislocation.
    """
    m_arr = np.atleast_2d(np.asarray(model, dtype=np.float64))
    if m_arr.shape[0] != 10:
        raise ValueError(f"model must be (10, n); got {m_arr.shape}")
    pts = np.atleast_2d(np.asarray(obs, dtype=np.float64))
    if pts.shape[0] != 3:
        raise ValueError(f"obs must be (3, m); got {pts.shape}")

    n_stat = pts.shape[1]
    U = np.zeros((3, n_stat))
    Dg = np.zeros((9, n_stat))
    S = np.zeros((6, n_stat))
    flag = np.zeros(n_stat, dtype=int)

    alpha = 1.0 / (2.0 * (1.0 - nu))
    lam = 2.0 * mu * nu / (1.0 - 2.0 * nu)

    for col in range(m_arr.shape[1]):
        (length, width, depth, dip, strike,
         east, north, ss, ds, op) = m_arr[:, col]

        if length <= 0 or width <= 0 or depth < 0:
            flag[:] = 1
            continue

        de = pts[0] - east
        dn = pts[1] - north
        xs, ys = _rotate_in(de, dn, strike)

        for i in range(n_stat):
            try:
                r = dc3d(
                    xs[i], ys[i], pts[2, i], depth, dip,
                    (length / 2.0, length / 2.0),   # positive half-lengths
                    (0.0, width),                   # updip from `depth`
                    (ss, ds, op),
                    alpha=alpha, quadrant_fix=quadrant_fix, strict=False,
                )
            except ValueError:
                flag[i] = 1
                continue

            e, n = _rotate_out(r[0], r[1], strike)
            U[0, i] += e
            U[1, i] += n
            U[2, i] += r[2]

            # Gradients come back in the fault frame. Rotating a rank-2 tensor
            # properly needs the full similarity transform; only the trace and
            # the diagonal-derived stress invariants are frame-independent.
            # Since every call site discards D and S, the honest thing is to
            # return the fault-frame gradients and say so rather than ship an
            # untested rotation.
            Dg[:, i] += r[3:12]

    # Stress from the gradient, isotropic elasticity. Fault-frame, as above.
    exx, eyx, ezx, exy, eyy, ezy, exz, eyz, ezz = Dg
    theta = exx + eyy + ezz
    S[0] = lam * theta + 2.0 * mu * exx
    S[1] = mu * (exy + eyx)
    S[2] = mu * (exz + ezx)
    S[3] = lam * theta + 2.0 * mu * eyy
    S[4] = mu * (eyz + ezy)
    S[5] = lam * theta + 2.0 * mu * ezz

    return U, Dg, S, flag


def green_functions(
    segments: np.ndarray,
    profile_x: np.ndarray,
    datatype: int,
    *,
    length: float = 5000.0,
    quadrant_fix: bool = False,
) -> np.ndarray:
    """The Green's-function matrix `06 Ku-en`'s ``make_G.m`` builds.

    Args:
        segments: ``(k, 4)`` -- ``[width, depth, dip, east]`` per fault
                  segment, matching ``total_fault_segs`` in ``make_geometry.m``.
        profile_x: station coordinates along the fault-perpendicular profile.
        datatype: 1 fault-normal horizontal, 2 fault-parallel horizontal,
                  3 vertical -- the same encoding ``InputData.m`` uses.
        length:   fault length. ``make_G.m`` hardcodes 5000, long enough that
                  along-strike effects vanish; that is how a 3D kernel is used
                  for a plane-strain problem.

    Returns:
        ``(len(profile_x), 2 * k)`` -- strike-slip columns then dip-slip,
        with the sign convention of ``make_G.m`` (negated for datatypes 1
        and 2, kept for 3).

    This is a direct translation of ``make_G.m``, including the
    ``abs(dip) + 180`` and ``strike = 180 if dip < 0 else 0`` construction,
    which is the backslip sign flip rather than a physical dip.
    """
    segs = np.atleast_2d(np.asarray(segments, dtype=np.float64))
    if segs.shape[1] != 4:
        raise ValueError(f"segments must be (k, 4); got {segs.shape}")
    if datatype not in (1, 2, 3):
        raise ValueError(f"datatype must be 1, 2 or 3; got {datatype}")

    xs = np.asarray(profile_x, dtype=np.float64).ravel()
    obs = np.vstack([xs, np.zeros_like(xs), np.zeros_like(xs)])
    row = {1: 0, 2: 1, 3: 2}[datatype]

    g_ss = np.zeros((len(xs), segs.shape[0]))
    g_ds = np.zeros((len(xs), segs.shape[0]))
    for i, (width, depth, dip, east) in enumerate(segs):
        strike = 180.0 if dip < 0 else 0.0
        fault = [length, width, depth, abs(dip) + 180.0, strike, east, 0.0]
        for slip, out in (((1.0, 0.0, 0.0), g_ss), ((0.0, 1.0, 0.0), g_ds)):
            u, _, _, _ = disloc3d(
                np.array([[*fault, *slip]]).T, obs,
                quadrant_fix=quadrant_fix,
            )
            out[:, i] = u[row]

    block = np.hstack([g_ss, g_ds])
    return block if datatype == 3 else -block
