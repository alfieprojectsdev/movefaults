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

import logging
import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from functools import lru_cache
from itertools import islice
from pathlib import Path

import pymap3d

logger = logging.getLogger(__name__)


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


# Estimated stations carry at least one trailing flag token after Z -- BSW 5.4
# writes two ("A   G", "W   G"), older files and some panels write one
# ("IGS14"). A priori carry-through ends at the Z coordinate with nothing
# after it, which is the only case this needs to exclude. Anchoring on
# "something non-numeric follows Z" is therefore both sufficient and tolerant
# of the flag vocabulary, which is not fixed across versions.
_FLAGGED = re.compile(r"[-+]?\d+\.\d+\s+(?![-+]?\d)\S+")

_DATUM = re.compile(r"LOCAL GEODETIC DATUM:\s*(\S+)")

# A directory of CRD files, or several read as one series.
CrdDirs = str | Path | Sequence[str | Path]


def read_crd_file(
    path: Path, *, estimated_only: bool = True
) -> list[tuple[str, float, float, float]]:
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

    ``estimated_only`` (default True) keeps ONLY stations the solution actually
    estimated, identified by the trailing flag columns (e.g. ``A   G``). A
    Bernese CRD also lists every station in the a priori file, unchanged and
    unflagged, whether or not it was observed that day.

    Including those is not a cosmetic problem. CLAV has 31 days of RINEX in
    2025; its CRD entry appears on all 360, carrying the a priori coordinate
    verbatim on the other 329. Plotted, that is a flat line with a 31-day step
    in it -- indistinguishable from a real 31-day displacement, and its
    suspiciously perfect 1.6 mm scatter is the signature of a number that was
    never measured. Across a 38-station comparison, 2136 of 13680 epochs
    (15.6%) were a priori carry-through presented as observations.

    Pass ``estimated_only=False`` only to read an a priori file deliberately.
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
            if estimated_only and not _FLAGGED.search(line):
                continue   # a priori carry-through, not an estimate
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

    Two-digit year rule: YY <= 80 -> 2000 + YY, YY > 80 -> 1900 + YY.

    **Convention: ``year + DOY/365.25``, matching ``RUNX_v2.py``.**
    DOY 1 maps to ``year + 0.0027``, not to ``year.0000``.

    This is deliberate and must not be "corrected". An earlier version used
    ``(DOY - 1)/365.25``, which is arguably the better definition in isolation
    -- it puts DOY 1 at the start of the year -- but it disagrees with the
    legacy pipeline by exactly one day (0.002738 yr) at every epoch.

    Why the legacy convention wins:

    * The hand-maintained ``offsets`` catalog is written in it. Inverting real
      entries confirms it: ``ALBU 2025.7474`` -> DOY 272.99 and
      ``AROY 2023.1314`` -> DOY 47.99, whole days under this rule and
      fractional under the other.
    * ``parse_offsets_file`` reads those decimal years verbatim and
      ``estimate_velocity`` splits segments on them, so a series built on the
      other convention places every offset one day early relative to its own
      epochs.
    * Every published PLOT file and velocity came from ``RUNX_v2.py``.
    * PHIVOLCS staff compute catalog entries by hand using this rule.

    The absolute epoch carries no scientific meaning here; agreement between
    the series and the catalog does. A pipeline that is "more correct" in
    isolation while disagreeing with its own offset catalog is strictly worse.

    Examples:
        "23001"  ->  2023 + 1/365.25    ~  2023.0027
        "23365"  ->  2023 + 365/365.25  ~  2023.9993
        "99365"  ->  1999 + 365/365.25  ~  1999.9993
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
    # DOY, not DOY-1 -- see the docstring. Changing this silently shifts
    # every epoch one day relative to the offsets catalog.
    return year + doy / 365.25


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

    # 4-digit-year form FIRST: RNX2SNX writes FIN_YYYYDDDS (7 digits, S =
    # sub-session). Taking "the last five digits" of FIN_20250010 yields
    # "50010", which parses as year 2050 DOY 010 -- every epoch silently
    # misdated by 25 years, and any day whose tail exceeds 366 (DOY >= 100 with
    # certain sub-sessions) REJECTED outright. That is how 360 daily CRD files
    # became 144 usable epochs, all in 2050.
    m = re.search(r"(?<!\d)(\d{4})(\d{3})(\d)$", stem)
    if m:
        return m.group(1)[2:] + m.group(2)

    # 2-digit-year form: F1_23001, FIN_23001, AB23001
    m = re.search(r"(?<!\d)(\d{5})$", stem)
    if m:
        return m.group(1)

    # Fall back to any 5-digit run
    m = re.search(r"(\d{5})", stem)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------


def _crd_dirs(crd_dir: CrdDirs) -> list[Path]:
    """One directory, or several in the order given (oldest first, for a series
    spanning years)."""
    if isinstance(crd_dir, (str, Path)):
        return [Path(crd_dir)]
    return [Path(d) for d in crd_dir]


