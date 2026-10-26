"""Tests for panel_sanitizer — fixtures are verbatim PGN_WK panel lines (RH-004)."""
from __future__ import annotations

from pathlib import Path

import pytest
from bernese_workflow.panel_sanitizer import (
    find_dangling_jumps,
    find_dangling_waits,
    provision_opt_dir,
    sanitize_panel_text,
    set_addneq2_maxpar,
)

# ---------------------------------------------------------------------------
# Separator conversion (safe path)
# ---------------------------------------------------------------------------

def test_mixed_separator_path_converted():
    # Campaign-agnostic on purpose. This fixture previously used "${P}/SOB",
    # the instructor's demo campaign — a genuine hardcoded-campaign hazard
    # that went unnoticed because no check existed for it. Using it here made
    # a panel with two problems the example of a panel with one.
    line = r'SESSION_TABLE 1  "${P}/${V_CAMP}\GEN\SESSIONS.SES"'
    res = sanitize_panel_text(line)
    assert res.changed is True
    assert '"${P}/${V_CAMP}/GEN/SESSIONS.SES"' in res.text
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


# ---------------------------------------------------------------------------
# set_addneq2_maxpar (readiness task B)
# ---------------------------------------------------------------------------

def test_set_maxpar_rewrites_value_only():
    text = 'MAXPAR 1  "5000"\nMSG_MAXPAR 1  "Maximum number of parameters"\n'
    out, changed = set_addneq2_maxpar(text, 1580)
    assert changed is True
    assert 'MAXPAR 1  "1580"' in out
    assert 'MSG_MAXPAR 1  "Maximum number of parameters"' in out  # help text untouched


def test_set_maxpar_no_line_is_noop():
    out, changed = set_addneq2_maxpar('SOMETHING 1  "1"\n', 1580)
    assert changed is False


def test_set_maxpar_rejects_nonpositive():
    with pytest.raises(ValueError, match="MAXPAR"):
        set_addneq2_maxpar('MAXPAR 1  "5000"\n', 0)


# ---------------------------------------------------------------------------
# provision_opt_dir — wire sanitizer into the copy-to-$U path
# ---------------------------------------------------------------------------

def test_provision_sanitizes_inp_sizes_maxpar_and_copies_scripts(tmp_path):
    gold = tmp_path / "gold"
    src = gold / "PGN_WK"
    src.mkdir(parents=True)
    # Clean panel with mixed separators (safe to convert) + a MAXPAR line.
    (src / "ADDNEQ2.INP").write_text(
        'SESSION_TABLE 1  "${P}/${V_CAMP}\\GEN\\SESSIONS.SES"\nMAXPAR 1  "5000"\n'
    )
    # A Perl script must be copied verbatim (backslashes preserved).
    (src / "helper.pl").write_text('$x =~ s/a\\tb/c/;\n')

    dest = tmp_path / "GPSUSER" / "OPT"
    report = provision_opt_dir(gold, dest, n_stations=270)  # provision from the tree root

    assert report.ok is True
    addneq2 = (dest / "PGN_WK" / "ADDNEQ2.INP").read_text()
    assert '"${P}/${V_CAMP}/GEN/SESSIONS.SES"' in addneq2   # separators fixed
    # MAXPAR is a CEILING and is raise-only: the panel already carries 5000,
    # which exceeds the computed 1580 (270*4+500), so it is LEFT ALONE. Lowering
    # it would undo a value someone raised deliberately against an observed
    # ADDNEQ2 overflow — exactly what the real PAGENET panel's 10000 records.
    assert 'MAXPAR 1  "5000"' in addneq2
    assert (dest / "PGN_WK" / "helper.pl").read_text() == '$x =~ s/a\\tb/c/;\n'  # verbatim


def test_provision_strict_refuses_dirty_panel(tmp_path):
    src = tmp_path / "gold"
    src.mkdir()
    (src / "ADDNEQ2.INP").write_text('  "U" "C:\\Bernese\\GPSUSER54\\"\n')  # drive path

    dest = tmp_path / "OPT"
    with pytest.raises(ValueError, match="unresolved hazards"):
        provision_opt_dir(src, dest, strict=True)


