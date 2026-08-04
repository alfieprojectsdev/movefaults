"""Tests for the pre-BPE RINEX header validator (BRN-006)."""
from __future__ import annotations

import gzip as _gzip
import shutil
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bernese_workflow.rinex_header_validator import (
    Mismatch,
    ValidationError,
    ValidationReport,
    _ant_types_match,
    _is_rinex_obs,
    _open_rinex_text,
    _parse_atx_antenna_types,
    _parse_rinex_headers,
    _parse_sta_type002,
    _resolve_station_code,
    _strip_compression_suffixes,
    validate_rinex_headers,
)

# ---------------------------------------------------------------------------
# Minimal RINEX 2 observation header (80-col fixed width)
# ---------------------------------------------------------------------------

def _rinex2_obs(
    marker: str = "BOST",
    receiver: str = "LEICA GR50",
    antenna: str = "LEIAR20      NONE",
) -> str:
    """Return a minimal RINEX 2 OBS file with correct 80-column fixed-width headers.

    RINEX column layout (0-indexed):
      0-19:  serial number (blank)
      20-39: receiver/antenna type  ← what the validator reads
      40-59: firmware / empty
      60-79: record label
    """
    lines = [
        "     2.11           OBSERVATION DATA    G (GPS)             RINEX VERSION / TYPE",
        f"{marker:<60}MARKER NAME         ",
        f"{'':20}{receiver:<20}{'1.00/5.00':<20}REC # / TYPE / VERS ",
        f"{'':20}{antenna:<20}{'':20}ANT # / TYPE        ",
        f"{'':60}END OF HEADER       ",
    ]
    return "\n".join(lines) + "\n"


def _write_rinex(tmp_path: Path, filename: str, content: str) -> Path:
    p = tmp_path / filename
    p.write_text(content, encoding="ascii")
    return p


# ---------------------------------------------------------------------------
# Minimal Bernese STA TYPE 002 content
# ---------------------------------------------------------------------------

def _make_sta_content(stations: list[dict]) -> str:
    """Generate minimal STA file content for TYPE 002 only."""
    header = (
        "PHIVOLCS CORS NETWORK                                           01-JAN-26 00:00\n"
        "--------------------------------------------------------------------------------\n\n"
        "FORMAT VERSION: 1.03\n"
        "TECHNIQUE:      GNSS\n\n"
        "TYPE 002: STATION INFORMATION\n"
        "-----------------------------\n\n"
        "STATION NAME          FLG          FROM                   TO         "
        "RECEIVER TYPE         RECEIVER SERIAL NBR   REC #   "
        "ANTENNA TYPE          ANTENNA SERIAL NBR    ANT #    NORTH      EAST      UP     "
        "AZIMUTH  LONG NAME  DESCRIPTION             REMARK\n"
        "****************      ***  YYYY MM DD HH MM SS  YYYY MM DD HH MM SS  "
        "********************  ********************  ******  "
        "********************  ********************  ******  ***.****  ***.****  ***.****  "
        "******  *********  **********************  ************************\n"
    )
    rows = []
    for s in stations:
        name = s["name"]
        sname = f"{name} 00000S000"
        rec = f"{s.get('receiver', 'LEICA GR50'):<20}"
        ant = f"{s.get('antenna', 'LEIAR20'):<20}"
        # Build a line that puts receiver at [69:89] and antenna at [121:141]
        # sname (16) + 6sp + 001 + 2sp + from(19) + 2sp + to(19) + 2sp + receiver(20) + 2sp + serial(20) + 2sp + 999999 + 2sp + antenna(20)
        from_s = "1980  1  1  0  0  0"
        to_s = "2099 12 31  0  0  0"
        row = (
            f"{sname:<16}      001  {from_s}  {to_s}  "
            f"{rec}  {'':20}  999999  "
            f"{ant}  {'NONE':20}  999999    0.0000    0.0000    0.0000          "
            f"{name[:4]}00PHL  PHIVOLCS CORS              "
        )
        rows.append(row)
    return header + "\n".join(rows) + "\n"


# ---------------------------------------------------------------------------
# RINEX header parsing
# ---------------------------------------------------------------------------

def test_parse_rinex_headers_extracts_rec_and_ant(tmp_path):
    _write_rinex(tmp_path, "BOST001a.23o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR20      NONE"))
    result = _parse_rinex_headers(tmp_path)
    assert "BOST" in result
    assert result["BOST"]["receiver"] == "LEICA GR50"
    assert result["BOST"]["antenna"] == "LEIAR20      NONE"


def test_parse_rinex_headers_uses_marker_name(tmp_path):
    """MARKER NAME header takes precedence over filename for station code."""
    _write_rinex(tmp_path, "XXXX001a.23o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR20      NONE"))
    result = _parse_rinex_headers(tmp_path)
    # marker name "BOST" wins over filename prefix "XXXX"
    assert "BOST" in result
    assert "XXXX" not in result


