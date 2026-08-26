"""
Okada elastic half-space dislocation, callable from Python on Linux.

WHY THIS EXISTS
---------------
Every dislocation model under ``analysis/`` routes through ``disloc.mexw64`` --
a Windows-only compiled MATLAB binary that cannot run on the R740 and cannot be
rebuilt without MATLAB. That single file is why fault-parameter modelling still
happens on somebody's Windows desktop.

The C source was in the tree the whole time, at
``analysis/08 Bootstrapping/disloc.c``: Okada's dislocation, C version by
P. Cervelli. Removing the MATLAB entry point is all it took.

This module builds that source into a shared library on first use and calls it
through ``ctypes``. No MATLAB, no compiler toolchain beyond ``cc``, no build
step in the install.

CALLING CONVENTION
------------------
Taken from the ``mexFunction`` that was removed, so it matches what every
existing ``.m`` script passes:

``model``  ``(10, n)`` -- one dislocation per column::

    [length, width, depth, dip, strike, east, north,
     strike_slip, dip_slip, opening]

``coords`` ``(2, m)`` -- one station per column, ``[x; y]``.

Returns ``(3, m)`` -- ``[E; N; U]`` displacement per station.
"""
from __future__ import annotations

import ctypes
import subprocess
import threading
from pathlib import Path

import numpy as np

_SRC_DIR = Path(__file__).parent / "_disloc"
_SOURCE = _SRC_DIR / "disloc_core.c"
_LIB = _SRC_DIR / "libdisloc.so"

_lock = threading.Lock()
_handle: ctypes.CDLL | None = None


class DislocBuildError(RuntimeError):
    """The C core could not be compiled. Names the compiler output."""


class UnphysicalModel(ValueError):
    """One or more dislocations failed ``GoodModel()`` and were skipped.

    The original signalled this with ``mexWarnMsgTxt`` and carried on with the
    offending dislocation contributing nothing. Raising instead of warning is
    deliberate: a model silently missing a fault segment produces a plausible
    displacement field that is wrong, and that is the failure mode hardest to
    notice downstream. Pass ``strict=False`` to get the original behaviour.
    """


def _build() -> None:
    cmd = ["cc", "-O2", "-fPIC", "-shared", "-o", str(_LIB), str(_SOURCE), "-lm"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 or not _LIB.exists():
        raise DislocBuildError(
            "Could not build the disloc core.\n"
            f"  command: {' '.join(cmd)}\n"
            f"  stderr : {proc.stderr.strip()[:800]}"
        )


def _load() -> ctypes.CDLL:
    """Load the shared library, building it if absent or stale."""
    global _handle
    with _lock:
        if _handle is not None:
            return _handle
        if not _LIB.exists() or _LIB.stat().st_mtime < _SOURCE.stat().st_mtime:
            _build()
        lib = ctypes.CDLL(str(_LIB))
        lib.Disloc.restype = None
        lib.Disloc.argtypes = [
            np.ctypeslib.ndpointer(np.float64, flags="C_CONTIGUOUS"),  # output
            np.ctypeslib.ndpointer(np.float64, flags="C_CONTIGUOUS"),  # model
            np.ctypeslib.ndpointer(np.float64, flags="C_CONTIGUOUS"),  # coords
            ctypes.c_double,  # nu
            ctypes.c_int,     # NumStat
            ctypes.c_int,     # NumDisl
            ctypes.c_int,     # RefStat
        ]
        lib.disloc_last_unphysical.restype = ctypes.c_int
        lib.disloc_last_unphysical.argtypes = []
        _handle = lib
        return lib


def disloc(
    model: np.ndarray,
    coords: np.ndarray,
    nu: float = 0.25,
    ref_station: int = 0,
    *,
    strict: bool = True,
) -> np.ndarray:
    """Surface displacements from rectangular dislocations in an elastic half-space.

    Args:
        model: ``(10, n)`` array, one dislocation per column.
        coords: ``(2, m)`` array, one station per column.
        nu: Poisson's ratio. The MATLAB call sites all pass ``0.25``.
        ref_station: 1-based station index to reference displacements against;
            ``0`` for absolute. When non-zero the reference column is dropped
            from the result, matching the original's ``mxSetN`` shrink.
        strict: raise ``UnphysicalModel`` if any dislocation is rejected.

    Returns:
        ``(3, m)`` array of ``[E; N; U]``, or ``(3, m - 1)`` when
        ``ref_station`` is set.

    Raises:
        ValueError: on a wrong input shape.
        UnphysicalModel: if ``strict`` and any dislocation failed ``GoodModel``.
        DislocBuildError: if the C core cannot be compiled.
    """
    model = np.ascontiguousarray(model, dtype=np.float64)
    coords = np.ascontiguousarray(coords, dtype=np.float64)

    if model.ndim != 2 or model.shape[0] != 10:
        raise ValueError(f"model must be (10, n); got {model.shape}")
    if coords.ndim != 2 or coords.shape[0] != 2:
        raise ValueError(f"coords must be (2, m); got {coords.shape}")

    n_disl = model.shape[1]
    n_stat = coords.shape[1]
    if not 0 <= ref_station <= n_stat:
        raise ValueError(f"ref_station must be 0..{n_stat}; got {ref_station}")

    lib = _load()
    # The C core reads all three arrays column-major, so pass Fortran order
    # flattened -- the same bytes MATLAB would have handed it.
    out = np.zeros(3 * n_stat, dtype=np.float64)
    lib.Disloc(
        out,
        np.asfortranarray(model).ravel(order="F"),
        np.asfortranarray(coords).ravel(order="F"),
        ctypes.c_double(nu),
        ctypes.c_int(n_stat),
        ctypes.c_int(n_disl),
        ctypes.c_int(ref_station),
    )

    rejected = lib.disloc_last_unphysical()
    if rejected and strict:
        raise UnphysicalModel(
            f"{rejected} of {n_disl} dislocation(s) rejected by GoodModel and "
            "skipped: negative length/width/depth, or the fault breaks the "
            "surface. Pass strict=False to skip them silently."
        )

    result = out.reshape((3, n_stat), order="F")
    if ref_station:
        result = np.delete(result, ref_station - 1, axis=1)
    return result


def last_unphysical_count() -> int:
    """Dislocations rejected by the most recent :func:`disloc` call."""
    return _load().disloc_last_unphysical()