def test_provision_strict_is_atomic_no_partial_write(tmp_path):
    """A clean panel ordered before a dirty one must NOT be written when strict aborts."""
    src = tmp_path / "gold"
    src.mkdir()
    (src / "AAA_clean.INP").write_text('RADIO 1  "SAVED"\n')          # sorts first, clean
    (src / "ZZZ_dirty.INP").write_text('SESSION_YEAR 1  "2026"\n')    # sorts last, dirty

    dest = tmp_path / "OPT"
    with pytest.raises(ValueError, match="unresolved hazards"):
        provision_opt_dir(src, dest, strict=True)
    assert not (dest / "AAA_clean.INP").exists()  # nothing written on abort
    assert not dest.exists() or list(dest.rglob("*.INP")) == []


def test_provision_nonstrict_collects_warnings(tmp_path):
    src = tmp_path / "gold"
    src.mkdir()
    (src / "ADDNEQ2.INP").write_text('SESSION_YEAR 1  "2026"\n')  # hardcoded date

    dest = tmp_path / "OPT"
    report = provision_opt_dir(src, dest, strict=False)
    assert report.ok is False
    assert "ADDNEQ2.INP" in report.warnings
    assert (dest / "ADDNEQ2.INP").exists()  # non-strict still writes


def test_maxpar_is_raised_when_the_panel_is_below_the_computed_value(tmp_path):
    """The heuristic still applies upward — an undersized panel gets sized up."""
    gold, dest = tmp_path / "gold", tmp_path / "U"
    (gold / "PGN_WK").mkdir(parents=True)
    (gold / "PGN_WK" / "ADDNEQ2.INP").write_text('MAXPAR 1  "1000"\n', encoding="ascii")

    provision_opt_dir(gold, dest, n_stations=270)

    assert 'MAXPAR 1  "1580"' in (dest / "PGN_WK" / "ADDNEQ2.INP").read_text()


def test_maxpar_is_never_lowered(tmp_path):
    """Regression: a computed value below the panel's must not overwrite it.

    PR #65's real PAGENET ADDNEQ2.INP ships MAXPAR "10000", raised after an
    actual parameter overflow during the training week and flagged in
    PROVENANCE.md as not to be reverted. compute_maxpar(72) is 1000, so the
    pre-2026-08-04 behaviour would have silently undone that fix during routine
    provisioning.
    """
    gold, dest = tmp_path / "gold", tmp_path / "U"
    (gold / "PGN_WK").mkdir(parents=True)
    (gold / "PGN_WK" / "ADDNEQ2.INP").write_text('MAXPAR 1  "10000"\n', encoding="ascii")

    provision_opt_dir(gold, dest, n_stations=72)

    assert 'MAXPAR 1  "10000"' in (dest / "PGN_WK" / "ADDNEQ2.INP").read_text()


def test_dry_run_writes_nothing_at_all(tmp_path):
    """Regression: provision_opt_dir had no dry-run mode, so callers claiming one lied.

    scripts/provision_gpsuser.py printed "DRY RUN — nothing will be written" and
    then wrote every panel, because there was no way to ask it not to.
    """
    gold, dest = tmp_path / "gold", tmp_path / "U"
    (gold / "PGN_WK").mkdir(parents=True)
    (gold / "PGN_WK" / "ADDNEQ2.INP").write_text('MAXPAR 1  "1000"\n', encoding="ascii")
    (gold / "PGN_WK" / "helper.pl").write_text("print 1;\n", encoding="ascii")

    report = provision_opt_dir(gold, dest, n_stations=270, dry_run=True)

    assert report.written, "the plan should still be reported"
    assert not dest.exists(), "dry run must not create the destination tree"
    assert not (dest / "PGN_WK" / "ADDNEQ2.INP").exists()


def test_hardcoded_campaign_under_P_is_flagged(tmp_path):
    """`${P}/<name>` pins a panel to one campaign and must not pass silently.

    The real PGN_WK/MENU.INP arrived with `ACTIVE_CAMPAIGN 1 "${P}/SOB"` and a
    SESSION_TABLE under the same path — SOB being the instructor's demo campaign,
    a directory that does not exist on the target server. Both lines previously
    sanitized to `changed=True, warnings=0`: the backslashes were converted and
    the panel reported clean, so the foreign campaign reached $U silently.
    """
    result = sanitize_panel_text(
        'ACTIVE_CAMPAIGN 1  "${P}/SOB"\n'
        'SESSION_TABLE 1  "${P}/SOB\\GEN\\SESSIONS.SES"\n'
    )
    kinds = [w.kind for w in result.warnings]
    assert kinds.count("hardcoded_campaign") == 2
    assert result.ok is False


