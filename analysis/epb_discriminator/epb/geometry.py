"""Sky geometry: satellite directions, the design matrix and the weights.

Static over a scenario. Satellites move about 0.5 deg/min, so over a 20-minute
scenario the geometry changes a little; holding it fixed is a known
simplification, noted in NOTES.md.
"""

from __future__ import annotations

import numpy as np


def make_sky(n_sat: int, rng: np.random.Generator, el_mask_deg: float = 10.0):
    """Random azimuth and elevation (degrees) for n_sat satellites above the mask.

    sin(el) is drawn uniformly above the mask, which spreads satellites over the
    visible cap roughly the way a real constellation does at low latitude. Real
    geometry from broadcast ephemeris is a later option.
    """
    az = rng.uniform(0.0, 360.0, n_sat)
    s = rng.uniform(np.sin(np.radians(el_mask_deg)), 1.0, n_sat)
    el = np.degrees(np.arcsin(s))
    return az, el


def los_enu(az_deg, el_deg) -> np.ndarray:
    """Unit vectors receiver -> satellite in East, North, Up. Shape (N, 3)."""
    az, el = np.radians(az_deg), np.radians(el_deg)
    return np.column_stack([np.cos(el) * np.sin(az), np.cos(el) * np.cos(az), np.sin(el)])


def design_matrix(los: np.ndarray) -> np.ndarray:
    """Rows [-e, -n, -u, 1]: velocity toward a satellite shortens the range. (N, 4)."""
    return np.column_stack([-los, np.ones(len(los))])


def weights(el_deg, sigma0: float) -> np.ndarray:
    """w_i = 1 / sigma_i^2 with sigma_i = sigma0 / sin(el_i). (N,)."""
    sigma = sigma0 / np.sin(np.radians(el_deg))
    return 1.0 / sigma**2


def sky_distance_deg(az1, el1, az2, el2):
    """Great-circle angle between sky directions, degrees."""
    a1, e1, a2, e2 = map(np.radians, (az1, el1, az2, el2))
    c = np.sin(e1) * np.sin(e2) + np.cos(e1) * np.cos(e2) * np.cos(a1 - a2)
    return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))
