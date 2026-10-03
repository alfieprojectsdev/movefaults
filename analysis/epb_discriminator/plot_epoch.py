#!/usr/bin/env python3
"""Session 1 figure: a quake epoch and a bubble epoch, side by side.

Top row: the per-satellite normalized residuals (Baarda w) at one epoch inside
each event. Bottom row: the normalized chi2 over time, with the alpha = 0.001
threshold. Under a quake every line of sight fits one rigid motion, so the
residuals stay small; under a bubble the affected satellites stand out.

Writes figures/epoch_quake_vs_epb_seed<seed>.png and a .json beside it holding
the config and seed, so the figure can be regenerated exactly.

Usage (from the repo root):
    uv run python analysis/epb_discriminator/plot_epoch.py [--seed 42]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from scipy import stats  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from epb.residual import chi2_norm, normalized_resid, wls  # noqa: E402
from epb.scenario import Config, build  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cfg = Config()
    dof = cfg.n_sat - 4
    thr = stats.chi2.ppf(1 - 0.001, dof) / dof
    fig, ax = plt.subplots(2, 2, figsize=(11, 7), sharey="row")

    for col, label in enumerate(("quake", "epb")):
        s = build(label, cfg, np.random.default_rng(args.seed))
        _, r, _ = wls(s.H, s.W, s.y)
        c = chi2_norm(r, s.W, dof)
        onset = s.truth["quake_onset_s"] if label == "quake" else s.truth["epb_onset_s"]
        mid = cfg.quake_dur_s / 2 if label == "quake" else cfg.epb_dur_s / 2
        k = int((onset + mid) * cfg.rate_hz)
        w = normalized_resid(s.H, s.W, r[k])
        hit = np.zeros(cfg.n_sat, dtype=bool)
        hit[s.truth["epb_sats"]] = True

        a = ax[0, col]
        a.bar(np.arange(cfg.n_sat), w, color=np.where(hit, "#C0392B", "#5D6D7E"))
        a.axhline(stats.norm.ppf(1 - 0.0005), ls="--", lw=1, color="k")
        a.axhline(-stats.norm.ppf(1 - 0.0005), ls="--", lw=1, color="k")
        a.set_title(f"{label}: epoch t = {k / cfg.rate_hz:.0f} s, per-satellite w")
        a.set_xlabel("satellite (red = inside the bubble)")
        a.set_ylabel("normalized residual w")

        b = ax[1, col]
        b.plot(s.t, c, lw=0.7, color="#1F618D")
        b.axhline(thr, ls="--", lw=1, color="k", label="alpha = 0.001")
        b.axvline(k / cfg.rate_hz, color="#C0392B", lw=0.8)
        b.set_yscale("log")
        b.set_xlabel("time (s)")
        b.set_ylabel("chi2 / dof")
        b.legend(loc="upper right", fontsize=8)

    fig.suptitle(f"Residual test, quake vs plasma bubble (synthetic, seed {args.seed})")
    fig.tight_layout()
    out = HERE / "figures" / f"epoch_quake_vs_epb_seed{args.seed}"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out.with_suffix(".png"), dpi=110)
    out.with_suffix(".json").write_text(
        json.dumps({"seed": args.seed, "config": asdict(cfg)}, indent=2) + "\n"
    )
    print(out.with_suffix(".png"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
