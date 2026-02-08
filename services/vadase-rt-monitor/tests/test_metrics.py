import pytest
import math
from src.utils.metrics import (
    compute_horizontal_magnitude,
    convert_m_to_mm,
    convert_mm_to_m,
    compute_3d_magnitude
)

def test_compute_horizontal_magnitude():
    # Test case from docstring: 3-4-5 triangle
    assert compute_horizontal_magnitude(3.0, 4.0) == 5.0

    # Test with zero values
    assert compute_horizontal_magnitude(0.0, 0.0) == 0.0

    # Test with negative values
    assert compute_horizontal_magnitude(-3.0, 4.0) == 5.0
    assert compute_horizontal_magnitude(3.0, -4.0) == 5.0
    assert compute_horizontal_magnitude(-3.0, -4.0) == 5.0

    # Test with only one component
    assert compute_horizontal_magnitude(10.0, 0.0) == 10.0
    assert compute_horizontal_magnitude(0.0, 10.0) == 10.0

    # Test with floats
    assert math.isclose(compute_horizontal_magnitude(1.0, 1.0), math.sqrt(2.0))

def test_convert_m_to_mm():
    assert convert_m_to_mm(1.0) == 1000.0
    assert convert_m_to_mm(0.0) == 0.0
    assert convert_m_to_mm(0.001) == 1.0
    assert convert_m_to_mm(-1.0) == -1000.0

def test_convert_mm_to_m():
    assert convert_mm_to_m(1000.0) == 1.0
    assert convert_mm_to_m(0.0) == 0.0
    assert convert_mm_to_m(1.0) == 0.001
    assert convert_mm_to_m(-1000.0) == -1.0

def test_compute_3d_magnitude():
    # Test 1-1-1
    assert math.isclose(compute_3d_magnitude(1.0, 1.0, 1.0), math.sqrt(3.0))

    # Test 3-4-12 (should be 13)
    # sqrt(3^2 + 4^2 + 12^2) = sqrt(9 + 16 + 144) = sqrt(169) = 13
    assert compute_3d_magnitude(3.0, 4.0, 12.0) == 13.0

    # Test zeros
    assert compute_3d_magnitude(0.0, 0.0, 0.0) == 0.0
