#!/usr/bin/env python3
"""Confirm or eliminate ionospheric disturbance as the cause of a bad day.

WHY THIS EXISTS
2025 DOY 036 failed with a 89 mm Helmert RMS against a ~3 mm daily norm, and
"maybe it was the ionosphere" is the kind of suspicion that either gets checked
properly once or gets repeated forever. Chasing it by hand -- searching for
solar flare reports, eyeballing TEC maps -- is slow, unrepeatable, and
impossible to apply to 365 days.

WHAT IT DOES NOT DO
It does not decide. It returns CONFIRMED / ELIMINATED / INCONCLUSIVE with the
numbers behind each, because "the ionosphere did it" is a claim about the
world, not about our software, and the evidence should be legible to someone
who disagrees.

THREE INDEPENDENT LINES OF EVIDENCE
1. TEC over the Philippines, from the CODE global ionosphere maps we ALREADY
   download with every day's products. No new data needed for 365 days. A
   disturbed day shows anomalous absolute TEC.
2. Intra-day TEC variability. Equatorial plasma bubbles are a Philippine
   speciality -- the magnetic equator runs just south -- and they show as rapid
   post-sunset structure rather than a raised daily mean. A day can be quiet by
   Kp and still be locally shredded.
3. Kp / ap geomagnetic indices from GFZ. Storms are global and independent of
   our data entirely, so agreement between this and (1) is real corroboration
   rather than one measurement seen twice.

They can disagree, and that is the point. A geomagnetic storm with normal local
TEC, or wild local TEC with Kp = 1, each mean something different from both
agreeing.

Usage:
    scripts/atmospheric_anomaly.py --doy 36
    scripts/atmospheric_anomaly.py --doy 36 --year 2025
    scripts/atmospheric_anomaly.py --scan              # rank the whole year
"""
from __future__ import annotations

import argparse
import gzip
import math
import os
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

# Manila-ish; the LUZON network centroid is close enough for a TEC comparison
# whose signal is tens of TECU.
SITE_LAT, SITE_LON = 14.6, 121.0

KP_URL = ("https://www-app3.gfz-potsdam.de/kp_index/"
          "Kp_ap_Ap_SN_F107_since_1932.txt")
KP_CACHE = Path.home() / ".cache" / "gfz_kp_ap.txt"

# Thresholds. Stated here rather than buried, because they are judgements and a
# reader should be able to disagree with a number rather than with the code.
Z_STRONG = 3.0      # |z| beyond this: anomalous against the year's own spread
Z_WEAK = 2.0
KP_STORM = 5.0      # Kp >= 5 is the conventional geomagnetic-storm threshold
KP_ACTIVE = 4.0


def _legendre(nmax: int, x: float) -> list[list[float]]:
    """Normalised associated Legendre functions, as Bernese IONEX-style GIMs use."""
    p = [[0.0] * (nmax + 1) for _ in range(nmax + 1)]
    p[0][0] = 1.0
    s = math.sqrt(max(0.0, 1.0 - x * x))
    for n in range(1, nmax + 1):
        p[n][n] = p[n - 1][n - 1] * s * math.sqrt((2 * n - 1) / (2 * n)) \
            if n > 0 else 1.0
        if n >= 1:
            p[n][n - 1] = x * math.sqrt(2 * n - 1) * p[n - 1][n - 1]
        for m in range(n - 2, -1, -1):
            a = math.sqrt(((2 * n - 1) * (2 * n + 1)) / ((n - m) * (n + m)))
            b = math.sqrt(((2 * n - 3) * (n + m - 1) * (n - m - 1)) /
                          ((n - m) * (n + m) * (2 * n - 3))) if n >= 2 else 0.0
            p[n][m] = a * x * p[n - 1][m] - (b * p[n - 2][m] if n >= 2 else 0.0)
    return p


