"""Tests for timeseries.crd_pipeline — RUNX_v2 Python port."""
from __future__ import annotations

from pathlib import Path

import pytest
from pogf_geodetic_suite.timeseries.crd_pipeline import (
    _extract_session_from_filename,
    crd_directory_to_enu,
    read_crd_file,
    session_to_decimal_year,
)

# ---------------------------------------------------------------------------
# Minimal CRD file fixture
# ---------------------------------------------------------------------------

def _write_crd(path: Path, stations: list[dict]) -> None:
    """Write a minimal Bernese 5.4 CRD file."""
    header = (
        "PHIVOLCS CORS NETWORK                                           01-MAY-26 00:00\n"
        "--------------------------------------------------------------------------------\n"
        "LOCAL GEODETIC DATUM: IGS14                 EPOCH: 2015-01-01 00:00:00\n"
        "\n"
        " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM\n"
        "\n"
    )
    rows = []
    for i, s in enumerate(stations, start=1):
        name = s["name"]
        dome = s.get("dome", "00000S000")
        sname = f"{name[:4]} {dome}"
        rows.append(
            f"  {i:3d}  {sname:<14}  {s['x']:>15.5f} {s['y']:>15.5f}  {s['z']:>15.5f}    IGS14"
        )
    path.write_text(header + "\n".join(rows) + "\n", encoding="ascii")


# ECEF coordinates for a realistic Philippine station (BOST)
BOST_X, BOST_Y, BOST_Z = -3186600.123, 5765432.679, 567890.456
# A second station nearby
PBIS_X, PBIS_Y, PBIS_Z = -3100000.000, 5700000.000, 600000.000


# ---------------------------------------------------------------------------
# read_crd_file
# ---------------------------------------------------------------------------

def test_read_crd_file_extracts_coordinates(tmp_path):
    crd = tmp_path / "F1_23001.CRD"
    _write_crd(crd, [
        {"name": "BOST", "x": BOST_X, "y": BOST_Y, "z": BOST_Z},
    ])
    result = read_crd_file(crd)
    assert len(result) == 1
    code, x, y, z = result[0]
    assert code == "BOST"
    assert x == pytest.approx(BOST_X, rel=1e-6)
    assert y == pytest.approx(BOST_Y, rel=1e-6)
    assert z == pytest.approx(BOST_Z, rel=1e-6)


def test_read_crd_file_multiple_stations(tmp_path):
    crd = tmp_path / "F1_23001.CRD"
    _write_crd(crd, [
        {"name": "BOST", "x": BOST_X, "y": BOST_Y, "z": BOST_Z},
        {"name": "PBIS", "x": PBIS_X, "y": PBIS_Y, "z": PBIS_Z},
    ])
    result = read_crd_file(crd)
    codes = [r[0] for r in result]
    assert "BOST" in codes and "PBIS" in codes


def test_read_crd_file_station_code_uppercased(tmp_path):
    crd = tmp_path / "F1_23001.CRD"
    _write_crd(crd, [{"name": "bost", "x": BOST_X, "y": BOST_Y, "z": BOST_Z}])
    result = read_crd_file(crd)
    assert result[0][0] == "BOST"


def test_read_crd_file_skips_header_lines(tmp_path):
    crd = tmp_path / "F1_23001.CRD"
    # Write a file where the only non-header line has an integer first field
    content = (
        "TITLE LINE\n"
        "-----\n"
        "LOCAL GEODETIC DATUM: IGS14  EPOCH: 2015-01-01\n"
        "\n"
        " NUM  STATION NAME  X  Y  Z  FLAG\n"
        "\n"
        f"    1  BOST 00000S000  {BOST_X:.5f} {BOST_Y:.5f}  {BOST_Z:.5f}    IGS14\n"
    )
    crd.write_text(content, encoding="ascii")
    result = read_crd_file(crd)
    assert len(result) == 1 and result[0][0] == "BOST"


