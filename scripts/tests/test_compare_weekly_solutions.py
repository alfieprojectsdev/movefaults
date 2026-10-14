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
