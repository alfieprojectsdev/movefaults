import pytest
from datetime import datetime, timezone
from src.parsers.nmea_parser import parse_ldm, parse_lvm, validate_nmea_checksum

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
    assert result['dE'] == 0.0101
    assert result['dN'] == 0.0204
    assert result['dU'] == 0.0459
    assert result['cq'] == 0.05
    assert result['n_sats'] == 19
    assert result['reset_indicator'] == 0
    assert result['epoch_completeness'] == 1.0
    assert result['overall_completeness'] == 1.0
    
    # Date/Time Verification: 030215 -> March 2nd, 2015 (mmddyy)
    expected_ts = datetime(2015, 3, 2, 11, 38, 5, 500000, tzinfo=timezone.utc)
    assert result['timestamp'] == expected_ts
    assert result['start_time'] == expected_ts

def test_parse_lvm_spec_example():
    """
    Test LVM parsing using the example from docs/NMEA.md
    """
    # Note: The spec example had a space " 0.00012" and ended with "*47."
    # We will replicate strict string from spec but trim the trailing dot if it expects pure NMEA
    sentence = "$GNLVM,113805.50,030215,0.0011,0.0021,0.0015,0.0023,0.0040,0.0092, 0.00012,0.00015,0.00035,0.043561,19*47"
    
    result = parse_lvm(sentence)
    
    assert result is not None
    assert result['vE'] == 0.0011
    assert result['vN'] == 0.0021
    assert result['vU'] == 0.0015
    assert result['covEN'] == 0.00012
    assert result['cq'] == 0.043561
    assert result['n_sats'] == 19
    
    expected_ts = datetime(2015, 3, 2, 11, 38, 5, 500000, tzinfo=timezone.utc)
    assert result['timestamp'] == expected_ts
