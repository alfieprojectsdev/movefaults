"""Tests for joint rate + step estimation.

The cases here are chosen around one question PHIVOLCS asked directly: can the
step amplitude at an earthquake be estimated instead of eyeballed? The answer
has to hold in the awkward case -- a step near the end of the record -- because
that is where the current segmented fit fails, and fails loudly enough to have
reached a published plot (ALBU, 2025-11-11).
"""
from __future__ import annotations

import numpy as np
import pytest
from pogf_geodetic_suite.timeseries.analysis import (
    OffsetEvent,
    OffsetType,
    estimate_velocity,
    estimate_velocity_joint,
)

RATE_M_YR = np.array([-0.035, 0.010, 0.002])   # realistic PH rates, m/yr


def synth(t: np.ndarray, steps: dict[float, np.ndarray] | None = None,
          noise: float = 0.0, seed: int = 0) -> np.ndarray:
    """Linear motion plus exact steps; optional Gaussian noise in metres."""
    enu = np.outer(t - t[0], RATE_M_YR)
    for date, amp in (steps or {}).items():
        enu += np.outer((t >= date).astype(float), amp)
    if noise:
        enu = enu + np.random.default_rng(seed).normal(0.0, noise, enu.shape)
    return enu


def test_recovers_known_step_and_rate():
    t = np.linspace(2014.0, 2025.0, 400)
    amp = np.array([0.050, -0.030, 0.012])       # 50, -30, 12 mm
    enu = synth(t, {2019.0: amp})

    r = estimate_velocity_joint(
        t, enu, offsets=[OffsetEvent(2019.0, OffsetType.EQ)], station="SYN"
    )

    assert r.ve_mm_yr == pytest.approx(RATE_M_YR[0] * 1000, abs=1e-6)
    assert r.vn_mm_yr == pytest.approx(RATE_M_YR[1] * 1000, abs=1e-6)
    assert len(r.steps) == 1
    s = r.steps[0]
    assert s.de_mm == pytest.approx(50.0, abs=1e-6)
    assert s.dn_mm == pytest.approx(-30.0, abs=1e-6)
    assert s.du_mm == pytest.approx(12.0, abs=1e-6)
    assert s.resolvable


def test_multiple_steps_are_separable():
    t = np.linspace(2014.0, 2026.0, 600)
    enu = synth(t, {2017.512: np.array([0.040, -0.020, 0.005]),
                    2022.570: np.array([-0.015, 0.025, -0.008])})

    r = estimate_velocity_joint(
        t, enu,
        offsets=[OffsetEvent(2022.570, OffsetType.EQ),   # deliberately unsorted
                 OffsetEvent(2017.512, OffsetType.EQ)],
        station="SYN",
    )

    assert [s.date for s in r.steps] == [2017.512, 2022.570]
    assert r.steps[0].de_mm == pytest.approx(40.0, abs=1e-6)
    assert r.steps[1].dn_mm == pytest.approx(25.0, abs=1e-6)
    assert r.ve_mm_yr == pytest.approx(RATE_M_YR[0] * 1000, abs=1e-6)


def test_the_albu_case_segmented_fails_and_joint_does_not():
    """
    The defect that reached a published plot.

    ALBU's continuous series ends 7 days after the 2025.7474 Bogo earthquake.
    The segmented fit reports the slope of that week; the joint fit constrains
    the rate with the whole record and reports the step separately.
    """
    t = np.concatenate([
        np.linspace(2014.4, 2025.7474, 1200),
        np.linspace(2025.7480, 2025.7666, 7),     # seven daily epochs
    ])
    enu = synth(t, {2025.7474: np.array([0.030, -0.010, 0.004])},
                noise=0.004, seed=7)
    offs = [OffsetEvent(2025.7474, OffsetType.EQ)]

    segmented = estimate_velocity(t, enu, offsets=offs, station="ALBU")
    final = segmented.final_velocity
    assert final.t_end - final.t_start < 0.03            # a week of data

    # The comparison that matters: error against the rate we actually put in,
    # not an arbitrary magnitude threshold.
    truth_e = RATE_M_YR[0] * 1000
    segmented_error = abs(final.ve_mm_yr - truth_e)
    assert segmented_error > 100.0                       # wrong by ~7x the signal

    joint = estimate_velocity_joint(t, enu, offsets=offs, station="ALBU")
    assert abs(joint.ve_mm_yr - truth_e) < 1.0
    assert abs(joint.ve_mm_yr - truth_e) < segmented_error / 100
    assert joint.ve_mm_yr == pytest.approx(truth_e, abs=1.0)
    assert joint.vn_mm_yr == pytest.approx(RATE_M_YR[1] * 1000, abs=1.0)
    # The step is recovered, but the data cannot really constrain it -- and the
    # result says so rather than leaving the caller to notice.
    assert joint.steps[0].de_mm == pytest.approx(30.0, abs=6.0)
    assert not joint.steps[0].resolvable
    assert joint.unresolvable_steps == [joint.steps[0]]