def test_parse_rinex_headers_skips_non_rinex(tmp_path):
    (tmp_path / "readme.txt").write_text("not a RINEX file")
    (tmp_path / "data.T01").write_text("Trimble")
    result = _parse_rinex_headers(tmp_path)
    assert result == {}


def test_parse_rinex_headers_multiple_stations(tmp_path):
    _write_rinex(tmp_path, "BOST001a.23o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR20      NONE"))
    _write_rinex(tmp_path, "PBIS001a.23o", _rinex2_obs("PBIS", "TRIMBLE NETR9", "TRM57971.00  NONE"))
    result = _parse_rinex_headers(tmp_path)
    assert "BOST" in result
    assert "PBIS" in result
    assert result["PBIS"]["receiver"] == "TRIMBLE NETR9"


def test_parse_rinex_headers_detects_bernese_rxo(tmp_path):
    """Bernese campaign RAW/ holds .RXO RINEX Observation files — must be detected.

    Regression: .RXO was previously unrecognized, so a real campaign yielded an
    empty header set and the validator passed vacuously (defeating BRN-006).
    """
    _write_rinex(
        tmp_path,
        "BRST00FRA_20230100.RXO",
        _rinex2_obs("BRST", "SEPT POLARX5", "LEIAR25.R4   NONE"),
    )
    result = _parse_rinex_headers(tmp_path)
    assert "BRST" in result
    assert result["BRST"]["receiver"] == "SEPT POLARX5"


# ---------------------------------------------------------------------------
# STA TYPE 002 parsing
# ---------------------------------------------------------------------------

def test_parse_sta_type002_extracts_receiver_and_antenna(tmp_path):
    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([
            {"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"},
        ]),
        encoding="ascii",
    )
    result = _parse_sta_type002(sta)
    assert "BOST" in result
    assert result["BOST"]["receiver"] == "LEICA GR50"
    assert result["BOST"]["antenna"] == "LEIAR20"


def test_parse_sta_type002_multiple_stations(tmp_path):
    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([
            {"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"},
            {"name": "PBIS", "receiver": "LEICA GR50", "antenna": "LEIAR20"},
        ]),
        encoding="ascii",
    )
    result = _parse_sta_type002(sta)
    assert "BOST" in result and "PBIS" in result


def test_parse_sta_type002_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        _parse_sta_type002(tmp_path / "NONEXISTENT.STA")


# ---------------------------------------------------------------------------
# Antenna type comparison
# ---------------------------------------------------------------------------

def test_ant_types_match_exact():
    assert _ant_types_match("LEIAR20      NONE", "LEIAR20      NONE")


def test_ant_types_match_radome_tolerance():
    """RINEX includes radome; STA may store bare model name — still a match."""
    assert _ant_types_match("LEIAR20      NONE", "LEIAR20")


def test_ant_types_mismatch():
    assert not _ant_types_match("LEIAR20      NONE", "TRM57971.00  NONE")


def test_ant_types_match_both_empty():
    assert _ant_types_match("", "")


# ---------------------------------------------------------------------------
# ATX parsing
# ---------------------------------------------------------------------------

def test_parse_atx_antenna_types(tmp_path):
    atx = tmp_path / "igs14.atx"
    atx.write_text(
        "                                                            START OF ANTENNA    \n"
        "LEIAR20      NONE                        I14                TYPE / SERIAL NO    \n"
        "                                                            END OF ANTENNA      \n"
        "                                                            START OF ANTENNA    \n"
        "TRM57971.00  NONE                        I14                TYPE / SERIAL NO    \n"
        "                                                            END OF ANTENNA      \n",
        encoding="ascii",
    )
    types = _parse_atx_antenna_types(atx)
    assert "LEIAR20      NONE" in types
    assert "TRM57971.00  NONE" in types


# ---------------------------------------------------------------------------
# Full validation — matching case
# ---------------------------------------------------------------------------

def test_validate_matching_headers(tmp_path):
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()
    _write_rinex(raw_dir, "BOST001a.23o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR20      NONE"))

    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([{"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"}]),
        encoding="ascii",
    )

    report = validate_rinex_headers(raw_dir, sta)
    assert report.ok
    assert report.mismatches == []
    assert report.missing_from_sta == []


# ---------------------------------------------------------------------------
# Full validation — mismatch cases
# ---------------------------------------------------------------------------

def test_validate_receiver_mismatch(tmp_path):
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()
    _write_rinex(raw_dir, "BOST001a.23o", _rinex2_obs("BOST", "TRIMBLE NETR9", "LEIAR20      NONE"))

    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([{"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"}]),
        encoding="ascii",
    )

    report = validate_rinex_headers(raw_dir, sta)
    assert not report.ok
    assert len(report.mismatches) == 1
    m = report.mismatches[0]
    assert m.station == "BOST"
    assert m.field == "receiver"
    assert m.header_value == "TRIMBLE NETR9"
    assert m.sta_value == "LEICA GR50"


