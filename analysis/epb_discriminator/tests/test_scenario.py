"""Scenarios: one of each label, the right shapes, and identical output per seed."""

from __future__ import annotations

import numpy as np
import pytest
from epb.scenario import LABELS, Config, build


@pytest.mark.parametrize("label", LABELS)
def test_every_label_builds(label):
    cfg = Config()
    s = build(label, cfg, np.random.default_rng(7))
    T = int(cfg.duration_s * cfg.rate_hz)
    assert s.label == label
    assert s.y.shape == (T, cfg.n_sat)
    assert s.H.shape == (cfg.n_sat, 4)
    assert s.W.shape == (cfg.n_sat,)
    assert s.truth["seed_label"] == label


def test_same_seed_same_scenario():
    a = build("quake+epb", Config(), np.random.default_rng(11))
    b = build("quake+epb", Config(), np.random.default_rng(11))
    np.testing.assert_array_equal(a.y, b.y)
    np.testing.assert_array_equal(a.truth.pop("v_true"), b.truth.pop("v_true"))
    assert a.truth == b.truth


def test_station_level_outputs_are_lvm_shaped():
    # The same epochs as the per-satellite data, reduced to what an LVM sentence
    # carries: velocity, its covariance, cq and the satellite count.
    cfg = Config()
    s = build("quake", cfg, np.random.default_rng(2))
    T = len(s.t)
    assert s.station["v"].shape == (T, 3)
    assert s.station["cov"].shape == (T, 3, 3)
    assert s.station["cq"].shape == (T,)
    assert (s.station["n_sats"] == cfg.n_sat).all()
    # during the pulse the estimated velocity tracks the true one within its own
    # stated uncertainty (vertical is the weakest component: it trades off
    # against the clock term, so a fixed tolerance would be the wrong test)
    k = int(cfg.quake_onset_s + cfg.quake_dur_s / 2)
    err = s.station["v"][k] - s.truth["v_true"][k]
    sd = np.sqrt(np.diag(s.station["cov"][k]))
    assert (np.abs(err) < 4 * sd).all(), (err, sd)


def test_epb_satellites_are_a_sky_sector_not_a_random_draw():
    cfg = Config(n_sat=12, epb_n_affected=4)
    s = build("epb", cfg, np.random.default_rng(3))
    idx = s.truth["epb_sats"]
    assert len(idx) == 4
    # the chosen ones are the 4 closest to the bubble's sky point
    d = s.truth["sky_distance_deg"]
    assert set(idx) == set(np.argsort(d)[:4].tolist())


def test_quiet_has_no_signal_and_quake_moves_every_satellite():
    cfg = Config()
    q = build("quiet", cfg, np.random.default_rng(5))
    assert q.truth["quake_onset_s"] is None and q.truth["epb_sats"] == []
    k = build("quake", cfg, np.random.default_rng(5))
    assert k.truth["quake_onset_s"] is not None
    assert np.abs(k.truth["v_true"]).max() > 0


def test_quake_plus_epb_starts_the_bubble_after_the_pulse():
    cfg = Config()
    s = build("quake+epb", cfg, np.random.default_rng(9))
    assert s.truth["epb_onset_s"] - s.truth["quake_onset_s"] == pytest.approx(cfg.coseismic_lag_s)