def test_campaign_variables_are_not_flagged(tmp_path):
    """A panel referring to $P generically, or via a variable, is fine."""
    result = sanitize_panel_text(
        'DATAPOOL 1  "${P}"\n'
        'CAMPAIGN 1  "${P}/${V_CAMP}"\n'
        'OTHER 1  "${D}/PGN"\n'
    )
    assert not [w for w in result.warnings if w.kind == "hardcoded_campaign"]


# --- PCF dialects: find_dangling_waits must understand both -----------------

_PCF_COLUMNAR = """PID SCRIPT   OPT_DIR  CAMPAIGN CPU      F WAIT FOR....
001 R2S_COP  NO_OPT            ANY      1 000
101 POLUPD   R2S_GEN           ANY      1 001
113 ORBGEN   R2S_GEN           ANY      1 101 111
599 DUMMY    NO_OPT            ANY      1 113 522
"""

_PCF_KEYWORD = """# PID  SCRIPT    OPT_DIR   PARAMETERS
001  R2S_COP   NO_OPT    CPU=ANY; WAIT=000
101  POLUPD    R2S_GEN   CPU=ANY; WAIT=001
"""


def test_dangling_waits_detected_in_columnar_dialect():
    """The 5.2 dialect has no `WAIT=` keyword — the WAIT list is a bare column.

    Regression for 2026-08-05: the detector matched only `WAIT=`, so against a
    PHIVOLCS 5.2 PCF it found zero WAITs, reported zero dangling, and returned a
    clean bill having inspected nothing. That report signed off LUZON_DLY.PCF,
    which then failed on its first process with "Invalid PID: 000". A checker
    that silently does not understand its input converts "unverified" into
    "verified", which is worse than having no checker.
    """
    d = find_dangling_waits(_PCF_COLUMNAR)
    pids = sorted(x.pid for x in d)
    # 000 and 111 and 522 are referenced but never defined; 001/101/113 are.
    assert pids == ["000", "111", "522"], pids


def test_dangling_waits_still_detected_in_keyword_dialect():
    """The 5.4 dialect must keep working — 000 is referenced, never defined."""
    d = find_dangling_waits(_PCF_KEYWORD)
    assert [x.pid for x in d] == ["000"]


def test_clean_columnar_pcf_reports_nothing():
    """And a well-formed columnar PCF must not produce false positives."""
    clean = """PID SCRIPT   OPT_DIR  CAMPAIGN CPU      F WAIT FOR....
001 R2S_COP  NO_OPT            ANY      1
101 POLUPD   R2S_GEN           ANY      1 001
599 DUMMY    NO_OPT            ANY      1 001 101
"""
    assert find_dangling_waits(clean) == []


def test_variable_table_rows_are_not_read_as_dependencies():
    """A PCF's variable and parameter tables must not be parsed as process rows."""
    with_tables = _PCF_COLUMNAR + """
PID USER         PASSWORD PARAM1   PARAM2
201                       $201
VARIABLE DESCRIPTION                              DEFAULT
V_CLU    Maximum number of stations per cluster    10
"""
    pids = sorted(x.pid for x in find_dangling_waits(with_tables))
    assert pids == ["000", "111", "522"], pids


# --- find_dangling_jumps: NEXTJOB and PARALLEL targets, both dialects -------

_REPO = Path(__file__).resolve().parents[3]


def test_dangling_jumps_in_keyword_dialect():
    pcf = """# PID  SCRIPT    OPT_DIR   PARAMETERS
011  RNX_COP   R2S_GEN   CPU=ANY; WAIT=001;  NEXTJOB= 099 999
021  CCRNXOAP  R2S_GEN   CPU=ANY; WAIT=011
022  CCRNXO_P  R2S_GEN   CPU=ANY; WAIT=021;  PARALLEL=020
099  DUMMY     R2S_GEN   CPU=ANY; WAIT=022
"""
    r = find_dangling_jumps(pcf)
    assert r.checked == 3
    assert [(d.line, d.keyword, d.pid) for d in r.dangling] == [
        (2, "NEXTJOB", "999"),
        (4, "PARALLEL", "020"),
    ]


