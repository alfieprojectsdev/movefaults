from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from src.parsers.nmea_parser import (
    NMEAChecksumError,
    parse_ldm,
    parse_lvm,
    parse_vadase_displacement,
    parse_vadase_velocity,
    validate_nmea_checksum,
)


def _calculate_checksum(sentence: str) -> str:
    """Helper to calculate NMEA checksum"""
    body = sentence.lstrip("$").split("*")[0]
    checksum = 0
    for char in body:
        checksum ^= ord(char)
    return f"{checksum:02X}"

def _create_sentence(body: str) -> str:
    """Helper to create a full NMEA sentence with valid checksum"""
    checksum = _calculate_checksum(body)
    return f"${body}*{checksum}"


def test_validate_nmea_checksum():
    # Test with valid checksum (using LVM example from spec)
    # Payload: GNLVM,113805.50,030215,0.0011,0.0021,0.0015,0.0023,0.0040,0.0092, 0.00012,0.00015,0.00035,0.043561,19
    # Checksum calculation:
    # XOR of characters between $ and *
    # Let's rely on the provided example having a valid checksum of 47 for now.

    # Simple known valid case
    # $GPZDA,201530.00,04,07,2002,00,00*60
    assert validate_nmea_checksum("$GPZDA,201530.00,04,07,2002,00,00*60") is True

    # Invalid case
    assert validate_nmea_checksum("$GPZDA,201530.00,04,07,2002,00,00*99") is False


def test_parse_ldm_spec_example():
    """
    Test LDM parsing using the example from docs/NMEA.md
    """
    # Note: checksum *47 in spec example is incorrect, calculated is *4C
    sentence = "$GNLDM,113805.50,030215,113805.50,030215,0.0101,0.0204,0.0459,0.0021,0.0020,0.0041,0.00021,0.00023,0.00041,0.05,19,0,1,1*4C"

    result = parse_ldm(sentence)

    assert result is not None
    assert result["dE"] == 0.0101
    assert result["dN"] == 0.0204
    assert result["dU"] == 0.0459
    assert result["cq"] == 0.05
    assert result["n_sats"] == 19
    assert result["reset_indicator"] == 0
    assert result["epoch_completeness"] == 1.0
    assert result["overall_completeness"] == 1.0

    # Date/Time Verification: 030215 -> March 2nd, 2015 (mmddyy)
    expected_ts = datetime(2015, 3, 2, 11, 38, 5, 500000, tzinfo=UTC)
    assert result["timestamp"] == expected_ts


def test_parse_vadase_velocity():
    """Test $PTNL,VEL sentence parsing"""
    sentence = "$PTNL,VEL,123045.50,2.34,-1.56,0.12,1*75"
    fixed_now = datetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)

    with patch("src.parsers.nmea_parser.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        # We also need to mock datetime.now(timezone.utc) if that's how it's called
        # Wait, the code calls datetime.now(timezone.utc)

        result = parse_vadase_velocity(sentence)

    assert result is not None
    # 123045.50 -> 12:30:45.500000
    expected_ts = datetime(2023, 10, 27, 12, 30, 45, 500000, tzinfo=UTC)
    assert result["timestamp"] == expected_ts
    assert result["vN"] == 2.34
    assert result["vE"] == -1.56
    assert result["vU"] == 0.12
    assert result["quality"] == 1


def test_parse_vadase_displacement():
    """Test $PTNL,POS sentence parsing"""
    sentence = "$PTNL,POS,123045.50,0.12,-0.08,0.01,1*68"
    fixed_now = datetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)

    with patch("src.parsers.nmea_parser.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now

        result = parse_vadase_displacement(sentence)

    assert result is not None
    expected_ts = datetime(2023, 10, 27, 12, 30, 45, 500000, tzinfo=UTC)
    assert result["timestamp"] == expected_ts
    assert result["dN"] == 0.12
    assert result["dE"] == -0.08
    assert result["dU"] == 0.01
    assert result["quality"] == 1


def test_parse_lvm_spec_example():
    """
    Test LVM parsing using the example from docs/NMEA.md
    """
    # Note: The spec example had a space " 0.00012" and ended with "*47."
    # We will replicate strict string from spec but trim the trailing dot if it expects pure NMEA
    sentence = "$GNLVM,113805.50,030215,0.0011,0.0021,0.0015,0.0023,0.0040,0.0092, 0.00012,0.00015,0.00035,0.043561,19*47"

    result = parse_lvm(sentence)

    assert result is not None
    assert result["vE"] == 0.0011
    assert result["vN"] == 0.0021
    assert result["vU"] == 0.0015
    assert result["covEN"] == 0.00012
    assert result["cq"] == 0.043561
    assert result["n_sats"] == 19

    expected_ts = datetime(2015, 3, 2, 11, 38, 5, 500000, tzinfo=UTC)
    assert result["timestamp"] == expected_ts


@pytest.mark.parametrize("vn, ve, vu, qual", [
    ("2.34", "-1.56", "0.12", "1"),
    ("0.00", "0.00", "0.00", "2"),
    ("-10.5", "5.5", "1.1", "0"),
])
def test_parse_vadase_velocity_values(vn, ve, vu, qual):
    """Test parse_vadase_velocity with different valid values"""
    body = f"PTNL,VEL,123045.50,{vn},{ve},{vu},{qual}"
    sentence = _create_sentence(body)

    fixed_now = datetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)

    with patch("src.parsers.nmea_parser.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now
        result = parse_vadase_velocity(sentence)

    assert result is not None
    assert result["vN"] == float(vn)
    assert result["vE"] == float(ve)
    assert result["vU"] == float(vu)
    assert result["quality"] == int(qual)


def test_parse_vadase_velocity_invalid_checksum():
    """Test parse_vadase_velocity with invalid checksum"""
    # Valid checksum is 75 for this string, using 99 to force error
    sentence = "$PTNL,VEL,123045.50,2.34,-1.56,0.12,1*99"
    with pytest.raises(NMEAChecksumError):
        parse_vadase_velocity(sentence)


def test_parse_vadase_velocity_malformed():
    """Test parse_vadase_velocity with malformed sentences"""
    # Missing field
    sentence = _create_sentence("PTNL,VEL,123045.50,2.34,-1.56,0.12")
    assert parse_vadase_velocity(sentence) is None

    # Wrong prefix
    sentence = _create_sentence("OTHER,VEL,123045.50,2.34,-1.56,0.12,1")
    assert parse_vadase_velocity(sentence) is None


def test_parse_vadase_velocity_invalid_float():
    r"""
    Test parse_vadase_velocity with values that pass regex but fail float conversion.
    The regex `[-\d.]+` allows strings like `.` or `-.` which are not valid floats.
    """
    # "." matches `[-\d.]+` but float('.') raises ValueError
    body = "PTNL,VEL,123045.50,.,-1.56,0.12,1"
    sentence = _create_sentence(body)

    fixed_now = datetime(2023, 10, 27, 10, 0, 0, tzinfo=UTC)

    with patch("src.parsers.nmea_parser.datetime") as mock_datetime:
        mock_datetime.now.return_value = fixed_now

        # Currently the code raises ValueError, but good practice is to return None or specific error.
        # We'll assert that it raises ValueError for now, or change the code to handle it.
        # Given the task is "Testing Improvement", we should document current behavior or improve it.
        # We'll assume we want to fix this fragility, so we expect None (handled gracefully).
        # This test will likely fail initially if we don't fix the code.
        result = parse_vadase_velocity(sentence)
        assert result is None
