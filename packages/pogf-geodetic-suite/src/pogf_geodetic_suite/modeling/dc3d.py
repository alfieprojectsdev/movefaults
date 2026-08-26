"""
Okada (1992) DC3D -- displacement, strain and tilt at depth, without MATLAB.

WHAT THIS UNLOCKS
-----------------
`_disloc/` (PR #147) replaced `disloc.mexw64`, which `03 Yu` and
`08 Bootstrapping` use. It computes SURFACE displacement only -- Okada 1985.

`disloc3d.mexw64` is the other MATLAB binary, and the only one left. It is
used by `analysis/06 Ku-en Dislocation Model/`, which is the code path behind
the newest published Philippine results: `inversion and monte carlo` at
900,000 samples for Central Luzon, Masbate and Northern Leyte
(`docs/project_documentation/dislocation_model_results.md`). Reproducing those
runs on Linux needs DC3D, which is Okada 1992 -- internal deformation, and a
different formulation from the 1985 surface solution.

This module is that. The C transliteration is in `_dc3d/dc3d_core.c`.

TWO IMPLEMENTATIONS, AND WHY YOU CAN CHOOSE
-------------------------------------------
`dc3d(...)`                   Okada's original. No copyleft.
`dc3d(..., quadrant_fix=True)` Okada's, wrapped in A.M. Bradley's
                              cancellation-error fix. **EPL 1.0.**

Stock DC3D loses relative precision where ``sqrt(eta**2 + q**2) / R`` is
small -- inside four cones extending from the corners of the rectangle. Okada
substitutes around the exact singular rays, but not around their
neighbourhoods. Bradley's fix evaluates in the first quadrant and reflects.

The default is the unencumbered core, because whether our geometries fall in
those cones is an empirical question that `test_dc3d.py` answers rather than
assumes. Turn the fix on when the geometry needs it and accept that the
resulting binary contains an EPL file.

ATTRIBUTION
-----------
Okada, Y. (1992). Internal deformation due to shear and tensile faults in a
half-space. *Bulletin of the Seismological Society of America*, 82(2),
1018-1040. Original Fortran DC3D coded by Y. Okada, September 1990 (NIED).

Bradley, A.M. (2012). Cancellation-error fix, in Stanford CDFM `dc3dm` v0.3,
`external/dc3omp.f`. Eclipse Public License 1.0.

See `docs/external-sources/README.md`.
"""
from __future__ import annotations

import ctypes
import subprocess
import threading
from pathlib import Path

import numpy as np

_SRC_DIR = Path(__file__).parent / "_dc3d"
_CORE = _SRC_DIR / "dc3d_core.c"
_QUAD = _SRC_DIR / "dc3d_quadrant.c"
_LIB = _SRC_DIR / "libdc3d.so"

_lock = threading.Lock()
_handle: ctypes.CDLL | None = None

#: Return codes from the C layer.
_RC_OK = 0
_RC_SINGULAR = 1
_RC_POSITIVE_Z = 2


class DC3DBuildError(RuntimeError):
    """The C core could not be compiled. Carries the compiler output."""


class SingularObservation(ValueError):
    """The observation point coincides with a fault edge (r == 0).

    The Fortran returns zeros here. Zeros are a plausible displacement, so
    they are indistinguishable from "no deformation" downstream -- hence an
    exception by default. ``strict=False`` restores the original behaviour.
    """


def _sources(quadrant_fix: bool) -> list[Path]:
    return [_CORE, _QUAD] if quadrant_fix else [_CORE]


