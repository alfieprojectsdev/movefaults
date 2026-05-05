"""Tests for the pre-BPE RINEX header validator (BRN-006)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from bernese_workflow.rinex_header_validator import (
    Mismatch,
    ValidationError,
    ValidationReport,
    _ant_types_match,
    _parse_atx_antenna_types,
    _parse_rinex_headers,
    _parse_sta_type002,
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
    """Station in STA but no RINEX in RAW/ — expected, not a validation failure."""
    raw_dir = tmp_path / "RAW"
    raw_dir.mkdir()
    # No RINEX files — RAW/ is empty

    sta = tmp_path / "TEST.STA"
    sta.write_text(
        _make_sta_content([{"name": "BOST", "receiver": "LEICA GR50", "antenna": "LEIAR20"}]),
        encoding="ascii",
    )

    report = validate_rinex_headers(raw_dir, sta)
    assert report.ok  # not an error
    assert "BOST" in report.missing_from_raw


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
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="BPE finished", stderr="", returncode=0)
        result = backend.run("NORAW", 2023, "0100")

    # Reached here without ValidationError → pre-flight was correctly skipped
    assert result is not None
