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

import logging
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

    @property
    def ok(self) -> bool:
        """True only if there are no errors that would cause RXOBV3 to silently drop stations."""
        return not self.mismatches and not self.missing_from_sta and not self.atx_missing


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
        super().__init__("\n".join(lines))


# ---------------------------------------------------------------------------
# RINEX observation file parser
# ---------------------------------------------------------------------------


def _is_rinex_obs(path: Path) -> bool:
    """Return True for RINEX 2 (.YYo) and RINEX 3 (.rnx / .obs) obs files."""
    s = path.suffix.lower()
    if s in (".rnx", ".obs"):
        return True
    # RINEX 2: extension is .<2-digit-year>o, e.g. .23o
    return len(s) == 4 and s[1:3].isdigit() and s[3] == "o"


def _parse_rinex_headers(raw_dir: Path) -> dict[str, dict[str, str]]:
    """Scan RAW/ recursively for RINEX observation files; extract REC/ANT types.

    Returns a dict keyed by 4-char station code:
        {"receiver": "<type>", "antenna": "<type>"}

    Station code comes from the MARKER NAME header if present, else the
    first 4 chars of the filename (upper-cased).
    """
    result: dict[str, dict[str, str]] = {}

    for p in raw_dir.rglob("*"):
        if not p.is_file() or not _is_rinex_obs(p):
            continue

        station_code = p.name[:4].upper()
        rec_type = ""
        ant_type = ""
        marker_name = ""

        try:
            with p.open(encoding="ascii", errors="replace") as fh:
                for raw_line in fh:
                    line = raw_line.rstrip("\n")
                    if len(line) < 60:
                        if "END OF HEADER" in line:
                            break
                        continue
                    label = line[60:].strip()
                    if label == "MARKER NAME":
                        marker_name = line[:60].strip()
                    elif label == "REC # / TYPE / VERS":
                        rec_type = line[_RNX_TYPE_SLICE].strip()
                    elif label == "ANT # / TYPE":
                        ant_type = line[_RNX_TYPE_SLICE].strip()
                    elif label == "END OF HEADER":
                        break
        except OSError as exc:
            logger.warning("Cannot read %s: %s", p, exc)
            continue

        if marker_name and len(marker_name) >= 4:
            station_code = marker_name[:4].upper()

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
) -> ValidationReport:
    """Cross-check RINEX OBS headers in raw_dir against the campaign STA file.

    Args:
        raw_dir:   Campaign RAW/ directory containing RINEX observation files.
        sta_path:  Campaign .STA file (must exist).
        atx_path:  Staged ATX antenna calibration file (optional; ATX check
                   is skipped when None or when the file does not exist).

    Returns:
        ValidationReport.  Call .ok to see if validation passed.
        Callers wishing to abort on failure should raise ValidationError(report).
    """
    report = ValidationReport()

    rinex_headers = _parse_rinex_headers(raw_dir)
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

        # ATX coverage: check that the antenna type appears in the calibration file
        if atx_types is not None and hdr_ant:
            hdr_ant_base = hdr_ant.split()[0]
            if not any(hdr_ant_base in atx_entry for atx_entry in atx_types):
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
