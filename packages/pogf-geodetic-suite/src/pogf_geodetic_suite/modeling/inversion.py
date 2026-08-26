"""
2-D interseismic dislocation inversion — the grid search, restructured.

PORT OF ``analysis/03 Yu 2D Interseismic Dislocation/makeG_2ds_v3.m``.

WHAT THE MATLAB DOES
--------------------
Six nested loops over fault parameters, and for every combination it builds a
Green's function with ``disloc``, solves a weighted least-squares problem for
slip, and records the misfit::

    for D  = 0:1:20          (21)
    for W  = 0:1:30          (31)
    for dip = 70:1:90        (21)
    for block_motion = 0:1:40 (41)

**21 x 31 x 21 x 41 = 560,511 dislocation calls**, serial, in MATLAB, on a
Windows desktop -- and `08 Bootstrapping` wraps the whole thing in N resampling
iterations.

THE RESTRUCTURING, WHICH MATTERS MORE THAN THE VECTORISATION
------------------------------------------------------------
The Green's function depends on **geometry only** -- D, W, dip. ``block_motion``
enters solely as a shift applied to the *data* (``d = Vorth - block_motion``
for stations east of the fault). So the innermost 41 iterations reuse one
Green's function and are pure linear algebra.

Computing G once per geometry drops the dislocation calls from **560,511 to
13,671** -- a 41x reduction before any parallelism, purely from noticing that
the inner loop was recomputing a constant.

The remaining 13,671 are independent and embarrassingly parallel; the R740 has
24 cores.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
The choice of inversion *method* -- grid search, bootstrap, or the MCMC in
``06 Ku-en`` -- is a scientific decision recorded in
``docs/project_documentation/inversion_method_decision.md`` and is not settled.
This module ports the **incumbent**, because it is the method that produced the
published numbers and the only one with Philippine inputs. It is written so the
misfit evaluation is reusable by whichever method wins.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .disloc import disloc


@dataclass(frozen=True)
class GridPoint:
    """One evaluated model."""

    depth: float
    width: float
    dip: float
    block_motion: float
    slip: float
    chi2: float
    reduced_chi2: float
    wrms: float


@dataclass(frozen=True)
class GridResult:
    best_wrms: GridPoint
    best_reduced_chi2: GridPoint
    points: np.ndarray          # structured array of every evaluation
    disloc_calls: int           # geometries actually evaluated
    naive_calls: int            # what the MATLAB would have done


def green_function(
    depth: float,
    width: float,
    dip: float,
    x_km: np.ndarray,
    nu: float = 0.25,
    fault_length: float = 1000.0,
) -> np.ndarray:
    """North-component Green's function for unit strike-slip on one patch.

    Mirrors the MATLAB exactly, including its conventions:

    * fault row ``[length, width, depth, -180 + dip, strike=0, E=0, N=0]``
      -- ``length=1000`` is what makes this a 2-D (plane-strain) problem
    * a single patch (``patchfault`` with ``nhe=nve=1`` returns the fault)
    * only the **north** component is kept (``G11 = G11(2:3:end)``)
    """
    model = np.array(
        [[fault_length], [width], [depth], [-180.0 + dip], [0.0], [0.0], [0.0],
         [1.0], [0.0], [0.0]]
    )
    coords = np.vstack([x_km, np.zeros_like(x_km)])
    u = disloc(model, coords, nu=nu, strict=False)
    return u[1]  # north component


def grid_search(
    x_km: np.ndarray,
    v_parallel: np.ndarray,
    sigma: np.ndarray,
    *,
    depths: np.ndarray | None = None,
    widths: np.ndarray | None = None,
    dips: np.ndarray | None = None,
    block_motions: np.ndarray | None = None,
    nu: float = 0.25,
) -> GridResult:
    """Search fault geometry and block motion against a velocity profile.

    Args:
        x_km: fault-perpendicular distance per station, negative west.
        v_parallel: fault-parallel velocity per station.
        sigma: per-station standard deviation (the MATLAB's ``err``).
        depths, widths, dips, block_motions: search axes. Defaults are the
            MATLAB's exact ranges.

    Returns:
        :class:`GridResult`, including how many dislocation calls were actually
        needed versus how many the MATLAB would have made.
    """
    depths = np.arange(0, 21, 1.0) if depths is None else np.asarray(depths, float)
    widths = np.arange(0, 31, 1.0) if widths is None else np.asarray(widths, float)
    dips = np.arange(70, 91, 1.0) if dips is None else np.asarray(dips, float)
    block_motions = (
        np.arange(0, 41, 1.0) if block_motions is None else np.asarray(block_motions, float)
    )

    x_km = np.asarray(x_km, float)
    v_parallel = np.asarray(v_parallel, float)
    sigma = np.asarray(sigma, float)
    if not (x_km.shape == v_parallel.shape == sigma.shape):
        raise ValueError("x_km, v_parallel and sigma must have the same shape")
    if np.any(sigma <= 0):
        raise ValueError("sigma must be positive")

    var = sigma**2
    inv_var = 1.0 / var
    trace_inv_cov = float(inv_var.sum())
    # inv(chol(diag(var))) is diagonal, so the weighting is just 1/sigma.
    w = 1.0 / sigma

    east = x_km >= 0  # the MATLAB's `com = find(xy(:,1)>=0)`

    dtype = np.dtype(
        [("depth", "f8"), ("width", "f8"), ("dip", "f8"), ("block_motion", "f8"),
         ("slip", "f8"), ("chi2", "f8"), ("reduced_chi2", "f8"), ("wrms", "f8")]
    )
    rows = np.empty(len(depths) * len(widths) * len(dips) * len(block_motions), dtype=dtype)

    # block_motion shifts the DATA, so build every shifted vector once.
    # (n_block, n_station)
    d_all = np.tile(v_parallel, (len(block_motions), 1))
    d_all[:, east] -= block_motions[:, None]

    k = 0
    calls = 0
    for depth in depths:
        for width in widths:
            for dip in dips:
                g = green_function(depth, width, dip, x_km, nu=nu)
                calls += 1

                # Vectorised over every block_motion at once: the Green's
                # function is constant here, which is the whole restructuring.
                gw = g * w
                gg = float(gw @ gw)
                if gg == 0.0:
                    slips = np.zeros(len(block_motions))
                else:
                    slips = (d_all * w) @ gw / gg

                resid = d_all - slips[:, None] * g          # (n_block, n_station)
                chi2 = (resid**2 * inv_var).sum(axis=1)
                n = resid.shape[1]
                wrms = np.sqrt((resid**2 * inv_var).sum(axis=1) / trace_inv_cov)

                m = len(block_motions)
                rows["depth"][k : k + m] = depth
                rows["width"][k : k + m] = width
                rows["dip"][k : k + m] = dip
                rows["block_motion"][k : k + m] = block_motions
                rows["slip"][k : k + m] = slips
                rows["chi2"][k : k + m] = chi2
                rows["reduced_chi2"][k : k + m] = chi2 / n
                rows["wrms"][k : k + m] = wrms
                k += m

    def _point(i: int) -> GridPoint:
        r = rows[i]
        return GridPoint(
            depth=float(r["depth"]), width=float(r["width"]), dip=float(r["dip"]),
            block_motion=float(r["block_motion"]), slip=float(r["slip"]),
            chi2=float(r["chi2"]), reduced_chi2=float(r["reduced_chi2"]),
            wrms=float(r["wrms"]),
        )

    best_w = int(np.argmin(rows["wrms"]))
    # The MATLAB selects the reduced chi-squared CLOSEST TO 1, not the smallest.
    best_c = int(np.argmin(np.abs(rows["reduced_chi2"] - 1.0)))

    return GridResult(
        best_wrms=_point(best_w),
        best_reduced_chi2=_point(best_c),
        points=rows,
        disloc_calls=calls,
        naive_calls=len(rows),
    )
