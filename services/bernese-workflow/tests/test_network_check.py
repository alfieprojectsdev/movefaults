"""The network check, on small synthetic years with the saved-file layout of a real run."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from bernese_workflow import network_check as nc

YEAR = 2023
STATIONS = [f"S{i:03d}" for i in range(30)]
SPLIT_AT = 18  # S000-S017 stay put; S018-S029 are the group that can shift


def _xyz(index: int) -> tuple[float, float, float]:
    """A station position in the Philippines, about 40 km from the next one."""
    lat, lon = math.radians(8.0 + 0.3 * index), math.radians(122.0 + 0.2 * index)
    r = 6_378_000.0
    return r * math.cos(lat) * math.cos(lon), r * math.cos(lat) * math.sin(lon), r * math.sin(lat)


def _east(xyz: tuple[float, float, float], mm: float) -> tuple[float, float, float]:
    lon = math.atan2(xyz[1], xyz[0])
    m = mm / 1000.0
    return xyz[0] - math.sin(lon) * m, xyz[1] + math.cos(lon) * m, xyz[2]


def _write_day(year_dir: Path, doy: int, shift_mm: dict[str, float], stations=STATIONS) -> None:
    lines = ["title", "-" * 80, "LOCAL GEODETIC DATUM: IGS20", "", "NUM  STATION NAME", ""]
    for i, name in enumerate(stations):
        # A small repeatable wobble, so the medians aren't all exactly equal.
        wobble = 1.5 * math.sin(doy * 1.7 + i)
        x, y, z = _east(_xyz(int(name[1:])), shift_mm.get(name, 0.0) + wobble)
        lines.append(f"{i + 1:3d}  {name} {name}       {x:14.5f} {y:14.5f} {z:14.5f}    A")
    # A station carried along from the a priori file: no flag, so not estimated.
    lines.append(" 99  NOTE NOTE        1000000.00000  2000000.00000  3000000.00000")
    (year_dir / "STA").mkdir(parents=True, exist_ok=True)
    (year_dir / "STA" / f"FIN_{year_dir.name}{doy:03d}0.CRD").write_text("\n".join(lines) + "\n")


def _write_prc(year_dir: Path, doy: int) -> None:
    rows = []
    for i in range(len(STATIONS) - 1):
        a, b = STATIONS[i], STATIONS[i + 1]
        rows.append(
            f"  {i + 1:3d}   {a} {a}         {b} {b}            tot   31       86     14 83.7%"
        )
    text = "\n".join(rows) + (
        "\n RNX2SNX: Verification of fiducial stations\n"
        " |   1 | S000 11111M001   | I W |  1.00  1.00  1.00 |   |\n"
        " |   2 | S001 11112M001   | I A |  9.00  9.00  9.00 | V |\n"
        " |   3 | S002 11113M001   | I W |  1.00  1.00  1.00 |   |\n"
    )
    (year_dir / "OUT").mkdir(parents=True, exist_ok=True)
    (year_dir / "OUT" / f"R2S_{year_dir.name}{doy:03d}0.PRC").write_text(text)


@pytest.fixture
def year_dir(tmp_path: Path) -> Path:
    return tmp_path / str(YEAR)


def _quiet_year(year_dir: Path, days=range(1, 41)) -> None:
    for doy in days:
        _write_day(year_dir, doy, {})


def test_quiet_year_has_no_findings_and_says_what_it_checked(year_dir):
    _quiet_year(year_dir)
    result = nc.check_year(year_dir, YEAR)
    assert result.findings == []
    assert len(result.checked) == 40
    assert result.summary() == "network check: 40 days checked, none suspect"


def test_a_shifted_group_is_reported_with_the_baseline_that_joins_it(year_dir):
    _quiet_year(year_dir)
    _write_day(year_dir, 20, dict.fromkeys(STATIONS[SPLIT_AT:], -22.0))
    _write_prc(year_dir, 20)
    result = nc.check_year(year_dir, YEAR)
    assert [f.doy for f in result.findings] == [20]
    finding = result.findings[0]
    assert finding.moved == 12
    assert finding.datum == ("S000", "S002")
    assert sorted(finding.groups) == [12, 18]
    assert finding.separation_mm == pytest.approx(22.0, abs=2.0)
    assert finding.links == (("S017", "S018"),)
    assert "joined by S017-S018" in str(finding)
    assert "1 of 40 days suspect (DOY 020)" in result.summary()


def test_a_real_offset_that_lasts_is_not_a_bad_day(year_dir):
    for doy in range(1, 41):
        _write_day(year_dir, doy, dict.fromkeys(STATIONS, -40.0) if doy >= 20 else {})
    assert nc.check_year(year_dir, YEAR).findings == []


def test_a_bad_day_at_the_end_of_the_data_is_compared_with_the_days_before(year_dir):
    _quiet_year(year_dir, range(1, 21))
    _write_day(year_dir, 21, dict.fromkeys(STATIONS[SPLIT_AT:], -30.0))
    assert [f.doy for f in nc.check_year(year_dir, YEAR).findings] == [21]


def test_below_the_share_a_few_moved_stations_are_not_a_finding(year_dir):
    _quiet_year(year_dir)
    _write_day(year_dir, 20, dict.fromkeys(STATIONS[:7], -80.0))  # 7 of 30 is 23%
    assert nc.check_year(year_dir, YEAR).findings == []


def test_a_day_without_enough_stations_is_not_checked_rather_than_clean(year_dir):
    _quiet_year(year_dir)
    _write_day(year_dir, 20, {}, stations=STATIONS[:10])
    result = nc.check_year(year_dir, YEAR)
    assert 20 in result.not_checked and 20 not in result.checked
    assert result.summary().endswith("; 1 day not checked")


def test_a_requested_day_with_no_solution_is_not_checked(year_dir):
    _quiet_year(year_dir)
    result = nc.check_year(year_dir, YEAR, [20, 200])
    assert result.checked == [20]
    assert result.not_checked == [200]


def test_a_finding_survives_a_missing_processing_summary(year_dir):
    _quiet_year(year_dir)
    _write_day(year_dir, 20, dict.fromkeys(STATIONS[SPLIT_AT:], -22.0))
    finding = nc.check_year(year_dir, YEAR).findings[0]
    assert finding.datum == () and finding.links == ()


def test_only_estimated_stations_are_read(year_dir):
    _write_day(year_dir, 1, {})
    stations = nc.read_crd(year_dir / "STA" / f"FIN_{YEAR}0010.CRD")
    assert "NOTE" not in stations and len(stations) == 30


def test_an_offset_near_the_end_of_the_data_is_marked_as_one_sided(year_dir):
    for doy in range(1, 41):
        _write_day(year_dir, doy, dict.fromkeys(STATIONS, -40.0) if doy >= 38 else {})
    result = nc.check_year(year_dir, YEAR)
    assert [f.doy for f in result.findings] == [38, 39, 40]
    assert all(f.one_sided for f in result.findings)
    assert "real offset isn't ruled out" in str(result.findings[0])
    assert "DOY 038, 039, 040 compared on one side only" in result.summary()


def test_a_bad_day_with_both_sides_is_not_marked_as_one_sided(year_dir):
    _quiet_year(year_dir)
    _write_day(year_dir, 20, dict.fromkeys(STATIONS[SPLIT_AT:], -22.0))
    result = nc.check_year(year_dir, YEAR)
    assert not result.findings[0].one_sided
    assert "one side" not in str(result.findings[0]) + result.summary()


def test_a_small_network_splits_at_a_group_smaller_than_the_usual_minimum():
    # 7 of 27 is suspect, and the 75 mm gap is the split, not a cut at the usual 8.
    shifts = {f"S{i:03d}": (0.3 * i, 0.0) for i in range(20)}
    shifts |= {f"M{i:03d}": (-80.0 - 0.3 * i, 0.0) for i in range(7)}
    groups, separation, _ = nc._split(shifts, [])
    assert sorted(groups) == [7, 20]
    assert separation == pytest.approx(85.0, abs=5.0)


def test_the_split_follows_the_axis_with_the_gap_not_the_wider_scatter():
    # The scatter is in north; the 8 shifted stations are only visible in east.
    shifts = {f"S{i:03d}": (0.1 * i, 6.0 * (-1) ** i) for i in range(22)}
    shifts |= {f"M{i:03d}": (40.0 + 0.1 * i, 6.0 * (-1) ** i) for i in range(8)}
    groups, separation, _ = nc._split(shifts, [])
    assert sorted(groups) == [8, 22]
    assert separation == pytest.approx(40.0, abs=3.0)


def test_a_missing_processing_summary_does_not_read_as_no_datum_stations(year_dir):
    _quiet_year(year_dir)
    _write_day(year_dir, 20, dict.fromkeys(STATIONS[SPLIT_AT:], -22.0))
    assert "datum" not in str(nc.check_year(year_dir, YEAR).findings[0])


def test_one_day_is_written_as_one_day(year_dir):
    _quiet_year(year_dir)
    assert nc.check_year(year_dir, YEAR, [20]).summary() == (
        "network check: 1 day checked, none suspect"
    )


def test_a_file_that_only_resembles_a_solution_is_ignored(year_dir):
    _quiet_year(year_dir)
    (year_dir / "STA" / f"FIN_{YEAR}ABC0.CRD").write_text("not a day\n")
    assert len(nc.check_year(year_dir, YEAR).checked) == 40


def test_a_requested_day_uses_only_its_neighbours(year_dir, monkeypatch):
    _quiet_year(year_dir)
    read: list[str] = []
    real = nc.read_crd
    monkeypatch.setattr(nc, "read_crd", lambda p: read.append(p.name) or real(p))
    assert nc.check_year(year_dir, YEAR, [20]).checked == [20]
    assert len(read) == 2 * nc.WINDOW_DAYS + 1


def test_cli_exit_codes(year_dir, capsys):
    argv = ["--campaign", "X", "--year", str(YEAR), "--year-dir", str(year_dir)]
    assert nc.main(argv) == 2  # nothing solved is not a pass
    _quiet_year(year_dir)
    assert nc.main(argv) == 0
    _write_day(year_dir, 20, dict.fromkeys(STATIONS[SPLIT_AT:], -22.0))
    assert nc.main(argv) == 1
    assert "DOY 020" in capsys.readouterr().out
    assert nc.main([*argv, "--from", "30", "--to", "40"]) == 0