def read_gim(path: Path) -> list[dict]:
    """Parse a Bernese .ION file into a list of hourly models."""
    opener = gzip.open if path.suffix == ".gz" else open
    models, cur, in_coef = [], None, False
    with opener(path, "rt", errors="replace") as fh:
        for line in fh:
            if "MODEL NUMBER" in line:
                if cur:
                    models.append(cur)
                cur = {"coef": {}, "lat_pole": 0.0, "lon_pole": 0.0, "nmax": 15}
                in_coef = False
            elif cur is not None:
                if "MAXIMUM DEGREE" in line:
                    cur["nmax"] = int(line.split(":")[1])
                elif "LATITUDE OF NORTH GEOMAGNETIC POLE" in line:
                    cur["lat_pole"] = float(line.split(":")[1])
                elif "EAST LONGITUDE" in line and "lon_pole" in cur \
                        and cur["lon_pole"] == 0.0:
                    cur["lon_pole"] = float(line.split(":")[1])
                elif "FROM EPOCH" in line:
                    cur["epoch"] = line.split(":", 1)[1].strip()
                elif line.strip().startswith("DEGREE  ORDER"):
                    in_coef = True
                elif in_coef:
                    f = line.split()
                    if len(f) >= 3:
                        try:
                            cur["coef"][(int(f[0]), int(f[1]))] = float(f[2])
                        except ValueError:
                            in_coef = False
    if cur:
        models.append(cur)
    return [m for m in models if m["coef"]]


def tec_at(model: dict, lat_deg: float, lon_deg: float, hour: float) -> float:
    """Evaluate a GIM at a location. Geomagnetic frame, sun-fixed longitude."""
    lp, gp = math.radians(model["lat_pole"]), math.radians(model["lon_pole"])
    la, lo = math.radians(lat_deg), math.radians(lon_deg)
    # geographic -> geomagnetic latitude
    sinb = (math.sin(la) * math.sin(lp)
            + math.cos(la) * math.cos(lp) * math.cos(lo - gp))
    beta = math.asin(max(-1.0, min(1.0, sinb)))
    # sun-fixed longitude
    s = math.radians((hour - 12.0) * 15.0 + lon_deg)
    s = math.atan2(math.sin(s), math.cos(s))

    nmax = model["nmax"]
    p = _legendre(nmax, math.sin(beta))
    total = 0.0
    for (n, m), c in model["coef"].items():
        if n > nmax or abs(m) > nmax:
            continue
        val = p[n][abs(m)]
        total += c * (val * math.cos(abs(m) * s) if m >= 0
                      else val * math.sin(abs(m) * s))
    return total


def day_tec(datapool: Path, year: int, doy: int) -> tuple[float, float, int]:
    """(mean TEC, intra-day peak-to-peak, hours) over the site."""
    hits = sorted(datapool.glob(f"*{year}{doy:03d}0000*GIM.ION*"))
    if not hits:
        return (float("nan"), float("nan"), 0)
    models = read_gim(hits[0])
    vals = [tec_at(m, SITE_LAT, SITE_LON, h % 24)
            for h, m in enumerate(models)]
    vals = [v for v in vals if not math.isnan(v)]
    if not vals:
        return (float("nan"), float("nan"), 0)
    return (sum(vals) / len(vals), max(vals) - min(vals), len(vals))


