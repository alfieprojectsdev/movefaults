#!/usr/bin/env python3
"""Compare two weekly SINEX solutions by Helmert alignment, not by subtraction.

WHY THIS EXISTS
The PHREF 2025 reprocessing (BSW 5.4, Linux, 33-41 stations) has to be checked
against PHIVOLCS production (BSW 5.2, Windows, ~93 stations). A raw coordinate
difference would be meaningless: the two solutions realise their datum
differently -- different software version, different network geometry,
different constraints -- so the difference is dominated by translation,
rotation and scale that say nothing about whether the processing is sound.

So: estimate a 7-parameter similarity transformation on the common stations,
REPORT THE PARAMETERS (a large scale or rotation is itself a finding), and then
report the post-fit residuals per station rotated into local North/East/Up.

THIS IS AN AGREEMENT TEST, NOT A REPRODUCTION TEST. It cannot be bit-for-bit
and must not be presented as though it could. The question it answers is
whether two independent solutions agree to within the precision either claims.

READING THE OUTPUT
  Tx/Ty/Tz  translation, mm      -- datum origin offset
  s         scale, ppb           -- a real scale difference is a red flag
  Rx/Ry/Rz  rotation, mas        -- orientation
  residuals per station in N/E/U, mm, after removing the above

  few mm, unstructured        -> the port reproduces production within noise
  systematic in Up only       -> troposphere / loading model difference
  spatially organised         -> network-geometry effect from the smaller set
  one or two stations far out  -> station-specific metadata; check .STA/BLQ

Usage:
    scripts/compare_weekly_solutions.py --ours WKG_2375.SNX --theirs WK_2375.SNX
    scripts/compare_weekly_solutions.py --ours A.SNX --theirs B.SNX --format md
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np

A_WGS84 = 6378137.0
F_WGS84 = 1.0 / 298.257223563


def read_sinex(path: Path) -> tuple[dict[str, np.ndarray], str]:
    """Return {station: xyz} and the header line.

    Only STAX/STAY/STAZ are taken. A station is kept only if all three
    components are present -- a partial station would silently bias the fit.
    """
    txt = path.read_text(errors="replace").splitlines()
    header = txt[0] if txt else ""
    comp: dict[str, dict[str, float]] = {}
    inblk = False
    for line in txt:
        if line.startswith("+SOLUTION/ESTIMATE"):
            inblk = True
            continue
        if line.startswith("-SOLUTION/ESTIMATE"):
            break
        if not inblk or line.startswith("*"):
            continue
        f = line.split()
        # idx TYPE CODE PT SOLN REF_EPOCH UNIT S ESTIMATE STD_DEV
        if len(f) < 9 or f[1] not in ("STAX", "STAY", "STAZ"):
            continue
        try:
            comp.setdefault(f[2].upper(), {})[f[1]] = float(f[8])
        except ValueError:
            continue
    out = {
        s: np.array([v["STAX"], v["STAY"], v["STAZ"]])
        for s, v in comp.items()
        if {"STAX", "STAY", "STAZ"} <= v.keys()
    }
    return out, header


def xyz_to_neu_rotation(xyz: np.ndarray) -> np.ndarray:
    """Rotation taking a Cartesian delta to local North/East/Up at this site."""
    x, y, z = xyz
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    lat = math.atan2(z, p * (1 - (2 * F_WGS84 - F_WGS84**2)))
    for _ in range(5):  # iterate the geodetic latitude
        e2 = 2 * F_WGS84 - F_WGS84**2
        n = A_WGS84 / math.sqrt(1 - e2 * math.sin(lat) ** 2)
        lat = math.atan2(z + e2 * n * math.sin(lat), p)
    sla, cla, slo, clo = (
        math.sin(lat), math.cos(lat), math.sin(lon), math.cos(lon),
    )
    return np.array([
        [-sla * clo, -sla * slo,  cla],   # North
        [-slo,        clo,        0.0],   # East
        [ cla * clo,  cla * slo,  sla],   # Up
    ])


def helmert(ours: np.ndarray, theirs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """7-parameter fit taking `ours` onto `theirs`.

    Returns (params, residuals). params = [Tx,Ty,Tz (m), s (unitless),
    Rx,Ry,Rz (rad)]. Residuals are theirs - transformed(ours), in metres.
    """
    n = len(ours)
    A = np.zeros((3 * n, 7))
    L = (theirs - ours).reshape(-1)
    for i, (x, y, z) in enumerate(ours):
        A[3 * i + 0] = [1, 0, 0, x, 0.0,  z,  -y]
        A[3 * i + 1] = [0, 1, 0, y, -z,  0.0,  x]
        A[3 * i + 2] = [0, 0, 1, z, y,   -x,  0.0]
    p, *_ = np.linalg.lstsq(A, L, rcond=None)
    res = (L - A @ p).reshape(n, 3)
    return p, res


def helmert_robust(ours, theirs, sites, max_iter=10, k=4.0, floor_mm=15.0):
    """Iteratively reject stations, refit, repeat until the set is stable.

    A single badly-placed station drags the 7-parameter fit and inflates the
    residuals of every OTHER station, so an unrejected outlier does not merely
    show up as itself -- it corrupts the whole week. AIUB document exactly this
    for HELMR1: "if one of the stations has an exceptionally wrong coordinate,
    the residuals for all stations may exceed the thresholds".

    Rejection is at k sigma OR `floor_mm`, whichever is LARGER, so a very clean
    week does not start discarding good stations for being 4 sigma from an
    already-tight mean.
    """
    keep = np.ones(len(ours), dtype=bool)
    rejected: list[str] = []
    for _ in range(max_iter):
        p, res = helmert(ours[keep], theirs[keep])
        full = ((theirs - ours).reshape(-1) - _design(ours) @ p).reshape(-1, 3)
        h = np.hypot(full[:, 0], full[:, 1]) * 1000.0
        sigma = float(np.sqrt(np.mean(h[keep] ** 2)))
        thr = max(k * sigma, floor_mm)
        new = keep & (h <= thr)
        if new.sum() < 5 or (new == keep).all():
            break
        rejected += [sites[i] for i in range(len(sites)) if keep[i] and not new[i]]
        keep = new
    p, _ = helmert(ours[keep], theirs[keep])
    res_all = ((theirs - ours).reshape(-1) - _design(ours) @ p).reshape(-1, 3)
    return p, res_all, keep, rejected


def _design(xyz: np.ndarray) -> np.ndarray:
    n = len(xyz)
    A = np.zeros((3 * n, 7))
    for i, (x, y, z) in enumerate(xyz):
        A[3 * i + 0] = [1, 0, 0, x, 0.0,  z,  -y]
        A[3 * i + 1] = [0, 1, 0, y, -z,  0.0,  x]
        A[3 * i + 2] = [0, 0, 1, z, y,   -x,  0.0]
    return A


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ours", type=Path, required=True)
    ap.add_argument("--theirs", type=Path, required=True)
    ap.add_argument("--label", default="", help="week label for the header line")
    ap.add_argument("--format", choices=("txt", "md"), default="txt")
    ap.add_argument("--quiet", action="store_true", help="summary line only")
    args = ap.parse_args()

    ours, h_ours = read_sinex(args.ours)
    theirs, h_theirs = read_sinex(args.theirs)
    common = sorted(set(ours) & set(theirs))
    if len(common) < 4:
        print(f"FATAL: only {len(common)} common stations; a 7-parameter fit "
              f"needs at least 3 and is meaningless below ~5.", file=sys.stderr)
        return 1

    xyz_o = np.array([ours[s] for s in common])
    xyz_t = np.array([theirs[s] for s in common])
    p, res, keep, rejected = helmert_robust(xyz_o, xyz_t, common)
    res = res.reshape(len(common), 3)

    neu = np.array([xyz_to_neu_rotation(xyz_o[i]) @ res[i] for i in range(len(common))])
    neu_mm = neu * 1000.0

    if not args.quiet:
        print(f"# Weekly comparison {args.label}".rstrip())
        print(f"  ours  : {args.ours.name}   {len(ours)} stations")
        print(f"  theirs: {args.theirs.name}   {len(theirs)} stations")
        print(f"  common: {len(common)}   ours-only: {len(set(ours)-set(theirs))}"
              f"   theirs-only: {len(set(theirs)-set(ours))}")
        print(f"  used in fit: {int(keep.sum())}"
              + (f"   REJECTED: {' '.join(rejected)}" if rejected else "   rejected: none"))
        print()
        print("  Helmert parameters (ours -> theirs)")
        print(f"    Tx {p[0]*1000:9.2f} mm    Ty {p[1]*1000:9.2f} mm    "
              f"Tz {p[2]*1000:9.2f} mm")
        print(f"    scale {p[3]*1e9:8.2f} ppb")
        r2m = 180.0 / math.pi * 3600.0 * 1000.0   # rad -> milliarcsec
        print(f"    Rx {p[4]*r2m:9.3f} mas   Ry {p[5]*r2m:9.3f} mas   "
              f"Rz {p[6]*r2m:9.3f} mas")
        print()
        hdr = ("site", "N mm", "E mm", "U mm", "H mm")
        rows = []
        for i, s in enumerate(common):
            n_, e_, u_ = neu_mm[i]
            rows.append((s, f"{n_:.1f}", f"{e_:.1f}", f"{u_:.1f}",
                         f"{math.hypot(n_, e_):.1f}"))
        rows.sort(key=lambda r: -float(r[4]))
        if args.format == "md":
            print("| " + " | ".join(hdr) + " |")
            print("|" + "|".join("---" for _ in hdr) + "|")
            for r in rows:
                print("| " + " | ".join(r) + " |")
        else:
            print("  " + "  ".join(h.rjust(7) for h in hdr))
            for r in rows:
                print("  " + "  ".join(c.rjust(7) for c in r))
        print()

    rms = lambda v: float(np.sqrt(np.mean(v**2)))  # noqa: E731
    kept_mm = neu_mm[keep]
    hz = np.hypot(kept_mm[:, 0], kept_mm[:, 1])
    neu_mm = kept_mm
    common_kept = [c for i, c in enumerate(common) if keep[i]]
    print(f"  RMS  N {rms(neu_mm[:,0]):6.2f}  E {rms(neu_mm[:,1]):6.2f}  "
          f"U {rms(neu_mm[:,2]):6.2f} mm   horizontal {rms(hz):6.2f} mm"
          f"   (n={int(keep.sum())} of {len(common)})")
    worst = int(np.argmax(hz))
    print(f"  worst horizontal (kept): {common_kept[worst]} {hz[worst]:.1f} mm"
          + (f"   [rejected: {' '.join(rejected)}]" if rejected else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
