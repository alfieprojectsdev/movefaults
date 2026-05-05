"""
CRD-to-ENU pipeline — Python port of RUNX_v2.py.

Reads Bernese 5.4 CRD files from a campaign directory, extracts ECEF
coordinates per station per session, and transforms to local ENU coordinates
relative to a chosen reference station.

File naming convention assumed: the 5-char YYDDD session code appears at
the end of the filename stem, e.g. ``F1_23001.CRD`` → session ``23001``.
A custom extractor can be supplied if the campaign uses a different scheme.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pymap3d


@dataclass(frozen=True)
class StationEpoch:
    """ENU displacement for one station at one epoch."""
    station: str
    decimal_year: float
    east_m: float
    north_m: float
    up_m: float


# ---------------------------------------------------------------------------
# CRD file parser
# ---------------------------------------------------------------------------


def read_crd_file(path: Path) -> list[tuple[str, float, float, float]]:
    """
    Parse a Bernese 5.4 CRD file; return ECEF coordinates per station.

    Returns:
        List of (station_code: str, X: float, Y: float, Z: float).
        Header lines are skipped by checking that the first field is an integer
        (the sequence number that precedes every data row).

    CRD data lines have two layouts depending on whether a dome number is
    present after the station code:
        WITH dome:    NUM  NAME  DOME  X  Y  Z  FLAG
        WITHOUT dome: NUM  NAME  X  Y  Z  FLAG

    Both are handled by trying to parse the third field as a float.
    """
    results: list[tuple[str, float, float, float]] = []
    with path.open(encoding="ascii", errors="replace") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) < 5:
                continue
            try:
                int(parts[0])   # sequence number filters header/blank lines
            except ValueError:
                continue
            station = parts[1][:4].upper()
            # Detect whether dome is present: if parts[2] is not a float, it is.
            try:
                x = float(parts[2])
                y, z = float(parts[3]), float(parts[4])
            except ValueError:
                # parts[2] is the dome number (e.g. "00000S000")
                try:
                    x, y, z = float(parts[3]), float(parts[4]), float(parts[5])
                except (ValueError, IndexError):
                    continue
            results.append((station, x, y, z))
    return results


# ---------------------------------------------------------------------------
# Session-to-decimal-year conversion
# ---------------------------------------------------------------------------


def session_to_decimal_year(session: str) -> float:
    """
    Convert a 5-char Bernese YYDDD session code to a decimal year.

    Two-digit year rule: YY ≤ 80 → 2000 + YY, YY > 80 → 1900 + YY.

    Examples:
        "23001"  →  2023 + 0/365.25  ≈  2023.0000
        "23365"  →  2023 + 364/365.25  ≈  2023.9973
        "99365"  →  1999 + 364/365.25  ≈  1999.9973
    """
    if len(session) < 5:
        raise ValueError(f"Session code must be at least 5 characters, got: {session!r}")
    try:
        yy = int(session[:2])
        doy = int(session[2:5])
    except ValueError as exc:
        raise ValueError(f"Cannot parse session code {session!r}: {exc}") from exc

    if not 1 <= doy <= 366:
        raise ValueError(f"Day-of-year {doy} out of range in session {session!r}")

    year = 2000 + yy if yy <= 80 else 1900 + yy
    return year + (doy - 1) / 365.25


def _extract_session_from_filename(filename: str) -> str | None:
    """
    Extract the trailing 5-digit YYDDD session code from a CRD filename.

    Matches the last run of exactly 5 digits in the filename stem.
    Examples:
        "F1_23001.CRD"   →  "23001"
        "AB23001.CRD"    →  "23001"
        "FIN_23001.CRD"  →  "23001"
        "PIVSMIND.CRD"   →  None   (no numeric session)
    """
    stem = Path(filename).stem
    # Prefer 5-digit run at the end of the stem
    m = re.search(r"(\d{5})$", stem)
    if m:
        return m.group(1)
    # Fall back to any 5-digit run
    m = re.search(r"(\d{5})", stem)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------


def crd_directory_to_enu(
    crd_dir: Path,
    reference_station: str,
    *,
    session_extractor: Callable[[str], str | None] | None = None,
) -> list[StationEpoch]:
    """
    Read all *.CRD files in crd_dir; return ENU time series for all stations.

    Python port of the RUNX_v2.py core pipeline:
    1. Parse ECEF coordinates from each CRD file.
    2. Extract the session date from the filename (YYDDD → decimal year).
    3. Look up the reference station's geodetic coordinates.
    4. Transform all other stations to local ENU relative to the reference.

    Args:
        crd_dir:            Directory containing Bernese *.CRD files.
        reference_station:  4-char station code used as the ENU origin.
        session_extractor:  Optional callable mapping filename → YYDDD session
                            string.  Defaults to the built-in pattern matcher.

    Returns:
        List of StationEpoch, sorted by (station, decimal_year).

    Raises:
        ValueError: if no usable CRD files are found, or if the reference
                    station does not appear in any CRD file.
    """
    if session_extractor is None:
        session_extractor = _extract_session_from_filename

    ref = reference_station.upper()[:4]

    # Pass 1: collect all epochs
    epochs: list[tuple[float, list[tuple[str, float, float, float]]]] = []
    for crd_path in sorted(crd_dir.glob("*.CRD")):
        session = session_extractor(crd_path.name)
        if session is None:
            continue
        try:
            decimal_year = session_to_decimal_year(session)
        except ValueError:
            continue
        stations = read_crd_file(crd_path)
        if stations:
            epochs.append((decimal_year, stations))

    if not epochs:
        raise ValueError(f"No usable *.CRD files found in {crd_dir}")

    # Pass 2: locate reference station geodetic coordinates
    ref_lat = ref_lon = ref_alt = None
    for _, stations in epochs:
        for code, x, y, z in stations:
            if code == ref:
                ref_lat, ref_lon, ref_alt = pymap3d.ecef2geodetic(x, y, z, deg=True)
                break
        if ref_lat is not None:
            break

    if ref_lat is None:
        raise ValueError(
            f"Reference station {ref!r} not found in any CRD file in {crd_dir}"
        )

    # Pass 3: transform all non-reference stations to ENU
    results: list[StationEpoch] = []
    for decimal_year, stations in epochs:
        for code, x, y, z in stations:
            if code == ref:
                continue
            east, north, up = pymap3d.ecef2enu(
                x, y, z, ref_lat, ref_lon, ref_alt, deg=True
            )
            results.append(
                StationEpoch(
                    station=code,
                    decimal_year=decimal_year,
                    east_m=float(east),
                    north_m=float(north),
                    up_m=float(up),
                )
            )

    results.sort(key=lambda ep: (ep.station, ep.decimal_year))
    return results
