"""
Outlier rejection in scripts/compare_weekly_solutions.py, on synthetic
stations at Philippine latitudes where ECEF X/Y and local North/East differ most.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import numpy as np

_spec = importlib.util.spec_from_file_location(
    "compare_weekly_solutions",
    Path(__file__).resolve().parents[1] / "compare_weekly_solutions.py",
)
cws = importlib.util.module_from_spec(_spec)
sys.modules["compare_weekly_solutions"] = cws
_spec.loader.exec_module(cws)

A = cws.A_WGS84
E2 = 2 * cws.F_WGS84 - cws.F_WGS84**2


def _xyz(lat_deg: float, lon_deg: float, h: float = 50.0) -> np.ndarray:
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = A / math.sqrt(1 - E2 * math.sin(lat) ** 2)
    return np.array(
        [
            (n + h) * math.cos(lat) * math.cos(lon),
            (n + h) * math.cos(lat) * math.sin(lon),
            (n * (1 - E2) + h) * math.sin(lat),
        ]
    )


def _network(n: int = 30, seed: int = 1):
    rng = np.random.default_rng(seed)
    sites = [f"S{i:03d}" for i in range(n)]
    ours = np.array([_xyz(rng.uniform(6, 19), rng.uniform(119, 127)) for _ in sites])
    return sites, ours, rng


def _shift(xyz: np.ndarray, n_m: float, e_m: float, u_m: float) -> np.ndarray:
    return cws.xyz_to_neu_rotation(xyz).T @ np.array([n_m, e_m, u_m])


def _theirs(ours, rng, sigma_h_m: float, sigma_u_m: float) -> np.ndarray:
    return np.array(
        [x + _shift(x, *rng.normal(0, sigma_h_m, 2), rng.normal(0, sigma_u_m)) for x in ours]
    )


def test_a_30mm_east_outlier_is_rejected_even_when_the_vertical_is_noisy():
    # 2 mm horizontal, 12 mm vertical noise: the vertical used to inflate the
    # X/Y sigma enough that a 30 mm East outlier stayed under the threshold.
    sites, ours, rng = _network()
    theirs = _theirs(ours, rng, 0.002, 0.012)
    theirs[7] += _shift(ours[7], 0.0, 0.030, 0.0)
    _, _, keep, rejected = cws.helmert_robust(ours, theirs, sites)
    assert rejected == ["S007"]
    assert keep.sum() == len(sites) - 1


def test_a_vertical_only_outlier_is_not_rejected_by_a_horizontal_test():
    sites, ours, rng = _network(seed=2)
    theirs = _theirs(ours, rng, 0.002, 0.005)
    theirs[3] += _shift(ours[3], 0.0, 0.0, 0.060)
    _, _, _, rejected = cws.helmert_robust(ours, theirs, sites)
    assert "S003" not in rejected


def test_a_clean_network_rejects_nothing():
    sites, ours, rng = _network(seed=3)
    theirs = _theirs(ours, rng, 0.002, 0.007)
    _, _, keep, rejected = cws.helmert_robust(ours, theirs, sites)
    assert rejected == []
    assert keep.all()


def test_the_rotation_matches_the_geodetic_frame_it_was_built_from():
    # The tests above shift stations with `xyz_to_neu_rotation` itself, so a
    # wrong rotation (geocentric latitude, swapped rows, flipped sign) would
    # move the synthetic outlier and the detector together and still pass.
    # Check it against the geodetic latitude/longitude `_xyz` started from.
    for lat_deg, lon_deg, h in ((6.0, 119.0, 0.0), (12.3, 123.4, 500.0), (18.9, 126.9, 2400.0)):
        lat, lon = math.radians(lat_deg), math.radians(lon_deg)
        north = [-math.sin(lat) * math.cos(lon), -math.sin(lat) * math.sin(lon), math.cos(lat)]
        east = [-math.sin(lon), math.cos(lon), 0.0]
        up = [math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon), math.sin(lat)]
        rot = cws.xyz_to_neu_rotation(_xyz(lat_deg, lon_deg, h))
        np.testing.assert_allclose(rot, [north, east, up], atol=1e-12)


def test_a_station_with_two_solution_numbers_is_refused_not_overwritten(tmp_path):
    """A discontinuity (an earthquake offset, an antenna change) gives a station a
    second SOLN. Keyed on the site code alone, the second would silently replace the
    first for the whole week. No weekly file on gps3 has one yet (all 7,002 rows are
    SOLN 1, checked 2026-10-26), so refuse rather than guess which one is meant."""
    rows = []
    for k, (soln, x) in enumerate([("1", -3.0e6), ("2", -3.1e6)]):
        for j, (t, v) in enumerate([("STAX", x), ("STAY", 5.0e6), ("STAZ", 1.5e6)]):
            rows.append(
                f" {3 * k + j + 1:5d} {t}   LGYE  A {soln:>4} 25:001:43200 m    2 {v: .14E} 1.0E-03"
            )
    snx = tmp_path / "two_soln.snx"
    snx.write_text("%=SNX 2.02\n+SOLUTION/ESTIMATE\n" + "\n".join(rows) + "\n-SOLUTION/ESTIMATE\n")
    try:
        cws.read_sinex(snx)
    except ValueError as e:
        assert "LGYE" in str(e)
    else:
        raise AssertionError("a second SOLN for LGYE was accepted silently")