def test_step_amplitude_carries_a_usable_uncertainty():
    t = np.linspace(2014.0, 2025.0, 800)
    enu = synth(t, {2019.0: np.array([0.050, 0.0, 0.0])}, noise=0.005, seed=3)

    r = estimate_velocity_joint(
        t, enu, offsets=[OffsetEvent(2019.0, OffsetType.EQ)], station="SYN"
    )
    s = r.steps[0]
    assert s.de_mm == pytest.approx(50.0, abs=3 * s.sig_de)
    assert 0.0 < s.sig_de < 5.0
    assert s.resolvable


def test_rate_change_term_detects_a_genuine_slope_change():
    """`rate_changes=True` turns "did the rate change?" into a testable claim."""
    t = np.linspace(2014.0, 2026.0, 600)
    enu = np.outer(t - t[0], RATE_M_YR)
    post = np.where(t >= 2020.0, t - 2020.0, 0.0)
    enu = enu + np.outer(post, np.array([0.020, 0.0, 0.0]))   # +20 mm/yr after

    offs = [OffsetEvent(2020.0, OffsetType.EQ)]
    r = estimate_velocity_joint(t, enu, offsets=offs, station="SYN",
                                rate_changes=True)
    # Pre-event rate is recovered cleanly once the change is in the model.
    assert r.ve_mm_yr == pytest.approx(RATE_M_YR[0] * 1000, abs=1e-6)

    # Without the term, the single rate is dragged toward the post-event slope.
    r2 = estimate_velocity_joint(t, enu, offsets=offs, station="SYN")
    assert r2.ve_mm_yr > r.ve_mm_yr + 5.0


def test_no_offsets_is_a_plain_linear_fit():
    t = np.linspace(2014.0, 2025.0, 300)
    r = estimate_velocity_joint(t, synth(t), station="SYN")
    assert r.steps == []
    assert r.ve_mm_yr == pytest.approx(RATE_M_YR[0] * 1000, abs=1e-6)


def test_events_outside_the_observed_span_are_dropped():
    """A column of all zeros or all ones is useless or collinear, not an error."""
    t = np.linspace(2018.0, 2025.0, 200)
    r = estimate_velocity_joint(
        t, synth(t),
        offsets=[OffsetEvent(2010.0, OffsetType.EQ),    # before the record
                 OffsetEvent(2030.0, OffsetType.CE)],   # after it
        station="SYN",
    )
    assert r.steps == []
    assert r.ve_mm_yr == pytest.approx(RATE_M_YR[0] * 1000, abs=1e-6)


def test_too_few_epochs_raises_rather_than_returning_nonsense():
    t = np.array([2020.0, 2020.5, 2021.0])
    enu = synth(t, {2020.4: np.array([0.01, 0.01, 0.01])})
    with pytest.raises(ValueError, match="cannot constrain"):
        estimate_velocity_joint(
            t, enu, offsets=[OffsetEvent(2020.4, OffsetType.EQ)], station="SYN"
        )


def test_rate_change_is_returned_not_discarded():
    """The ALBU case: the post-event slope genuinely differs from the pre-event one."""
    t = np.linspace(2014.4, 2025.8, 900)
    # East -39 -> -30 mm/yr and Up +9 -> +2 mm/yr across the event, as ALBU shows.
    pre = np.array([-0.039, 0.009, 0.009])
    delta = np.array([0.009, 0.0, -0.007])
    post = np.where(t >= 2017.512, t - 2017.512, 0.0)
    enu = np.outer(t - t[0], pre) + np.outer(post, delta)
    enu += np.outer((t >= 2017.512).astype(float), np.array([0.0, -0.085, 0.0]))

    r = estimate_velocity_joint(
        t, enu, offsets=[OffsetEvent(2017.512, OffsetType.EQ)],
        station="ALBU", rate_changes=True,
    )

    assert len(r.rate_changes) == 1
    rc = r.rate_changes[0]
    assert rc.dve_mm_yr == pytest.approx(9.0, abs=1e-6)
    assert rc.dvu_mm_yr == pytest.approx(-7.0, abs=1e-6)
    assert rc.any_significant()
    assert rc.significant()[0] and rc.significant()[2]

    # Baseline rate is the FIRST interval, not an average of both.
    assert r.ve_mm_yr == pytest.approx(-39.0, abs=1e-6)

    intervals = r.interval_rates()
    assert len(intervals) == 2
    assert intervals[0].ve_mm_yr == pytest.approx(-39.0, abs=1e-6)
    assert intervals[1].ve_mm_yr == pytest.approx(-30.0, abs=1e-6)
    assert intervals[1].vu_mm_yr == pytest.approx(2.0, abs=1e-6)

    assert r.rate_at(2016.0)[0] == pytest.approx(-39.0, abs=1e-6)
    assert r.rate_at(2020.0)[0] == pytest.approx(-30.0, abs=1e-6)

    # The step is still separable from the rate change.
    assert r.steps[0].dn_mm == pytest.approx(-85.0, abs=1e-6)


