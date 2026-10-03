#!/usr/bin/env python3
"""Session 2 sweeps: cost on true quakes, power, blind spots, station-level view.

Writes figures/session2_power.png and figures/session2_results.json (every
number, plus the config and seeds), and prints the tables NOTES.md quotes.

Usage (from the repo root):
    uv run python analysis/epb_discriminator/run_session2.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from epb.eval import blind_spots, power_grid, quake_cost  # noqa: E402
from epb.scenario import Config  # noqa: E402

ALPHA = 0.001
WINDOW_S = 30.0
SEEDS = range(20)
AMPS_MM = [2, 4, 6, 10, 20, 40]
N_AFF = [1, 2, 3, 5]
PEAKS_MM = [5, 10, 15, 30, 60, 120]


def main() -> int:
    base = Config()
    cost = quake_cost(PEAKS_MM, SEEDS, alpha=ALPHA, window_s=WINDOW_S, base=base)
    grid = power_grid(
        [a / 1000 for a in AMPS_MM], N_AFF, SEEDS, alpha=ALPHA, window_s=WINDOW_S, base=base
    )
    spots = {n: blind_spots(500, n, seed=7, alpha=ALPHA, base=base) for n in (6, 10, 20)}

    print("Cost on true quakes (share of pulse epochs):")
    print("  peak mm/s   epoch-test reject   window-test reject   station alarm")
    for r in cost:
        print(
            f"  {r['peak_mm_s']:9.0f}   {r['epoch_reject']:17.4f}   {r['window_reject']:18.4f}   {r['station_alarm']:13.2f}"
        )

    def table(name):
        print(f"\n{name} (rows: bubble RMS mm/s; cols: satellites affected {N_AFF})")
        for i, a in enumerate(AMPS_MM):
            print(f"  {a:5d}  " + "  ".join(f"{v:5.2f}" for v in grid[name][i]))

    for k in ("epoch", "window", "station", "window_given_station"):
        table(k)

    print("\nBlind spots over 500 random geometries (median / 95th):")
    for n, b in spots.items():
        print(
            f"  N={n:2d}  MDB {b['mdb_mm_s']['median']:6.1f}/{b['mdb_mm_s']['p95']:7.1f} mm/s"
            f"  leak_h {b['leak_h']['median']:.2f}/{b['leak_h']['p95']:.2f}"
            f"  leak_u {b['leak_u']['median']:.2f}/{b['leak_u']['p95']:.2f}"
            f"  fake_h@MDB {b['fake_h_at_mdb_mm_s']['median']:5.1f}/{b['fake_h_at_mdb_mm_s']['p95']:6.1f} mm/s"
        )

    fig, ax = plt.subplots(1, 3, figsize=(13, 4), sharey=True)
    titles = {
        "epoch": "per-epoch residual test",
        "window": f"{WINDOW_S:.0f} s window residual test",
        "station": "current detector false alarms",
    }
    for a, k in zip(ax, ("epoch", "window", "station"), strict=True):
        im = a.imshow(grid[k], vmin=0, vmax=1, cmap="viridis", origin="lower", aspect="auto")
        a.set_xticks(range(len(N_AFF)), N_AFF)
        a.set_yticks(range(len(AMPS_MM)), AMPS_MM)
        a.set_xlabel("satellites in the bubble")
        a.set_title(titles[k], fontsize=10)
        for i in range(len(AMPS_MM)):
            for j in range(len(N_AFF)):
                v = grid[k][i, j]
                a.text(
                    j,
                    i,
                    f"{v:.2f}",
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="w" if v < 0.6 else "k",
                )
    ax[0].set_ylabel("bubble RMS range-rate (mm/s)")
    fig.colorbar(im, ax=ax, shrink=0.8, label="share of bubble epochs")
    fig.suptitle(
        f"Plasma bubble: detection by residual tests vs false quake alarms (alpha {ALPHA}, {len(SEEDS)} seeds)"
    )
    out = HERE / "figures" / "session2_power.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")

    res = {
        "alpha": ALPHA,
        "window_s": WINDOW_S,
        "seeds": list(SEEDS),
        "config": asdict(base),
        "amps_mm_s": AMPS_MM,
        "n_affected": N_AFF,
        "quake_cost": cost,
        "power": {k: v.tolist() for k, v in grid.items()},
        "blind_spots": {str(n): b for n, b in spots.items()},
    }
    (HERE / "figures" / "session2_results.json").write_text(json.dumps(res, indent=2) + "\n")
    print(f"\n{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