def test_validate_antenna_mismatch(tmp_path):
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()
    _write_rinex(raw_dir, "BOST001a.23o", _rinex2_obs("BOST", "LEICA GR50", "TRM57971.00  NONE"))

    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([{"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"}]),
        encoding="ascii",
    )

    report = validate_rinex_headers(raw_dir, sta)
    assert not report.ok
    assert any(m.field == "antenna" for m in report.mismatches)


def test_validate_missing_from_sta(tmp_path):
    """RINEX data present for a station that has no STA TYPE 002 entry."""
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()
    _write_rinex(raw_dir, "BOST001a.23o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR20      NONE"))

    sta = tmp_path / "EMPTY.STA"
    sta.write_text(
        _make_sta_content([]),  # no stations in STA
        encoding="ascii",
    )

    report = validate_rinex_headers(raw_dir, sta)
    assert not report.ok
    assert "BOST" in report.missing_from_sta


def test_validate_missing_from_raw_is_warning_not_error(tmp_path):
    """A station in STA with no data THIS session is a warning, not a failure.

    Deliberately staged with RINEX present for a DIFFERENT station. The earlier
    version used a completely empty RAW/, which conflated two distinct
    conditions — "this station has no data" (routine; stations drop in and out)
    and "there is no data at all" (a broken source path or session filter, and
    now a hard error). Proving the first with the second meant the test would
    have passed even if the scan were blind, which is precisely the defect this
    module was fixed for.
    """
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()
    # PGOO has data; BOST is in the STA but absent from this session.
    _write_rinex(raw_dir, "pgoo0010.24o",
                 _rinex2_obs("PGOO", "LEICA GR50", "LEIAR20      NONE"))

    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([
            {"name": "PGOO", "receiver": "LEICA GR50", "antenna": "LEIAR20"},
            {"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"},
        ]),
        encoding="ascii",
    )

    report = validate_rinex_headers(raw_dir, sta)
    assert report.ok  # not an error
    assert "BOST" in report.missing_from_raw
    assert not report.no_rinex_found


def test_validate_atx_missing(tmp_path):
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()
    _write_rinex(raw_dir, "BOST001a.23o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR20      NONE"))

    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([{"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"}]),
        encoding="ascii",
    )

    atx = tmp_path / "igs14.atx"
    atx.write_text(
        "                                                            START OF ANTENNA    \n"
        "TRM57971.00  NONE                        I14                TYPE / SERIAL NO    \n"
        "                                                            END OF ANTENNA      \n",
        encoding="ascii",
    )

    report = validate_rinex_headers(raw_dir, sta, atx_path=atx)
    assert not report.ok
    assert any("BOST" in entry for entry in report.atx_missing)


def test_validate_atx_no_substring_false_positive(tmp_path):
    """An ATX model that merely contains the header model as a substring is NOT a match.

    Regression: substring matching let header "LEIAR10" pass against an ATX that
    only had "LEIAR10R", masking a genuinely uncalibrated antenna.
    """
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()
    _write_rinex(raw_dir, "BOST001a.23o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR10      NONE"))

    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([{"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR10"}]),
        encoding="ascii",
    )

    atx = tmp_path / "igs20.atx"
    atx.write_text(
        "                                                            START OF ANTENNA    \n"
        "LEIAR10R     NONE                        I20                TYPE / SERIAL NO    \n"
        "                                                            END OF ANTENNA      \n",
        encoding="ascii",
    )

    report = validate_rinex_headers(raw_dir, sta, atx_path=atx)
    assert not report.ok
    assert any("BOST" in entry for entry in report.atx_missing)


# ---------------------------------------------------------------------------
# ValidationError formatting
# ---------------------------------------------------------------------------

def test_validation_error_message_contains_station_and_field():
    report = ValidationReport(
        mismatches=[Mismatch("BOST", "receiver", "TRIMBLE NETR9", "LEICA GR50")],
    )
    err = ValidationError(report)
    msg = str(err)
    assert "BOST" in msg
    assert "receiver" in msg
    assert "TRIMBLE NETR9" in msg
    assert "LEICA GR50" in msg


# ---------------------------------------------------------------------------
# LinuxBPEBackend.run() pre-flight integration
# ---------------------------------------------------------------------------

def test_linux_bpe_run_raises_validation_error_on_mismatch(tmp_path):
    from bernese_workflow.backends import LinuxBPEBackend

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )

    # Set up campaign with mismatched RINEX header
    campaign_path = tmp_path / "GPSDATA" / "TESTCAMP"
    raw_dir = campaign_path / "RAW"
    raw_dir.mkdir(parents=True)
    sta_dir = campaign_path / "STA"
    sta_dir.mkdir(parents=True)

    _write_rinex(raw_dir, "BOST001a.23o", _rinex2_obs("BOST", "TRIMBLE NETR9", "LEIAR20      NONE"))
    (sta_dir / "TESTCAMP.STA").write_text(
        _make_sta_content([{"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"}]),
        encoding="ascii",
    )

    with pytest.raises(ValidationError) as exc_info:
        backend.run("TESTCAMP", 2023, "0100")

    assert "BOST" in str(exc_info.value)
    assert exc_info.value.report.mismatches[0].field == "receiver"


