#!/usr/bin/env python3
"""Day-to-day coordinate repeatability from a run's FIN_*.SNX solutions.

WHY THIS EXISTS
`Sessions finished: OK: 1 Error: 0` says the pipeline executed. It says nothing
about whether the numbers are any good — a BPE can complete cleanly and produce
a solution with centimetre scatter. Given how many defects in this campaign were
"a check that reports success without having inspected anything", the run needed
one check that looks at the output.

WHAT IT MEASURES, AND WHAT IT DOES NOT
Repeatability is PRECISION, not accuracy: the scatter of each station about its
own mean over the days processed. It will look excellent for a solution sitting
in the wrong reference frame, because every day is wrong in the same way. It
therefore does NOT validate the I20 frame and must not be cited as evidence that
these coordinates are comparable with the I14 series (runbook §1.4, §4b.6).

Expect, for daily double-difference solutions: horizontal 2-4 mm, vertical
6-10 mm. Markedly worse at ONE station is usually that station — antenna,
multipath, short sessions — rather than the configuration. If the configuration
were wrong, everything would degrade together, which is what makes a single
outlier reassuring rather than alarming.

Usage:
    scripts/coord_repeatability.py                     # $S/LUZON/2025 by default
    scripts/coord_repeatability.py '<glob of SNX.gz>'
"""
from __future__ import annotations

import collections
import glob
import gzip
import math
import os
import sys

DEFAULT_PATTERN = "$S/LUZON/2025/SOL/FIN_2025*.SNX.gz"
MIN_DAYS = 3  # below this, an RMS about the mean is not worth printing


def read_positions(path: str) -> dict[str, tuple[float, float, float]]:
    """Return {station: (X, Y, Z)} from a SINEX SOLUTION/ESTIMATE block."""
    vals: dict[str, dict[str, float]] = collections.defaultdict(dict)
    in_block = False
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            if line.startswith("+SOLUTION/ESTIMATE"):
                in_block = True
                continue
            if line.startswith("-SOLUTION/ESTIMATE"):
                break
            if not in_block or line.startswith("*"):
                continue
            parts = line.split()
            # index type code pt soln epoch unit s value stddev
            if len(parts) >= 9 and parts[1] in ("STAX", "STAY", "STAZ"):
                vals[parts[2]][parts[1]] = float(parts[8])
    return {
        sta: (d["STAX"], d["STAY"], d["STAZ"])
        for sta, d in vals.items()
        if len(d) == 3
    }


def to_neu(dx: float, dy: float, dz: float, lat: float, lon: float) -> tuple[float, ...]:
    """Rotate an ECEF offset into local North/East/Up at the given geodetic point."""
    sl, cl = math.sin(lon), math.cos(lon)
    sb, cb = math.sin(lat), math.cos(lat)
    return (
        -sb * cl * dx - sb * sl * dy + cb * dz,
        -sl * dx + cl * dy,
        cb * cl * dx + cb * sl * dy + sb * dz,
    )


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else os.path.expandvars(DEFAULT_PATTERN)
    files = sorted(glob.glob(pattern))
    if not files:
        print(f"no solutions matched: {pattern}", file=sys.stderr)
        return 1

    # station -> {doy: (X, Y, Z)}
    series: dict[str, dict[str, tuple[float, float, float]]] = collections.defaultdict(dict)
    for path in files:
        doy = os.path.basename(path).split("FIN_2025")[1][:3]
        for sta, xyz in read_positions(path).items():
            series[sta][doy] = xyz

    days = sorted({d for byday in series.values() for d in byday})
    print(f"days: {len(days)}  ({days[0]}-{days[-1]})   stations: {len(series)}\n")
    print(f"{'STA':<6}{'n':>3}  {'RMS N':>8}{'RMS E':>8}{'RMS U':>8}   (mm about the mean)")

    rows = []
    for sta, byday in sorted(series.items()):
        if len(byday) < MIN_DAYS:
            continue
        pos = list(byday.values())
        mean = [sum(p[i] for p in pos) / len(pos) for i in range(3)]
        x, y, z = mean
        lon = math.atan2(y, x)
        lat = math.atan2(z, math.hypot(x, y))
        acc = [0.0, 0.0, 0.0]
        for p in pos:
            for i, v in enumerate(to_neu(*(p[i] - mean[i] for i in range(3)), lat, lon)):
                acc[i] += v * v
        rms = [math.sqrt(a / len(pos)) * 1000 for a in acc]
        rows.append((sta, len(pos), rms))
        print(f"{sta:<6}{len(pos):>3}  {rms[0]:8.1f}{rms[1]:8.1f}{rms[2]:8.1f}")

    if rows:
        def median(i: int) -> float:
            return sorted(r[2][i] for r in rows)[len(rows) // 2]

        print(f"\nmedian: N {median(0):.1f} mm   E {median(1):.1f} mm   U {median(2):.1f} mm")
        print("\nPRECISION ONLY — says nothing about the reference frame. See the")
        print("module docstring before quoting these numbers anywhere.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
