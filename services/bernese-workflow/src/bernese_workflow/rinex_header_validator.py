"""
Pre-BPE RINEX header validator.

Reads RINEX OBS headers from the campaign RAW/ directory, extracts
REC TYPE and ANT TYPE per station, then cross-checks against:
  1. The campaign .STA file TYPE 002 entries (required)
  2. The staged ATX antenna calibration file (optional)

Raises ValidationError — never silently passes — if any station would be
dropped by RXOBV3 (PID 221/222) due to header/STA discrepancies.
"""
from __future__ import annotations

import gzip
import logging
import subprocess
import zlib
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Fixed-column slices in STA TYPE 002 data lines (0-indexed)
_STA_NAME_SLICE = slice(0, 4)
_STA_REC_SLICE = slice(69, 89)
_STA_ANT_SLICE = slice(121, 141)

# Fixed-column slices in RINEX OBS header records (0-indexed)
# Both REC # / TYPE / VERS and ANT # / TYPE put their type field in cols 20-39
_RNX_TYPE_SLICE = slice(20, 40)


# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Mismatch:
    station: str
    field: str          # "receiver" or "antenna"
    header_value: str   # what the RINEX file says
    sta_value: str      # what the .STA TYPE 002 says


@dataclass
class ValidationReport:
    mismatches: list[Mismatch] = field(default_factory=list)
    missing_from_sta: list[str] = field(default_factory=list)   # RINEX present, no STA entry
    missing_from_raw: list[str] = field(default_factory=list)   # in STA, no RINEX found (warning only)
    atx_missing: list[str] = field(default_factory=list)        # antenna type absent from ATX
    warnings: list[str] = field(default_factory=list)
    no_rinex_found: bool = False   # source dir yielded zero RINEX for the session (vacuous-pass guard)

    @property
    def ok(self) -> bool:
        """True only if there are no errors that would cause RXOBV3 to silently drop stations.

        ``no_rinex_found`` is a hard error when set: a validation that parsed zero
        RINEX files can never legitimately "pass" — that was the defeat behind the
        empty-``RAW/`` vacuous pass (the validator ran before RNX_COP staged any data).
        """
        return (
            not self.mismatches
            and not self.missing_from_sta
            and not self.atx_missing
            and not self.no_rinex_found
        )


class ValidationError(Exception):
    def __init__(self, report: ValidationReport) -> None:
        self.report = report
        lines = [f"Pre-BPE RINEX header validation failed ({len(report.mismatches)} mismatch(es)):"]
        for m in report.mismatches:
            lines.append(
                f"  {m.station} [{m.field}]: RINEX={m.header_value!r}  STA={m.sta_value!r}"
            )
        if report.missing_from_sta:
            lines.append(
                f"  Stations present in RAW/ but absent from STA TYPE 002: "
                f"{report.missing_from_sta}"
            )
        if report.atx_missing:
            lines.append(f"  Antenna types absent from ATX: {report.atx_missing}")
        if report.no_rinex_found:
            lines.append(
                "  No RINEX observation files found for the session in the source directory "
                "— validation cannot run (empty/wrong source, or data not yet staged)."
            )
        super().__init__("\n".join(lines))


# ---------------------------------------------------------------------------
# RINEX observation file parser
# ---------------------------------------------------------------------------


# Compression suffixes we can transparently read. Stripped right-to-left, and
# repeatedly: real DATAPOOL names carry two extensions (``.crx.gz``, ``.24d.Z``).
#
#   .gz  RFC 1952 gzip         -> Python's gzip module
#   .z   UNIX compress (LZW)   -> GNU gzip subprocess; see _open_rinex_text
_COMPRESSION_SUFFIXES = frozenset({".gz", ".z"})

# Observation-data extensions, AFTER compression suffixes are stripped.
#   .rnx  RINEX 3 long name, uncompressed
#   .obs  RINEX observation, generic
#   .rxo  Bernese RINEX Observation copy, found in campaign RAW/
#   .crx  RINEX 3 long name, Hatanaka-compacted (CRINEX)
_RINEX_OBS_SUFFIXES = frozenset({".rnx", ".obs", ".rxo", ".crx"})