def test_unchanged_rate_is_not_reported_as_significant():
    """A rate change fitted where none exists must fail its own test."""
    t = np.linspace(2014.0, 2026.0, 900)
    enu = synth(t, {2019.0: np.array([0.040, 0.0, 0.0])}, noise=0.004, seed=11)

    r = estimate_velocity_joint(
        t, enu, offsets=[OffsetEvent(2019.0, OffsetType.EQ)],
        station="SYN", rate_changes=True,
    )
    assert not r.rate_changes[0].any_significant()
    for a, b in zip(r.interval_rates()[0:1], r.interval_rates()[1:2], strict=True):
        assert abs(a.ve_mm_yr - b.ve_mm_yr) < 3.0


def test_interval_rates_without_rate_changes_is_one_interval():
    t = np.linspace(2014.0, 2025.0, 300)
    r = estimate_velocity_joint(
        t, synth(t, {2019.0: np.array([0.03, 0.0, 0.0])}),
        offsets=[OffsetEvent(2019.0, OffsetType.EQ)], station="SYN",
    )
    assert r.rate_changes == []
    assert len(r.interval_rates()) == 1
    assert r.rate_at(2024.0)[0] == pytest.approx(r.ve_mm_yr)


# ── Duplicate catalog dates ──────────────────────────────────────────────────
#
# Two entries on the same day are two legitimate catalog records describing one
# discontinuity — an earthquake and an equipment change on the same date is the
# realistic case. A step column is `t >= date`, so a duplicate date builds a
# column identical to its neighbour: G loses rank and the station dies with
# "design matrix is rank deficient", a message that blames event spacing and
# says nothing about the real cause.

def test_duplicate_event_dates_do_not_break_the_fit():
    t = np.linspace(2015.0, 2025.0, 400)
    enu = synth(t, steps={2019.5: np.array([0.02, -0.01, 0.005])})

    dup = [
        OffsetEvent(date=2019.5, offset_type=OffsetType.EQ),
        OffsetEvent(date=2019.5, offset_type=OffsetType.CE),
    ]
    r = estimate_velocity_joint(t, enu, offsets=dup, station="DUP")

    # One step, not two: the duplicate collapses rather than raising.
    assert len(r.steps) == 1
    assert r.steps[0].date == pytest.approx(2019.5)


def test_duplicate_dates_give_the_same_answer_as_a_single_entry():
    t = np.linspace(2015.0, 2025.0, 400)
    enu = synth(t, steps={2019.5: np.array([0.02, -0.01, 0.005])})

    one = [OffsetEvent(date=2019.5, offset_type=OffsetType.EQ)]
    dup = [*one, OffsetEvent(date=2019.5, offset_type=OffsetType.CE)]

    a = estimate_velocity_joint(t, enu, offsets=one, station="A")
    b = estimate_velocity_joint(t, enu, offsets=dup, station="B")

    assert b.ve_mm_yr == pytest.approx(a.ve_mm_yr)
    assert b.vn_mm_yr == pytest.approx(a.vn_mm_yr)
    assert b.vu_mm_yr == pytest.approx(a.vu_mm_yr)


def test_three_entries_on_one_date_still_collapse_to_one_step():
    t = np.linspace(2015.0, 2025.0, 400)
    enu = synth(t, steps={2019.5: np.array([0.02, -0.01, 0.005])})
    events = [
        OffsetEvent(date=2019.5, offset_type=OffsetType.EQ),
        OffsetEvent(date=2019.5, offset_type=OffsetType.CE),
        OffsetEvent(date=2019.5, offset_type=OffsetType.UK),
    ]
    r = estimate_velocity_joint(t, enu, offsets=events, station="TRIP")
    assert len(r.steps) == 1


def test_distinct_nearby_dates_are_still_two_steps():
    # De-duplication must key on the date, not on "close enough" — two events a
    # month apart are separately resolvable in a ten-year record.
    t = np.linspace(2015.0, 2025.0, 800)
    enu = synth(t, steps={2019.5: np.array([0.02, -0.01, 0.005]),
                          2019.6: np.array([0.01, 0.02, -0.003])})
    events = [
        OffsetEvent(date=2019.5, offset_type=OffsetType.EQ),
        OffsetEvent(date=2019.6, offset_type=OffsetType.EQ),
    ]
    r = estimate_velocity_joint(t, enu, offsets=events, station="TWO")
    assert len(r.steps) == 2


