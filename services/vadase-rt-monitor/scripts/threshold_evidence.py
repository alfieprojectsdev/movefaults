"""Measure the VADASE alarm threshold against real captures.

Produces every figure in docs/project_documentation/vadase_threshold_evidence.md.
The captures are PHIVOLCS field data and are not in the repository; point --data
at the directory that holds them (services/vadase-rt-monitor/data, git-ignored).

Run from services/vadase-rt-monitor:

    PYTHONPATH=. uv run python scripts/threshold_evidence.py --data data

Horizontal speed is sqrt(vE^2 + vN^2) from $GNLVM, parsed by the service's own
parser, so the numbers are what the detector would see. Event origins are from
the USGS catalogue (earthquake.usgs.gov/fdsnws/event/1), not from staff labels.
"""

from __future__ import annotations

import argparse
import glob
import math
import statistics as st
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from src.parsers.nmea_parser import NMEAChecksumError, parse_lvm

THRESHOLD_MM_S = 15.0  # config/stations.yml, threshold_mm_s for PBIS and BOST


@dataclass
class Event:
    origin: str  # UTC, ISO 8601, from USGS
    mag: str
    lat: float
    lon: float
    depth_km: float


@dataclass
class Capture:
    name: str
    pattern: str
    station_lat: float  # docs/bern52/crd_catalog.csv
    station_lon: float
    staff_label: str
    events: list[Event] = field(default_factory=list)


CAPTURES = [
    Capture(
        "TUA2 2025-10-06",
        "NMEA_TUA2 LDM_20251006_150000/*.rtl",
        17.7350,
        121.4552,
        "anomalous spike",
    ),  # USGS: no M4+ within 1000 km, 14:00-16:30 UTC
    Capture(
        "BOST 2023-12-02",
        "NMEA_BOST LDM_20231202_140000/*.rtl",
        7.8659,
        126.3797,
        "EQ-related",
        [Event("2023-12-02T14:37:04", "7.6 Mww", 8.5266, 126.4161, 40.0)],
    ),
    Capture(
        "PBIS 2023-12-03",
        "NMEA_PBIS LDM_20231203_140000/*.rtl",
        8.1892,
        126.3539,
        "EQ-related",
        [Event("2023-12-03T14:35:56", "6.0 Mww", 8.7320, 126.8230, 13.0)],
    ),
    Capture(
        "DGOS 2025-10-09/10",
        "NMEA_DGOS_10102025/*.rtl",
        6.7447,
        125.3560,
        "EQ-related",
        [
            Event("2025-10-10T01:43:59", "7.4 Mww", 7.2866, 126.6902, 59.4),
            Event("2025-10-10T11:12:05", "6.7 Mww", 7.2127, 126.6578, 47.0),
        ],
    ),
    Capture(
        "DGOS 2026-01-28",
        "DGOS_NMEA_01282026/*.rtl",
        6.7447,
        125.3560,
        "unlabelled",
        [
            Event("2026-01-28T06:47:01", "5.9 mb", 6.4317, 123.7410, 16.0),
            Event("2026-01-28T08:38:47", "5.6 mb", 6.5064, 123.6429, 10.0),
            Event("2026-01-28T01:41:49", "5.4 mb", 6.5110, 123.8484, 10.0),
        ],
    ),
]


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, l1, p2, l2 = map(math.radians, (lat1, lon1, lat2, lon2))
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin((l2 - l1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))