def test_read_crd_file_without_dome(tmp_path):
    """CRD file where station name is listed without a dome number."""
    crd = tmp_path / "nodome.CRD"
    content = (
        "TITLE\n\n\n NUM  STATION  X  Y  Z  FLAG\n\n"
        f"    1  BOST  {BOST_X:.5f} {BOST_Y:.5f}  {BOST_Z:.5f}    IGS14\n"
    )
    crd.write_text(content, encoding="ascii")
    result = read_crd_file(crd)
    assert len(result) == 1
    assert result[0][0] == "BOST"
    assert result[0][1] == pytest.approx(BOST_X, rel=1e-6)


# ---------------------------------------------------------------------------
# session_to_decimal_year
# ---------------------------------------------------------------------------

def test_session_to_decimal_year_doy_001():
    # DOY 1 is year + 1/365.25, NOT year.0000 -- see the function docstring.
    # Exact, not approx: the two candidate conventions differ by 0.002738, and
    # the abs=0.01 tolerance this test used to carry was too loose to tell them
    # apart. That is why the off-by-one survived review.
    assert session_to_decimal_year("23001") == 2023 + 1 / 365.25


def test_session_to_decimal_year_doy_365():
    assert session_to_decimal_year("23365") == 2023 + 365 / 365.25


def test_session_to_decimal_year_matches_runx_v2_for_every_doy():
    """The convention is RUNX_v2.py's. Pin it across the whole year.

    RUNX_v2.py:
        day  = int(allyear[2:5]) / 365.25
        date = int(year) + day
    """
    for doy in range(1, 367):
        legacy = 2023 + doy / 365.25
        assert session_to_decimal_year(f"23{doy:03d}") == legacy


def test_session_to_decimal_year_is_not_the_doy_minus_one_convention():
    """Guard against the change being silently reverted as a 'correction'.

    (DOY-1)/365.25 puts DOY 1 at year.0000 and is arguably the better
    definition in isolation, but it disagrees with the offsets catalog by
    exactly one day at every epoch.
    """
    for doy in (1, 100, 273, 365):
        got = session_to_decimal_year(f"25{doy:03d}")
        other = 2025 + (doy - 1) / 365.25
        assert got != other
        assert got - other == pytest.approx(1 / 365.25, rel=1e-12)


@pytest.mark.parametrize(
    "catalog_entry, expected_doy",
    [
        (2025.7474, 273),   # ALBU, the 2025 Bogo earthquake
        (2017.5147, 188),   # ALBU
        (2023.1314, 48),    # AROY
    ],
)
def test_offsets_catalog_entries_invert_to_whole_days(catalog_entry, expected_doy):
    """Real entries from the production `offsets` file land on whole DOYs.

    This is the evidence that the catalog is written in this convention, and
    it is what makes the choice checkable rather than asserted. Under
    (DOY-1)/365.25 each of these would invert to a whole day plus one.
    """
    year = int(catalog_entry)
    doy = round((catalog_entry - year) * 365.25)
    assert doy == expected_doy
    # and the forward direction agrees to better than a tenth of a day
    reconstructed = session_to_decimal_year(f"{year % 100:02d}{doy:03d}")
    assert abs(reconstructed - catalog_entry) < 0.1 / 365.25


def test_session_to_decimal_year_19xx_range():
    year = session_to_decimal_year("99001")
    assert int(year) == 1999


def test_session_to_decimal_year_20xx_range():
    year = session_to_decimal_year("00001")
    assert int(year) == 2000


def test_session_to_decimal_year_rejects_short_code():
    with pytest.raises(ValueError):
        session_to_decimal_year("2300")


def test_session_to_decimal_year_rejects_invalid_doy():
    with pytest.raises(ValueError, match="Day-of-year"):
        session_to_decimal_year("23400")  # DOY 400 is invalid


# ---------------------------------------------------------------------------
# _extract_session_from_filename
# ---------------------------------------------------------------------------

def test_extract_session_trailing_digits():
    assert _extract_session_from_filename("F1_23001.CRD") == "23001"


def test_extract_session_prefix_variant():
    assert _extract_session_from_filename("AB23001.CRD") == "23001"


