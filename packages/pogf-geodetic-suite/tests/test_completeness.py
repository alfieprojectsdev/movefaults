"""Tests for the RINEX completeness scan.

The test that matters is `test_reproduces_the_2025_short_reference_days`: it
reconstructs the failure this module exists to predict, from the day numbers
recorded in SESSION_LOG_20260729_storage.md §24.1. If that one passes, the
tool would have caught six of the eight days the 2025 run lost, before staging
rather than after failing.
"""
from __future__ import annotations

import pytest
from pogf_geodetic_suite.qc.completeness import (
    DEFAULT_REFERENCE_STATIONS,
    Coverage,
    compress_ranges,
    days_in_year,
    is_leap_year,
    scan,
)

# ---------------------------------------------------------------------------
# leap years — the legacy checker used `% 4 == 0` and got 1900/2100 wrong
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "year, leap",
    [(2024, True), (2025, False), (2000, True), (1900, False), (2100, False), (2400, True)],
)
def test_is_leap_year(year, leap):
    assert is_leap_year(year) is leap


def test_legacy_mod4_rule_disagrees_on_century_years():
    """Pin the bug that was fixed, so it is not reintroduced as a simplification."""
    for year in (1900, 2100, 2200):
        assert (year % 4 == 0) is True
        assert is_leap_year(year) is False


@pytest.mark.parametrize("year, n", [(2024, 366), (2025, 365), (1900, 365), (2000, 366)])
def test_days_in_year(year, n):
    assert days_in_year(year) == n


# ---------------------------------------------------------------------------
# range compression
# ---------------------------------------------------------------------------


def test_compress_ranges_empty():
    assert compress_ranges([]) == ""


def test_compress_ranges_single():
    assert compress_ranges([7]) == "007"


def test_compress_ranges_contiguous():
    assert compress_ranges([1, 2, 3, 4]) == "001-004"


def test_compress_ranges_mixed():
    assert compress_ranges([1, 2, 3, 5, 9, 10]) == "001-003, 005, 009-010"


def test_compress_ranges_pads_to_three_digits():
    # DOY numbers sort visually only when padded; `9, 100` is a misread waiting
    # to happen in a log somebody reads months later.
    assert compress_ranges([9, 100]) == "009, 100"


# ---------------------------------------------------------------------------
# filename parsing — RINEX 2 and RINEX 3, which is the gap in the legacy tool
# ---------------------------------------------------------------------------


def _touch(root, name):
    p = root / name
    p.write_text("")
    return p


def test_scan_finds_rinex2_lower_and_upper(tmp_path):
    _touch(tmp_path, "ALCO0010.25o")
    _touch(tmp_path, "MAR20020.25O")
    cov = scan(tmp_path, 2025)
    assert cov.by_station["ALCO"] == {1}
    assert cov.by_station["MAR2"] == {2}


def test_scan_finds_hatanaka_and_compressed(tmp_path):
    _touch(tmp_path, "ALCO0030.25d")
    _touch(tmp_path, "ALCO0040.25o.gz")
    _touch(tmp_path, "ALCO0050.25D.Z")
    cov = scan(tmp_path, 2025)
    assert cov.by_station["ALCO"] == {3, 4, 5}


def test_scan_finds_rinex3(tmp_path):
    # Every IGS fiducial is RINEX 3. The legacy checker matched .YYo only and
    # so was blind to exactly the stations whose absence broke the 2025 run.
    _touch(tmp_path, "PIMO00PHL_R_20250010000_01D_30S_MO.rnx")
    _touch(tmp_path, "AIRA00JPN_R_20250010000_01D_30S_MO.crx.gz")
    cov = scan(tmp_path, 2025)
    assert cov.by_station["PIMO"] == {1}
    assert cov.by_station["AIRA"] == {1}
    assert cov.by_day[1] == {"PIMO", "AIRA"}