# ── The sigma that goes on the map ───────────────────────────────────────────
#
# `rate_at(t_end)` returns b + Σd_i. Those parameters are fitted together from
# the same epochs, so their errors are correlated and the sigma of the sum is
# not sig_ve. Quoting sig_ve beside a changed rate is wrong in the worst
# direction: it is the SMALLEST number available, so the error ellipse drawn
# from it looks tighter than the fit supports. Measured against Monte Carlo, a
# rate change six months before the end of a ten-year record understates the
# published sigma by a factor of about 80.

def _late_change_series(ev_date: float, seed: int = 1):
    t = np.linspace(2015.0, 2025.0, 600)
    ramp = np.where(t >= ev_date, t - ev_date, 0.0)
    rng = np.random.default_rng(seed)
    enu = (np.outer(t - t[0], RATE_M_YR)
           + np.outer(ramp, np.array([0.010, -0.004, 0.001]))
           + np.outer((t >= ev_date).astype(float), np.array([0.02, -0.01, 0.005]))
           + rng.normal(0, 0.004, (t.size, 3)))
    return t, enu


def test_rate_sigma_at_is_the_sigma_of_the_rate_in_force():
    t, enu = _late_change_series(2024.5)
    ev = [OffsetEvent(date=2024.5, offset_type=OffsetType.EQ)]
    r = estimate_velocity_joint(t, enu, offsets=ev, station="LATE",
                                rate_changes=True, exclude_outliers=False)

    published = r.rate_sigma_at(r.t_end)

    # An order of magnitude is the point; the exact factor depends on the noise
    # draw. Before this existed, sig_ve went on the map unchanged.
    assert published[0] > 10 * r.sig_ve
    assert published[1] > 10 * r.sig_vn
    assert published[2] > 10 * r.sig_vu


def test_rate_sigma_matches_direct_covariance_propagation():
    # Var(b + d) = Var(b) + 2Cov(b, d) + Var(d), recomputed here from the design
    # matrix rather than trusting the stored sub-covariance.
    t, enu = _late_change_series(2024.0)
    ev_date = 2024.0
    ev = [OffsetEvent(date=ev_date, offset_type=OffsetType.EQ)]
    r = estimate_velocity_joint(t, enu, offsets=ev, station="LATE",
                                rate_changes=True, exclude_outliers=False)

    t0 = float(t.mean())
    G = np.column_stack([
        np.ones(t.size), t - t0,
        (t >= ev_date).astype(float),
        np.where(t >= ev_date, t - ev_date, 0.0),
    ])
    model, _, _, _ = np.linalg.lstsq(G, enu, rcond=None)
    mse = np.sum((enu - G @ model) ** 2, axis=0) / (t.size - G.shape[1])
    cov = np.linalg.inv(G.T @ G)
    w = np.array([0.0, 1.0, 0.0, 1.0])          # slope + slope-change
    expected = np.sqrt(float(w @ cov @ w) * mse) * 1000.0

    assert r.rate_sigma_at(r.t_end) == pytest.approx(tuple(expected), rel=1e-9)


def test_rate_sigma_equals_the_baseline_when_no_change_applies():
    # Before the first rate change — and whenever rate_changes is off — the rate
    # in force IS the baseline, so the two sigmas are the same quantity.
    t, enu = _late_change_series(2024.0)
    ev = [OffsetEvent(date=2024.0, offset_type=OffsetType.EQ)]

    r = estimate_velocity_joint(t, enu, offsets=ev, station="LATE",
                                rate_changes=True, exclude_outliers=False)
    assert r.rate_sigma_at(2016.0) == (r.sig_ve, r.sig_vn, r.sig_vu)

    plain = estimate_velocity_joint(t, enu, offsets=ev, station="LATE",
                                    rate_changes=False, exclude_outliers=False)
    assert plain.rate_sigma_at(plain.t_end) == (
        plain.sig_ve, plain.sig_vn, plain.sig_vu)


def test_rate_sigma_falls_back_when_the_covariance_was_not_retained():
    # A result built by hand (a test fixture, a deserialised record) has no
    # covariance. Returning the baseline is the honest fallback; raising would
    # make hand-built results unusable.
    from dataclasses import replace

    t, enu = _late_change_series(2024.0)
    ev = [OffsetEvent(date=2024.0, offset_type=OffsetType.EQ)]
    r = estimate_velocity_joint(t, enu, offsets=ev, station="LATE",
                                rate_changes=True, exclude_outliers=False)
    bare = replace(r, _rate_cov_unit=None, _mse=None)

    assert bare.rate_sigma_at(bare.t_end) == (bare.sig_ve, bare.sig_vn, bare.sig_vu)
