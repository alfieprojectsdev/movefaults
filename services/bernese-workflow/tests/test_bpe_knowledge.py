"""Tests for bpe_knowledge and the real config/bernese/bpe_errors.yaml.

The file is edited by people who are not programmers, so most of these tests
are about the mistakes an edit can make and the message that comes back.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bernese_workflow.bpe_knowledge import (
    DEFAULT_PATH,
    KnowledgeBaseError,
    explain,
    load,
    loads,
    main,
)
from bernese_workflow.bpe_scanner import scan, scan_file

FIXTURES = Path(__file__).parent / "fixtures" / "bpe_errors"

_ROW = """\
  - emitter: neqckdim
    message: DIMENSION TOO SMALL
    scope: configuration
    status: established
    diagnosis: d
    remedy: r
    source: s
"""


def test_the_real_file_loads() -> None:
    kb = load(DEFAULT_PATH)
    assert len(kb.entries) >= 11


def test_every_captured_failure_has_a_row() -> None:
    """The scanner's corpus is the minimum the knowledge base must know."""
    kb = load(DEFAULT_PATH)
    failed = 0
    for path in sorted(FIXTURES.glob("*.PRT")):
        report = scan_file(path)
        if not report.failed:
            continue
        failed += 1
        assert report.cause is not None, path.name
        assert kb.lookup(report.cause) is not None, f"{path.name}: {report.cause.signature}"
    assert failed == 10


def test_lookup_ignores_emitter_case_and_message_numbers() -> None:
    kb = loads("entries:\n" + _ROW.replace("emitter: neqckdim", "emitter: NEQCKDIM"))
    cause = scan(
        " *** SR neqckdim: DIMENSION TOO SMALL\n"
        "                  Requested num. of parameters:        1001\n"
        " 29-AUG-2026  09:00:00  00:00:01  00:00:00  ERR ADDNEQ2   ERROR IN MAIN PROGRAM\n"
    ).cause
    assert cause is not None
    entry = kb.lookup(cause)
    assert entry is not None and entry.scope == "configuration"


def test_message_is_pasted_as_printed() -> None:
    """Quoted names are dropped on both sides, so the pasted text matches."""
    kb = load(DEFAULT_PATH)
    cause = scan(
        ' *** SR chkmax: Dimension for parameter "MAXSNG" exceeded\n'
        " 01-JAN-2026  00:00:00  00:00:01  00:00:00  ERR GPSEST    ERROR IN MAIN PROGRAM\n"
    ).cause
    assert cause is not None
    assert kb.lookup(cause) is not None


def test_atl_read_error_matches_its_source_format() -> None:
    """No capture of this one; text from GTATML.f FORMAT 901, which prints one line."""
    kb = load(DEFAULT_PATH)
    cause = scan(
        " *** SR GTATML: ERROR READING ATMOSPHERIC TIDAL LOADING CORRECTION VALUES\n"
        "                STATION NAME : PTAG 22006M005\n"
        " 01-JAN-2026  00:00:00  00:00:01  00:00:00  ERR GPSEST    ERROR IN MAIN PROGRAM\n"
    ).cause
    assert cause is not None
    entry = kb.lookup(cause)
    assert entry is not None and "trailing" not in entry.message
    assert "blank line" in entry.remedy


def test_unknown_error_has_no_row() -> None:
    kb = load(DEFAULT_PATH)
    cause = scan(
        " *** SR NOSUCH: SOMETHING NEW\n"
        " 01-JAN-2026  00:00:00  00:00:01  00:00:00  ERR GPSEST    ERROR IN MAIN PROGRAM\n"
    ).cause
    assert cause is not None
    assert kb.lookup(cause) is None


