"""
NMEA Parser for Leica VADASE LDM and LVM sentences
Implements full parsing with checksum validation
"""

from datetime import UTC, date, datetime
from typing import Any


class NMEAChecksumError(Exception):
    """Raised when NMEA checksum validation fails"""

    pass


def validate_nmea_checksum(sentence: str) -> bool:
    """
    Validate NMEA 0183 checksum

    Args:
        sentence: Complete NMEA sentence with checksum

    Returns:
        True if checksum is valid

    Example:
        >>> validate_nmea_checksum("$GNLVM,113805.50,030215,...*47")
        True
    """
    if "*" not in sentence:
        return False

    body, checksum_str = sentence.rsplit("*", 1)
    body = body.lstrip("$")

    # Calculate XOR checksum
    checksum = 0
    for char in body:
        checksum ^= ord(char)

    expected = int(checksum_str[:2], 16)
    return checksum == expected


def _parse_nmea_time(time_str: str) -> tuple[int, int, int, int]:
    """
    Parse NMEA time string (hhmmss.ss) into components.

    Args:
        time_str: Time in format 'hhmmss.ss'

    Returns:
        tuple: (hour, minute, second, microsecond)
    """
    hh = int(time_str[0:2])
    mm = int(time_str[2:4])
    ss = float(time_str[4:])
    microsecond = int(round((ss % 1) * 1_000_000))
    return hh, mm, int(ss), microsecond


def parse_time_date(time_str: str, date_str: str) -> datetime:
    """
    Parse NMEA time (hhmmss.ss) and date (mmddyy) into datetime object

    Args:
        time_str: Time in format 'hhmmss.ss'
        date_str: Date in format 'mmddyy'

    Returns:
        datetime object in UTC timezone

    Example:
        >>> parse_time_date('113805.50', '030215')
        datetime.datetime(2015, 2, 3, 11, 38, 5, 500000, tzinfo=timezone.utc)
    """
    hh, mm, ss, microsecond = _parse_nmea_time(time_str)

    # Date: mmddyy
    month = int(date_str[0:2])
    day = int(date_str[2:4])
    year = 2000 + int(date_str[4:6])  # Assumes 21st century

    return datetime(year, month, day, hh, mm, ss, microsecond, tzinfo=UTC)


def parse_lvm(sentence: str) -> dict[str, Any] | None:
    """
    Parse $GNLVM (Leica Velocity Measurement) sentence

    Args:
        sentence: Complete NMEA sentence with checksum

    Returns:
        Dict containing parsed fields or None if parsing fails

    Fields returned:
        - timestamp: datetime object (UTC)
        - vE, vN, vU: velocity components (m/s)
        - varE, varN, varU: velocity variances (m²/s²)
        - covEN, covEU, covUN: covariances (m²/s²)
        - cq: 3D component quality (m/s)
        - n_sats: number of satellites used

    Example:
        >>> parse_lvm("$GNLVM,113805.50,030215,0.0011,0.0021,0.0015,...*47")
        {'timestamp': datetime(...), 'vE': 0.0011, 'vN': 0.0021, ...}
    """
    # Validate checksum first
    if not validate_nmea_checksum(sentence):
        raise NMEAChecksumError(f"Invalid checksum: {sentence}")

    # Remove checksum for parsing
    sentence = sentence.split("*")[0]

    # Parse fields
    fields = sentence.split(",")

    if fields[0] not in ["$GNLVM", "$GPLVM"]:
        return None

    try:
        return {
            "timestamp": parse_time_date(fields[1], fields[2]),
            "vE": float(fields[3]),  # m/s (East)
            "vN": float(fields[4]),  # m/s (North)
            "vU": float(fields[5]),  # m/s (Up)
            "varE": float(fields[6]),  # m²/s²
            "varN": float(fields[7]),  # m²/s²
            "varU": float(fields[8]),  # m²/s²
            "covEN": float(fields[9]),  # m²/s²
            "covEU": float(fields[10]),  # m²/s²
            "covUN": float(fields[11]),  # m²/s²
            "cq": float(fields[12]),  # m/s (3D quality)
            "n_sats": int(fields[13]),
        }
    except (IndexError, ValueError) as e:
        print(f"Error parsing LVM sentence: {e}")
        return None


def parse_ldm(sentence: str) -> dict[str, Any] | None:
    """
    Parse $GNLDM (Leica Displacement Measurement) sentence

    Args:
        sentence: Complete NMEA sentence with checksum

    Returns:
        Dict containing parsed fields or None if parsing fails

    Fields returned:
        - timestamp: datetime object (UTC)
        - start_time: datetime when displacement computation started
        - dE, dN, dU: displacement components (m)
        - varE, varN, varU: displacement variances (m²)
        - covEN, covEU, covUN: covariances (m²)
        - cq: 3D component quality (m)
        - n_sats: number of satellites used
        - reset_indicator: 0 = stream enable, 1 = ref position change
        - epoch_completeness: 0-1 ratio for current epoch
        - overall_completeness: 0-1 ratio since start

    Example:
        >>> parse_ldm("$GNLDM,113805.50,030215,113805.50,030215,0.0101,...*47")
        {'timestamp': datetime(...), 'dE': 0.0101, ...}
    """
    if not validate_nmea_checksum(sentence):
        raise NMEAChecksumError(f"Invalid checksum: {sentence}")

    sentence = sentence.split("*")[0]
    fields = sentence.split(",")

    if fields[0] not in ["$GNLDM", "$GPLDM"]:
        return None

    try:
        return {
            "timestamp": parse_time_date(fields[1], fields[2]),
            "start_time": parse_time_date(fields[3], fields[4]),
            "dE": float(fields[5]),  # m (East)
            "dN": float(fields[6]),  # m (North)
            "dU": float(fields[7]),  # m (Up)
            "varE": float(fields[8]),  # m²
            "varN": float(fields[9]),  # m²
            "varU": float(fields[10]),  # m²
            "covEN": float(fields[11]),  # m²
            "covEU": float(fields[12]),  # m²
            "covUN": float(fields[13]),  # m²
            "cq": float(fields[14]),  # m (3D quality)
            "n_sats": int(fields[15]),
            "reset_indicator": int(fields[16]),
            "epoch_completeness": float(fields[17]),
            "overall_completeness": float(fields[18]),
        }
    except (IndexError, ValueError) as e:
        print(f"Error parsing LDM sentence: {e}")
        return None


