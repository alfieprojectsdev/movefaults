"""Compose truth, noise and labels into one scenario.

y_i = -u_i . v + b + d_i + e_i, per epoch and satellite (see README).
Each scenario also carries what an LVM-style station-level stream would show
for the same epochs, so both feature sets can be compared on identical data.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np

from .geometry import design_matrix, los_enu, make_sky, sky_distance_deg, weights
from .residual import station_level
from .signals import epb_range_rate, glitch, quake_velocity

LABELS = ("quiet", "quake", "epb", "glitch", "quake+epb")


@dataclass(frozen=True)
class Config:
    """Every number here is a placeholder until calibrated (see README)."""

    n_sat: int = 10
    el_mask_deg: float = 10.0
    sigma0: float = 0.003  # m/s, per-satellite range-rate noise at zenith
    rate_hz: float = 1.0
    duration_s: float = 1500.0
    clock_drift: float = 0.01  # m/s, constant over the scenario
    quake_onset_s: float = 300.0
    quake_peak_enu: tuple = (0.05, 0.03, 0.01)  # m/s
    quake_dur_s: float = 20.0
    quake_shape: str = "halfsine"
    epb_onset_s: float = 300.0
    epb_dur_s: float = 600.0
    epb_amp: float = 0.01  # m/s RMS
    epb_n_affected: int = 3
    epb_band_hz: tuple = (0.02, 0.3)
    glitch_amp: float = 0.03  # m/s
    glitch_kind: str = "spike"
    coseismic_lag_s: float = 600.0  # ionospheric disturbance after a large quake
    extra: dict = field(default_factory=dict)


@dataclass
class Scenario:
    label: str
    y: np.ndarray  # (T, N) observations, m/s
    H: np.ndarray  # (N, 4)
    W: np.ndarray  # (N,)
    t: np.ndarray  # (T,) seconds
    truth: dict
    station: dict  # LVM-style outputs: v, cov, cq, n_sats per epoch


def build(label: str, cfg: Config, rng: np.random.Generator) -> Scenario:
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}; one of {LABELS}")
    n = cfg.n_sat
    t = np.arange(int(cfg.duration_s * cfg.rate_hz)) / cfg.rate_hz
    az, el = make_sky(n, rng, cfg.el_mask_deg)
    los = los_enu(az, el)
    H, W = design_matrix(los), weights(el, cfg.sigma0)

    # Draw every random quantity in a fixed order whatever the label, so a
    # label change never shifts the noise of the others for the same seed.
    bub_az, bub_el = rng.uniform(0, 360), np.degrees(np.arcsin(rng.uniform(0.3, 1.0)))
    glitch_sat = int(rng.integers(n))
    noise = rng.standard_normal((len(t), n)) / np.sqrt(W)
    epb_rng = np.random.default_rng(rng.integers(2**63))

    v = np.zeros((len(t), 3))
    d = np.zeros((len(t), n))
    truth = {
        "seed_label": label,
        "az_deg": az.tolist(),
        "el_deg": el.tolist(),
        "quake_onset_s": None,
        "epb_onset_s": None,
        "epb_sats": [],
        "glitch_sat": None,
        "sky_distance_deg": sky_distance_deg(az, el, bub_az, bub_el).tolist(),
        "config": asdict(cfg),
    }

    if "quake" in label:
        v = quake_velocity(
            t, cfg.quake_onset_s, cfg.quake_peak_enu, cfg.quake_dur_s, cfg.quake_shape
        )
        truth["quake_onset_s"] = cfg.quake_onset_s
    if "epb" in label:
        onset = cfg.quake_onset_s + cfg.coseismic_lag_s if label == "quake+epb" else cfg.epb_onset_s
        # A bubble is crossed by the rays that point at it: pick the satellites
        # nearest one sky point, not a uniform random subset.
        dist = np.asarray(truth["sky_distance_deg"])
        sats = np.argsort(dist)[: cfg.epb_n_affected]
        mask = np.zeros(n, dtype=bool)
        mask[sats] = True
        d += epb_range_rate(
            t, onset, cfg.epb_dur_s, cfg.epb_amp, mask, epb_rng, cfg.rate_hz, cfg.epb_band_hz
        )
        truth["epb_onset_s"] = onset
        truth["epb_sats"] = sorted(int(i) for i in sats)
    if label == "glitch":
        d += glitch(t, cfg.quake_onset_s, glitch_sat, cfg.glitch_amp, n, cfg.glitch_kind)
        truth["glitch_sat"] = glitch_sat

    y = -(v @ los.T) + cfg.clock_drift + d + noise
    truth["v_true"] = v
    station = station_level(H, W, y, dof=n - 4)
    return Scenario(label, y, H, W, t, truth, station)
