"""Session 2 evaluation: decisions per epoch, and the sweeps built on them.

Three decisions are compared on the same scenarios:

- reject_epoch:  the per-epoch global test, chi2/dof against chi2(N-4).
- reject_window: chi2 summed over a trailing window of W epochs, against
                 chi2(W(N-4)). A bubble is sustained and the noise is not,
                 so summing over time should find what one epoch cannot.
- station_alarm: the current detector, horizontal speed >= threshold, computed
                 from the scenario's LVM-style station output alone.

Both residual tests use per-satellite data; the station alarm does not. The
gap between them is what the spike is meant to measure.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy import stats

from .residual import leakage, mdb, wls
from .scenario import Config, build


def _q(s):
    """Per-epoch weighted residual sum of squares (T,), and its dof."""
    _, r, _ = wls(s.H, s.W, s.y)
    return r**2 @ s.W, s.H.shape[0] - 4


def reject_epoch(s, alpha: float) -> np.ndarray:
    q, dof = _q(s)
    return q > stats.chi2.ppf(1 - alpha, dof)


def reject_window(s, window_s: float, alpha: float) -> np.ndarray:
    """Trailing-window test. The first window-1 epochs cannot be tested: False."""
    q, dof = _q(s)
    w = max(1, int(round(window_s * s.truth["config"]["rate_hz"])))
    csum = np.concatenate([[0.0], np.cumsum(q)])
    out = np.zeros(len(q), dtype=bool)
    sums = csum[w:] - csum[:-w]
    out[w - 1 :] = sums > stats.chi2.ppf(1 - alpha, dof * w)
    return out


def station_alarm(s, threshold_mm_s: float = 15.0) -> np.ndarray:
    v = s.station["v"]
    return np.hypot(v[:, 0], v[:, 1]) * 1000 >= threshold_mm_s


def _core(s, cfg: Config, onset_key: str, dur: float) -> np.ndarray:
    on = s.truth[onset_key]
    return (s.t >= on + 0.1 * dur) & (s.t <= on + 0.9 * dur)


def power_grid(amps, n_affected, seeds, *, alpha=0.001, window_s=30.0, base=Config()):
    """Detection rate inside the bubble's core, per (amp, n_affected).

    Returns dict of arrays shaped (len(amps), len(n_affected)) for 'epoch',
    'window' and 'station' (the share of bubble epochs that trip the current
    detector, i.e. false quake alarms), plus 'window_given_station': of the
    epochs that trip the detector, the share the window test flags.
    """
    keys = ("epoch", "window", "station", "window_given_station")
    out = {k: np.full((len(amps), len(n_affected)), np.nan) for k in keys}
    for i, a in enumerate(amps):
        for j, n in enumerate(n_affected):
            cfg = replace(base, epb_amp=a, epb_n_affected=n)
            acc = {k: [] for k in keys}
            for seed in seeds:
                s = build("epb", cfg, np.random.default_rng(seed))
                core = _core(s, cfg, "epb_onset_s", cfg.epb_dur_s)
                re, rw, st = (
                    reject_epoch(s, alpha)[core],
                    reject_window(s, window_s, alpha)[core],
                    station_alarm(s)[core],
                )
                acc["epoch"].append(re.mean())
                acc["window"].append(rw.mean())
                acc["station"].append(st.mean())
                if st.any():
                    acc["window_given_station"].append(rw[st].mean())
            for k in keys:
                if acc[k]:
                    out[k][i, j] = float(np.mean(acc[k]))
    return out


def quake_cost(peaks_mm_s, seeds, *, alpha=0.001, window_s=30.0, base=Config()):
    """Share of true-quake pulse epochs the residual tests reject, per peak.

    In this model a quake is a rigid motion and fits exactly, so the expected
    answer is alpha at every amplitude. The number that matters will come from
    real data, where multipath and unmodelled effects grow with shaking.
    """
    rows = []
    for p in peaks_mm_s:
        factor = (p / 1000) / np.linalg.norm(base.quake_peak_enu)  # peak p mm/s, same direction
        cfg = replace(base, quake_peak_enu=tuple(np.array(base.quake_peak_enu) * factor))
        e, w, st = [], [], []
        for seed in seeds:
            s = build("quake", cfg, np.random.default_rng(seed))
            pulse = (s.t >= cfg.quake_onset_s) & (s.t <= cfg.quake_onset_s + cfg.quake_dur_s)
            e.append(reject_epoch(s, alpha)[pulse].mean())
            w.append(reject_window(s, window_s, alpha)[pulse].mean())
            st.append(station_alarm(s)[pulse].mean())
        rows.append(
            {
                "peak_mm_s": p,
                "epoch_reject": float(np.mean(e)),
                "window_reject": float(np.mean(w)),
                "station_alarm": float(np.mean(st)),
            }
        )
    return rows


def blind_spots(n_geometries, n_sat, seed, *, alpha=0.001, power=0.8, base=Config()):
    """MDB and leakage over random geometries, in mm/s.

    leak_h / leak_u: horizontal and vertical velocity error per unit bias on
    one satellite. fake_h_at_mdb: the horizontal velocity a bias exactly at the
    MDB produces while still passing the test, which is the size of quake an
    undetected single-satellite fault can fake.
    """
    rng = np.random.default_rng(seed)
    from .geometry import design_matrix, los_enu, make_sky, weights

    mdbs, lh, lu, fake = [], [], [], []
    for _ in range(n_geometries):
        az, el = make_sky(n_sat, rng, base.el_mask_deg)
        H = design_matrix(los_enu(az, el))
        W = weights(el, base.sigma0)
        m = mdb(H, W, alpha=alpha, power=power)
        L = leakage(H, W)
        h = np.hypot(L[:, 0], L[:, 1])
        mdbs.extend(m * 1000)
        lh.extend(h)
        lu.extend(np.abs(L[:, 2]))
        fake.extend(h * m * 1000)

    def q(x):
        return {"median": float(np.median(x)), "p95": float(np.percentile(x, 95))}

    return {"mdb_mm_s": q(mdbs), "leak_h": q(lh), "leak_u": q(lu), "fake_h_at_mdb_mm_s": q(fake)}