def test_extract_session_fin_prefix():
    assert _extract_session_from_filename("FIN_23001.CRD") == "23001"


def test_extract_session_no_digits_returns_none():
    assert _extract_session_from_filename("PIVSMIND.CRD") is None


# ---------------------------------------------------------------------------
# crd_directory_to_enu
# ---------------------------------------------------------------------------

def test_crd_directory_to_enu_basic(tmp_path):
    _write_crd(tmp_path / "F1_23001.CRD", [
        {"name": "BOST", "x": BOST_X, "y": BOST_Y, "z": BOST_Z},
        {"name": "PBIS", "x": PBIS_X, "y": PBIS_Y, "z": PBIS_Z},
    ])
    results = crd_directory_to_enu(tmp_path, reference_station="BOST")
    assert len(results) == 1
    assert results[0].station == "PBIS"
    assert isinstance(results[0].east_m, float)
    assert isinstance(results[0].decimal_year, float)
    assert int(results[0].decimal_year) == 2023


def test_crd_directory_to_enu_excludes_reference(tmp_path):
    _write_crd(tmp_path / "F1_23001.CRD", [
        {"name": "BOST", "x": BOST_X, "y": BOST_Y, "z": BOST_Z},
        {"name": "PBIS", "x": PBIS_X, "y": PBIS_Y, "z": PBIS_Z},
    ])
    results = crd_directory_to_enu(tmp_path, reference_station="BOST")
    stations = [r.station for r in results]
    assert "BOST" not in stations


def test_crd_directory_to_enu_multiple_epochs(tmp_path):
    for session, dx in [("23001", 0.0), ("23002", 0.001), ("23003", 0.002)]:
        _write_crd(tmp_path / f"F1_{session}.CRD", [
            {"name": "BOST", "x": BOST_X,      "y": BOST_Y, "z": BOST_Z},
            {"name": "PBIS", "x": PBIS_X + dx,  "y": PBIS_Y, "z": PBIS_Z},
        ])
    results = crd_directory_to_enu(tmp_path, reference_station="BOST")
    assert len(results) == 3
    epochs = [r.decimal_year for r in results]
    assert epochs == sorted(epochs)  # sorted by (station, year)


def test_crd_directory_to_enu_sorted_by_station_then_time(tmp_path):
    for session in ["23001", "23002"]:
        _write_crd(tmp_path / f"F1_{session}.CRD", [
            {"name": "BOST", "x": BOST_X, "y": BOST_Y, "z": BOST_Z},
            {"name": "PBIS", "x": PBIS_X, "y": PBIS_Y, "z": PBIS_Z},
            {"name": "ALBU", "x": PBIS_X + 1000, "y": PBIS_Y, "z": PBIS_Z},
        ])
    results = crd_directory_to_enu(tmp_path, reference_station="BOST")
    stations = [r.station for r in results]
    assert stations == sorted(stations)


def test_crd_directory_to_enu_raises_if_no_crd_files(tmp_path):
    (tmp_path / "README.txt").write_text("nothing here")
    with pytest.raises(ValueError, match="No usable"):
        crd_directory_to_enu(tmp_path, reference_station="BOST")


def test_crd_directory_to_enu_raises_if_reference_missing(tmp_path):
    _write_crd(tmp_path / "F1_23001.CRD", [
        {"name": "PBIS", "x": PBIS_X, "y": PBIS_Y, "z": PBIS_Z},
    ])
    with pytest.raises(ValueError, match="BOST"):
        crd_directory_to_enu(tmp_path, reference_station="BOST")


def test_crd_directory_to_enu_custom_session_extractor(tmp_path):
    # Campaign uses a non-standard 5-char session code embedded differently
    _write_crd(tmp_path / "PIVS_2023001.CRD", [
        {"name": "BOST", "x": BOST_X, "y": BOST_Y, "z": BOST_Z},
        {"name": "PBIS", "x": PBIS_X, "y": PBIS_Y, "z": PBIS_Z},
    ])

    def custom_extractor(filename: str) -> str | None:
        # Extract last 5 digits before extension
        import re
        m = re.search(r"(\d{5})", Path(filename).stem)
        return m.group(1) if m else None

    results = crd_directory_to_enu(
        tmp_path, reference_station="BOST",
        session_extractor=custom_extractor,
    )
    assert len(results) == 1
    assert results[0].station == "PBIS"


