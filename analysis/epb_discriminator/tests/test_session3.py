"""Session 3: the correlated noise models, and what they do to the window test."""

from __future__ import annotations

import numpy as np
from epb.eval import reject_window
from epb.scenario import Config, build


def _noise(cfg: Config, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    s = build("quiet", cfg, np.random.default_rng(seed))
    return s.y - cfg.clock_drift, 1.0 / np.sqrt(s.W)


def _lag1(x: np.ndarray) -> float:
    return float(np.mean([np.corrcoef(x[:-1, i], x[1:, i])[0, 1] for i in range(x.shape[1])]))


def test_tdcp_keeps_the_per_epoch_sigma_and_correlates_neighbours_at_minus_half():
    e, sigma = _noise(Config(noise_model="tdcp", duration_s=6000))
    assert np.allclose(e.std(axis=0) / sigma, 1.0, atol=0.05)
    assert -0.55 < _lag1(e) < -0.45


def test_white_noise_is_uncorrelated_and_unchanged_by_default():
    e, _ = _noise(Config(duration_s=6000))
    assert abs(_lag1(e)) < 0.05
    a = build("epb", Config(), np.random.default_rng(3)).y
    b = build("epb", Config(noise_model="white", mp_amp=0.0), np.random.default_rng(3)).y
    assert np.array_equal(a, b)


def test_multipath_residual_fraction_scales_what_is_left():
    quiet = {"sigma0": 1e-9, "mp_amp": 0.01, "mp_period_s": 30.0, "duration_s": 3000}
    full, _ = _noise(Config(**quiet))
    left, _ = _noise(Config(**quiet, mp_resid_frac=0.2))
    assert np.isclose(left.std() / full.std(), 0.2, rtol=0.02)


def test_differenced_noise_breaks_the_nominal_window_threshold():
    # Squares of correlated errors are positively correlated whatever the
    # sign, so the window sum is wider than chi2 and over-alarms. The window
    # threshold has to be calibrated on quiet data, not taken from chi2.
    rates = {}
    for model in ("white", "tdcp"):
        cfg = Config(noise_model=model, duration_s=3000)
        rates[model] = np.mean(
            [
                reject_window(build("quiet", cfg, np.random.default_rng(seed)), 30, 0.01).mean()
                for seed in range(20)
            ]
        )
    assert rates["white"] < 0.015
    assert rates["tdcp"] > 1.5 * rates["white"]