# RINEX 2 short-name final character: 'o' plain observation, 'd' Hatanaka
# (CRINEX) observation. Deliberately EXCLUDES 'n'/'g'/'l' (navigation) and
# 'm' (meteorological) — feeding those to the header parser yields no
# REC/ANT records and would pollute the station set.
_RINEX2_OBS_CHARS = frozenset({"o", "d"})


def _strip_compression_suffixes(name: str) -> str:
    """Remove trailing compression suffixes, right to left, repeatedly.

    A single strip is not enough and a single regex is the wrong shape: real
    DATAPOOL names stack a data extension under a compression one, and both
    orders of two extensions occur —

        PZAM0860.26d.gz                              -> PZAM0860.26d
        GFCN0100.23D.Z                               -> GFCN0100.23D
        CUSV00THA_R_20260860000_01D_30S_MO.crx.gz    -> ...MO.crx
        CUSV00THA_R_20260860000_01D_30S_MO.rnx.gz    -> ...MO.rnx

    Looping also means a hypothetical double-compressed name degrades sensibly
    rather than being silently misclassified.
    """
    stem = name
    while True:
        dot = stem.rfind(".")
        if dot < 0 or stem[dot:].lower() not in _COMPRESSION_SUFFIXES:
            return stem
        stem = stem[:dot]


def _is_rinex_obs(path: Path) -> bool:
    """True for a RINEX observation file, compressed or not.

    Recognises RINEX 2 short names (``.<yy>o`` plain, ``.<yy>d`` Hatanaka),
    RINEX 3 long names (``.rnx`` plain, ``.crx`` Hatanaka), ``.obs``, and the
    Bernese ``.RXO`` copy — each optionally carrying a ``.gz`` or ``.Z``.

    WHY COMPRESSION IS HANDLED HERE (measured on gps3, 2026-08-03). This
    function previously tested ``path.suffix`` directly, which made it blind to
    every file in a real DATAPOOL: all 3,010 archive files there are ``.gz`` and
    20 are ``.Z``, so ``suffix`` was the *compression* extension and never
    matched. Hatanaka was a second, independent miss — ``.26d``/``.crx`` were
    absent from the accepted set, so even decompressed the majority of PAGENET
    files would still have been skipped.

    The consequence was worse than a skipped file. ``validate_rinex_headers``
    only surfaces an empty scan as an error when called with
    ``require_stations=True``; under the default it returns a **passing** report
    having examined nothing — approving every session while inspecting none of
    it, with the first symptom appearing much later as an RXOBV3 hard abort
    mid-BPE. The unit suite could not see any of this, because its fixtures use
    uncompressed ``.YYo``/``.rnx`` names that do not occur in the data.
    """
    stem = _strip_compression_suffixes(path.name)
    dot = stem.rfind(".")
    if dot < 0:
        return False
    s = stem[dot:].lower()
    if s in _RINEX_OBS_SUFFIXES:
        return True
    # RINEX 2 short name: .<2-digit-year><type-char>, e.g. .26o, .26d
    return len(s) == 4 and s[1:3].isdigit() and s[3] in _RINEX2_OBS_CHARS


def _file_matches_session(path: Path, year: int, session: str) -> bool:
    """True if ``path`` belongs to the given Bernese session.

    Needed because a DATAPOOL source directory (e.g. ``$D/PGN``) holds RINEX for
    *all* days; an intermittent station (present only on some DOYs) must be
    validated against the single session actually being processed — otherwise a
    station missing from one day's data is masked by its presence on another.

    Matches the naming schemes seen in a live PAGENET campaign:
      * RINEX 2 short name  ``pzam0870.26o`` -> chars [4:7] == DOY ("087")
                            (station(4) + DOY(3) + session/hour char)
      * RINEX 3 long name   ``CUSV..._20260870000_...`` -> contains "2026087" (year+DOY)
      * Bernese .RXO copy   ``PLG2..._20260870.RXO``    -> contains "20260870" (year+session)
    """
    name = path.name
    doy = session[:3]  # Bernese daily session ssss = DOY(3) + session-index(1)
    # RINEX 2 short name: 4-char station + 3-digit DOY + 1 session/hour char
    if len(name) >= 7 and name[4:7] == doy:
        return True
    # RINEX 3 long name (year+DOY) or Bernese .RXO copy (year+session)
    if f"{year}{doy}" in name or f"{year}{session}" in name:
        return True
    return False


