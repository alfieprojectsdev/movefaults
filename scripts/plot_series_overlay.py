#!/usr/bin/env python3
"""Superimpose ENU time series from two or more processing runs.

WHY THIS EXISTS
The 2025 PHREF reprocessing (BSW 5.4, Linux) needs to be looked at beside
PHIVOLCS production (BSW 5.2, Windows), not just summarised. The weekly Helmert
comparison says the two agree at 1.3 mm North / 2.4 mm East; this is the
picture behind that number, and it is where a reader notices things a summary
statistic hides -- an offset that starts mid-year, a station that drifts, a
week that jumps.

BOTH SIDES GO THROUGH THE SAME CHAIN. PHIVOLCS retains no 2025 PLOT files, so
her SINEX becomes CRD (scripts/sinex_to_crd.py) and then enters the same
`crd-to-plots` that produces ours. That is deliberate: had her PLOT files been
available we would be comparing her processing chain AND her solutions at once,
with no way to separate them. Here, any difference on the plot is a difference
in the SOLUTIONS.

THE REFERENCE STATION MUST MATCH ACROSS SERIES
These are relative ENU. Two series referenced to different stations sit at a
constant offset that looks like disagreement and is not. The Helmert comparison
did not care -- the transformation absorbed the datum -- but a plot cannot.
Pass the same -r to every crd-to-plots run.

Usage:
    scripts/plot_series_overlay.py VIGN \
        --series "ours daily:$HOME/ts-compare/ours-daily" \
        --series "ours weekly:$HOME/ts-compare/ours-weekly" \
        --series "PHIVOLCS weekly:$HOME/ts-compare/hers-weekly" \
        -o vign.png
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")          # headless: this runs over ssh on the R740
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

# Distinct in both hue and marker, so the figure survives being printed in
# greyscale or read by someone with colour-vision deficiency.
STYLES = [
    {"color": "#1f77b4", "marker": ".", "ms": 3, "ls": "none", "alpha": 0.55},
    {"color": "#d62728", "marker": "o", "ms": 4, "ls": "-", "lw": 0.8, "alpha": 0.9},
    {"color": "#2ca02c", "marker": "s", "ms": 4, "ls": "-", "lw": 0.8, "alpha": 0.9},
    {"color": "#9467bd", "marker": "^", "ms": 4, "ls": "-", "lw": 0.8, "alpha": 0.9},
]


def load(series_dir: Path, site: str) -> np.ndarray | None:
    """Read a PLOT file: decimal_year  E  N  U, metres."""
    f = series_dir / site
    if not f.is_file():
        return None
    try:
        a = np.loadtxt(f)
    except Exception:  # noqa: BLE001
        return None
    if a.ndim == 1:
        a = a.reshape(1, -1)
    return a if a.size else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("site")
    ap.add_argument("--series", action="append", required=True,
                    metavar="LABEL:DIR",
                    help="repeatable; first one is drawn as the background scatter")
    ap.add_argument("-o", "--output", type=Path, default=None)
    ap.add_argument("--detrend", action="store_true",
                    help="remove each component's mean, so the shapes are "
                         "comparable when the series sit at different offsets")
    args = ap.parse_args()

    loaded = []
    for spec in args.series:
        if ":" not in spec:
            print(f"--series wants LABEL:DIR, got {spec!r}", file=sys.stderr)
            return 2
        label, d = spec.split(":", 1)
        a = load(Path(d).expanduser(), args.site)
        if a is None:
            print(f"  {label}: no series for {args.site} in {d}", file=sys.stderr)
            continue
        loaded.append((label.strip(), a))

    if not loaded:
        print(f"FATAL: {args.site} not found in any series", file=sys.stderr)
        return 1

    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True)
    comps = [("East", 1), ("North", 2), ("Up", 3)]

    for ax, (name, col) in zip(axes, comps, strict=True):
        for i, (label, a) in enumerate(loaded):
            st = STYLES[i % len(STYLES)]
            y = a[:, col] * 1000.0                      # m -> mm
            if args.detrend:
                y = y - np.mean(y)
            ax.plot(a[:, 0], y, label=label, **st)
        ax.set_ylabel(f"{name} (mm)")
        ax.grid(alpha=0.25, lw=0.5)

        # Robust limits. A handful of failed days (TGDN has two, up to 4.6 m
        # off) otherwise set the scale and compress the real signal into a flat
        # line. Clipping the VIEW keeps them visible at the frame edge instead
        # of deleting them -- the count is annotated, so nothing is hidden.
        allv = np.concatenate([
            (a[:, col] * 1000.0) - (np.mean(a[:, col] * 1000.0) if args.detrend else 0.0)
            for _, a in loaded
        ])
        med = np.median(allv)
        mad = np.median(np.abs(allv - med)) or 1.0
        lo, hi = med - 8 * 1.4826 * mad, med + 8 * 1.4826 * mad
        n_out = int(np.sum((allv < lo) | (allv > hi)))
        if n_out:
            ax.set_ylim(lo, hi)
            ax.text(0.995, 0.04, f"{n_out} beyond axis", transform=ax.transAxes,
                    ha="right", va="bottom", fontsize=7, color="#666")
    axes[0].legend(loc="upper right", fontsize=9, framealpha=0.9)
    axes[-1].set_xlabel("decimal year")

    detr = " (mean removed)" if args.detrend else ""
    fig.suptitle(f"{args.site} — ENU time series{detr}", fontsize=13)
    fig.tight_layout()

    out = args.output or Path(f"{args.site}.png")
    fig.savefig(out, dpi=130)
    print(f"  wrote {out}")

    # The numbers behind the picture: an eyeballed plot is not a measurement.
    print(f"\n  {args.site}: epochs and spread per series")
    for label, a in loaded:
        e, n, u = (a[:, c] * 1000.0 for c in (1, 2, 3))
        print(f"    {label:<20} n={len(a):4d}  "
              f"span {a[0,0]:.3f}-{a[-1,0]:.3f}  "
              f"sd E {np.std(e):6.2f}  N {np.std(n):6.2f}  U {np.std(u):6.2f} mm")
    if len(loaded) >= 2:
        # Offsets between series means: this is the number that tells you
        # whether a visible gap is a real disagreement or a datum difference.
        base_label, base = loaded[0]
        for label, a in loaded[1:]:
            d = [np.mean(a[:, c]) * 1000 - np.mean(base[:, c]) * 1000 for c in (1, 2, 3)]
            print(f"    mean offset {label} - {base_label}: "
                  f"E {d[0]:+7.2f}  N {d[1]:+7.2f}  U {d[2]:+7.2f} mm")
    return 0


if __name__ == "__main__":
    sys.exit(main())