def test_scan_ignores_other_years(tmp_path):
    _touch(tmp_path, "ALCO0010.24o")
    _touch(tmp_path, "PIMO00PHL_R_20240010000_01D_30S_MO.rnx")
    cov = scan(tmp_path, 2025)
    assert cov.by_station == {}


def test_scan_recurses_into_subdirectories(tmp_path):
    sub = tmp_path / "2025" / "001"
    sub.mkdir(parents=True)
    _touch(sub, "ALCO0010.25o")
    cov = scan(tmp_path, 2025)
    assert cov.by_station["ALCO"] == {1}


def test_scan_records_rinex_looking_files_it_cannot_parse(tmp_path):
    _touch(tmp_path, "not-a-station.25o")
    cov = scan(tmp_path, 2025)
    assert cov.by_station == {}
    assert len(cov.unparsed) == 1


def test_scan_ignores_unrelated_files(tmp_path):
    _touch(tmp_path, "README.md")
    _touch(tmp_path, "solution.SNX")
    cov = scan(tmp_path, 2025)
    assert cov.unparsed == []


# ---------------------------------------------------------------------------
# the actual point of the module
# ---------------------------------------------------------------------------


def test_gaps_lists_absent_days(tmp_path):
    _touch(tmp_path, "ALCO0010.25o")
    _touch(tmp_path, "ALCO0030.25o")
    cov = scan(tmp_path, 2025)
    gaps = cov.gaps("ALCO")
    assert 2 in gaps
    assert 1 not in gaps
    assert len(gaps) == 363


def test_short_days_flags_days_below_the_helmert_minimum():
    cov = Coverage(year=2025)
    cov.by_day[1] = {"PIMO", "AIRA", "DARW"}   # 3 refs — fine
    cov.by_day[2] = {"PIMO", "AIRA"}           # 2 refs — short
    cov.by_day[3] = {"ALCO", "MAR2"}           # 0 refs — short
    short = cov.short_days(DEFAULT_REFERENCE_STATIONS, 3, 1, 3)
    assert [d for d, _, _ in short] == [2, 3]
    assert short[0][1] == 2
    assert short[1][2] == []


def test_short_days_counts_only_reference_stations():
    """Twenty local stations do not make a day processable."""
    cov = Coverage(year=2025)
    cov.by_day[1] = {f"L{i:03d}" for i in range(20)} | {"PIMO"}
    short = cov.short_days(DEFAULT_REFERENCE_STATIONS, 3, 1, 1)
    assert short == [(1, 1, ["PIMO"])]


def test_days_with_no_data_at_all_are_reported_as_short():
    cov = Coverage(year=2025)
    short = cov.short_days(DEFAULT_REFERENCE_STATIONS, 3, 10, 12)
    assert [d for d, _, _ in short] == [10, 11, 12]


def test_reproduces_the_2025_short_reference_days(tmp_path):
    """The case this module exists for.

    SESSION_LOG_20260729_storage.md §24.1 records eight absent days in the 2025
    LUZON run. Six — DOY 058-061, 079 and 345 — were "fewer than three
    reference stations". Build a datapool with exactly that shape and confirm
    the scan names those six and nothing else.
    """
    starved = {58, 59, 60, 61, 79, 345}
    for doy in range(1, 366):
        # locals are always present; they are not what makes a day processable
        _touch(tmp_path, f"ALCO{doy:03d}0.25o")
        refs = ["PIMO"] if doy in starved else ["PIMO", "AIRA", "DARW", "ALIC"]
        for sta in refs:
            _touch(tmp_path, f"{sta}00XXX_R_2025{doy:03d}0000_01D_30S_MO.rnx")

    cov = scan(tmp_path, 2025)
    short = cov.short_days(DEFAULT_REFERENCE_STATIONS, 3)

    assert {d for d, _, _ in short} == starved
    assert compress_ranges([d for d, _, _ in short]) == "058-061, 079, 345"
    for _, count, present in short:
        assert count == 1 and present == ["PIMO"]
