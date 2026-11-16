"""Tests for timeseries.status.field_status: every station's velocity in one pass.

Synthetic, like test_timeseries_status.py: known ENU models are written as
daily CRD files and read back through the real file path. The property that
matters most is that the field and the one-station view give the same numbers.
"""
from __future__ import annotations

import json

import numpy as np
import pymap3d
import pytest
from pogf_geodetic_suite.timeseries.status import (
    FIELD_SCHEMA,
    field_status,
    station_status,
)

REF = "REF0"
REF_GEO = (14.5, 121.0, 50.0)
T0 = 2020.0

# code: (ENU offset from REF in m, rate mm/yr E N U)
STATIONS = {
    "AAAA": (np.array([15000.0, 8000.0, 20.0]), np.array([30.0, -12.0, 2.0])),
    "BBBB": (np.array([-40000.0, 25000.0, -5.0]), np.array([-5.0, 18.0, -1.0])),
    "SHRT": (np.array([9000.0, -30000.0, 10.0]), np.array([10.0, 10.0, 0.0])),
    "FARR": (np.array([900000.0, 0.0, 0.0]), np.array([4.0, 4.0, 0.0])),  # ~8 degrees away
}
STEP_T = 2022 + 1 / 365.25  # BBBB's catalogued earthquake
STEP_MM = np.array([25.0, -10.0, -8.0])
NO_REF_DAY = (2021, 101)  # one day whose file lacks the reference


def _sessions() -> list[tuple[int, int]]:
    days = [(y, d) for y in range(2020, 2024) for d in range(1, 366, 5)]
    assert NO_REF_DAY in days
    return days


def _crd_line(i: int, name: str, xyz) -> str:
    x, y, z = xyz
    return f"  {i:3d}  {name} 00000S000  {x:>15.5f} {y:>15.5f}  {z:>15.5f}    A   G"


def _write_crd(path, rows: list[str], datum: str = "IGS20") -> None:
    header = (
        "SYNTHETIC TEST NETWORK                                          16-NOV-26 00:00\n"
        "--------------------------------------------------------------------------------\n"
        f"LOCAL GEODETIC DATUM: {datum}                 EPOCH: 2020-01-01 00:00:00\n"
        "\n"
        " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM\n"
        "\n"
    )
    path.write_text(header + "\n".join(rows) + "\n", encoding="ascii")


@pytest.fixture(scope="module")
def network(tmp_path_factory):
    """Daily CRD files for four stations and a catalog. Returns (crd_dir, catalog)."""
    root = tmp_path_factory.mktemp("field")
    crd_dir = root / "STA"
    crd_dir.mkdir()
    rng = np.random.default_rng(20261116)
    ref_xyz = pymap3d.geodetic2ecef(*REF_GEO)
    for y, d in _sessions():
        t = y + d / 365.25
        rows = [] if (y, d) == NO_REF_DAY else [_crd_line(1, REF, ref_xyz)]
        for i, (code, (offset, rate)) in enumerate(STATIONS.items(), start=2):
            if code == "SHRT" and y < 2023:
                continue  # under a year of data: 2023 only
            enu_mm = (t - T0) * rate + rng.normal(0.0, [1.5, 1.5, 4.0])
            if code == "BBBB" and t >= STEP_T:
                enu_mm = enu_mm + STEP_MM
            e, n, u = offset + enu_mm / 1000.0
            rows.append(_crd_line(i, code, pymap3d.enu2ecef(e, n, u, *REF_GEO)))
        _write_crd(crd_dir / f"F1_{y % 100:02d}{d:03d}.CRD", rows)
    catalog = root / "offsets"
    catalog.write_text(f"# synthetic\nBBBB  {STEP_T:.4f}  EQ\n", encoding="utf-8")
    return crd_dir, catalog


@pytest.fixture(scope="module")
def field(network):
    crd_dir, catalog = network
    return field_status(crd_dir, REF, offsets_catalog=catalog)


def _by_code(field):
    return {s["station"]: s for s in field["stations"]}


def test_every_station_but_the_reference_is_in_the_field(field):
    assert field["schema"] == FIELD_SCHEMA
    assert sorted(_by_code(field)) == sorted(STATIONS)
    assert field["reference"] == REF
    assert field["left_out"] == []


def test_field_velocity_equals_the_one_station_view(field, network):
    """The map and the plot must never disagree about a station."""
    crd_dir, catalog = network
    for code, entry in _by_code(field).items():
        one = station_status(crd_dir, code, REF, offsets_catalog=catalog)
        assert entry["velocity"] == one["velocity"], code
        assert entry["reference_distance_deg"] == one["reference_distance_deg"], code
        assert entry["n_epochs"] == len(one["series"]["t"]), code
        assert entry["n_segments"] == len(one["segments"]), code