def fetch_kp() -> dict[tuple[int, int, int], tuple[float, int]]:
    """{(y,m,d): (max Kp, daily Ap)} from GFZ. Cached; network only once."""
    if not KP_CACHE.is_file() or KP_CACHE.stat().st_size < 10000:
        KP_CACHE.parent.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(["curl", "-sS", "--max-time", "120", "-o",
                            str(KP_CACHE), KP_URL], check=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  (Kp unavailable: {exc}) ", file=sys.stderr)
            return {}
    out: dict[tuple[int, int, int], tuple[float, int]] = {}
    for line in KP_CACHE.read_text(errors="replace").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        f = line.split()
        if len(f) < 28:
            continue
        try:
            y, m, d = int(f[0]), int(f[1]), int(f[2])
            kps = [float(x) for x in f[7:15]]
            ap = int(float(f[23]))
        except (ValueError, IndexError):
            continue
        out[(y, m, d)] = (max(kps), ap)
    return out


def zscore(x: float, series: list[float]) -> float:
    good = [v for v in series if not math.isnan(v)]
    if len(good) < 10 or math.isnan(x):
        return float("nan")
    mu = sum(good) / len(good)
    sd = (sum((v - mu) ** 2 for v in good) / (len(good) - 1)) ** 0.5
    return float("nan") if sd == 0 else (x - mu) / sd


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--doy", type=int, help="day of year to investigate")
    ap.add_argument("--year", type=int, default=2025)
    ap.add_argument("--scan", action="store_true",
                    help="rank every day of the year by disturbance")
    ap.add_argument("--datapool", type=Path,
                    default=Path(os.environ.get("D", "")) / "BSW54")
    args = ap.parse_args()

    if not args.datapool.is_dir():
        print(f"FATAL: no GIM directory at {args.datapool} "
              f"(source LOADGPS.setvar, or pass --datapool)", file=sys.stderr)
        return 1
    if not args.scan and args.doy is None:
        print("give --doy N or --scan", file=sys.stderr)
        return 2

    print(f"reading ionosphere maps from {args.datapool} ...", file=sys.stderr)
    tec = {d: day_tec(args.datapool, args.year, d) for d in range(1, 366)}
    means = [tec[d][0] for d in range(1, 366)]
    ptps = [tec[d][1] for d in range(1, 366)]
    kp = fetch_kp()

    def row(d: int) -> tuple:
        m, p, n = tec[d]
        dt = date(args.year, 1, 1) + timedelta(days=d - 1)
        k, a = kp.get((dt.year, dt.month, dt.day), (float("nan"), -1))
        return (d, dt, m, p, n, zscore(m, means), zscore(p, ptps), k, a)

    if args.scan:
        rows = [row(d) for d in range(1, 366) if tec[d][2] > 0]
        rows.sort(key=lambda r: -max(
            abs(r[5]) if not math.isnan(r[5]) else 0,
            abs(r[6]) if not math.isnan(r[6]) else 0))
        print(f"\n{'DOY':>4} {'date':>10} {'TEC':>7} {'z':>6} "
              f"{'range':>7} {'z':>6} {'Kp':>5} {'Ap':>4}")
        print("-" * 52)
        for r in rows[:25]:
            print(f"{r[0]:4d} {r[1].isoformat():>10} {r[2]:7.1f} {r[5]:6.2f} "
                  f"{r[3]:7.1f} {r[6]:6.2f} {r[7]:5.1f} {r[8]:4d}")
        print(f"\n{len(rows)} days with ionosphere maps. "
              f"Ranked by |z| of daily mean TEC or intra-day range.")
        return 0

    d, dt, m, p, n, zm, zp, k, a = row(args.doy)
    if n == 0:
        print(f"No ionosphere map for {args.year} DOY {d:03d}.", file=sys.stderr)
        return 1

    print(f"\nAtmospheric anomaly check — {args.year} DOY {d:03d} "
          f"({dt.isoformat()})")
    print(f"  site {SITE_LAT:.1f}N {SITE_LON:.1f}E, {n} hourly maps")
    print("-" * 58)
    print(f"  mean TEC over site      {m:8.1f} TECU    z = {zm:+.2f}")
    print(f"  intra-day range         {p:8.1f} TECU    z = {zp:+.2f}")
    if not math.isnan(k):
        print(f"  max Kp (GFZ)            {k:8.1f}         Ap = {a}")
    else:
        print("  max Kp (GFZ)                 n/a")

    reasons, verdict = [], "ELIMINATED"
    strong = [z for z in (zm, zp) if not math.isnan(z) and abs(z) >= Z_STRONG]
    weak = [z for z in (zm, zp) if not math.isnan(z) and Z_WEAK <= abs(z) < Z_STRONG]
    if strong:
        verdict = "CONFIRMED"
        reasons.append(f"local TEC {abs(strong[0]):.1f} sigma from the year's norm")
    elif weak:
        verdict = "INCONCLUSIVE"
        reasons.append(f"local TEC mildly unusual ({abs(weak[0]):.1f} sigma)")
    if not math.isnan(k):
        if k >= KP_STORM:
            reasons.append(f"geomagnetic storm (Kp {k:.1f})")
            verdict = "CONFIRMED"
        elif k >= KP_ACTIVE:
            reasons.append(f"active geomagnetic conditions (Kp {k:.1f})")
            if verdict == "ELIMINATED":
                verdict = "INCONCLUSIVE"
        else:
            reasons.append(f"geomagnetically quiet (Kp {k:.1f})")

    print("-" * 58)
    print(f"  VERDICT: {verdict}")
    for r in reasons:
        print(f"    - {r}")
    if verdict == "ELIMINATED":
        print("\n  The ionosphere does not explain this day. Look elsewhere:")
        print("    a single station's data, an orbit/ERP problem, or the")
        print("    reference-frame screening itself.")
    elif verdict == "CONFIRMED":
        print("\n  Consistent with an ionospheric cause. This does not prove it")
        print("    caused the processing failure -- it removes the need to keep")
        print("    wondering, and points the next check at the same day's")
        print("    ambiguity-resolution statistics.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