def test_linux_bpe_run_skips_check_when_raw_missing(tmp_path):
    """If RAW/ doesn't exist, pre-flight check is skipped (warning logged)."""
    from bernese_workflow.backends import LinuxBPEBackend

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
    )

    # No RAW/ or STA set up — should not raise ValidationError
    # It will fail on the perl subprocess, so we mock that
    with patch("bernese_workflow.backends.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="BPE finished", stderr="", returncode=0)
        result = backend.run("NORAW", 2023, "0100")

    # Reached here without ValidationError → pre-flight was correctly skipped
    assert result is not None


# ---------------------------------------------------------------------------
# Per-session filtering + non-vacuous guard (gaps #1, #12)
# ---------------------------------------------------------------------------

def test_parse_rinex_headers_filters_by_session(tmp_path):
    """A multi-day source dir yields only the requested session's stations."""
    # PLG2 present only on DOY 086; BOST on 087 — RINEX2 short names (chars 4:8 = session)
    _write_rinex(tmp_path, "plg20860.26o", _rinex2_obs("PLG2", "LEICA GR50", "LEIAR20      NONE"))
    _write_rinex(tmp_path, "bost0870.26o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR20      NONE"))

    only_087 = _parse_rinex_headers(tmp_path, year=2026, session="0870")
    assert "BOST" in only_087
    assert "PLG2" not in only_087  # the intermittent station is filtered out

    only_086 = _parse_rinex_headers(tmp_path, year=2026, session="0860")
    assert "PLG2" in only_086
    assert "BOST" not in only_086


def test_parse_rinex_headers_session_filter_matches_rinex3_longname(tmp_path):
    """RINEX 3 long names (YYYYDDD) also honour the session filter."""
    _write_rinex(
        tmp_path,
        "CUSV00THA_R_20260870000_01D_30S_MO.rnx",
        _rinex2_obs("CUSV", "SEPT POLARX5", "LEIAR25.R4   NONE"),
    )
    result = _parse_rinex_headers(tmp_path, year=2026, session="0870")
    assert "CUSV" in result
    # different session → excluded
    assert _parse_rinex_headers(tmp_path, year=2026, session="0880") == {}


def test_validate_no_rinex_found_is_error_when_required(tmp_path):
    """Empty/wrong source dir must NOT pass vacuously when require_stations=True.

    This is the empty-RAW/ defeat: validating before RNX_COP staged any data
    parsed zero stations and reported ok. With require_stations the report fails.
    """
    empty = tmp_path / "PGN"
    empty.mkdir()
    sta = tmp_path / "TEST.STA"
    sta.write_text(_make_sta_content([{"name": "BOST"}]), encoding="ascii")

    report = validate_rinex_headers(empty, sta, require_stations=True)
    assert not report.ok
    assert report.no_rinex_found
    assert "No RINEX" in str(ValidationError(report))


def test_validate_no_rinex_found_passes_only_when_explicitly_permitted(tmp_path):
    """An empty source passes ONLY when a caller opts out deliberately.

    require_stations defaulted to False until 2026-08-04, so the vacuous pass
    was what you got by accident and the safe behaviour had to be requested.
    That is now inverted: permissiveness is the thing you must ask for.
    """
    empty = tmp_path / "RAW"
    empty.mkdir()
    sta = tmp_path / "TEST.STA"
    sta.write_text(_make_sta_content([{"name": "BOST"}]), encoding="ascii")

    report = validate_rinex_headers(empty, sta, require_stations=False)
    assert report.ok
    assert not report.no_rinex_found

    # ...and the default is now the safe one.
    strict = validate_rinex_headers(empty, sta)
    assert not strict.ok
    assert strict.no_rinex_found


def test_linux_bpe_validates_datapool_source_per_session(tmp_path):
    """Backend with rinex_source_dir validates the DATAPOOL source, not empty RAW/.

    Reproduces the PLG2 hard-abort class: an intermittent station present in the
    source for this session but missing from STA must be caught pre-BPE.
    """
    from bernese_workflow.backends import LinuxBPEBackend

    source = tmp_path / "DATAPOOL" / "PGN"
    source.mkdir(parents=True)
    # PLG2 present for session 0860 but absent from STA → RXOBV3 would hard-abort
    _write_rinex(source, "plg20860.26o", _rinex2_obs("PLG2", "LEICA GR50", "LEIAR20      NONE"))

    campaign_path = tmp_path / "GPSDATA" / "PAGENET"
    (campaign_path / "RAW").mkdir(parents=True)  # empty, as it is pre-BPE
    sta_dir = campaign_path / "STA"
    sta_dir.mkdir(parents=True)
    (sta_dir / "PAGENET.STA").write_text(
        _make_sta_content([{"name": "BOST"}]),  # PLG2 deliberately absent
        encoding="ascii",
    )

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
        rinex_source_dir=source,
    )

    with pytest.raises(ValidationError) as exc_info:
        backend.run("PAGENET", 2026, "0860")
    assert "PLG2" in str(exc_info.value)


