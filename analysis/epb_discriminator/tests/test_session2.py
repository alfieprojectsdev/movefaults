"""Session 2: the windowed statistic, the evaluation helpers and the ledger."""

from __future__ import annotations

import numpy as np
import pytest
from epb.eval import reject_epoch, reject_window, station_alarm
from epb.ledger import Ledger, LedgerError
from epb.scenario import Config, build


def test_window_statistic_holds_its_false_reject_rate():
    # Summing chi2 over a window must keep the stated alpha under the null,
    # or every power number built on it is wrong.
    cfg = Config(duration_s=3000)
    rates = []
    for seed in range(20):
        s = build("quiet", cfg, np.random.default_rng(seed))
        rates.append(reject_window(s, window_s=30, alpha=0.01).mean())
    assert abs(np.mean(rates) - 0.01) < 0.004


def test_epoch_statistic_holds_its_false_reject_rate():
    cfg = Config(duration_s=3000)
    s = build("quiet", cfg, np.random.default_rng(1))
    assert abs(reject_epoch(s, alpha=0.01).mean() - 0.01) < 0.006


def test_window_is_more_sensitive_than_single_epoch_for_a_sustained_bubble():
    cfg = Config(epb_amp=0.006, epb_n_affected=3)
    e, w = [], []
    for seed in range(10):
        s = build("epb", cfg, np.random.default_rng(seed))
        core = _core(s, cfg)
        e.append(reject_epoch(s, alpha=0.001)[core].mean())
        w.append(reject_window(s, window_s=30, alpha=0.001)[core].mean())
    assert np.mean(w) > np.mean(e)


def test_station_alarm_is_the_current_horizontal_speed_rule():
    cfg = Config()
    s = build("quake", cfg, np.random.default_rng(0))
    alarm = station_alarm(s, threshold_mm_s=15.0)
    vh = np.hypot(s.station["v"][:, 0], s.station["v"][:, 1]) * 1000
    np.testing.assert_array_equal(alarm, vh >= 15.0)
    k = int(cfg.quake_onset_s + cfg.quake_dur_s / 2)
    assert alarm[k]  # a 58 mm/s horizontal pulse trips it


def _core(s, cfg):
    on = s.truth["epb_onset_s"]
    return (s.t >= on + 0.1 * cfg.epb_dur_s) & (s.t <= on + 0.9 * cfg.epb_dur_s)


# ---- ledger --------------------------------------------------------------


def test_status_change_needs_cited_evidence_whose_output_was_stored():
    led = Ledger()
    c = led.open_claim("H_epb", confidence=0.5)
    ev = led.add_evidence(
        c, check="resid_chi2", result="reject_H_eq", value=4.1, output=b"chi2=4.1"
    )
    led.update(c, status="supported", confidence=0.7, cite=ev["output_hash"])
    assert led.claims[c]["status"] == "supported"
    assert led.claims[c]["confidence"] == 0.7


def test_update_without_or_with_a_wrong_citation_is_rejected():
    led = Ledger()
    c = led.open_claim("H_eq")
    with pytest.raises(LedgerError):
        led.update(c, status="rejected", cite=None)
    with pytest.raises(LedgerError):
        led.update(c, status="rejected", cite="0" * 64)
    assert led.claims[c]["status"] == "open"


def test_evidence_for_one_claim_cannot_be_cited_for_another():
    led = Ledger()
    a, b = led.open_claim("H_eq"), led.open_claim("H_epb")
    ev = led.add_evidence(a, check="resid_chi2", result="support", value=0.9, output=b"x")
    with pytest.raises(LedgerError):
        led.update(b, status="supported", cite=ev["output_hash"])


def test_evidence_result_vocabulary_is_closed():
    led = Ledger()
    c = led.open_claim("H_glitch")
    with pytest.raises(LedgerError):
        led.add_evidence(c, check="resid_chi2", result="probably", value=1.0, output=b"x")


def test_quake_plus_bubble_keeps_both_hypotheses_open():
    # Brief, constraint 4: co-seismic overlap must not force one hypothesis.
    led = Ledger()
    eq, epb = led.open_claim("H_eq"), led.open_claim("H_epb")
    led.add_evidence(eq, check="resid_chi2", result="support", value=1.0, output=b"pulse fits")
    led.add_evidence(epb, check="resid_chi2", result="support", value=6.2, output=b"later misfit")
    assert led.claims[eq]["status"] == "open" and led.claims[epb]["status"] == "open"


def test_quake_cost_scales_the_peak_in_mm_per_s():
    from epb.eval import quake_cost

    rows = quake_cost([5.0, 60.0], seeds=range(3))
    # a 5 mm/s pulse stays under the 15 mm/s detector, a 60 mm/s one trips it
    assert rows[0]["station_alarm"] < 0.2
    assert rows[1]["station_alarm"] > 0.5
