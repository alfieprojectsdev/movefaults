"""Tests for bpe_scanner.

The fixtures in ``fixtures/bpe_errors/`` are verbatim BPE step outputs captured
on gps3, renamed ``<campaign>_<original name>``. Each failure exists twice: the
``.PRT`` protocol and the ``.LOG``, which carry the same message block in
different surroundings, so both are checked.

The 29 August MAXPAR log was not kept. ``MXPREP_*`` reproduces it: EXAMPLE
2023/0100's final ADDNEQ2 (option dir R2S_FIN) run on a copy of the campaign
with MAXPAR lowered from 6000 to 100, on 2026-10-15. ``MXP230100_*`` is the
first attempt at that, made in REPR_MODE, whose fresh campaign has no STA
files: an unplanned but genuine OPNERR failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bernese_workflow.bpe_scanner import kind_of, scan, scan_file

FIXTURES = Path(__file__).parent / "fixtures" / "bpe_errors"

# (fixture stem, failed program, cause signature, cause params that must be present)
_CCRNXO = ("CCRNXO", ("O_CCRNXO:concatenateOrMergeRinexFiles", "NO_INPUT_FILES"), {})
_GTATML = (
    "GPSEST",
    ("GTATML", "ATMOSPHERIC_TIDAL_LOADING_CORRECTION_VALUES_NOT_FOUND"),
    {
        "return_code": "2",
        "station_name": "PTAG 22006M005",
        "file_name": "${P}/PHD252000/STA/PHDEN.ATL",
    },
)
_GTOCNL = (
    "GPSEST",
    ("GTOCNL", "OCEAN_LOADING_CORRECTION_VALUES_NOT_FOUND"),
    {
        "return_code": "2",
        "station_name": "PTTN PTTN",
        "file_name": "${P}/PHN252000/STA/PHNAT.BLQ",
    },
)
_HELMR1 = ("HELMR1", ("HELMR1", "NO_REDUNDANCY_NO_VERIFICATION_OF_SITES_POSSIBLE"), {})

EXPECTED = {
    **{
        f"{camp}_RP25{doy}0_022_002": _CCRNXO
        for camp in ("LUZON", "LZFLT")
        for doy in ("121", "122", "123", "125")
    },
    "PHD252000_RP252000_322_015": _GTATML,
    "PHD252000_RP252000_322_016": _GTATML,
    "PHN252000_RP252000_322_017": _GTOCNL,
    "LZY250360_RP250360_513_000": _HELMR1,
    "MXPREP_MX230100_511_000": (
        "ADDNEQ2",
        ("neqckdim", "DIMENSION_TOO_SMALL"),
        # Evidence, not a conclusion: 101 is the first request that overflowed,
        # not the number of parameters the solution needs.
        {"requested_num_of_parameters": "101", "maximum_size_of_the_array": "100"},
    ),
    "MXP230100_MX230100_511_000": (
        "ADDNEQ2",
        ("OPNERR", "OPEN_FAILED"),
        {"file_name": "${P}/MXP230100/STA/EXAMPLE.STA", "iostat": "2"},
    ),
}


def test_every_failure_fixture_has_an_expectation() -> None:
    """A fixture added without an expected record would never be checked."""
    stems = {p.stem for p in FIXTURES.glob("*.LOG")}
    assert stems == set(EXPECTED)


@pytest.mark.parametrize("suffix", [".PRT", ".LOG"])
@pytest.mark.parametrize("stem", sorted(EXPECTED))
def test_failure_corpus(stem: str, suffix: str) -> None:
    program, signature, params = EXPECTED[stem]
    report = scan_file(FIXTURES / f"{stem}{suffix}")

    assert report.failed
    assert report.failed_program == program
    assert report.cause is not None
    assert report.cause.severity == "error"
    assert report.cause.signature == signature
    for key, value in params.items():
        assert report.cause.params[key] == value


def test_errors_without_failure_are_not_a_cause() -> None:
    """CCRNXO reports each empty RINEX file with ``***`` and carries on.

    Five error blocks, PROGRAM ENDED, no ERR line: the step succeeded, and a
    breaker counting ``***`` lines would have stopped a healthy run.
    """
    report = scan_file(FIXTURES / "LUZON_RP251230_022_004.PRT")

    assert not report.failed
    assert report.cause is None
    errors = [m for m in report.messages if m.severity == "error"]
    assert len(errors) == 5
    assert {m.signature for m in errors} == {("O_RNXBASE:rdHdrLine", "EMPTY_RINEX_FILE")}
    assert errors[0].program == "CCRNXO"
    assert errors[0].params["rinex_file_name"] == "${P}/LUZON/ORX/DARW00AUS_20251210.RXO"
    assert errors[0].params["line_number"] == "1"


def test_warnings_before_the_cause_are_kept_but_not_blamed() -> None:
    report = scan_file(FIXTURES / "PHD252000_RP252000_322_015.PRT")

    warnings = [m for m in report.messages if m.severity == "warning"]
    assert [m.emitter for m in warnings] == ["D_STACRX:chkType002"] * 6 + ["HEDINF"]
    assert warnings[0].kind == "OVERLAPPING_INTERVALS_IN_TYPE_FILE"
    assert warnings[0].detail[0].split()[:2] == ["BTUN", "BTUN"]
    assert report.cause is not None and report.cause.emitter == "GTATML"


def test_line_numbers_point_at_the_header() -> None:
    path = FIXTURES / "PHN252000_RP252000_322_017.PRT"
    lines = path.read_text().splitlines()
    for m in scan_file(path).messages:
        assert lines[m.line - 1].lstrip().startswith(("***", "###"))


def test_same_failure_gives_same_signature() -> None:
    """The breaker counts signatures; the numbers in a message must not split them."""
    text = (FIXTURES / "MXPREP_MX230100_511_000.PRT").read_text()
    a = scan(text)
    b = scan(
        text.replace(":         101", ":        2417").replace(":         100", ":        2416")
    )
    assert a.cause is not None and b.cause is not None
    assert a.cause.signature == b.cause.signature
    assert a.cause.params != b.cause.params


def test_cause_is_the_last_error_before_err() -> None:
    text = (
        " *** FN O_RNXBASE:rdHdrLine, PG CCRNXO\n"
        "        Empty RINEX file.\n"
        "\n"
        " *** SR O_CCRNXO:concatenateOrMergeRinexFiles, PG CCRNXO\n"
        "        No input files\n"
        "\n"
        " 12-AUG-2026  11:59:10  00:00:00  00:00:00  ERR CCRNXO    ERROR IN MAIN PROGRAM\n"
    )
    report = scan(text)
    assert report.cause is not None
    assert report.cause.kind == "NO_INPUT_FILES"


def test_failure_without_an_error_message_has_no_cause() -> None:
    """A Perl-level failure has an ERR line and no ``***``. Unknown, not guessed."""
    report = scan(" 01-JAN-2026  00:00:00  00:00:00  ERR RUNBPE.pm  Script failed\n")
    assert report.failed
    assert report.cause is None


def test_header_variants() -> None:
    text = (
        " ### PG ORBGEN (06-Aug-2026 14:46:36)\n"
        "        Satellite excluded because of the satellite selection options\n"
        "        Satellite number: 102\n"
        "\n"
        " ### SR UPDTRP: EPOCH,SVN,SVNREF,O-C TOO BIG:  1410 236  13       -0.622 (GANP-ORID)\n"
        " ### SR solcheck:    1 singular element(s) found:\n"
        "                    Num   Type\n"
        " 02-SEP-2026  14:22:18  00:00:15  00:00:15  MSG GPSEST    PROGRAM ENDED\n"
    )
    orbgen, updtrp, solcheck = scan(text).messages

    assert (orbgen.emitter_type, orbgen.program) == ("PG", "ORBGEN")
    assert orbgen.kind == "SATELLITE_EXCLUDED_BECAUSE_OF_THE_SATELLITE_SELECTION_OPTIONS"
    assert orbgen.params["satellite_number"] == "102"
    assert updtrp.kind == "EPOCH_SVN_SVNREF_O_C_TOO_BIG"
    assert updtrp.detail == ()
    # The MSG line ends the block even without a blank line before it.
    assert solcheck.kind == "SINGULAR_ELEMENT_FOUND"
    assert solcheck.detail == ("Num   Type",)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("DIMENSION TOO SMALL", "DIMENSION_TOO_SMALL"),
        (
            "NO REDUNDANCY. NO VERIFICATION OF SITES POSSIBLE",
            "NO_REDUNDANCY_NO_VERIFICATION_OF_SITES_POSSIBLE",
        ),
        ("   1 singular element(s) found:", "SINGULAR_ELEMENT_FOUND"),
        (
            "Overlapping intervals in TYPE 002, file: ${P}/X.STA",
            "OVERLAPPING_INTERVALS_IN_TYPE_FILE",
        ),
        ("-0.622", ""),
        (
            "16 OF 16 SATELLITES WITH DATA PROBLEMS AT EPOCH   1914   (HERT-WSRT)",
            "OF_SATELLITES_WITH_DATA_PROBLEMS_AT_EPOCH",
        ),
        (
            'Empty "Long Name" column for station "ALAB ALAB" found in',
            "EMPTY_COLUMN_FOR_STATION_FOUND_IN",
        ),
        (
            "Noted event flag 'New site occupation event' in observaton record.",
            "NOTED_EVENT_FLAG_NEW_SITE_OCCUPATION_EVENT_IN_OBSERVATON_RECORD",
        ),
    ],
)
def test_kind_of(text: str, kind: str) -> None:
    assert kind_of(text) == kind