def test_linux_bpe_datapool_source_empty_for_session_raises(tmp_path):
    """require_stations: source with no RINEX for the session fails loudly, not vacuously."""
    from bernese_workflow.backends import LinuxBPEBackend

    source = tmp_path / "DATAPOOL" / "PGN"
    source.mkdir(parents=True)
    # data only for 0860, but we ask for 0870 → zero matches
    _write_rinex(source, "bost0860.26o", _rinex2_obs("BOST", "LEICA GR50", "LEIAR20      NONE"))

    campaign_path = tmp_path / "GPSDATA" / "PAGENET"
    sta_dir = campaign_path / "STA"
    sta_dir.mkdir(parents=True)
    (sta_dir / "PAGENET.STA").write_text(
        _make_sta_content([{"name": "BOST"}]), encoding="ascii"
    )

    backend = LinuxBPEBackend(
        bernese_root=tmp_path / "BERN54",
        user_dir=tmp_path / "GPSUSER",
        campaign_dir=tmp_path / "GPSDATA",
        rinex_source_dir=source,
    )

    with pytest.raises(ValidationError) as exc_info:
        backend.run("PAGENET", 2026, "0870")
    assert "No RINEX" in str(exc_info.value)


# ===========================================================================
# Task C2 — compressed and Hatanaka RINEX recognition
#
# These tests exist because the 128 that preceded them all passed while
# `_is_rinex_obs` was blind to every file in a real DATAPOOL. The fixtures
# above use uncompressed `.YYo`/`.rnx` names; the archive on gps3 contains
# 3,010 `.gz` and 20 `.Z` files and not one uncompressed observation file.
# A suite whose fixtures do not span the production filename space cannot
# fail on a matcher bug, however wrong the matcher is.
# ===========================================================================

# Real DATAPOOL on gps3 — used by the integration test below when present.
_GPS3_DATAPOOL = Path("/home/gps3/GPSDATA/DATAPOOL/PGN")
_GPS3_STA = Path("/home/gps3/GPSDATA/DATAPOOL/REF54/PGN.STA")


def _lzw_compress_small(data: bytes) -> bytes:
    """Encode `data` as a UNIX-compress (.Z) stream. Small inputs only.

    Nothing on a stock Ubuntu box can *write* .Z — `compress`/`ncompress` are
    not installed and GNU gzip only reads the format — so a `.Z` fixture has to
    be either committed as a binary blob or generated here. Generated wins: the
    real samples are ~1.6 MB, and a committed blob is opaque to review.

    The `compress` format pads the code stream to an 8-code boundary each time
    the code width grows, a bug-compatibility quirk that is awkward to
    reproduce. We avoid it rather than implement it: width starts at 9 bits and
    only grows once the dictionary reaches 512. Block mode reserves 256 as
    CLEAR so codes are issued from 257, leaving 255 entries of headroom — one
    per emitted code. Keep fixtures small and the width never changes.

    Verified round-tripping through GNU `gzip -dc` on gps3, 2026-08-03.
    """
    MAX_9BIT = 512
    dictionary: dict[bytes, int] = {bytes([i]): i for i in range(256)}
    next_code = 257
    w = b""
    codes: list[int] = []

    for byte in data:
        c = bytes([byte])
        wc = w + c
        if wc in dictionary:
            w = wc
            continue
        codes.append(dictionary[w])
        if next_code >= MAX_9BIT:
            raise ValueError(
                "fixture too large for the 9-bit-only encoder "
                f"(dictionary hit {next_code}); shorten it"
            )
        dictionary[wc] = next_code
        next_code += 1
        w = c
    if w:
        codes.append(dictionary[w])
    if next_code >= MAX_9BIT:
        raise ValueError("fixture too large for the 9-bit-only encoder")

    out = bytearray(b"\x1f\x9d")
    out.append(0x80 | 16)  # block mode | maxbits=16
    bitbuf = bitcount = 0
    for code in codes:
        bitbuf |= code << bitcount
        bitcount += 9
        while bitcount >= 8:
            out.append(bitbuf & 0xFF)
            bitbuf >>= 8
            bitcount -= 8
    if bitcount:
        out.append(bitbuf & 0xFF)
    return bytes(out)


def _crinex(rinex_text: str) -> str:
    """Wrap a RINEX header in CRINEX (Hatanaka) framing.

    The point of this fixture: a CRINEX file carries the original RINEX header
    VERBATIM after two CRINEX lines, and compacts only the observation records
    below END OF HEADER. So header validation needs decompression but never
    `crx2rnx`. Shape copied from a real PZAM0860.26d.gz on gps3.
    """
    return (
        "1.0                 COMPACT RINEX FORMAT"
        "                    CRINEX VERS   / TYPE\n"
        "RNX2CRX ver.4.0.7                       "
        "28-03-26 00:01      CRINEX PROG / DATE\n"
    ) + rinex_text


