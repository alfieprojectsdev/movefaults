"""
Utility functions for computing derived metrics from VADASE data
"""

import math


def compute_horizontal_magnitude(east: float, north: float) -> float:
    """
    Compute horizontal magnitude from East and North components
    
    Args:
        east: East component (any unit)
        north: North component (same unit as east)
        
    Returns:
        Horizontal magnitude (same unit as inputs)
        
    Example:
        >>> compute_horizontal_magnitude(3.0, 4.0)
        5.0
    """
    return math.hypot(east, north)


def convert_m_to_mm(value_m: float) -> float:
    """
    Convert meters to millimeters
    
    Args:
        value_m: Value in meters
        
    Returns:
        Value in millimeters
    """
    return value_m * 1000.0


def convert_mm_to_m(value_mm: float) -> float:
    """
    Convert millimeters to meters
    
    Args:
        value_mm: Value in millimeters
        
    Returns:
        Value in meters
    """
    return value_mm / 1000.0


def compute_3d_magnitude(east: float, north: float, up: float) -> float:
    """
    Compute 3D magnitude from East, North, and Up components
    
    Args:
        east: East component (any unit)
        north: North component (same unit)
        up: Up component (same unit)
        
    Returns:
        3D magnitude (same unit as inputs)
    """
    return math.sqrt(east**2 + north**2 + up**2)