import pytest
from datetime import datetime, timezone
from unittest.mock import patch
from src.parsers.nmea_parser import parse_vadase_velocity, NMEAChecksumError

def calculate_checksum(sentence_body):
    checksum = 0
    for char in sentence_body:
        checksum ^= ord(char)
    return f"{checksum:02X}"

def create_nmea(body):
    cksum = calculate_checksum(body)
    return f"${body}*{cksum}"

@pytest.fixture
def mock_datetime():
    with patch('src.parsers.nmea_parser.datetime') as mock_dt:
        # Setup a fixed time for 'now'
        fixed_now = datetime(2023, 10, 27, 0, 0, 0, tzinfo=timezone.utc)
        mock_dt.now.return_value = fixed_now

        # We also need to ensure side_effect allows creation of datetime objects
        # because parse_vadase_velocity calls datetime.now().replace(...)
        # The result of .replace() is a new datetime object.
        # Since mock_dt.now() returns a real datetime object (fixed_now),
        # .replace() will work and return a real datetime object.

        yield mock_dt

def test_parse_vadase_velocity_valid(mock_datetime):
    # Body: PTNL,VEL,123045.50,2.34,-1.56,0.12,1
    body = "PTNL,VEL,123045.50,2.34,-1.56,0.12,1"
    sentence = create_nmea(body)

    result = parse_vadase_velocity(sentence)

    expected_ts = datetime(2023, 10, 27, 12, 30, 45, 500000, tzinfo=timezone.utc)

    assert result is not None
    assert result['timestamp'] == expected_ts
    assert result['vN'] == pytest.approx(2.34)
    assert result['vE'] == pytest.approx(-1.56)
    assert result['vU'] == pytest.approx(0.12)
    assert result['quality'] == 1

def test_parse_vadase_velocity_checksum_error():
    # Valid body but wrong checksum
    body = "PTNL,VEL,123045.50,2.34,-1.56,0.12,1"
    # Correct checksum is calculated by create_nmea, so let's manually break it
    sentence = f"${body}*00" # 00 is likely wrong

    with pytest.raises(NMEAChecksumError):
        parse_vadase_velocity(sentence)

def test_parse_vadase_velocity_invalid_format(mock_datetime):
    # Correct checksum but invalid format (e.g. non-numeric velocity)
    body = "PTNL,VEL,123045.50,two,-1.56,0.12,1"
    sentence = create_nmea(body)

    result = parse_vadase_velocity(sentence)
    assert result is None

def test_parse_vadase_velocity_incomplete(mock_datetime):
    # Missing fields
    body = "PTNL,VEL,123045.50,2.34"
    sentence = create_nmea(body)

    result = parse_vadase_velocity(sentence)
    assert result is None
