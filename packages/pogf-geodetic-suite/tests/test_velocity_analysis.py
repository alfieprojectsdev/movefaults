"""Tests for timeseries.analysis — velocity estimation from ENU time series."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from pogf_geodetic_suite.timeseries.analysis import (
    OffsetEvent,
    OffsetType,
    SegmentVelocity,
    VelocityResult,
    _detect_outliers_iqr,
    _fit_segment,
    estimate_velocity,
    parse_offsets_file,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _synthetic_enu(
    t: np.ndarray,
    ve: float = 10.0,
    vn: float = -5.0,
    vu: float = 2.0,
    noise: float = 0.001,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Generate synthetic ENU (metres) with prescribed velocity (mm/yr)."""
    if rng is None:
        rng = np.random.default_rng(42)
    # v mm/yr → m/yr; displacement = v_m_yr * t (centred at t[0])
    t_rel = t - t[0]
    enu = np.column_stack([
        (ve / 1000) * t_rel,
        (vn / 1000) * t_rel,
        (vu / 1000) * t_rel,
    ])
    return enu + rng.normal(0, noise, enu.shape)


# ---------------------------------------------------------------------------
# _detect_outliers_iqr
# ---------------------------------------------------------------------------

def test_detect_outliers_iqr_flags_extreme_value():
    data = np.zeros((10, 3))
    data[5, 0] = 100.0  # extreme East spike
    mask = _detect_outliers_iqr(data, factor=3.0)
    assert mask[5]
    assert not mask[:5].any()
    assert not mask[6:].any()


def test_detect_outliers_iqr_no_outliers_in_clean_series():
    rng = np.random.default_rng(0)
    data = rng.normal(0, 0.001, (50, 3))
    mask = _detect_outliers_iqr(data, factor=3.0)
    assert not mask.any()


def test_detect_outliers_iqr_factor_controls_sensitivity():
    rng = np.random.default_rng(5)
    data = rng.normal(0, 0.001, (50, 3))  # non-zero IQR background
    data[25, 1] = 0.05  # moderate spike — 50× noise level
    # Tight factor catches it, very loose factor does not
    strict = _detect_outliers_iqr(data, factor=1.0)
    loose = _detect_outliers_iqr(data, factor=100.0)
    assert strict[25]
    assert not loose[25]


# ---------------------------------------------------------------------------
# _fit_segment
# ---------------------------------------------------------------------------

def test_fit_segment_recovers_known_velocity():
    t = np.linspace(2010, 2020, 100)
    # 10 mm/yr East, -5 mm/yr North, 2 mm/yr Up (no noise)
    enu = np.column_stack([
        (10 / 1000) * (t - t[0]),
        (-5 / 1000) * (t - t[0]),
        (2 / 1000) * (t - t[0]),
    ])
    vel, sig, r2 = _fit_segment(t, enu)
    assert vel == pytest.approx([10.0, -5.0, 2.0], abs=0.01)
    assert r2 == pytest.approx([1.0, 1.0, 1.0], abs=1e-6)


def test_fit_segment_uncertainty_decreases_with_more_data():
    rng = np.random.default_rng(7)
    noise = 0.002

    t_small = np.linspace(2010, 2020, 10)
    t_large = np.linspace(2010, 2020, 100)
    enu_s = _synthetic_enu(t_small, noise=noise, rng=rng)
    enu_l = _synthetic_enu(t_large, noise=noise, rng=rng)

    _, sig_small, _ = _fit_segment(t_small, enu_s)
    _, sig_large, _ = _fit_segment(t_large, enu_l)

    # More data → smaller standard error
    assert np.all(sig_large < sig_small)


def test_fit_segment_r2_near_one_for_low_noise():
    t = np.linspace(2010, 2020, 50)
    enu = _synthetic_enu(t, noise=1e-6)  # near-zero noise
    _, _, r2 = _fit_segment(t, enu)
    assert np.all(r2 > 0.999)


# ---------------------------------------------------------------------------
# estimate_velocity — single segment
# ---------------------------------------------------------------------------

def test_estimate_velocity_single_segment_recovers_velocity():
    t = np.linspace(2010, 2020, 120)
    enu = _synthetic_enu(t, ve=15.0, vn=-8.0, vu=3.0, noise=0.001)

    result = estimate_velocity(t, enu, station="BOST")
    assert isinstance(result, VelocityResult)
    assert result.station == "BOST"
    assert len(result.segments) == 1

    sv = result.final_velocity
    assert sv.ve_mm_yr == pytest.approx(15.0, abs=0.5)
    assert sv.vn_mm_yr == pytest.approx(-8.0, abs=0.5)
    assert sv.vu_mm_yr == pytest.approx(3.0, abs=0.5)


def test_estimate_velocity_final_velocity_is_last_segment():
    t = np.linspace(2010, 2020, 200)
    enu = _synthetic_enu(t, ve=10.0, noise=0.001)
    # Add offset at midpoint — second segment has a different velocity
    offset = [OffsetEvent(date=2015.0, offset_type=OffsetType.EQ)]
    result = estimate_velocity(t, enu, offsets=offset, station="BOST")
    assert len(result.segments) == 2
    assert result.final_velocity is result.segments[-1]


