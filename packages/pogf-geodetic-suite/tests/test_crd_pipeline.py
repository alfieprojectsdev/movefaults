"""Tests for timeseries.crd_pipeline — RUNX_v2 Python port."""
from __future__ import annotations

from pathlib import Path

import pytest
from pogf_geodetic_suite.timeseries.crd_pipeline import (
    StationEpoch,
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
    # DOY 1 of 2023 = 2023.0000...
    year = session_to_decimal_year("23001")
    assert year == pytest.approx(2023.0, abs=0.01)


def test_session_to_decimal_year_doy_365():
    # DOY 365 = last day of most years
    year = session_to_decimal_year("23365")
    assert year == pytest.approx(2023.997, abs=0.001)


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
