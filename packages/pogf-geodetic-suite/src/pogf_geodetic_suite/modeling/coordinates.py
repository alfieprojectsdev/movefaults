import pymap3d
from typing import Tuple

def geodetic_to_enu(lat: float, lon: float, alt: float, 
                    lat0: float, lon0: float, alt0: float) -> Tuple[float, float, float]:
    """
    Converts geodetic coordinates (lat, lon, alt) to local ENU (East, North, Up).
    
    Args:
        lat, lon: Latitude and Longitude of the target point (decimal degrees).
        alt: Ellipsoidal height of the target point (meters).
        lat0, lon0: Latitude and Longitude of the reference point (decimal degrees).
        alt0: Ellipsoidal height of the reference point (meters).
        
    Returns:
        (east, north, up) in meters.
    """
    return pymap3d.geodetic2enu(lat, lon, alt, lat0, lon0, alt0, deg=True)

def ecef_to_geodetic(x: float, y: float, z: float) -> Tuple[float, float, float]:
    """Converts ECEF coordinates (x, y, z) to geodetic (lat, lon, alt)."""
    return pymap3d.ecef2geodetic(x, y, z, deg=True)