# --- name recognition -------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        # RINEX 2 short name, plain observation
        "pgsn0010.24o",
        "PGSN0010.24O",
        "pgsn0010.24o.gz",
        "PGSN0010.24O.Z",
        # RINEX 2 short name, Hatanaka
        "pgsn0010.24d",
        "PZAM0860.26d.gz",
        "GFCN0100.23D.Z",
        # RINEX 3 long name, plain
        "PGSN00PHL_R_20240010000_01D_30S_MO.rnx",
        "PGSN00PHL_R_20240010000_01D_30S_MO.rnx.gz",
        # RINEX 3 long name, Hatanaka
        "PGSN00PHL_R_20240010000_01D_30S_MO.crx",
        "CUSV00THA_R_20260860000_01D_30S_MO.crx.gz",
        # Generic / Bernese copy
        "something.obs",
        "PLG2_20260870.RXO",
        "PLG2_20260870.RXO.gz",
    ],
)
def test_is_rinex_obs_accepts_real_datapool_names(name):
    """Every form that actually occurs in a PAGENET/IGS DATAPOOL must match."""
    assert _is_rinex_obs(Path(name)), f"{name} should be recognised as RINEX OBS"


@pytest.mark.parametrize(
    "name",
    [
        # Navigation, meteorological, glonass — no REC/ANT records to read.
        "pgsn0010.24n",
        "pgsn0010.24n.gz",
        "PGSN0010.24N.Z",
        "pgsn0010.24m",
        "pgsn0010.24g",
        # Products that share the directory but are not observations.
        "COD22442.SP3.Z",
        "COD22442.CLK.Z",
        "COD22442.BIA.Z",
        "PGN.STA",
        # No extension at all, and bare compression.
        "README",
        "archive.gz",
    ],
)
def test_is_rinex_obs_rejects_non_observation_files(name):
    """Nav/met/product files must not be pulled into the station set."""
    assert not _is_rinex_obs(Path(name)), f"{name} should NOT be treated as RINEX OBS"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("PZAM0860.26d.gz", "PZAM0860.26d"),
        ("GFCN0100.23D.Z", "GFCN0100.23D"),
        ("CUSV00THA_R_20260860000_01D_30S_MO.crx.gz", "CUSV00THA_R_20260860000_01D_30S_MO.crx"),
        ("PGSN00PHL_R_20240010000_01D_30S_MO.rnx.gz", "PGSN00PHL_R_20240010000_01D_30S_MO.rnx"),
        ("pgsn0010.24o", "pgsn0010.24o"),          # nothing to strip
        ("weird.24o.gz.Z", "weird.24o"),           # right-to-left, repeatedly
        ("noextension", "noextension"),
    ],
)
def test_strip_compression_suffixes(name, expected):
    """Stripping is right-to-left and looping — one pass is not enough."""
    assert _strip_compression_suffixes(name) == expected


# --- reading through compression --------------------------------------------


def test_open_rinex_text_reads_plaintext(tmp_path):
    p = tmp_path / "pgsn0010.24o"
    p.write_text(_rinex2_obs("PGSN"), encoding="ascii")
    with _open_rinex_text(p) as fh:
        assert "MARKER NAME" in "".join(fh)


def test_open_rinex_text_reads_gzip(tmp_path):
    p = tmp_path / "pgsn0010.24o.gz"
    with _gzip.open(p, "wt", encoding="ascii") as fh:
        fh.write(_rinex2_obs("PGSN"))
    with _open_rinex_text(p) as fh:
        assert "MARKER NAME" in "".join(fh)


@pytest.mark.skipif(shutil.which("gzip") is None, reason="GNU gzip required to read .Z")
def test_open_rinex_text_reads_lzw_dot_z(tmp_path):
    """Python's gzip cannot read .Z; the validator must shell out to GNU gzip."""
    text = _rinex2_obs("PGSN")
    p = tmp_path / "pgsn0010.24o.Z"
    p.write_bytes(_lzw_compress_small(text.encode("ascii")))

    # Guard the premise: if Python could read it, the subprocess path would be
    # dead code and this test would be asserting nothing. BadGzipFile is the
    # specific failure — gzip magic is 1f 8b, LZW is 1f 9d.
    with pytest.raises(_gzip.BadGzipFile):
        with _gzip.open(p, "rt") as fh:
            fh.read()

    with _open_rinex_text(p) as fh:
        assert "MARKER NAME" in "".join(fh)


@pytest.mark.skipif(shutil.which("gzip") is None, reason="GNU gzip required to read .Z")
def test_lzw_fixture_is_readable_by_system_gzip(tmp_path):
    """The fixture generator must produce a stream GNU gzip actually accepts."""
    raw = _rinex2_obs("PGSN").encode("ascii")
    p = tmp_path / "x.Z"
    p.write_bytes(_lzw_compress_small(raw))
    proc = subprocess.run(["gzip", "-dc", str(p)], capture_output=True)
    assert proc.returncode == 0
    assert proc.stdout == raw