def percentile(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    k = (len(xs) - 1) * p / 100
    f, c = math.floor(k), math.ceil(k)
    return xs[f] if f == c else xs[f] + (xs[c] - xs[f]) * (k - f)


def load(data: Path, pattern: str) -> tuple[list[tuple[datetime, float, float]], int]:
    """(timestamp, horizontal mm/s, cq mm/s) per $GNLVM, and the count rejected."""
    rows, rejected = [], 0
    for fn in sorted(glob.glob(str(data / pattern))):
        text = Path(fn).read_bytes().decode("ascii", "replace").replace("\r", "")
        for line in text.split("\n"):
            if not line.startswith(("$GNLVM", "$GPLVM")):
                continue
            try:
                r = parse_lvm(line)
            except NMEAChecksumError:  # parse_lvm raises on a bad checksum
                rejected += 1
                continue
            if r is None:
                rejected += 1
                continue
            rows.append((r["timestamp"], math.hypot(r["vE"], r["vN"]) * 1000.0, r["cq"] * 1000.0))
    rows.sort()
    return rows, rejected


def longest_run(rows: list[tuple[datetime, float, float]]) -> int:
    """Longest run of consecutive (1 s apart) readings at or above the threshold."""
    best = run = 0
    prev = None
    for t, h, _ in rows:
        if h >= THRESHOLD_MM_S:
            run = run + 1 if prev is not None and run and (t - prev).total_seconds() <= 1.5 else 1
        else:
            run = 0
        best = max(best, run)
        prev = t
    return best


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True, help="directory holding the captures")
    args = ap.parse_args()

    for cap in CAPTURES:
        rows, rejected = load(args.data, cap.pattern)
        if not rows:
            print(f"\n== {cap.name}: NO READINGS under {args.data / cap.pattern}")
            continue
        vh = [h for _, h, _ in rows]
        cq = [c for _, _, c in rows]
        gaps = [(b[0] - a[0]).total_seconds() for a, b in pairwise(rows)]
        over = [r for r in rows if r[1] >= THRESHOLD_MM_S]
        peak = max(rows, key=lambda r: r[1])
        print(f"\n== {cap.name}  (staff label: {cap.staff_label})")
        print(
            f"   {rows[0][0]:%Y-%m-%d %H:%M:%S} to {rows[-1][0]:%Y-%m-%d %H:%M:%S} UTC, "
            f"{len(rows)} readings, {rejected} rejected, "
            f"{sum(1 for g in gaps if g <= 1.5)}/{len(gaps)} intervals at 1 s"
        )
        print(
            f"   horizontal mm/s: median {st.median(vh):.2f}  p99 {percentile(vh, 99):.2f}  "
            f"p99.9 {percentile(vh, 99.9):.2f}  max {peak[1]:.2f} at {peak[0]:%H:%M:%S}"
        )
        print(f"   cq mm/s: median {st.median(cq):.1f}  max {max(cq):.1f}")
        print(
            f"   readings >= {THRESHOLD_MM_S:g}: {len(over)}   longest consecutive run: {longest_run(rows)}"
        )
        if over:
            print(
                f"   cq on those readings: median {st.median(c for _, _, c in over):.1f}  "
                f"max {max(c for _, _, c in over):.1f}  min {min(c for _, _, c in over):.1f}"
            )

        accounted = 0
        for ev in cap.events:
            o = datetime.fromisoformat(ev.origin).replace(tzinfo=UTC)
            pre = [h for t, h, _ in rows if o - timedelta(minutes=30) <= t < o]
            win = [r for r in rows if o <= r[0] <= o + timedelta(minutes=10)]
            hits = [r for r in win if r[1] >= THRESHOLD_MM_S]
            accounted += len(hits)
            km = haversine_km(cap.station_lat, cap.station_lon, ev.lat, ev.lon)
            pk = max(win, key=lambda r: r[1]) if win else None
            pre_s = f"pre-event max {max(pre):.2f}" if pre else "no pre-event window"
            pk_s = f"peak {pk[1]:.2f} at +{(pk[0] - o).total_seconds():.0f} s" if pk else "no data"
            print(
                f"   M{ev.mag} {ev.origin}Z, {km:.0f} km, depth {ev.depth_km:g} km: "
                f"{pk_s}, {pre_s}, readings >= {THRESHOLD_MM_S:g} within 10 min: {len(hits)}"
            )
        if cap.events and over:
            print(
                f"   readings >= {THRESHOLD_MM_S:g} not within 10 min of a listed event: "
                f"{len(over) - accounted}"
            )


if __name__ == "__main__":
    main()