def test_estimate_velocity_removes_outliers():
    rng = np.random.default_rng(3)
    t = np.linspace(2010, 2020, 100)
    enu = _synthetic_enu(t, ve=10.0, noise=0.001, rng=rng)
    # Inject a spike at index 50
    enu[50, 0] = 5.0   # 5-metre East spike — obvious outlier
    result = estimate_velocity(t, enu, outlier_iqr_factor=3.0)
    sv = result.final_velocity
    assert len(sv.outlier_epochs) >= 1
    assert sv.ve_mm_yr == pytest.approx(10.0, abs=1.0)


def test_estimate_velocity_sorts_time_input():
    """Unsorted input should give the same result as sorted."""
    t = np.linspace(2010, 2020, 50)
    enu = _synthetic_enu(t, ve=10.0, noise=0.001)
    rev_result = estimate_velocity(t[::-1], enu[::-1, :], station="X")
    fwd_result = estimate_velocity(t, enu, station="X")
    assert rev_result.final_velocity.ve_mm_yr == pytest.approx(
        fwd_result.final_velocity.ve_mm_yr, abs=0.01
    )


def test_estimate_velocity_raises_on_wrong_shape():
    t = np.linspace(2010, 2020, 20)
    with pytest.raises(ValueError, match="shape"):
        estimate_velocity(t, t)  # 1-D instead of (N, 3)


def test_estimate_velocity_raises_on_length_mismatch():
    t = np.linspace(2010, 2020, 20)
    enu = np.zeros((30, 3))
    with pytest.raises(ValueError):
        estimate_velocity(t, enu)


def test_estimate_velocity_raises_when_too_few_clean_points():
    # 3-point segment where all points are outliers after removal
    t = np.array([2010.0, 2011.0, 2012.0])
    enu = np.zeros((3, 3))
    enu[0, :] = 100.0   # all three are extreme in different ways
    enu[1, :] = -100.0
    enu[2, :] = 200.0
    with pytest.raises(ValueError, match="3"):
        estimate_velocity(t, enu, outlier_iqr_factor=0.001)  # ultra-strict → removes all


# ---------------------------------------------------------------------------
# estimate_velocity — offset segmentation
# ---------------------------------------------------------------------------

def test_estimate_velocity_two_segments_different_velocities():
    rng = np.random.default_rng(9)
    t1 = np.linspace(2010, 2014.9, 60)
    t2 = np.linspace(2015.0, 2020, 60)
    t = np.concatenate([t1, t2])

    enu1 = _synthetic_enu(t1, ve=5.0, noise=0.001, rng=rng)
    enu2 = _synthetic_enu(t2, ve=20.0, noise=0.001, rng=rng)
    # Reset position at segment 2 (simulate offset step)
    enu = np.vstack([enu1, enu1[-1:] + enu2 - enu2[:1]])

    offsets = [OffsetEvent(date=2015.0, offset_type=OffsetType.EQ)]
    result = estimate_velocity(t, enu, offsets=offsets)

    assert len(result.segments) == 2
    assert result.segments[1].ve_mm_yr == pytest.approx(20.0, abs=1.5)


def test_estimate_velocity_offset_type_stored_in_event():
    ev = OffsetEvent(date=2015.0, offset_type=OffsetType.CE)
    assert ev.offset_type == OffsetType.CE
    assert ev.offset_type.value == "CE"


def test_segment_velocity_dataclass_frozen():
    sv = SegmentVelocity(
        ve_mm_yr=10.0, vn_mm_yr=-5.0, vu_mm_yr=2.0,
        sig_ve=0.1, sig_vn=0.1, sig_vu=0.1,
        r2_e=0.99, r2_n=0.99, r2_u=0.99,
        n_points=50, t_start=2010.0, t_end=2020.0,
    )
    with pytest.raises(Exception):
        sv.ve_mm_yr = 99.0  # frozen dataclass


# ---------------------------------------------------------------------------
# parse_offsets_file
# ---------------------------------------------------------------------------

def test_parse_offsets_file_reads_eq_and_ce(tmp_path):
    f = tmp_path / "offsets"
    f.write_text("ALBU 2017.5147 EQ\nBOST 2013.1234 CE\n", encoding="utf-8")
    result = parse_offsets_file(f)
    assert "ALBU" in result and "BOST" in result
    assert result["ALBU"][0].offset_type == OffsetType.EQ
    assert result["BOST"][0].offset_type == OffsetType.CE
    assert result["ALBU"][0].date == pytest.approx(2017.5147)


def test_parse_offsets_file_skips_comments_and_blanks(tmp_path):
    f = tmp_path / "offsets"
    f.write_text("# this is a comment\n\nBOST 2015.0 EQ\n", encoding="utf-8")
    result = parse_offsets_file(f)
    assert "BOST" in result
    assert len(result) == 1


def test_parse_offsets_file_unknown_type_defaults_to_uk(tmp_path):
    f = tmp_path / "offsets"
    f.write_text("BOST 2015.0 MYSTERY\n", encoding="utf-8")
    result = parse_offsets_file(f)
    assert result["BOST"][0].offset_type == OffsetType.UK


def test_parse_offsets_file_multiple_events_per_station(tmp_path):
    f = tmp_path / "offsets"
    f.write_text("BOST 2015.0 EQ\nBOST 2018.5 CE\n", encoding="utf-8")
    result = parse_offsets_file(f)
    assert len(result["BOST"]) == 2


def test_parse_offsets_file_site_uppercased(tmp_path):
    f = tmp_path / "offsets"
    f.write_text("bost 2015.0 EQ\n", encoding="utf-8")
    result = parse_offsets_file(f)
    assert "BOST" in result