@contextmanager
def _open_rinex_text(path: Path) -> Iterator[Iterable[str]]:
    """Yield decompressed text lines for a RINEX file, plain or compressed.

    Handles three cases:

    * **plain** — opened directly.
    * **.gz** — Python's ``gzip`` module. This is the overwhelmingly common case
      (3,010 of 3,030 compressed files in the gps3 DATAPOOL), so it is kept
      subprocess-free.
    * **.Z** — UNIX ``compress``/LZW. Python has **no LZW decoder**: ``gzip.open``
      on one of these raises ``BadGzipFile: Not a gzipped file (b'\\x1f\\x9d')``
      (``1f 9d`` being the LZW magic, against gzip's ``1f 8b``). GNU ``gzip -dc``
      reads both formats, so we shell out rather than take a third-party
      dependency for 20 files.

    NO HATANAKA DECOMPRESSION IS NEEDED, which is the reason this stayed small.
    A CRINEX file stores the original RINEX header **verbatim** after two
    ``CRINEX VERS``/``CRINEX PROG`` lines; only the observation records below
    ``END OF HEADER`` are compacted. Since this validator reads nothing past the
    header, ``crx2rnx`` never has to run — no RNXCMP build, no ``hatanaka``
    package.
    """
    suffix = path.suffix.lower()

    if suffix == ".gz":
        with gzip.open(path, "rt", encoding="ascii", errors="replace") as fh:
            yield fh
        return

    if suffix == ".z":
        proc = subprocess.Popen(
            ["gzip", "-dc", str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="ascii",
            errors="replace",
        )
        assert proc.stdout is not None
        try:
            yield proc.stdout
        finally:
            # The caller stops at END OF HEADER, typically a few hundred bytes
            # into a multi-megabyte file. Closing the pipe makes gzip's next
            # write fault with SIGPIPE, so it exits 141.
            #
            # THAT IS EXPECTED, NOT A FAILURE, and the exit status is
            # deliberately discarded. This project has been bitten four times by
            # the inverse mistake — treating a swallowed or signal-derived
            # status as meaningful (the smartd SIGPIPE bug, `lsof +D` exiting 1
            # on success, a trailing `[ cond ] && echo` becoming a script's
            # verdict). Here the reverse discipline applies: a non-zero status
            # from a process we deliberately cut off carries no information, and
            # checking it would turn every successful early exit into an error.
            proc.stdout.close()
            proc.terminate()
            proc.wait()
        return

    with path.open(encoding="ascii", errors="replace") as fh:
        yield fh


def _is_station_code(token: str) -> bool:
    """True for a bare 4-character alphanumeric Bernese station code."""
    return len(token) == 4 and token.isalnum()


def _resolve_station_code(
    *,
    filename_code: str,
    marker_name: str,
    marker_number: str,
    source: str,
) -> str:
    """Pick the 4-char station code, given RINEX headers that disagree.

    A PAGENET campaign mixes two naming conventions, and taking MARKER NAME as
    authoritative silently mis-identifies one of them. Measured on gps3 DOY 086:

        PAGENET CORS         IGS fiducial
        ------------------   ------------------
        MARKER NAME   BOGO CITY            CUSV
        MARKER NUMBER PBOG                 21904S001   (DOMES)
        filename      PBOG0860.26d.gz      CUSV00THA_R_...
        PGN.STA key   PBOG                 CUSV

    Preferring MARKER NAME yields "BOGO" for the first — absent from PGN.STA —
    so 9 of 72 stations were reported missing on data that processes correctly.
    A validator that fails on good data gets switched off, which costs more than
    the check was ever worth.

    Order of preference, most to least specific:
      1. MARKER NUMBER when it is a bare 4-char code (PAGENET convention).
         Skipped for IGS, where it holds a 9-char DOMES number.
      2. MARKER NAME when it is a single bare 4-char token (IGS convention).
         Rejected for "BOGO CITY" — a descriptive name, not a code.
      3. The filename's leading 4 characters, which is what the campaign and
         DATAPOOL are keyed on and the reliable fallback.

    Disagreement between the chosen code and the filename is logged: it is
    usually a misnamed file, which is worth knowing before RXOBV3 finds it.
    """
    chosen = filename_code
    if _is_station_code(marker_number):
        chosen = marker_number.upper()
    elif _is_station_code(marker_name):
        chosen = marker_name.upper()

    if chosen != filename_code:
        logger.info(
            "Station code %s from headers differs from filename code %s (%s)",
            chosen, filename_code, source,
        )
    return chosen


def _parse_rinex_headers(
    raw_dir: Path,
    *,
    year: int | None = None,
    session: str | None = None,
) -> dict[str, dict[str, str]]:
    """Scan RAW/ recursively for RINEX observation files; extract REC/ANT types.

    Returns a dict keyed by 4-char station code:
        {"receiver": "<type>", "antenna": "<type>"}

    Station code comes from the MARKER NAME header if present, else the
    first 4 chars of the filename (upper-cased).

    When both ``year`` and ``session`` are given, only files belonging to that
    session are parsed (per-session validation against a multi-day source dir).
    """
    result: dict[str, dict[str, str]] = {}
    filter_session = year is not None and session is not None

    for p in raw_dir.rglob("*"):
        if not p.is_file() or not _is_rinex_obs(p):
            continue
        # Skip dot-directories. Two independent reasons, the second decisive:
        #
        #   1. A leading dot is the conventional "not part of this dataset"
        #      marker. On gps3 the DATAPOOL holds `.excluded_plg2/`, where the
        #      two intermittent PLG2 files were hand-quarantined during the
        #      training week to get past the RXOBV3 abort. Recursing resurrects
        #      exactly the data someone deliberately set aside.
        #
        #   2. The validator must model what RNX_COP will actually stage, and
        #      RNX_COP globs the source directory without recursing. Validating
        #      files that will never be copied into the campaign produces
        #      failures that cannot occur in the run — the mirror image of the
        #      vacuous pass, and just as effective at getting the check ignored.
        #
        # NOTE this does NOT make the underlying problem go away: PLG2 is still
        # absent from PGN.STA, and the quarantine is a manual workaround that
        # task A is meant to replace with per-session detection and quarantine.
        if any(part.startswith(".") for part in p.relative_to(raw_dir).parts[:-1]):
            logger.debug("Skipping %s — inside a dot-directory", p)
            continue
        if filter_session and not _file_matches_session(p, year, session):  # type: ignore[arg-type]
            continue

        station_code = p.name[:4].upper()
        rec_type = ""
        ant_type = ""
        marker_name = ""
        marker_number = ""

        try:
            with _open_rinex_text(p) as fh:
                for raw_line in fh:
                    line = raw_line.rstrip("\n")
                    if len(line) < 60:
                        if "END OF HEADER" in line:
                            break
                        continue
                    label = line[60:].strip()
                    if label == "MARKER NAME":
                        marker_name = line[:60].strip()
                    elif label == "MARKER NUMBER":
                        marker_number = line[:60].strip()
                    elif label == "REC # / TYPE / VERS":
                        rec_type = line[_RNX_TYPE_SLICE].strip()
                    elif label == "ANT # / TYPE":
                        ant_type = line[_RNX_TYPE_SLICE].strip()
                    elif label == "END OF HEADER":
                        break
        except (OSError, EOFError, zlib.error) as exc:
            # A truncated or corrupt archive member must not abort the whole
            # scan — one unreadable file in a 677-file DATAPOOL should be a
            # warning about that file, not a failure of the validation run.
            logger.warning("Cannot read %s: %s", p, exc)
            continue

        station_code = _resolve_station_code(
            filename_code=station_code,
            marker_name=marker_name,
            marker_number=marker_number,
            source=p.name,
        )

        if rec_type or ant_type:
            result[station_code] = {"receiver": rec_type, "antenna": ant_type}
        else:
            logger.warning("No REC/ANT headers found in %s — skipping", p.name)

    return result


# ---------------------------------------------------------------------------
# STA TYPE 002 parser
# ---------------------------------------------------------------------------


def _parse_sta_type002(sta_path: Path) -> dict[str, dict[str, str]]:
    """Parse a Bernese .STA file; return TYPE 002 receiver/antenna info.

    Returns dict keyed by 4-char station code.
    """
    try:
        content = sta_path.read_text(encoding="ascii", errors="replace")
    except OSError as exc:
        raise FileNotFoundError(f"STA file not found: {sta_path}") from exc

    result: dict[str, dict[str, str]] = {}
    in_type002 = False
    past_header = False

    for line in content.splitlines():
        if "TYPE 002: STATION INFORMATION" in line:
            in_type002 = True
            past_header = False
            continue
        if not in_type002:
            continue
        # Skip header rows (dashes, column labels, asterisk templates, blanks)
        if line.startswith("---") or "STATION NAME" in line or line.strip().startswith("****"):
            past_header = True
            continue
        # New TYPE section ends this block
        if line.strip().startswith("TYPE ") and in_type002 and past_header:
            break
        if not past_header or not line.strip():
            continue
        if len(line) < 141:
            continue

        station_code = line[_STA_NAME_SLICE].strip()
        if not station_code:
            continue
        receiver = line[_STA_REC_SLICE].strip()
        antenna = line[_STA_ANT_SLICE].strip()
        result[station_code] = {"receiver": receiver, "antenna": antenna}

    return result


# ---------------------------------------------------------------------------
# ATX parser
# ---------------------------------------------------------------------------


def _parse_atx_antenna_types(atx_path: Path) -> frozenset[str]:
    """Extract all antenna type codes from an IGS ATX file.

    Returns a frozenset of type strings as they appear in the file
    (e.g. "LEIAR20      NONE", "TRM57971.00  NONE").
    """
    types: set[str] = set()
    try:
        with atx_path.open(encoding="ascii", errors="replace") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if len(line) < 60:
                    continue
                label = line[60:].strip()
                if label == "TYPE / SERIAL NO":
                    # Cols 0-19 hold the antenna type+radome code
                    ant_type = line[:20].strip()
                    if ant_type:
                        types.add(ant_type)
    except OSError as exc:
        logger.warning("Cannot read ATX file %s: %s", atx_path, exc)
    return frozenset(types)


# ---------------------------------------------------------------------------
# Antenna type comparison
# ---------------------------------------------------------------------------


def _ant_types_match(hdr_ant: str, sta_ant: str, atx_types: frozenset[str] | None = None) -> bool:
    """Compare antenna types allowing for radome suffix differences.

    RINEX headers include the radome: "LEIAR20      NONE"
    STA TYPE 002 may store just the model: "LEIAR20"
    Two types match if their first whitespace-delimited token is identical.
    """
    if hdr_ant == sta_ant:
        return True
    hdr_base = hdr_ant.split()[0] if hdr_ant else ""
    sta_base = sta_ant.split()[0] if sta_ant else ""
    return bool(hdr_base and hdr_base == sta_base)


# ---------------------------------------------------------------------------
# Main validation entry point
# ---------------------------------------------------------------------------


def validate_rinex_headers(
    raw_dir: Path,
    sta_path: Path,
    atx_path: Path | None = None,
    *,
    year: int | None = None,
    session: str | None = None,
    require_stations: bool = True,
) -> ValidationReport:
    """Cross-check RINEX OBS headers in raw_dir against the campaign STA file.

    Args:
        raw_dir:   Directory containing RINEX observation files. Point this at
                   the DATAPOOL source (``$D/$V_RNXDIR``) where RINEX lives
                   *before* the BPE runs — the campaign ``RAW/`` is empty until
                   RNX_COP copies data in, so validating it pre-BPE passes vacuously.
        sta_path:  Campaign .STA file (must exist).
        atx_path:  Staged ATX antenna calibration file (optional; ATX check
                   is skipped when None or when the file does not exist).
        year:      4-digit year. With ``session``, restricts validation to that
                   session's files (a multi-day source holds many DOYs).
        session:   4-char Bernese session (e.g. "0870"). See ``year``.
        require_stations: When True (the default), a source yielding zero RINEX
                   files is a hard error (``no_rinex_found``) rather than a
                   vacuous pass. Defaulted to False until 2026-08-04, which
                   meant the *safe* behaviour had to be opted into: any caller
                   using the defaults got a PASSING report from a scan that
                   read nothing. Fixing `_is_rinex_obs` removed that day's
                   instance; defaulting this to True removes the failure mode.
                   Pass False deliberately where an empty source is legitimate.

    Returns:
        ValidationReport.  Call .ok to see if validation passed.
        Callers wishing to abort on failure should raise ValidationError(report).
    """
    report = ValidationReport()

    rinex_headers = _parse_rinex_headers(raw_dir, year=year, session=session)
    if not rinex_headers and require_stations:
        report.no_rinex_found = True
        logger.error(
            "No RINEX observation files found in %s for session %s/%s — "
            "refusing to pass validation vacuously",
            raw_dir,
            year,
            session,
        )
        return report
    sta_info = _parse_sta_type002(sta_path)
    atx_types: frozenset[str] | None = None
    if atx_path is not None and atx_path.exists():
        atx_types = _parse_atx_antenna_types(atx_path)

    # Check each station found in RAW/
    for station, hdr in rinex_headers.items():
        if station not in sta_info:
            report.missing_from_sta.append(station)
            logger.warning(
                "Station %s has RINEX data in RAW/ but no STA TYPE 002 entry — "
                "RXOBV3 will drop it silently",
                station,
            )
            continue

        sta = sta_info[station]

        hdr_rec = hdr.get("receiver", "")
        sta_rec = sta.get("receiver", "")
        if hdr_rec != sta_rec:
            report.mismatches.append(
                Mismatch(station=station, field="receiver", header_value=hdr_rec, sta_value=sta_rec)
            )

        hdr_ant = hdr.get("antenna", "")
        sta_ant = sta.get("antenna", "")
        if not _ant_types_match(hdr_ant, sta_ant):
            report.mismatches.append(
                Mismatch(station=station, field="antenna", header_value=hdr_ant, sta_value=sta_ant)
            )

        # ATX coverage: check that the antenna type appears in the calibration file.
        # Compare on the model token (first whitespace-delimited field), matching
        # the semantics of _ant_types_match — a substring test would let
        # "LEIAR10" spuriously match an ATX entry "LEIAR10R   NONE".
        if atx_types is not None and hdr_ant:
            hdr_ant_base = hdr_ant.split()[0]
            atx_bases = {entry.split()[0] for entry in atx_types if entry.split()}
            if hdr_ant_base not in atx_bases:
                report.atx_missing.append(f"{station}: {hdr_ant!r}")
                logger.warning(
                    "Station %s antenna %r not found in ATX — Bernese will use generic model",
                    station,
                    hdr_ant,
                )

    # Warn about stations in STA with no RINEX data (expected, not an error)
    for station in sta_info:
        if station not in rinex_headers:
            report.missing_from_raw.append(station)
            logger.debug(
                "Station %s in STA file but no RINEX found in RAW/ (expected if data not yet staged)",
                station,
            )

    if report.mismatches:
        logger.error(
            "%d station(s) have header/STA mismatches and will be silently dropped by RXOBV3",
            len(report.mismatches),
        )

    return report