class TestFourDigitYearSessionCodes:
    """RNX2SNX writes FIN_YYYYDDDS -- seven digits, not five.

    Taking "the last five digits" of FIN_20250010 yields "50010", which parses
    as year 2050 DOY 010. Every epoch was silently misdated by 25 years, and
    any file whose 5-digit tail exceeded DOY 366 was rejected outright: a real
    360-file PHREF year produced 144 usable epochs, all dated 2050.

    Found 2026-09-01 while building the production time-series comparison.
    """

    def test_four_digit_year_form_is_read_as_the_correct_year(self):
        assert _extract_session_from_filename("FIN_20250010.CRD") == "25001"
        assert session_to_decimal_year("25001") == pytest.approx(2025.0027, abs=1e-4)

    def test_high_doy_is_no_longer_rejected(self):
        # "53650" -> DOY 650, out of range -> the file was silently dropped.
        assert _extract_session_from_filename("FIN_20253650.CRD") == "25365"
        assert session_to_decimal_year("25365") == pytest.approx(2025.9993, abs=1e-4)

    def test_every_day_of_a_full_year_survives(self):
        codes = {
            _extract_session_from_filename(f"FIN_2025{d:03d}0.CRD")
            for d in range(1, 366)
        }
        assert len(codes) == 365
        assert all(session_to_decimal_year(c) // 1 == 2025 for c in codes)

    def test_two_digit_year_forms_still_work(self):
        for name in ("F1_23001.CRD", "FIN_23001.CRD", "AB23001.CRD"):
            assert _extract_session_from_filename(name) == "23001"


class TestAPrioriStationsAreNotObservations:
    """A Bernese CRD lists every a priori station, observed or not.

    Estimated stations carry trailing flag columns ("A   G"); a priori
    carry-through ends at the Z coordinate. Including the latter fabricates
    epochs: CLAV has 31 days of RINEX in 2025 but a CRD entry on all 360, so
    its plotted series was a flat a priori line with a 31-day step that looked
    exactly like a real displacement.

    Found 2026-09-01 while investigating that apparent displacement.
    """

    @staticmethod
    def _crd(tmp_path, body: str) -> Path:
        p = tmp_path / "T_25001.CRD"
        p.write_text(
            "TEST: coordinates\n"
            + "-" * 80 + "\n"
            "LOCAL GEODETIC DATUM: IGS20             EPOCH: 2025-01-01 12:00:00\n\n"
            "NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG\n\n"
            + body,
            encoding="ascii",
        )
        return p

    def test_unflagged_a_priori_rows_are_skipped(self, tmp_path):
        p = self._crd(
            tmp_path,
            "    1  EEEE EEEE        -3121950.75632  5178608.38503  2022180.48849    A      G\n"
            "    2  AAAA AAAA        -3186293.42891  5286624.50395  1601158.41680\n",
        )
        got = {r[0] for r in read_crd_file(p)}
        assert got == {"EEEE"}, "an unflagged a priori row was read as an observation"

    def test_estimated_only_false_returns_everything(self, tmp_path):
        p = self._crd(
            tmp_path,
            "    1  EEEE EEEE        -3121950.75632  5178608.38503  2022180.48849    A      G\n"
            "    2  AAAA AAAA        -3186293.42891  5286624.50395  1601158.41680\n",
        )
        assert len({r[0] for r in read_crd_file(p, estimated_only=False)}) == 2

    def test_domes_form_is_still_parsed(self, tmp_path):
        p = self._crd(
            tmp_path,
            "    1  PIMO 22003M001   -3186293.42891  5286624.50395  1601158.41680    A      G\n",
        )
        rows = read_crd_file(p)
        assert len(rows) == 1
        assert rows[0][0] == "PIMO"
        assert rows[0][1] == pytest.approx(-3186293.42891)
