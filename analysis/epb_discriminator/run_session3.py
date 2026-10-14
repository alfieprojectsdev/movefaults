#!/usr/bin/env python3
"""Session 3: does the window test survive realistic noise?

Sessions 1-2 drew white noise per epoch. Real range-rate from time-differenced
carrier phase (TDCP) is the difference of consecutive phase errors, and real
phase carries multipath that drifts with the satellite. For each noise model:

1. null: on quiet scenarios, the false-alarm rate at the nominal chi2
   threshold, and a threshold calibrated as the (1 - alpha) quantile of the
   window statistic itself;
2. power: bubble detection at the CALIBRATED threshold, the share of bubble
   epochs that trip the current detector, and of those, the share the window
   test flags.

Writes figures/session3_results.json and figures/session3_power.png.

Usage (from the repo root):
    uv run python analysis/epb_discriminator/run_session3.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
from pathlib import Path

import matplotlib
import numpy as np
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from epb.eval import power_grid, reject_epoch, window_stat  # noqa: E402
from epb.scenario import Config, build  # noqa: E402

ALPHA = 0.001
WINDOW_S = 30.0
NULL_SEEDS = range(1000, 1060)
SEEDS = range(20)
AMPS_MM = [4, 6, 10, 20]
N_AFF = [1, 3, 5]

MODELS = {
    "white": Config(),
    "tdcp": Config(noise_model="tdcp"),
    "tdcp + multipath 300 s": Config(noise_model="tdcp", mp_amp=0.010, mp_period_s=300.0),
    "tdcp + multipath 30 s": Config(noise_model="tdcp", mp_amp=0.010, mp_period_s=30.0),
    "tdcp + multipath 30 s, 80 % removed": Config(
        noise_model="tdcp", mp_amp=0.010, mp_period_s=30.0, mp_resid_frac=0.2
    ),
    # sigma0 is a placeholder (3 mm/s); multipath matters relative to it.
    "tdcp, sigma0 1 mm/s": Config(noise_model="tdcp", sigma0=0.001),
    "tdcp + multipath 30 s, sigma0 1 mm/s": Config(
        noise_model="tdcp", sigma0=0.001, mp_amp=0.010, mp_period_s=30.0
    ),
    "same, 80 % removed": Config(
        noise_model="tdcp", sigma0=0.001, mp_amp=0.010, mp_period_s=30.0, mp_resid_frac=0.2
    ),
}


def null_calibration(cfg: Config) -> dict:
    cfg = replace(cfg, duration_s=3000.0)
    sums, ep, wn = [], [], []
    for seed in NULL_SEEDS:
        s = build("quiet", cfg, np.random.default_rng(seed))
        st, df = window_stat(s, WINDOW_S)
        st = st[~np.isnan(st)]
        sums.append(st)
        ep.append(reject_epoch(s, ALPHA).mean())
        wn.append((st > stats.chi2.ppf(1 - ALPHA, df)).mean())
    pooled = np.concatenate(sums)
    return {
        "epoch_false_alarm_at_nominal": float(np.mean(ep)),
        "window_false_alarm_at_nominal": float(np.mean(wn)),
        "window_threshold_calibrated": float(np.quantile(pooled, 1 - ALPHA)),
        "window_threshold_nominal_chi2": float(stats.chi2.ppf(1 - ALPHA, df)),
        "window_dof": int(df),
    }


def power(cfg: Config, threshold: float) -> dict:
    g = power_grid(
        [a / 1000 for a in AMPS_MM],
        N_AFF,
        SEEDS,
        alpha=ALPHA,
        window_s=WINDOW_S,
        base=cfg,
        window_threshold=threshold,
    )
    return {
        "window_calibrated": g["window"],
        "station": g["station"],
        "window_given_station": g["window_given_station"],
    }


def _json_safe(x):
    """NaN (no station alarm in any seed) as null, so the file is strict JSON."""
    if isinstance(x, dict):
        return {k: _json_safe(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_json_safe(v) for v in x]
    if isinstance(x, float) and np.isnan(x):
        return None
    return x


def main() -> int:
    results = {}
    for name, cfg in MODELS.items():
        cal = null_calibration(cfg)
        pw = power(cfg, cal["window_threshold_calibrated"])
        results[name] = {
            "config": asdict(cfg),
            "null": cal,
            **{k: v.tolist() for k, v in pw.items()},
        }

        print(f"\n== {name}")
        print(
            f"  null, nominal chi2 threshold: epoch false alarms {cal['epoch_false_alarm_at_nominal']:.4f},"
            f" window false alarms {cal['window_false_alarm_at_nominal']:.4f}  (alpha {ALPHA})"
        )
        print(
            f"  window threshold: nominal {cal['window_threshold_nominal_chi2']:.0f},"
            f" calibrated {cal['window_threshold_calibrated']:.0f} (dof {cal['window_dof']})"
        )
        for k in ("window_calibrated", "window_given_station"):
            print(f"  {k} (rows: bubble RMS mm/s {AMPS_MM}; cols: satellites {N_AFF})")
            for i, a in enumerate(AMPS_MM):
                print(f"    {a:4d}  " + "  ".join(f"{v:5.2f}" for v in pw[k][i]))

    fig, ax = plt.subplots(1, len(MODELS), figsize=(3.1 * len(MODELS), 3.6), sharey=True)
    for a, (name, r) in zip(ax, results.items(), strict=True):
        g = np.array(r["window_calibrated"])
        im = a.imshow(g, vmin=0, vmax=1, cmap="viridis", origin="lower", aspect="auto")
        a.set_xticks(range(len(N_AFF)), N_AFF)
        a.set_yticks(range(len(AMPS_MM)), AMPS_MM)
        a.set_xlabel("satellites in the bubble")
        a.set_title(name, fontsize=8)
        for i in range(len(AMPS_MM)):
            for j in range(len(N_AFF)):
                a.text(
                    j,
                    i,
                    f"{g[i, j]:.2f}",
                    ha="center",
                    va="center",
                    fontsize=7,
                    color="w" if g[i, j] < 0.6 else "k",
                )
    ax[0].set_ylabel("bubble RMS range-rate (mm/s)")
    fig.colorbar(im, ax=ax, shrink=0.8, label="share of bubble epochs flagged")
    fig.suptitle(
        f"{WINDOW_S:.0f} s window test at a threshold calibrated on quiet data (alpha {ALPHA}, {len(SEEDS)} seeds)",
        fontsize=10,
    )
    out = HERE / "figures" / "session3_power.png"
    fig.savefig(out, dpi=110, bbox_inches="tight")

    payload = {
        "alpha": ALPHA,
        "window_s": WINDOW_S,
        "null_seeds": [NULL_SEEDS.start, NULL_SEEDS.stop],
        "seeds": list(SEEDS),
        "amps_mm_s": AMPS_MM,
        "n_affected": N_AFF,
        "models": results,
    }
    (HERE / "figures" / "session3_results.json").write_text(
        json.dumps(_json_safe(payload), indent=2, allow_nan=False) + "\n"
    )
    print(f"\n{out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