@pytest.mark.parametrize(
    ("row", "complaint"),
    [
        (_ROW.replace("    remedy: r\n", ""), "missing: remedy"),
        (_ROW.replace("scope: configuration", "scope: config"), "scope must be"),
        (_ROW.replace("status: established", "status: done"), "status must be"),
        (_ROW.replace("    remedy: r\n", "    remdy: r\n"), "unknown field: remdy"),
        (_ROW.replace("remedy: r", "remedy: no"), "remedy must be text"),
        (
            _ROW.replace("message: DIMENSION TOO SMALL", "message: '(1001) 7'"),
            "nothing left to match",
        ),
        (_ROW.replace("    diagnosis: d\n", "    diagnosis:\n"), "diagnosis must be text"),
    ],
)
def test_editing_mistakes_are_named(row: str, complaint: str) -> None:
    with pytest.raises(KnowledgeBaseError) as exc:
        loads("entries:\n" + row)
    assert complaint in str(exc.value)
    assert "entry 1 (neqckdim)" in str(exc.value)


def test_duplicate_rows_are_refused() -> None:
    second = _ROW.replace("emitter: neqckdim", "emitter: NEQCKDIM")
    with pytest.raises(KnowledgeBaseError, match="entry 2 .* same error as entry 1"):
        loads("entries:\n" + _ROW + second)


@pytest.mark.parametrize(
    "text", ["", "- a\n", "entries: x\n", "entries: []\nextra: 1\n", "entries: [\n"]
)
def test_malformed_files_are_refused(text: str) -> None:
    with pytest.raises(KnowledgeBaseError):
        loads(text)


def test_explain_known_failure() -> None:
    kb = load(DEFAULT_PATH)
    text = explain(scan_file(FIXTURES / "MXPREP_MX230100_511_000.PRT"), kb)
    assert "ADDNEQ2 failed" in text
    assert "neqckdim: DIMENSION TOO SMALL" in text
    assert "Requested num. of parameters:         101" in text
    assert "scope: configuration" in text
    assert "Raise MAXPAR" in text


def test_explain_unknown_failure_shows_the_raw_message() -> None:
    kb = load(DEFAULT_PATH)
    report = scan(
        " *** SR NOSUCH: SOMETHING NEW\n"
        "                DETAIL : 7\n"
        " 01-JAN-2026  00:00:00  00:00:01  00:00:00  ERR GPSEST    ERROR IN MAIN PROGRAM\n"
    )
    text = explain(report, kb)
    assert "UNKNOWN" in text
    assert "*** SR NOSUCH: SOMETHING NEW" in text
    assert "DETAIL : 7" in text


def test_explain_failure_without_message() -> None:
    kb = load(DEFAULT_PATH)
    report = scan(" 01-JAN-2026  00:00:00  00:00:00  ERR RUNBPE.pm  Script failed\n")
    assert "no *** message" in explain(report, kb)


def test_explain_success() -> None:
    kb = load(DEFAULT_PATH)
    assert "did not fail" in explain(scan_file(FIXTURES / "LUZON_RP251230_022_004.PRT"), kb)


def test_main_exit_status(capsys: pytest.CaptureFixture[str]) -> None:
    known = str(FIXTURES / "PHN252000_RP252000_322_017.PRT")
    ok = str(FIXTURES / "LUZON_RP251230_022_004.PRT")
    assert main([known, ok]) == 0
    assert "GTOCNL" in capsys.readouterr().out


def test_main_unknown_is_status_1(tmp_path: Path) -> None:
    prt = tmp_path / "X.PRT"
    prt.write_text(
        " *** SR NOSUCH: SOMETHING NEW\n"
        " 01-JAN-2026  00:00:00  00:00:01  00:00:00  ERR GPSEST    ERROR IN MAIN PROGRAM\n"
    )
    assert main([str(prt)]) == 1


def test_main_bad_knowledge_base_is_status_2(tmp_path: Path) -> None:
    bad = tmp_path / "kb.yaml"
    bad.write_text("entries:\n" + _ROW.replace("scope: configuration", "scope: x"))
    assert main(["--kb", str(bad), str(FIXTURES / "LUZON_RP251230_022_004.PRT")]) == 2