def test_dangling_jumps_in_the_52_special_actions_table():
    """5.2 keeps jumps in a second table; PARALLEL names its source as $PID."""
    pcf = _PCF_COLUMNAR + """
PID USER         PASSWORD PARAM1   PARAM2
113                       PARALLEL $111
599                       NEXTJOB  101 700
"""
    r = find_dangling_jumps(pcf)
    assert r.checked == 5          # 3 targets + the 2 rows' own PIDs (113, 599)
    assert [(d.keyword, d.pid) for d in r.dangling] == [("PARALLEL", "111"), ("NEXTJOB", "700")]


def test_special_actions_rows_do_not_define_processes():
    """`111  $111` in the special-actions table is not process 111.

    If process 111 is deleted but its parameter row is left behind, a jump to
    it must still be reported -- and so must the WAIT on it.
    """
    pcf = _PCF_COLUMNAR + """
PID USER         PASSWORD PARAM1   PARAM2
111                       $111
113                       PARALLEL $111
"""
    assert [d.pid for d in find_dangling_jumps(pcf).dangling] == ["111"]
    assert "111" in {d.pid for d in find_dangling_waits(pcf)}


def test_special_action_on_an_undefined_process_is_dangling():
    pcf = _PCF_COLUMNAR + """
PID USER         PASSWORD PARAM1   PARAM2
514                       NEXTJOB  101
"""
    r = find_dangling_jumps(pcf)
    assert [(d.keyword, d.pid) for d in r.dangling] == [("NEXTJOB", "514")]


@pytest.mark.parametrize("target", ["31", "3011", "$V_X"])
def test_malformed_jump_targets_are_reported_not_skipped(target):
    """A target that is not a three-digit PID is a broken jump, not a non-reference."""
    pcf = f"001  R2S_COP  NO_OPT  CPU=ANY; NEXTJOB={target}\n"
    r = find_dangling_jumps(pcf)
    assert r.checked == 1
    assert [d.pid for d in r.dangling] == [target]   # verbatim, as findPID reads it


def test_placeholder_and_empty_jump_lists_are_not_references():
    """Stock 5.4 PCFs use `NEXTJOB= _ 901` and a bare `NEXTJOB=` (GOTO rows).

    BSW skips `_` as an empty slot and accepts an empty list, so neither may be
    reported; 901 is still checked.
    """
    pcf = (
        "901  DUMMY    NO_OPT  CPU=ANY\n"
        "283  MPRXTR   PPP_GE2 CPU=ANY; WAIT=901;  NEXTJOB= _ 901\n"
        "429  GOTO     NO_OPT  CPU=ANY; WAIT=901;  NEXTJOB=\n"
    )
    r = find_dangling_jumps(pcf)
    assert r.checked == 1
    assert r.dangling == []


def test_special_action_with_user_column_filled_is_read():
    pcf = _PCF_COLUMNAR + """
PID USER         PASSWORD PARAM1   PARAM2
113 someone      secret   PARALLEL $700
"""
    assert [d.pid for d in find_dangling_jumps(pcf).dangling] == ["700"]


def test_jump_check_reports_what_it_inspected():
    """No jumps at all is checked == 0, which a caller must not read as clean."""
    r = find_dangling_jumps(_PCF_KEYWORD)
    assert r.checked == 0 and r.dangling == []


def test_commented_jumps_are_ignored():
    pcf = "# 011  RNX_COP  R2S_GEN  CPU=ANY; NEXTJOB= 999\n001  R2S_COP  NO_OPT  CPU=ANY\n"
    assert find_dangling_jumps(pcf).checked == 0


