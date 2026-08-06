#!/usr/bin/env python3
"""Scan a run's FIN_*.SNX solutions for coherent multi-station motion.

WHY THIS EXISTS, AND WHY coord_repeatability.py IS NOT ENOUGH
This project's purpose is earthquake monitoring, and a real coseismic offset
is not one bad station — it is SEVERAL NEARBY stations moving together, often
by amounts well under any single-station outlier threshold. The first pass at
quality-checking this run's output (coord_repeatability.py) scanned for
stations exceeding 30 mm horizontal individually and concluded "no day is bad
network-wide." That conclusion was an artifact of the threshold: on 2025 DOY
126, FOURTEEN stations moved 8-30 mm in the same direction on the same day
(runbook §4b.11), and it was invisible to a check built to catch one bad
station rather than a coordinated shift.

WHAT DISTINGUISHES A REAL EVENT FROM A PROCESSING ARTIFACT
A real coseismic offset is a STEP: it persists in every subsequent daily
solution relative to the pre-event position, because the ground actually
moved. A processing artifact specific to one day's products or one day's
ambiguity resolution is a SPIKE: elevated on that day only, back to baseline
the next. This script flags coherent-motion days; TELLING THEM APART is a
manual read of the printed day-by-day series for the flagged stations, not
something this script decides for you.

For 2025 DOY 121-151, DOY 126 (14 stations), 129 (8) and 145 (13) all show
this pattern and all reverted completely the next day -- read as processing
artifacts, not seismic, and corroborated by the PHIVOLCS/USGS catalog showing
no recorded event on any of those three dates. DOY 147 carries a confirmed
M4.6 near General Nakar, Quezon and shows NO anomaly at the nearest stations
(POLI, MAUB, GUMA) -- consistent with M4.6 being below what daily static GNSS
resolves at tens of km, and a useful negative control: this scan does not
manufacture events out of ordinary noise.

WHAT THIS SCRIPT DOES NOT DO
It does not check the earthquake catalog itself, does not distinguish step
from spike automatically, and the NEIGHBOR_KM/THRESH_MM constants are tuned
for the ~135-station Luzon spacing, not validated for any other network.

Usage:
    scripts/network_coherence_scan.py                    # $S/LUZON/2025 by default
    scripts/network_coherence_scan.py '<glob of SNX.gz>'
"""
from __future__ import annotations

import collections
import glob
import gzip
import math
import os
import sys

DEFAULT_PATTERN = "$S/LUZON/2025/SOL/FIN_2025*.SNX.gz"
NEIGHBOR_KM = 120  # local network station spacing; excludes the fiducials by construction
THRESH_MM = 8.0  # roughly 2.5x median horizontal repeatability -- see coord_repeatability.py
COS_SIM_MIN = 0.5  # "same general direction", not opposite or orthogonal


def read_positions(path: str) -> dict[str, tuple[float, float, float]]:
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
            if len(parts) >= 9 and parts[1] in ("STAX", "STAY", "STAZ"):
                vals[parts[2]][parts[1]] = float(parts[8])
    return {s: (d["STAX"], d["STAY"], d["STAZ"]) for s, d in vals.items() if len(d) == 3}


def to_neu(dx: float, dy: float, dz: float, lat: float, lon: float) -> tuple[float, float, float]:
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

    series: dict[str, dict[str, tuple[float, float, float]]] = collections.defaultdict(dict)
    for path in files:
        doy = os.path.basename(path).split("FIN_2025")[1][:3]
        for sta, xyz in read_positions(path).items():
            series[sta][doy] = xyz

    mean = {
        sta: tuple(sum(p[i] for p in byday.values()) / len(byday) for i in range(3))
        for sta, byday in series.items()
    }

    def dist_km(a: str, b: str) -> float:
        return math.dist(mean[a], mean[b]) / 1000

    def offsets_for_day(doy: str) -> dict[str, tuple[float, float, float]]:
        out = {}
        for sta, byday in series.items():
            if doy not in byday:
                continue
            x, y, z = byday[doy]
            mx, my, mz = mean[sta]
            lon = math.atan2(my, mx)
            lat = math.atan2(mz, math.hypot(mx, my))
            out[sta] = to_neu(x - mx, y - my, z - mz, lat, lon)
        return out

    days = sorted({d for v in series.values() for d in v})
    print(f"{len(days)} days, {len(series)} stations, threshold {THRESH_MM} mm, "
          f"neighbor radius {NEIGHBOR_KM} km\n")

    any_flagged = False
    for doy in days:
        offs = offsets_for_day(doy)
        movers = {
            s: (n * 1000, e * 1000)
            for s, (n, e, u) in offs.items()
            if math.hypot(n, e) * 1000 > THRESH_MM
        }
        pairs = []
        names = sorted(movers)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if dist_km(a, b) > NEIGHBOR_KM:
                    continue
                na, ea = movers[a]
                nb, eb = movers[b]
                mag_a, mag_b = math.hypot(na, ea), math.hypot(nb, eb)
                cos_sim = (na * nb + ea * eb) / (mag_a * mag_b)
                if cos_sim > COS_SIM_MIN:
                    pairs.append((a, b, dist_km(a, b), cos_sim, mag_a, mag_b))
        if pairs:
            any_flagged = True
            stations_involved = sorted({s for a, b, *_ in pairs for s in (a, b)})
            print(f"DOY {doy}: {len(stations_involved)} station(s) moving coherently "
                  f"({', '.join(stations_involved)})")
            for a, b, d, c, ma, mb in sorted(pairs, key=lambda r: -r[3]):
                print(f"    {a}({ma:.0f}mm) <-> {b}({mb:.0f}mm)  {d:.0f} km apart, "
                      f"cos_sim={c:.2f}")
            print()

    if not any_flagged:
        print("No day shows two or more nearby stations moving coherently above threshold.")

    print("A flagged day is a SPIKE (processing artifact) if it reverts the next day, and a")
    print("STEP (real, worth investigating) if it persists. This script does not tell them")
    print("apart -- read the flagged stations' full day-by-day series before concluding either")
    print("way, and check the PHIVOLCS/USGS catalog for the date before ruling seismic in or out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
