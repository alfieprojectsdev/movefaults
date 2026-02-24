import pytest
import math
from src.utils.metrics import compute_horizontal_magnitude

def test_compute_horizontal_magnitude_basic():
    """Test with standard positive values (3-4-5 triangle)"""
    assert compute_horizontal_magnitude(3.0, 4.0) == pytest.approx(5.0)

def test_compute_horizontal_magnitude_negative():
    """Test with negative values"""
    assert compute_horizontal_magnitude(-3.0, 4.0) == pytest.approx(5.0)
    assert compute_horizontal_magnitude(3.0, -4.0) == pytest.approx(5.0)
    assert compute_horizontal_magnitude(-3.0, -4.0) == pytest.approx(5.0)

def test_compute_horizontal_magnitude_zero():
    """Test with zero values"""
    assert compute_horizontal_magnitude(0.0, 0.0) == pytest.approx(0.0)
    assert compute_horizontal_magnitude(0.0, 5.0) == pytest.approx(5.0)
    assert compute_horizontal_magnitude(5.0, 0.0) == pytest.approx(5.0)

def test_compute_horizontal_magnitude_precision():
    """Test with floating point precision"""
    # 1.0^2 + 1.0^2 = 2.0, sqrt(2.0) approx 1.41421356
    assert compute_horizontal_magnitude(1.0, 1.0) == pytest.approx(math.sqrt(2.0))

def test_compute_horizontal_magnitude_large_values():
    """Test with large values to check for overflow (though math.hypot handles it better)"""
    # This might fail with current implementation if values are TOO large,
    # but 1e100 should be fine for float64 squared.
    # 1e154 is around where it would overflow if squared: (1e154)^2 = 1e308 (near max float)
    val = 1e100
    expected = math.sqrt(2) * val
    assert compute_horizontal_magnitude(val, val) == pytest.approx(expected)