@pytest.mark.skipif(shutil.which("gzip") is None, reason="GNU gzip required to read .Z")
def test_open_rinex_text_early_exit_on_dot_z_is_not_an_error(tmp_path):
    """Stopping at END OF HEADER kills gzip with SIGPIPE; that must not raise.

    The validator reads a few hundred bytes of a multi-megabyte file, so the
    subprocess is always cut off mid-write. Its resulting 141 exit status is
    meaningless and must not be checked — the inverse of the swallowed-status
    bugs this project has hit repeatedly.
    """
    body = _rinex2_obs("PGSN")
    p = tmp_path / "pgsn0010.24o.Z"
    p.write_bytes(_lzw_compress_small(body.encode("ascii")))

    with _open_rinex_text(p) as fh:
        first = next(iter(fh))          # read ONE line, then abandon the stream
    assert "RINEX VERSION" in first     # context exit must not raise


# --- the header parser, end to end ------------------------------------------


def test_parse_rinex_headers_reads_compressed_and_hatanaka(tmp_path):
    """One session, four real-world encodings, four stations recovered."""
    src = tmp_path / "PGN"
    src.mkdir()

    (src / "paaa0010.24o").write_text(_rinex2_obs("PAAA"), encoding="ascii")

    with _gzip.open(src / "pbbb0010.24d.gz", "wt", encoding="ascii") as fh:
        fh.write(_crinex(_rinex2_obs("PBBB")))

    (src / "pccc0010.24o.Z").write_bytes(
        _lzw_compress_small(_rinex2_obs("PCCC").encode("ascii"))
    )

    with _gzip.open(
        src / "PDDD00PHL_R_20240010000_01D_30S_MO.crx.gz", "wt", encoding="ascii"
    ) as fh:
        fh.write(_crinex(_rinex2_obs("PDDD")))

    # Must be ignored: navigation file for the same session.
    with _gzip.open(src / "paaa0010.24n.gz", "wt", encoding="ascii") as fh:
        fh.write("     2.11           NAVIGATION DATA                         "
                 "RINEX VERSION / TYPE\n")

    headers = _parse_rinex_headers(src, year=2024, session="0010")
    assert set(headers) == {"PAAA", "PBBB", "PCCC", "PDDD"}
    assert headers["PBBB"]["receiver"] == "LEICA GR50"   # _rinex2_obs default
    assert headers["PDDD"]["antenna"] == "LEIAR20      NONE"


def test_hatanaka_header_needs_no_crx2rnx(tmp_path):
    """CRINEX stores the RINEX header verbatim — decompression alone suffices.

    Pinning this because it is the finding that kept C2 small: no RNXCMP build,
    no `hatanaka` package, no crx2rnx invocation anywhere in validation.
    """
    src = tmp_path / "PGN"
    src.mkdir()
    with _gzip.open(src / "pzam0860.26d.gz", "wt", encoding="ascii") as fh:
        fh.write(_crinex(_rinex2_obs("PZAM", "LEICA GR25", "LEIAR20      LEIM")))

    headers = _parse_rinex_headers(src, year=2026, session="0860")
    assert headers["PZAM"] == {"receiver": "LEICA GR25", "antenna": "LEIAR20      LEIM"}


def test_unreadable_member_warns_but_does_not_abort_the_scan(tmp_path):
    """One corrupt archive member must not fail validation of the other 676."""
    src = tmp_path / "PGN"
    src.mkdir()
    (src / "pgoo0010.24o").write_text(_rinex2_obs("PGOO"), encoding="ascii")
    (src / "pbad0010.24o.gz").write_bytes(b"\x1f\x8b\x08 truncated garbage")

    headers = _parse_rinex_headers(src, year=2024, session="0010")
    assert "PGOO" in headers


# --- integration against the real archive on gps3 ---------------------------


@pytest.mark.skipif(
    not _GPS3_DATAPOOL.is_dir() or not _GPS3_STA.is_file(),
    reason="real gps3 DATAPOOL not present (expected off-host)",
)
def test_real_gps3_datapool_is_visible_to_the_validator():
    """The regression that motivated C2, asserted against the real archive.

    Before the fix this returned zero stations for every session — the state
    that would have let a full BPE run proceed on unvalidated data.
    """
    headers = _parse_rinex_headers(_GPS3_DATAPOOL, year=2026, session="0860")
    assert len(headers) > 50, f"expected the DOY 086 network, got {len(headers)}"
    assert "PZAM" in headers          # RINEX 2 Hatanaka, gzipped
    assert "CUSV" in headers          # RINEX 3 long name, Hatanaka, gzipped
    assert all(h["receiver"] or h["antenna"] for h in headers.values())


