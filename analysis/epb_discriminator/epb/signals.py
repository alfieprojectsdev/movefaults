"""Truth signals: a quake's velocity pulse, a bubble's range-rate noise, a glitch.

Amplitudes and bands are placeholders until calibrated against a recorded day.
"""

from __future__ import annotations

import numpy as np


def quake_velocity(t, t0, peak_vel_enu, dur_s, shape="halfsine"):
    """Station velocity (T, 3) in m/s.

    halfsine: one positive lobe, so displacement steps to a permanent offset of
              peak * 2 * dur / pi.
    damped:   a decaying oscillation with period dur, which returns to rest
              (no permanent offset), as ground shaking without a static step does.
    """
    t = np.asarray(t, dtype=float)
    tau = t - t0
    peak = np.asarray(peak_vel_enu, dtype=float)
    if shape == "halfsine":
        g = np.where((tau >= 0) & (tau <= dur_s), np.sin(np.pi * tau / dur_s), 0.0)
    elif shape == "damped":
        g = np.where(tau >= 0, np.sin(2 * np.pi * tau / dur_s) * np.exp(-tau / dur_s), 0.0)
    else:
        raise ValueError(f"unknown shape {shape!r}")
    return g[:, None] * peak[None, :]


def _band_noise(n, rate_hz, band_hz, rng):
    """Unit-RMS noise limited to band_hz, by zeroing FFT bins outside it."""
    x = rng.standard_normal(n)
    f = np.fft.rfftfreq(n, 1.0 / rate_hz)
    X = np.fft.rfft(x)
    X[(f < band_hz[0]) | (f > band_hz[1])] = 0.0
    y = np.fft.irfft(X, n)
    rms = np.sqrt(np.mean(y**2))
    return y / rms if rms > 0 else y


def epb_range_rate(t, t0, dur_s, amp, sat_mask, rng, rate_hz=1.0, band_hz=(0.02, 0.3)):
    """Extra range-rate error (T, N) on the satellites in sat_mask during the bubble.

    Band-limited noise, independent per satellite, scaled to RMS `amp` and
    tapered in and out (Hann edges, 10 % of the duration) so the onset is not a
    step. Cycle slips are left for session 2.
    """
    t = np.asarray(t, dtype=float)
    n = len(t)
    out = np.zeros((n, len(sat_mask)))
    inside = (t >= t0) & (t <= t0 + dur_s)
    edge = max(dur_s * 0.1, 1e-9)
    tau = t - t0
    taper = np.clip(np.minimum(tau, dur_s - tau) / edge, 0.0, 1.0)
    win = np.where(inside, 0.5 - 0.5 * np.cos(np.pi * taper), 0.0)
    for i in np.flatnonzero(sat_mask):
        out[:, i] = amp * _band_noise(n, rate_hz, band_hz, rng) * win
    return out


def glitch(t, t0, sat_idx, amp, n_sat, kind="spike"):
    """A single-satellite fault (T, N): a one-epoch spike or a step from t0 on."""
    t = np.asarray(t, dtype=float)
    out = np.zeros((len(t), n_sat))
    if kind == "spike":
        out[np.argmin(np.abs(t - t0)), sat_idx] = amp
    elif kind == "step":
        out[t >= t0, sat_idx] = amp
    else:
        raise ValueError(f"unknown kind {kind!r}")
    return out
