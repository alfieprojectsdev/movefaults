import pytest
import math
from src.utils.metrics import (
    compute_horizontal_magnitude,
    convert_m_to_mm,
    convert_mm_to_m,
    compute_3d_magnitude,
)

def test_compute_horizontal_magnitude():
    """Test compute_horizontal_magnitude with various inputs."""
    # Pythogorean triplet 3, 4, 5
    assert compute_horizontal_magnitude(3.0, 4.0) == 5.0

    # Zero values
    assert compute_horizontal_magnitude(0.0, 0.0) == 0.0

    # Negative values (magnitude should be positive)
    assert compute_horizontal_magnitude(-3.0, -4.0) == 5.0
    assert compute_horizontal_magnitude(-3.0, 4.0) == 5.0

    # Floating point precision
    result = compute_horizontal_magnitude(1.0, 1.0)
    expected = math.sqrt(2)
    assert result == pytest.approx(expected)


def test_convert_m_to_mm():
    """Test convert_m_to_mm with various inputs."""
    # Standard positive value
    assert convert_m_to_mm(1.0) == 1000.0
    assert convert_m_to_mm(2.5) == 2500.0

    # Zero
    assert convert_m_to_mm(0.0) == 0.0

    # Negative value
    assert convert_m_to_mm(-1.0) == -1000.0

    # Floating point precision
    assert convert_m_to_mm(0.001) == pytest.approx(1.0)


def test_convert_mm_to_m():
    """Test convert_mm_to_m with various inputs."""
    # Standard positive value
    assert convert_mm_to_m(1000.0) == 1.0
    assert convert_mm_to_m(2500.0) == 2.5

    # Zero
    assert convert_mm_to_m(0.0) == 0.0

    # Negative value
    assert convert_mm_to_m(-1000.0) == -1.0

    # Floating point precision
    assert convert_mm_to_m(1.0) == pytest.approx(0.001)


def test_compute_3d_magnitude():
    """Test compute_3d_magnitude with various inputs."""
    # Standard values (3, 4, 12) -> 13
    assert compute_3d_magnitude(3.0, 4.0, 12.0) == 13.0

    # Zero values
    assert compute_3d_magnitude(0.0, 0.0, 0.0) == 0.0

    # Negative values
    assert compute_3d_magnitude(-3.0, 4.0, -12.0) == 13.0

    # Floating point precision
    result = compute_3d_magnitude(1.0, 1.0, 1.0)
    expected = math.sqrt(3)
    assert result == pytest.approx(expected)
