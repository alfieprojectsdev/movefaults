#!/usr/bin/env python3
"""Quantify what changes when outliers are actually excluded from velocity fits.

WHY THIS EXISTS
`vel_line_v8_newvelduetooffset_v4.m` calls `rmoutliers`, assigns the result to
`cleaned_d`, writes the flagged epochs to an `outliers` file -- and then fits
the regression against the RAW data anyway. The mask is computed, reported, and
discarded. That is why the work instruction has the analyst delete outlier
points by hand in the browser and re-run: the automatic detection never fed the
fit in the first place.

`estimate_velocity(..., exclude_outliers=True)` -- the default in this monorepo
-- does what the MATLAB evidently intended. It is the statistically defensible
choice and it is what PHIVOLCS has decided to publish going forward
(2026-08-13). But it means new velocities will NOT match the numbers already in
circulation, and someone comparing them will reasonably conclude the pipeline
is broken.

This script produces the delta table so that conversation happens once, with
numbers, instead of repeatedly. It answers: which sites change, by how much,
and why.

READING THE OUTPUT
Sites with no flagged epochs are identical to the last decimal -- the policy is
a no-op for them, and they are the majority. The differences concentrate
entirely in sites that have outliers, which is the point.

`n_out` counts flagged epochs in the FINAL segment only, since the final
segment is what `final_velocity` reports and what gets published. A site can
have outliers in an earlier segment and still show n_out=0 here.

CAVEAT THAT MATTERS MORE THAN THE TABLE
A velocity file is only meaningful alongside the exact `offsets` catalog that
produced it. The saved PHIVOLCS reference is dated 2026-07-09; the catalog was
edited 2026-07-29. Pass --offsets pointing at the catalog as it stood, or the
"published" column will disagree for reasons that have nothing to do with
outliers. See --check.

Usage:
    scripts/compare_velocity_outlier_policy.py --data DIR
    scripts/compare_velocity_outlier_policy.py --data DIR --check REFERENCE
    scripts/compare_velocity_outlier_policy.py --data DIR --format md > table.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "packages/pogf-geodetic-suite/src")
)
from pogf_geodetic_suite.timeseries.analysis import (  # noqa: E402
    estimate_velocity,
    parse_offsets_file,
)

# A secular velocity fitted to a final segment shorter than this is not a
# velocity, it is the slope of a few days of scatter. 1.0 yr is deliberately
# permissive -- Blewitt & Lavallee put the threshold for unbiased rates nearer
# 2.5 yr once annual signals are present. Anything flagged here is indefensible
# by any standard.
MIN_SPAN_YEARS = 1.0

# Sites the MATLAB cannot be compared against, each for its own reason. Kept
# here rather than silently dropped so the count in the summary is honest.
KNOWN_UNCOMPARABLE = {
    "BR14": "out-of-order offsets records; MATLAB fits stale timestamps",
    "LUZD": "out-of-order offsets records; MATLAB fits stale timestamps",
    "KA08": "1-point trailing segment; MATLAB emits NaN error bars",
}


def load_series(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Read a PHIVOLCS plot file: decimal_year  E  N  U, metres."""
    arr = np.loadtxt(path)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    return arr[:, 0], arr[:, 1:4]


