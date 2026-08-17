#!/usr/bin/env python3
"""Produce a GMT-ready velocity field from per-site ENU series.

WHY THIS EXISTS
Item 4 of the PHIVOLCS stage 3 wishlist (Cass, 2026-08-13): velocity vector
mapping / GMT-format input files. It is the first artefact of the ported
pipeline that the group can *look at* rather than read, which makes it the
cheapest available check that the port produces numbers people recognise.

WHAT IT WRITES
  <out>.psvelo   horizontal field, `psvelo -Se` / `velo -Se` format
  <out>.vert     vertical rates, for `psxy -Sc`
  <out>.log      what was decided per station, and why anything was excluded

The log is not a nicety. Every station this tool declines to map is a station
someone will ask about, and "it did not appear on the map" is not an answer.

DECISION SUPPORT, NOT AUTOMATION
Nothing here silently removes a station. Implausible velocities are written as
commented rows in the .psvelo file and listed in the log; sites with a
too-short final segment are flagged with the reason. The analyst decides
whether to reinstate them. That is the intended posture for this whole
pipeline: recommend, show the evidence, let a person confirm.

Plotting the result (GMT 6):

    gmt begin luzon_velocities png
      gmt coast -R119/123/13/19 -JM15c -Glightgray -Slightblue -Ba
      gmt velo luzon.psvelo -Se0.05/0.95/8 -A0.3c+e -Gred -W0.5p
    gmt end show

Usage:
    scripts/make_velocity_field.py --data DIR --crd FILE.CRD --ref S01R --out luzon
    scripts/make_velocity_field.py --data DIR --crd FILE.CRD --ref S01R --out luzon \
        --joint --rate-changes
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
    estimate_velocity_joint,
    parse_offsets_file,
)
from pogf_geodetic_suite.timeseries.gmt import (  # noqa: E402
    MIN_SPAN_YEARS,
    station_positions,
    to_vectors,
    write_psvelo,
    write_vertical,
)

# MIN_SPAN_YEARS is imported, not redefined here. Below it, a fitted rate is the
# slope of a few days of scatter rather than a velocity; deliberately
# permissive, see velocity_outlier_policy_delta.md. It used to be a second copy
# of the constant living in this script, which is how the threshold and the
# quarantine it drives could drift apart without anything failing.


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data", type=Path, required=True,
                    help="directory of per-site ENU plot files plus a site list")
    ap.add_argument("--sites", default="123", help="site-list filename inside --data")
    ap.add_argument("--offsets", type=Path, default=None,
                    help="offsets catalog (default: <data>/offsets)")
    ap.add_argument("--crd", type=Path, required=True,
                    help="any Bernese CRD file, used for station lon/lat")
    ap.add_argument("--ref", required=True,
                    help="reference station the ENU series is relative to; "
                         "recorded in every output header")
    ap.add_argument("--out", type=Path, required=True, help="output basename")
    ap.add_argument("--joint", action="store_true",
                    help="joint step+rate fit instead of independent segments")
    ap.add_argument("--rate-changes", action="store_true",
                    help="with --joint, also fit a rate change per event")
    ap.add_argument("--max-speed", type=float, default=200.0,
                    help="comment out stations faster than this (mm/yr); 0 disables")
    args = ap.parse_args()

    if args.rate_changes and not args.joint:
        print("--rate-changes requires --joint", file=sys.stderr)
        return 2

    offsets_path = args.offsets or (args.data / "offsets")
    catalog = parse_offsets_file(offsets_path) if offsets_path.is_file() else {}
    if not catalog:
        print(f"WARNING: no offsets catalog at {offsets_path} — every series will be "
              f"fitted as if it had no discontinuities.", file=sys.stderr)

    site_list = args.data / args.sites
    if not site_list.is_file():
        print(f"FATAL: no site list at {site_list}", file=sys.stderr)
        return 1
    sites = [s.strip().upper() for s in site_list.read_text().split() if s.strip()]

    try:
        positions = station_positions(args.crd)
    except Exception as exc:  # noqa: BLE001
        print(f"FATAL: cannot read positions from {args.crd}: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    results = []
    log: list[str] = []
    short_span: dict[str, str] = {}

    for site in sites:
        series = args.data / site
        if not series.is_file():
            log.append(f"{site}: EXCLUDED — no ENU series file")
            continue
        try:
            arr = np.loadtxt(series)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            t, enu = arr[:, 0], arr[:, 1:4]
            offs = catalog.get(site)
            if args.joint:
                r = estimate_velocity_joint(t, enu, offsets=offs, station=site,
                                            rate_changes=args.rate_changes)
                span = r.t_end - (r.rate_changes[-1].date if r.rate_changes
                                  else r.t_start)
                for s in r.unresolvable_steps:
                    log.append(f"{site}: NOTE — step at {s.date:.4f} is not "
                               f"resolvable ({s.n_before} before / {s.n_after} after)")
            else:
                r = estimate_velocity(t, enu, offsets=offs, station=site)
                seg = r.final_velocity
                span = seg.t_end - seg.t_start
        except Exception as exc:  # noqa: BLE001 - one bad site must not stop the map
            log.append(f"{site}: EXCLUDED — {type(exc).__name__}: {str(exc)[:70]}")
            continue

        if span < MIN_SPAN_YEARS:
            short_span[site] = f"final interval spans {span * 365.25:.0f} days"
            log.append(f"{site}: WITHHELD — final interval spans {span * 365.25:.0f} "
                       f"days; the fitted rate is scatter, not motion")
        results.append(r)

    if not results:
        print("FATAL: no station produced a velocity.", file=sys.stderr)
        return 1

    vectors, missing = to_vectors(results, positions)
    for site in missing:
        log.append(f"{site}: EXCLUDED — no position in {args.crd.name}")

    fit = ("joint step+rate" + (" +rate changes" if args.rate_changes else "")
           if args.joint else "independent segments (MATLAB-equivalent)")
    notes = [
        f"fit: {fit}",
        f"catalog: {offsets_path}",
        f"positions: {args.crd}",
        f"sites requested: {len(sites)}   mapped: {len(vectors)}",
    ]

    # `--out` is a basename, so the extension is APPENDED. with_suffix would
    # replace an existing one: `--out luzon_v1.2` wrote luzon_v1.psvelo and
    # `--out 2026.1` wrote 2026.psvelo, so two runs distinguished only by a
    # dotted version silently overwrote each other's output.
    psvelo = args.out.with_name(args.out.name + ".psvelo")
    vert = args.out.with_name(args.out.name + ".vert")
    logfile = args.out.with_name(args.out.name + ".log")

    n_h, quarantined = write_psvelo(
        vectors, psvelo, reference_station=args.ref,
        max_speed_mm_yr=(args.max_speed or None), withhold=short_span, notes=notes,
    )
    # Same withhold set as the horizontal file. Passing it to only one writer
    # published the questioned stations in the noisier component.
    n_v, _ = write_vertical(
        vectors, vert, reference_station=args.ref, withhold=short_span, notes=notes,
    )

    for site in quarantined:
        if site not in short_span:
            log.append(f"{site}: WITHHELD — speed exceeds {args.max_speed:g} mm/yr")

    logfile.write_text(
        "\n".join([f"# velocity field: {args.out}",
                   f"# reference station: {args.ref}",
                   f"# {fit}", ""] + sorted(log)) + "\n",
        encoding="utf-8",
    )

    print(f"horizontal: {psvelo}   {n_h} mapped"
          + (f", {len(quarantined)} commented out" if quarantined else ""))
    print(f"vertical:   {vert}   {n_v} mapped")
    print(f"log:        {logfile}   {len(log)} note(s)")
    if quarantined:
        print(f"\n{len(quarantined)} station(s) withheld from the map:")
        print("  " + " ".join(sorted(quarantined)))
        print("  Nothing was deleted — each is a commented row in the .psvelo with")
        print("  its reason. Review the log and uncomment anything you disagree with.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
