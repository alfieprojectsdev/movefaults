"""Tests for GMT velocity-field output.

Two of these guard things that make a *map* wrong rather than a number wrong,
which is the failure mode that survives review: once a velocity field is a PNG
in a presentation, the reference frame is unrecoverable and an implausible
vector has already rescaled every other arrow on the page.
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
from pogf_geodetic_suite.timeseries.gmt import (
    VelocityVector,
    to_vectors,
    write_psvelo,
    write_vertical,
)

POSITIONS = {
    "ANQ0": (121.05, 14.65, 80.0),      # (lon, lat, height)
    "AR17": (120.60, 16.40, 120.0),
    "TARL": (120.59, 15.48, 60.0),
}


def series(rate_m_yr, n=400, t0=2014.0, t1=2025.0, steps=None):
    t = np.linspace(t0, t1, n)
    enu = np.outer(t - t[0], np.asarray(rate_m_yr))
    for date, amp in (steps or {}).items():
        enu = enu + np.outer((t >= date).astype(float), np.asarray(amp))
    return t, enu


def test_psvelo_row_layout_and_units(tmp_path):
    v = VelocityVector("ANQ0", 121.05, 14.65, -74.537, 38.699, 0.9, 1.4)
    out = tmp_path / "vel.psvelo"
    n, quarantined = write_psvelo([v], out, reference_station="S01R")

    assert (n, quarantined) == (1, [])
    data = [ln for ln in out.read_text().splitlines() if not ln.startswith("#")]
    assert len(data) == 1
    f = data[0].split()
    # lon lat Ve Vn sigVe sigVn corrEN name
    assert len(f) == 8
    assert float(f[0]) == pytest.approx(121.05)
    assert float(f[1]) == pytest.approx(14.65)
    assert float(f[2]) == pytest.approx(-74.537)
    assert float(f[3]) == pytest.approx(38.699)
    assert float(f[6]) == 0.0          # correlation: honest zero, see module docs
    assert f[7] == "ANQ0"


def test_reference_frame_is_always_in_the_header(tmp_path):
    """A velocity map without a stated reference frame is misleading, not merely
    incomplete. The writer must not be able to omit it."""
    out = tmp_path / "vel.psvelo"
    write_psvelo([VelocityVector("ANQ0", 121.0, 14.6, -70.0, 30.0, 1.0, 1.0)],
                 out, reference_station="PIMO")
    header = out.read_text()
    assert "REFERENCE FRAME" in header
    assert "PIMO" in header
    assert "not ITRF" in header


def test_implausible_velocities_are_commented_not_dropped(tmp_path):
    """
    The short-final-segment defect, caught at the map boundary.

    TARL's published East rate is 2008 mm/yr — a week of scatter after an
    offset. GMT scales arrows to the largest vector, so one such station makes
    every real vector on the map invisible. It is commented rather than dropped
    so the omission is visible in the file.
    """
    good = VelocityVector("ANQ0", 121.05, 14.65, -74.5, 38.7, 0.9, 1.4)
    bad = VelocityVector("TARL", 120.59, 15.48, 2008.754, -1402.3, 500.0, 400.0)
    out = tmp_path / "vel.psvelo"

    n, quarantined = write_psvelo([good, bad], out, reference_station="S01R")

    assert n == 1
    assert quarantined == ["TARL"]
    text = out.read_text()
    assert "WITHHELD" in text
    assert "TARL" in text                       # still present, for the record
    data = [ln for ln in text.splitlines() if not ln.startswith("#")]
    assert len(data) == 1 and data[0].split()[7] == "ANQ0"


def test_quarantine_can_be_disabled(tmp_path):
    bad = VelocityVector("TARL", 120.59, 15.48, 2008.754, -1402.3, 500.0, 400.0)
    out = tmp_path / "vel.psvelo"
    n, quarantined = write_psvelo([bad], out, reference_station="S01R",
                                  max_speed_mm_yr=None)
    assert (n, quarantined) == (1, [])
    assert "WITHHELD" not in out.read_text()


def test_to_vectors_uses_the_joint_rate_in_force_at_the_end():
    """With a fitted rate change, the mapped vector must be the post-event rate."""
    t = np.linspace(2014.0, 2026.0, 800)
    pre = np.array([-0.039, 0.009, 0.002])
    post = np.where(t >= 2017.512, t - 2017.512, 0.0)
    enu = np.outer(t - t[0], pre) + np.outer(post, np.array([0.009, 0.0, 0.0]))

    r = estimate_velocity_joint(
        t, enu, offsets=[OffsetEvent(2017.512, OffsetType.EQ)],
        station="ANQ0", rate_changes=True,
    )
    vectors, skipped = to_vectors([r], POSITIONS)

    assert skipped == []
    assert vectors[0].ve_mm_yr == pytest.approx(-30.0, abs=1e-3)   # post, not pre
    assert vectors[0].lon_deg == pytest.approx(121.05)


def test_to_vectors_reports_stations_it_could_not_place():
    t, enu = series([-0.035, 0.010, 0.002])
    r = estimate_velocity(t, enu, station="ZZZZ")
    vectors, skipped = to_vectors([r], POSITIONS)
    assert vectors == []
    assert skipped == ["ZZZZ"]


def test_to_vectors_can_raise_instead_of_skipping():
    t, enu = series([-0.035, 0.010, 0.002])
    r = estimate_velocity(t, enu, station="ZZZZ")
    with pytest.raises(KeyError, match="ZZZZ"):
        to_vectors([r], POSITIONS, skip_missing=False)


def test_vertical_file_is_separate_and_carries_the_frame(tmp_path):
    v = VelocityVector("ANQ0", 121.05, 14.65, -74.5, 38.7, 0.9, 1.4,
                       vu_mm_yr=30.9, sig_vu=9.8)
    out = tmp_path / "vert.xyz"
    n, quarantined = write_vertical([v], out, reference_station="S01R")
    assert (n, quarantined) == (1, [])

    text = out.read_text()
    assert "REFERENCE FRAME" in text
    row = [ln for ln in text.splitlines() if not ln.startswith("#")][0].split()
    assert len(row) == 5
    assert float(row[2]) == pytest.approx(30.9)
    assert row[4] == "ANQ0"


def test_vertical_skips_stations_without_a_vertical_rate(tmp_path):
    v = VelocityVector("ANQ0", 121.05, 14.65, -74.5, 38.7, 0.9, 1.4)
    out = tmp_path / "vert.xyz"
    n, quarantined = write_vertical([v], out, reference_station="S01R")
    assert (n, quarantined) == (0, [])


def test_notes_reach_the_header(tmp_path):
    out = tmp_path / "vel.psvelo"
    write_psvelo([VelocityVector("ANQ0", 121.0, 14.6, -70.0, 30.0, 1.0, 1.0)],
                 out, reference_station="S01R",
                 notes=["epoch span: 2014.4 - 2025.8", "catalog: offsets@a950529"])
    text = out.read_text()
    assert "# epoch span: 2014.4 - 2025.8" in text
    assert "# catalog: offsets@a950529" in text


def test_speed_is_horizontal_only():
    v = VelocityVector("X", 0.0, 0.0, 30.0, 40.0, 1.0, 1.0, vu_mm_yr=999.0)
    assert v.speed_mm_yr == pytest.approx(50.0)


def test_caller_can_withhold_a_station_the_speed_filter_misses(tmp_path):
    """
    LUZD is the real case. Its -115 mm/yr East is implausible for the
    Philippines but passes a 200 mm/yr threshold, and it comes from 36 days of
    data. Without an explicit hold, a station the pipeline already flagged as
    "not a velocity" is still drawn on the map.
    """
    luzd = VelocityVector("LUZD", 120.456, 17.551, -115.455, 21.818, 28.4, 8.4)
    good = VelocityVector("ANQ0", 121.649, 16.260, -74.537, 38.699, 0.9, 1.4)
    out = tmp_path / "vel.psvelo"

    n, quarantined = write_psvelo(
        [good, luzd], out, reference_station="S01R",
        withhold={"LUZD": "final interval spans 36 days"},
    )

    assert n == 1 and quarantined == ["LUZD"]
    text = out.read_text()
    assert "final interval spans 36 days" in text
    data = [ln for ln in text.splitlines() if not ln.startswith("#")]
    assert len(data) == 1 and data[0].split()[7] == "ANQ0"


def test_withhold_reason_wins_over_the_speed_message(tmp_path):
    """A station failing both gets the specific reason, not the generic one."""
    bad = VelocityVector("ZBS1", 119.95, 15.41, 1339.664, -1483.298, 1784.8, 517.7)
    out = tmp_path / "vel.psvelo"
    write_psvelo([bad], out, reference_station="S01R",
                 withhold={"ZBS1": "final interval spans 3 days"})
    text = out.read_text()
    assert "final interval spans 3 days" in text
    assert "exceeds 200" not in text


# ── The quarantine must reach both files ─────────────────────────────────────
#
# `write_vertical` originally took no `withhold`, so a station the pipeline had
# already judged "not a velocity" was written into the vertical file as an
# ordinary data row while the horizontal file commented it out. Vertical is the
# noisier component by roughly three, so the unguarded file was the more
# misleading of the two — and nothing in it hinted the value was questioned.

def _vec(station="ANQ0", span=9.0, vu=30.9):
    return VelocityVector(station, 121.05, 14.65, -74.5, 38.7, 0.9, 1.4,
                          vu_mm_yr=vu, sig_vu=9.8, final_span_yr=span)


def test_withheld_station_is_commented_in_the_vertical_file(tmp_path):
    out = tmp_path / "vert.xyz"
    n, quarantined = write_vertical(
        [_vec()], out, reference_station="S01R",
        withhold={"ANQ0": "final interval spans 36 days"},
    )

    assert (n, quarantined) == (0, ["ANQ0"])
    text = out.read_text()
    assert "# WITHHELD (final interval spans 36 days)" in text
    # Commented, never deleted — the row is still recoverable by hand.
    assert "ANQ0" in text
    data_rows = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
    assert data_rows == []


def test_vertical_withhold_matches_the_horizontal_file(tmp_path):
    # The two writers must be able to take the same mapping, so a caller cannot
    # hold one file to a standard and forget the other.
    vectors = [_vec("ANQ0"), _vec("AR17")]
    withhold = {"ANQ0": "final interval spans 36 days"}

    h, h_q = write_psvelo(vectors, tmp_path / "h.psvelo",
                          reference_station="S01R", withhold=withhold)
    v, v_q = write_vertical(vectors, tmp_path / "v.vert",
                            reference_station="S01R", withhold=withhold)

    assert h_q == v_q == ["ANQ0"]
    assert h == v == 1


def test_vertical_withhold_is_case_insensitive(tmp_path):
    n, quarantined = write_vertical(
        [_vec("ANQ0")], tmp_path / "v.vert", reference_station="S01R",
        withhold={"anq0": "short span"},
    )
    assert quarantined == ["ANQ0"]
    assert n == 0


# ── The span guard belongs to the library ────────────────────────────────────
#
# A rate change near the end of a record yields a rate fitted from days, and the
# sigma published beside it is the baseline sigma rather than the post-event
# one — so the error ellipse understates rather than advertises the problem.
# When this check lived only in make_velocity_field.py, every other caller of
# to_vectors published that vector unguarded.

def test_to_vectors_records_the_span_the_rate_was_fitted_over():
    t = np.linspace(2015.0, 2025.0, 400)
    enu = np.column_stack([-0.035 * (t - 2015), 0.010 * (t - 2015),
                           0.002 * (t - 2015)])
    r = estimate_velocity(t, enu, station="ANQ0")

    vectors, _ = to_vectors([r], POSITIONS)

    assert vectors[0].final_span_yr == pytest.approx(10.0, abs=0.05)


def test_short_final_interval_flags_only_the_short_ones():
    from pogf_geodetic_suite.timeseries.gmt import short_final_interval

    vectors = [_vec("ANQ0", span=9.0), _vec("TARL", span=36 / 365.25)]
    withhold = short_final_interval(vectors)

    assert set(withhold) == {"TARL"}
    assert "36 days" in withhold["TARL"]


def test_short_final_interval_does_not_flag_an_unrecorded_span():
    # Absence of the measurement is not evidence the span is adequate; hiding a
    # station on missing metadata would withhold it for the wrong reason.
    from pogf_geodetic_suite.timeseries.gmt import short_final_interval

    bare = VelocityVector("ANQ0", 121.05, 14.65, -74.5, 38.7, 0.9, 1.4)
    assert short_final_interval([bare]) == {}