@pytest.mark.parametrize(
    ("pcf", "references"),
    [
        ("config/bernese/gpsuser52-luzon/PCF/PHIVOL_REL.PCF", 24),  # 12 rows + 12 targets
        ("config/bernese/gpsuser/PCF/PAGENET_DLY.PCF", 12),
    ],
)
def test_real_pcfs_have_no_dangling_jumps(pcf, references):
    """The production 5.2 PCF and a 5.4 PCF: every reference read, none dangling."""
    r = find_dangling_jumps((_REPO / pcf).read_text(errors="replace"))
    assert r.checked == references
    assert r.dangling == []


# --- find_dangling_jumps: as BSW 5.4 reads them (P_BPE.f90) -----------------
#
# 5.2 special-action rows are fixed width, `(I3,1X,A12,1X,A8,9(1X,A8))`: the
# keyword is only a keyword in PARAM1 (columns 27-34). A 5.2 `PARALLEL $201`
# does not name PID 201: BSW looks for the job whose PARAM1 is the label `$201`
# (pcf_updateParalleJob_V0), among the parameter rows it has already read.

_PCF_52_PROCS = """PID SCRIPT   OPT_DIR  CAMPAIGN CPU      F WAIT FOR....
201 RNXSMTAP R2S_GEN           ANY      1
211 RNXSMT_H R2S_GEN           ANY      1 201
PID USER         PASSWORD PARAM1   PARAM2
"""


def test_52_parallel_without_its_label_row_is_dangling():
    """PID 201 exists, but no row gives it PARAM1 `$201`: BSW stops at load."""
    pcf = _PCF_52_PROCS + "211                       PARALLEL $201\n"
    assert [(d.keyword, d.pid) for d in find_dangling_jumps(pcf).dangling] == [("PARALLEL", "201")]


def test_52_parallel_before_its_label_row_is_dangling():
    """The label is matched against rows already read, so order matters."""
    pcf = _PCF_52_PROCS + (
        "211                       PARALLEL $201\n"
        "201                       $201\n"
    )
    assert [(d.keyword, d.pid) for d in find_dangling_jumps(pcf).dangling] == [("PARALLEL", "201")]


def test_52_parallel_reads_param2_only():
    """BSW stops reading a PARALLEL row after PARAM2; later columns are not targets."""
    pcf = _PCF_52_PROCS + (
        "201                       $201\n"
        "211                       PARALLEL $201     V_X\n"
    )
    r = find_dangling_jumps(pcf)
    assert r.dangling == [] and r.checked == 2


def test_52_keyword_outside_param1_is_reported_not_skipped():
    """A misaligned row is not a jump to BSW; it must not pass as a clean one."""
    pcf = _PCF_52_PROCS + (
        "201                       $201\n"
        "211 PARALLEL $201\n"
    )
    assert [d.keyword for d in find_dangling_jumps(pcf).dangling] == ["PARALLEL"]


@pytest.mark.parametrize("line", [
    "331  RES_SUM   R2S_GEN   CPU=ANY; NEXTJOB=$301",
    "322  GPSEDT_P  R2S_EDT   CPU=ANY; PARALLEL=$301",
])
def test_keyword_dollar_target_is_not_a_pid(line):
    """findPID compares the token verbatim: `$301` is not PID 301."""
    pcf = "301  INIT_BSL  NO_OPT    CPU=ANY\n" + line + "\n"
    assert [d.pid for d in find_dangling_jumps(pcf).dangling] == ["$301"]


def test_keyword_parallel_takes_exactly_one_pid():
    """`PARALLEL=301 302` is looked up as the single PID '301 302' and fails."""
    pcf = (
        "301  INIT_BSL  NO_OPT    CPU=ANY\n"
        "302  SNGDIF    R2S_GEN   CPU=ANY\n"
        "322  GPSEDT_P  R2S_EDT   CPU=ANY; PARALLEL=301 302\n"
    )
    assert [d.pid for d in find_dangling_jumps(pcf).dangling] == ["301 302"]


def test_variable_table_is_not_read_for_jumps():
    pcf = (
        "001  R2S_COP   NO_OPT    CPU=ANY\n"
        "VARIABLE         DEFAULT           PARAMETERS\n"
        "V_X            = ;                 DESCRIPTION=was NEXTJOB=999\n"
    )
    r = find_dangling_jumps(pcf)
    assert r.dangling == [] and r.checked == 0