def parse_reference(path: Path) -> dict[str, tuple[float, float, float]]:
    """Parse `Velocity_rover(regress)_10` -> {site: (ve, vn, vu)} in mm/yr."""
    out: dict[str, tuple[float, float, float]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.split()
        # SITE  Ve  +-  sig  Vn  +-  sig  Vu  +-  sig
        if len(parts) != 10 or parts[2] != "+-":
            continue
        try:
            out[parts[0].upper()] = (float(parts[1]), float(parts[4]), float(parts[7]))
        except ValueError:
            continue
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True,
                    help="directory of per-site plot files plus a site list")
    ap.add_argument("--sites", default="123",
                    help="name of the site-list file inside --data (default: 123)")
    ap.add_argument("--offsets", type=Path, default=None,
                    help="offsets catalog (default: <data>/offsets)")
    ap.add_argument("--check", type=Path, default=None,
                    help="PHIVOLCS Velocity_rover(regress)_10 to verify the "
                         "exclude_outliers=False branch still reproduces")
    ap.add_argument("--format", choices=("txt", "md"), default="txt")
    args = ap.parse_args()

    offsets_path = args.offsets or (args.data / "offsets")
    if not offsets_path.is_file():
        print(f"FATAL: no offsets catalog at {offsets_path}", file=sys.stderr)
        return 1
    catalog = parse_offsets_file(offsets_path)

    site_list = args.data / args.sites
    if not site_list.is_file():
        print(f"FATAL: no site list at {site_list}", file=sys.stderr)
        return 1
    sites = [s.strip().upper() for s in site_list.read_text().split() if s.strip()]

    reference = parse_reference(args.check) if args.check else {}

    rows = []
    failed: list[tuple[str, str]] = []
    for site in sites:
        series = args.data / site
        if not series.is_file():
            failed.append((site, "no plot file"))
            continue
        try:
            t, enu = load_series(series)
            offs = catalog.get(site)
            pub = estimate_velocity(t, enu, offsets=offs, station=site,
                                    exclude_outliers=False).final_velocity
            new = estimate_velocity(t, enu, offsets=offs, station=site,
                                    exclude_outliers=True).final_velocity
        except Exception as exc:  # noqa: BLE001 - report per site, keep going
            failed.append((site, f"{type(exc).__name__}: {str(exc)[:60]}"))
            continue

        d = (new.ve_mm_yr - pub.ve_mm_yr,
             new.vn_mm_yr - pub.vn_mm_yr,
             new.vu_mm_yr - pub.vu_mm_yr)
        ref_ok = ""
        if reference:
            r = reference.get(site)
            if r is None:
                ref_ok = "-"
            else:
                worst = max(abs(pub.ve_mm_yr - r[0]), abs(pub.vn_mm_yr - r[1]),
                            abs(pub.vu_mm_yr - r[2]))
                # The reference file carries 5 decimals, so agreement can only
                # be claimed to that precision.
                ref_ok = "ok" if worst < 1e-4 else f"DIFF {worst:.5f}"
        rows.append((site, len(pub.outlier_epochs), pub, new, d, ref_ok))

    rows.sort(key=lambda r: -max(abs(x) for x in r[4]))

    hdr = ("site", "n", "span", "n_out", "Ve pub", "Ve new", "dVe",
           "Vn pub", "Vn new", "dVn", "Vu pub", "Vu new", "dVu")
    if args.check:
        hdr = (*hdr, "repro")

    def fmt(r):
        site, n_out, pub, new, d, ref_ok = r
        span = pub.t_end - pub.t_start
        # A final segment spanning less than MIN_SPAN_YEARS cannot carry a
        # meaningful secular velocity no matter how the outliers are treated.
        flag = "!" if span < MIN_SPAN_YEARS else ""
        cells = [site + flag, str(pub.n_points), f"{span:.2f}", str(n_out),
                 f"{pub.ve_mm_yr:.3f}", f"{new.ve_mm_yr:.3f}", f"{d[0]:+.3f}",
                 f"{pub.vn_mm_yr:.3f}", f"{new.vn_mm_yr:.3f}", f"{d[1]:+.3f}",
                 f"{pub.vu_mm_yr:.3f}", f"{new.vu_mm_yr:.3f}", f"{d[2]:+.3f}"]
        if args.check:
            cells.append(ref_ok)
        return cells

    body = [fmt(r) for r in rows]
    if args.format == "md":
        print("| " + " | ".join(hdr) + " |")
        print("|" + "|".join("---" for _ in hdr) + "|")
        for c in body:
            print("| " + " | ".join(c) + " |")
    else:
        widths = [max(len(hdr[i]), *(len(c[i]) for c in body)) if body else len(hdr[i])
                  for i in range(len(hdr))]
        print("  ".join(h.rjust(w) for h, w in zip(hdr, widths, strict=True)))
        print("  ".join("-" * w for w in widths))
        for c in body:
            print("  ".join(x.rjust(w) for x, w in zip(c, widths, strict=True)))

    changed = [r for r in rows if max(abs(x) for x in r[4]) > 1e-6]
    print()
    print(f"sites compared: {len(rows)}   unchanged: {len(rows) - len(changed)}   "
          f"changed: {len(changed)}")
    # Horizontal and vertical are reported separately on purpose: tectonic
    # interpretation runs on the horizontal, and quoting a single worst-case
    # number lets the noisy Up component stand in for the whole result.
    if rows:
        wh = max((max(abs(r[4][0]), abs(r[4][1])), r[0]) for r in rows)
        wv = max((abs(r[4][2]), r[0]) for r in rows)
        print(f"largest change, horizontal: {wh[0]:.3f} mm/yr at {wh[1]}")
        print(f"largest change, vertical:   {wv[0]:.3f} mm/yr at {wv[1]}")
    degen = [r[0] for r in rows if (r[2].t_end - r[2].t_start) < MIN_SPAN_YEARS]
    if degen:
        print(f"\nFINAL SEGMENT UNDER {MIN_SPAN_YEARS:g} YEAR ({len(degen)}) -- marked ! "
              f"in the table. These velocities are unusable regardless of\n"
              f"outlier policy; both implementations agree because both are "
              f"fitting days of scatter:\n  " + " ".join(degen))
    if reference:
        bad = [r[0] for r in rows if r[5].startswith("DIFF")]
        print(f"reproduces published (exclude_outliers=False): "
              f"{sum(1 for r in rows if r[5] == 'ok')}/{len(rows)}"
              + (f"   MISMATCH: {' '.join(bad)}" if bad else ""))
    for site, why in failed:
        note = KNOWN_UNCOMPARABLE.get(site)
        print(f"  skipped {site}: {why}" + (f"  [known: {note}]" if note else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
