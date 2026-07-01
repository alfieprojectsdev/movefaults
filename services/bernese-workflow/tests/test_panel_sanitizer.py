"""Tests for panel_sanitizer — fixtures are verbatim PGN_WK panel lines (RH-004)."""
from __future__ import annotations

from bernese_workflow.panel_sanitizer import (
    find_dangling_waits,
    sanitize_panel_text,
)

# ---------------------------------------------------------------------------
# Separator conversion (safe path)
# ---------------------------------------------------------------------------

def test_mixed_separator_path_converted():
    line = r'SESSION_TABLE 1  "${P}/SOB\GEN\SESSIONS.SES"'
    res = sanitize_panel_text(line)
    assert res.changed is True
    assert '"${P}/SOB/GEN/SESSIONS.SES"' in res.text
    assert "\\" not in res.text
    assert res.ok is True  # separator fix alone → no residual warning


def test_no_backslash_is_unchanged():
    line = 'RADIO 1  "SAVED"'
    res = sanitize_panel_text(line)
    assert res.changed is False
    assert res.text == line
    assert res.ok is True


# ---------------------------------------------------------------------------
# Foreign absolute path — flagged, NOT converted
# ---------------------------------------------------------------------------

def test_drive_letter_path_flagged_not_converted():
    line = r'  "U" "C:\Bernese\GPSUSER54\"'
    res = sanitize_panel_text(line)
    # The backslashes in a pure drive path must survive (converting them would
    # produce a still-broken C:/Bernese/... and hide the real remap needed).
    assert r"C:\Bernese\GPSUSER54" in res.text
    assert res.changed is False
    assert res.ok is False
    kinds = {w.kind for w in res.warnings}
    assert "foreign_abs_path" in kinds


def test_double_backslash_drive_path_flagged():
    line = r'  "MODEL" "C:\Bernese\BERN54\\GLOBAL\MODEL"'
    res = sanitize_panel_text(line)
    assert any(w.kind == "foreign_abs_path" for w in res.warnings)
    assert res.changed is False


# ---------------------------------------------------------------------------
# Hardcoded session / date literals — flagged
# ---------------------------------------------------------------------------

def test_hardcoded_session_stamp_flagged_and_separators_still_fixed():
    # This real line has BOTH: a mixed path (convert) and a frozen session (flag).
    line = r'  "${P}/SOB\SOL\$(FIN)_20261030.NQ0"'
    res = sanitize_panel_text(line)
    assert '"${P}/SOB/SOL/$(FIN)_20261030.NQ0"' in res.text  # separators fixed
    assert res.changed is True
    assert any(w.kind == "hardcoded_session" for w in res.warnings)  # still flagged


def test_hardcoded_date_directives_flagged():
    for line in ('SESSION_YEAR 1  "2026"', 'STADAT 1  "2026 04 14"', 'YR4_INFO 1  "2026"'):
        res = sanitize_panel_text(line)
        assert any(w.kind == "hardcoded_date" for w in res.warnings), line


def test_comment_and_widget_lines_not_flagged():
    text = (
        "#   Maximum number of parameters in combined NEQ> %%%%%% <   # MAXPAR\n"
        "  ## widget = spinbox; range = 500 20000 500\n"
        "# BEGIN_PANEL NO_CONDITION #########################\n"
    )
    res = sanitize_panel_text(text)
    assert res.warnings == []
    assert res.ok is True


def test_trailing_newline_preserved():
    assert sanitize_panel_text("A 1  \"x\"\n").text.endswith("\n")
    assert not sanitize_panel_text("A 1  \"x\"").text.endswith("\n")


# ---------------------------------------------------------------------------
# Dangling WAIT detection
# ---------------------------------------------------------------------------

_CLEAN_PCF = """\
001 SATMRK    PGN_GEN   CPU=ANY
002 ATX2PCV   PGN_GEN   CPU=ANY; WAIT=001
005 CRDMERGE  PGN_GEN   CPU=ANY; WAIT=001 002
"""


def test_no_dangling_waits_on_clean_pcf():
    assert find_dangling_waits(_CLEAN_PCF) == []


def test_dangling_wait_detected():
    pcf = _CLEAN_PCF + "099 DUMMY     NO_OPT    CPU=ANY; WAIT=001 522\n"
    dangling = find_dangling_waits(pcf)
    assert len(dangling) == 1
    assert dangling[0].pid == "522"


def test_multiple_dangling_pids_in_one_wait():
    pcf = "001 A PGN_GEN CPU=ANY\n099 B NO_OPT CPU=ANY; WAIT=001 777 888\n"
    pids = {d.pid for d in find_dangling_waits(pcf)}
    assert pids == {"777", "888"}