def _dated_crd_files(
    crd_dir: CrdDirs, session_extractor: Callable[[str], str | None]
) -> Iterator[tuple[float, Path]]:
    """Each *.CRD whose name carries a valid session date, with that date.

    The one file filter: a CRD with no YYDDD in its name, or an invalid date,
    is not an epoch (an a priori or combined CRD in the same directory), so
    nothing built on these epochs sees it.
    """
    for directory in _crd_dirs(crd_dir):
        for crd_path in sorted(directory.glob("*.CRD")):
            session = session_extractor(crd_path.name)
            if session is None:
                continue
            try:
                yield session_to_decimal_year(session), crd_path
            except ValueError:
                continue


@lru_cache(maxsize=20000)
def _read_unchanged(
    path: Path, _mtime_ns: int, _size: int
) -> list[tuple[str, float, float, float]]:
    return read_crd_file(path)


def _read_crd_cached(path: Path) -> list[tuple[str, float, float, float]]:
    """read_crd_file, parsing a file again only when it has changed. A long-lived
    reader such as the console would otherwise reparse a campaign's whole history
    on every request, and parsing is nearly all of the time a request takes.
    Callers must not modify the list."""
    st = path.stat()
    return _read_unchanged(path, st.st_mtime_ns, st.st_size)


def _dated_crd_epochs(
    crd_dir: CrdDirs, session_extractor: Callable[[str], str | None]
) -> list[tuple[float, list[tuple[str, float, float, float]]]]:
    """Every dated *.CRD (see `_dated_crd_files`) that holds a station, read once."""
    epochs: list[tuple[float, list[tuple[str, float, float, float]]]] = []
    for decimal_year, crd_path in _dated_crd_files(crd_dir, session_extractor):
        stations = _read_crd_cached(crd_path)
        if stations:
            epochs.append((decimal_year, stations))
    if not epochs:
        raise ValueError(f"No usable *.CRD files found in {crd_dir}")
    return epochs


def crd_datums(
    crd_dir: CrdDirs,
    *,
    session_extractor: Callable[[str], str | None] | None = None,
) -> dict[str, tuple[float, float]]:
    """Each geodetic datum the dated CRD files name, with the first and last
    decimal year that uses it.

    Coordinates in two datums are not one series: where they meet, the frame
    steps and the station has not moved. A file whose header names no datum is
    left out, since nothing can be said about it.
    """
    out: dict[str, tuple[float, float]] = {}
    extractor = session_extractor or _extract_session_from_filename
    for decimal_year, crd_path in _dated_crd_files(crd_dir, extractor):
        with open(crd_path, encoding="ascii", errors="replace") as fh:
            head = "".join(islice(fh, 6))
        m = _DATUM.search(head)
        if m:
            first, last = out.get(m[1], (decimal_year, decimal_year))
            out[m[1]] = (min(first, decimal_year), max(last, decimal_year))
    return out


def crd_station_codes(
    crd_dir: CrdDirs,
    *,
    session_extractor: Callable[[str], str | None] | None = None,
) -> list[str]:
    """The estimated stations in the files crd_directory_to_enu would read.

    Exactly the stations it would accept as a reference: same file filter,
    same parser. Raises ValueError if no usable CRD file is found.
    """
    epochs = _dated_crd_epochs(crd_dir, session_extractor or _extract_session_from_filename)
    return sorted({code for _, stations in epochs for code, *_ in stations})


def crd_directory_to_enu(
    crd_dir: CrdDirs,
    reference_station: str,
    *,
    session_extractor: Callable[[str], str | None] | None = None,
) -> list[StationEpoch]:
    """
    Read all *.CRD files in crd_dir; return ENU time series for all stations.

    Python port of the RUNX_v2.py core pipeline:
    1. Parse ECEF coordinates from each CRD file.
    2. Extract the session date from the filename (YYDDD → decimal year).
    3. Look up the reference station's geodetic coordinates in that same file.
    4. Transform that file's other stations to local ENU at that position, so the
       reference's own motion is subtracted day by day. The E, N and U axes are the
       reference's, so a far-away reference tilts them relative to the station's.

    A day whose file does not hold the reference gives no epochs for any station,
    as in RUNX_v2.py, so a reference with gaps shortens every series. The number
    of days lost is logged as a warning; it is not in the return value.

    Args:
        crd_dir:            Directory containing Bernese *.CRD files, or several
                            directories oldest first (a campaign's yearly folders),
                            read as one series.
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
    epochs = _dated_crd_epochs(crd_dir, session_extractor)

    # Pass 2: each day's stations relative to the reference's position THAT DAY.
    # This is what subtracts the reference's motion, as RUNX_v2.py does: it reads
    # the reference from each file and transforms only that file's stations. An
    # origin fixed once would leave every station's motion in the series, plate
    # motion included. A day whose file has no reference gives no epochs.
    results: list[StationEpoch] = []
    skipped = 0
    for decimal_year, stations in epochs:
        origin = next(((x, y, z) for code, x, y, z in stations if code == ref), None)
        if origin is None:
            skipped += 1
            continue
        ref_lat, ref_lon, ref_alt = pymap3d.ecef2geodetic(*origin, deg=True)
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

    if skipped == len(epochs):
        raise ValueError(
            f"Reference station {ref!r} not found in any CRD file in {crd_dir}"
        )
    if skipped:
        logger.warning(
            "%s: reference %s is missing from %d of %d daily CRD files; those days give no epochs",
            crd_dir, ref, skipped, len(epochs),
        )

    results.sort(key=lambda ep: (ep.station, ep.decimal_year))
    return results