def test_rates_are_recovered(field):
    for code in ("AAAA", "FARR"):
        v = _by_code(field)[code]["velocity"]["velocity_mm_yr"]
        got = np.array([v["e"], v["n"], v["u"]])
        # FARR's axes are the reference's, tilted ~8 degrees: only its size is comparable.
        if code == "AAAA":
            np.testing.assert_allclose(got, STATIONS[code][1], atol=0.5)


def test_offsets_come_from_the_catalog(field):
    by = _by_code(field)
    assert by["BBBB"]["n_offsets"] == 1 and by["BBBB"]["n_segments"] == 2
    assert by["AAAA"]["n_offsets"] == 0 and by["AAAA"]["n_segments"] == 1
    # BBBB's published rate is its final segment's: the step is not in it.
    v = by["BBBB"]["velocity"]["velocity_mm_yr"]
    np.testing.assert_allclose([v["e"], v["n"]], STATIONS["BBBB"][1][:2], atol=1.5)


def test_short_series_is_flagged_not_dropped(field):
    short = _by_code(field)["SHRT"]
    assert short["velocity"]["short_span"] is True
    assert _by_code(field)["AAAA"]["velocity"]["short_span"] is False


def test_far_station_is_flagged(field):
    by = _by_code(field)
    assert by["FARR"]["far_from_reference"] is True
    assert by["FARR"]["reference_distance_deg"] > 5
    assert by["AAAA"]["far_from_reference"] is False


def test_positions_are_geodetic(field):
    a = _by_code(field)["AAAA"]
    lat, lon, _ = pymap3d.enu2geodetic(*STATIONS["AAAA"][0], *REF_GEO)
    assert a["lat"] == pytest.approx(lat, abs=1e-4)
    assert a["lon"] == pytest.approx(lon, abs=1e-4)
    assert field["reference_position"]["lat"] == pytest.approx(REF_GEO[0], abs=1e-6)


def test_network_warnings_are_given_once(field):
    gaps = [w for w in field["warnings"] if "missing from 1 of" in w]
    assert len(gaps) == 1
    for entry in field["stations"]:
        assert not any("missing from" in w for w in entry["warnings"])


def test_span_and_provenance(field, network):
    _, catalog = network
    assert field["t_first"] == pytest.approx(2020 + 1 / 365.25)
    assert field["t_last"] == pytest.approx(2023 + 361 / 365.25)
    assert field["offsets_catalog"]["path"] == str(catalog)
    assert len(field["offsets_catalog"]["sha256"]) == 64
    assert field["outlier_rule"]["mode"] == "record"
    assert "white noise" in field["sigma"]


def test_result_is_strict_json(field):
    assert json.loads(json.dumps(field, allow_nan=False)) == field


def test_without_a_catalog_it_says_so(network):
    crd_dir, _ = network
    f = field_status(crd_dir, REF)
    assert f["offsets_catalog"] is None
    assert any("no offsets catalog" in w for w in f["warnings"])
    assert _by_code(f)["BBBB"]["n_segments"] == 1


def test_exclude_mode_matches_the_one_station_view(network):
    crd_dir, catalog = network
    f = field_status(crd_dir, REF, offsets_catalog=catalog, outlier_mode="exclude")
    one = station_status(crd_dir, "AAAA", REF, offsets_catalog=catalog, outlier_mode="exclude")
    assert f["outlier_rule"]["mode"] == "exclude"
    assert _by_code(f)["AAAA"]["velocity"] == one["velocity"]


def test_unknown_reference_is_refused(network):
    crd_dir, catalog = network
    with pytest.raises(ValueError, match="ZZZZ"):
        field_status(crd_dir, "ZZZZ", offsets_catalog=catalog)


def test_mixed_datums_are_warned_once(tmp_path):
    crd_dir = tmp_path / "STA"
    crd_dir.mkdir()
    ref_xyz = pymap3d.geodetic2ecef(*REF_GEO)
    for k, (y, d) in enumerate([(2020, 10), (2020, 200), (2021, 10), (2021, 200)]):
        sta = pymap3d.enu2ecef(1000.0 + k * 0.01, 2000.0, 0.0, *REF_GEO)
        _write_crd(
            crd_dir / f"F1_{y % 100:02d}{d:03d}.CRD",
            [_crd_line(1, REF, ref_xyz), _crd_line(2, "AAAA", sta)],
            datum="IGS14" if y == 2020 else "IGS20",
        )
    f = field_status(crd_dir, REF)
    assert sum("more than one geodetic datum" in w for w in f["warnings"]) == 1