def _build() -> None:
    """Compile both files. The quadrant fix is always built, never always used.

    Building it unconditionally keeps one shared library rather than two, and
    the choice is then made per call. A caller who must not ship EPL code at
    all should delete ``dc3d_quadrant.c``; the core builds and runs without it.
    """
    srcs = [str(p) for p in _sources(quadrant_fix=_QUAD.exists())]
    cmd = ["cc", "-O2", "-fPIC", "-shared", "-o", str(_LIB), *srcs, "-lm"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not _LIB.exists():
        raise DC3DBuildError(
            "Could not build the DC3D core.\n"
            f"  command: {' '.join(cmd)}\n"
            f"  stderr : {proc.stderr.strip()[:800]}"
        )


def _stale() -> bool:
    if not _LIB.exists():
        return True
    lib_mtime = _LIB.stat().st_mtime
    return any(p.exists() and p.stat().st_mtime > lib_mtime for p in (_CORE, _QUAD))


def _load() -> ctypes.CDLL:
    global _handle
    with _lock:
        if _handle is not None:
            return _handle
        if _stale():
            _build()
        lib = ctypes.CDLL(str(_LIB))
        sig = [
            ctypes.c_char,    # space
            ctypes.c_double,  # alpha
            ctypes.c_double, ctypes.c_double, ctypes.c_double,   # x, y, z
            ctypes.c_double,  # depth
            ctypes.c_double,  # dip
            ctypes.c_double, ctypes.c_double,   # al1, al2
            ctypes.c_double, ctypes.c_double,   # aw1, aw2
            ctypes.c_double, ctypes.c_double, ctypes.c_double,   # disl1..3
            np.ctypeslib.ndpointer(np.float64, flags="C_CONTIGUOUS"),  # out[12]
        ]
        lib.dc3d.restype = ctypes.c_int
        lib.dc3d.argtypes = sig
        if hasattr(lib, "dc3d_q"):
            lib.dc3d_q.restype = ctypes.c_int
            lib.dc3d_q.argtypes = sig
        _handle = lib
        return lib


def has_quadrant_fix() -> bool:
    """Whether Bradley's EPL-licensed fix is present in the built library."""
    return hasattr(_load(), "dc3d_q")


def alpha_from_poisson(nu: float = 0.25) -> float:
    """Okada's ``alpha = (lambda + mu) / (lambda + 2*mu)``, from Poisson's ratio.

    For a Poisson solid (``nu = 0.25``) this is ``2/3``, which is the value
    `06 Ku-en`'s ``make_G.m`` passes to ``disloc3d`` as ``.25`` for ``nu``.
    """
    return 1.0 / (2.0 * (1.0 - nu))


def dc3d(
    x: float,
    y: float,
    z: float,
    depth: float,
    dip: float,
    al: tuple[float, float],
    aw: tuple[float, float],
    disl: tuple[float, float, float],
    *,
    alpha: float = 2.0 / 3.0,
    half_space: bool = True,
    quadrant_fix: bool = False,
    strict: bool = True,
) -> np.ndarray:
    """Displacement and its gradients at one observation point.

    Args:
        x, y, z:   Observation point. ``z`` must be <= 0 (below the surface).
        depth:     Depth of the fault reference point (positive down).
        dip:       Dip angle in degrees.
        al:        ``(al1, al2)`` fault length along strike, as
                   ``(-strike, +strike)`` offsets from the reference point.
        aw:        ``(aw1, aw2)`` fault width, as ``(downdip, updip)``.
        disl:      ``(strike_slip, dip_slip, tensile)``.
        alpha:     Medium constant; see :func:`alpha_from_poisson`.
        half_space: ``True`` for a half-space, ``False`` for a whole space.
        quadrant_fix: Use Bradley's EPL-licensed fix. See the module docstring.
        strict:    Raise on a singular observation point rather than returning
                   zeros.

    Returns:
        ``(12,)`` array: ``[ux, uy, uz, uxx, uyx, uzx, uxy, uyy, uzy,
        uxz, uyz, uzz]`` -- the Fortran's ``U`` ordering, unchanged.

    Raises:
        ValueError: if ``z > 0``, which is outside the model's domain.
        SingularObservation: if ``strict`` and the point is on a fault edge.
    """
    lib = _load()
    if quadrant_fix and not hasattr(lib, "dc3d_q"):
        raise RuntimeError(
            "quadrant_fix=True but dc3d_quadrant.c is not built. It is EPL 1.0 "
            "and may have been removed deliberately; see the module docstring."
        )

    out = np.zeros(12, dtype=np.float64)
    fn = lib.dc3d_q if quadrant_fix else lib.dc3d
    space = b"H" if half_space else b"W"

    rc = fn(
        space, float(alpha),
        float(x), float(y), float(z), float(depth), float(dip),
        float(al[0]), float(al[1]), float(aw[0]), float(aw[1]),
        float(disl[0]), float(disl[1]), float(disl[2]),
        out,
    )
    if rc == _RC_POSITIVE_Z:
        raise ValueError(
            f"z must be <= 0 (below the free surface); got z={z}. "
            "The half-space solution is not defined above the surface."
        )
    if rc == _RC_SINGULAR and strict:
        raise SingularObservation(
            f"Observation point ({x}, {y}, {z}) is singular for this fault "
            "(r == 0 -- it lies on a fault edge). The original returns zeros, "
            "which is indistinguishable from no deformation; pass strict=False "
            "for that behaviour."
        )
    return out


def dc3d_grid(
    stations: np.ndarray,
    depth: float,
    dip: float,
    al: tuple[float, float],
    aw: tuple[float, float],
    disl: tuple[float, float, float],
    **kwargs,
) -> np.ndarray:
    """:func:`dc3d` over many observation points.

    Args:
        stations: ``(n, 3)`` array of ``(x, y, z)``.

    Returns:
        ``(n, 12)`` array, one row per station.

    The loop is in Python because DC3D is called once per station per fault
    patch and the C call dominates. If this ever becomes the bottleneck, the
    fix is a batched C entry point, not a faster Python loop.
    """
    pts = np.asarray(stations, dtype=np.float64)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(f"stations must be (n, 3); got {pts.shape}")
    return np.array(
        [dc3d(px, py, pz, depth, dip, al, aw, disl, **kwargs) for px, py, pz in pts]
    )