# --- station-code resolution across mixed naming conventions ----------------

def _rinex2_with_markers(marker_name: str, marker_number: str) -> str:
    """RINEX 2 header carrying both MARKER NAME and MARKER NUMBER."""
    return (
        "     2.11           OBSERVATION DATA    M                   RINEX VERSION / TYPE\n"
        f"{marker_name:<60}MARKER NAME         \n"
        f"{marker_number:<60}MARKER NUMBER       \n"
        f"{'':20}{'LEICA GR50':<20}{'4.52':<20}REC # / TYPE / VERS \n"
        f"{'':20}{'LEIAR25.R4      LEIT':<20}{'':20}ANT # / TYPE        \n"
        f"{'':60}END OF HEADER       \n"
    )


@pytest.mark.parametrize(
    ("marker_name", "marker_number", "filename_code", "expected", "why"),
    [
        # PAGENET CORS: descriptive name, code in MARKER NUMBER.
        ("BOGO CITY", "PBOG", "PBOG", "PBOG", "MARKER NUMBER wins over descriptive name"),
        ("SAN FERNANDO", "PSNR", "PSNR", "PSNR", "multi-word name must not be truncated"),
        # IGS fiducial: code in MARKER NAME, DOMES in MARKER NUMBER.
        ("CUSV", "21904S001", "CUSV", "CUSV", "DOMES number is not a station code"),
        ("DAEJ", "23902M002", "DAEJ", "DAEJ", "MARKER NAME used when it is a bare code"),
        # Degenerate headers fall back to the filename.
        ("", "", "PZAM", "PZAM", "empty headers fall back to filename"),
        ("SOME LONG SITE NAME", "", "PTAG", "PTAG", "unusable name falls back to filename"),
    ],
)
def test_resolve_station_code(marker_name, marker_number, filename_code, expected, why):
    got = _resolve_station_code(
        filename_code=filename_code,
        marker_name=marker_name,
        marker_number=marker_number,
        source="test",
    )
    assert got == expected, why


def test_pagenet_descriptive_marker_name_does_not_shadow_station_code(tmp_path):
    """Regression: 'BOGO CITY' must resolve to PBOG, not BOGO.

    Taking MARKER NAME[:4] reported 9 of 72 real DOY 086 stations as absent from
    PGN.STA, on data that processes correctly. A validator that fails on good
    data gets disabled, which is worse than not having it.
    """
    src = tmp_path / "PGN"
    src.mkdir()
    with _gzip.open(src / "PBOG0860.26d.gz", "wt", encoding="ascii") as fh:
        fh.write(_crinex(_rinex2_with_markers("BOGO CITY", "PBOG")))

    headers = _parse_rinex_headers(src, year=2026, session="0860")
    assert "PBOG" in headers
    assert "BOGO" not in headers


def test_igs_and_pagenet_conventions_coexist_in_one_session(tmp_path):
    """Both naming schemes appear in the same campaign; both must resolve."""
    src = tmp_path / "PGN"
    src.mkdir()
    with _gzip.open(src / "PBOG0860.26d.gz", "wt", encoding="ascii") as fh:
        fh.write(_crinex(_rinex2_with_markers("BOGO CITY", "PBOG")))
    with _gzip.open(
        src / "CUSV00THA_R_20260860000_01D_30S_MO.crx.gz", "wt", encoding="ascii"
    ) as fh:
        fh.write(_crinex(_rinex2_with_markers("CUSV", "21904S001")))

    headers = _parse_rinex_headers(src, year=2026, session="0860")
    assert set(headers) == {"PBOG", "CUSV"}


def test_dot_directories_are_not_scanned(tmp_path):
    """Hand-quarantined data must not be resurrected by the recursive walk.

    gps3's DATAPOOL carries `.excluded_plg2/` holding the two intermittent PLG2
    files set aside during the training week. rglob descends into it, so the
    validator reported PLG2 missing from PGN.STA on DOY 086/088 — files that
    RNX_COP, which globs without recursing, will never stage.
    """
    src = tmp_path / "PGN"
    (src / ".excluded_plg2").mkdir(parents=True)
    (src / "pgoo0860.26o").write_text(_rinex2_obs("PGOO"), encoding="ascii")
    (src / ".excluded_plg2" / "plg20860.26o").write_text(
        _rinex2_obs("PLG2"), encoding="ascii"
    )

    headers = _parse_rinex_headers(src, year=2026, session="0860")
    assert "PGOO" in headers
    assert "PLG2" not in headers, "quarantined station must stay quarantined"


def test_ordinary_subdirectories_are_still_scanned(tmp_path):
    """Only dot-directories are skipped; normal nesting still works."""
    src = tmp_path / "PGN"
    (src / "daily").mkdir(parents=True)
    (src / "daily" / "pgoo0860.26o").write_text(_rinex2_obs("PGOO"), encoding="ascii")

    headers = _parse_rinex_headers(src, year=2026, session="0860")
    assert "PGOO" in headers
