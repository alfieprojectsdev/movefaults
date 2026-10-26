"""Plan phase: which days run, in which blocks, and what is checked first.

The PHREF test at the bottom is the cutover plan's exit check for step E: the
plan derived from the datapool gives the same blocks and exclusions as
run_phref_year.sh, whose list was kept by hand. It needs gps3's datapool and
skips elsewhere; everything above it is synthetic.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bernese_workflow import run_plan
from bernese_workflow.run_plan import (
    addneq2_maxpar,
    build_plan,
    check_pcf,
    contiguous_blocks,
    fin_present,
    fix_stations,
    format_plan,
    pcf_option_dirs,
    pcf_variable,
)
from pogf_geodetic_suite.qc.completeness import Coverage

REPO = Path(__file__).resolve().parents[3]
REFS = ("AIRA", "DAEJ", "PIMO", "DARW")


def _coverage(year: int, by_day: dict[int, set[str]]) -> Coverage:
    cov = Coverage(year=year)
    for doy, stations in by_day.items():
        for s in stations:
            cov.by_day[doy].add(s)
            cov.by_station[s].add(doy)
    return cov


def _full(year: int = 2025) -> dict[int, set[str]]:
    """Every day of the year has three references and two local stations."""
    return {d: {"AIRA", "DAEJ", "PIMO", "BOST", "CRAN"} for d in range(1, 366)}


def test_contiguous_blocks():
    assert contiguous_blocks([]) == []
    assert contiguous_blocks([5, 1, 2, 3, 7, 6, 10]) == [(1, 3), (5, 7), (10, 10)]


def test_short_days_are_excluded_with_the_stations_present():
    days = _full()
    days[58] = {"DARW", "PIMO", "BOST"}
    days[345] = {"DAEJ", "PIMO"}
    del days[200]  # no data at all is as unprocessable as a short day
    plan = build_plan(
        2025, 1, 365, done=lambda d: False, coverage=_coverage(2025, days), references=REFS
    )
    short = {e.doy: e.detail for e in plan.excluded if e.reason == "short"}
    assert short == {
        58: "2 reference station(s): DARW PIMO",
        200: "0 reference station(s)",
        345: "2 reference station(s): DAEJ PIMO",
    }
    assert plan.blocks == [(1, 57), (59, 199), (201, 344), (346, 365)]
    assert plan.ok


def test_solved_wins_over_short_and_listed_needs_a_reason():
    days = _full()
    days[10] = {"PIMO"}
    plan = build_plan(
        2025,
        1,
        20,
        done=lambda d: d in (10, 11),
        coverage=_coverage(2025, days),
        references=REFS,
        listed={12: "receiver swap"},
    )
    assert [(e.doy, e.reason, e.detail) for e in plan.excluded] == [
        (10, "solved", ""),
        (11, "solved", ""),
        (12, "listed", "receiver swap"),
    ]
    assert plan.blocks == [(1, 9), (13, 20)]


def test_a_plan_that_never_saw_the_data_is_not_clean():
    plan = build_plan(2025, 1, 3, done=lambda d: False, coverage=None, references=REFS)
    assert plan.todo == [1, 2, 3]
    assert not plan.ok

    plan = build_plan(
        2025, 1, 3, done=lambda d: False, coverage=_coverage(2025, _full()), references=()
    )
    assert not plan.ok


def test_range_is_checked_against_the_year():
    with pytest.raises(ValueError):
        build_plan(2025, 1, 366, done=lambda d: False, coverage=None, references=REFS)
    build_plan(2024, 1, 366, done=lambda d: False, coverage=None, references=REFS)


def test_busiest_day_runs_first_and_ties_go_to_the_earliest():
    days = _full()
    days[30] |= {"X1", "X2"}
    days[40] |= {"X1", "X2"}
    plan = build_plan(
        2025, 25, 45, done=lambda d: d == 35, coverage=_coverage(2025, days), references=REFS
    )
    assert plan.busiest == 30
    assert plan.run_order[:2] == [30, 25]
    assert sorted(plan.run_order) == plan.todo
    assert "preflight: DOY 030 first, the busiest day (7 stations)" in format_plan(plan)


def test_busiest_is_never_a_solved_day():
    days = _full()
    days[30] |= {"X1", "X2", "X3"}
    plan = build_plan(
        2025, 25, 35, done=lambda d: d == 30, coverage=_coverage(2025, days), references=REFS
    )
    assert plan.busiest != 30


def test_pcf_variable_reads_both_dialects():
    pcf54 = (REPO / "config/bernese/gpsuser/PCF/PAGENET_DLY.PCF").read_text()
    pcf52 = (REPO / "config/bernese/gpsuser52-luzon/PCF/PHIVOL_REL.PCF").read_text()
    assert pcf_variable(pcf54, "V_REFINF") == "IGS20"
    assert pcf_variable(pcf52, "V_REFINF") == "IGS14"
    assert pcf_variable(pcf54, "V_ATLINF") == ""  # set, and empty
    assert pcf_variable(pcf54, "V_NOSUCH") is None


def test_fix_stations_skips_the_header():
    text = (
        "IGS20: list of stations with coordinates and velocities\n"
        "-----\n\nStation name\n****************\n"
        "AIRA 21742S001\nDAEJ 23902M002\n"
    )
    assert fix_stations(text) == {"AIRA", "DAEJ"}


def test_maxpar_of_every_addneq2_panel_the_pcf_uses(tmp_path: Path):
    pcf = (
        "PID  SCRIPT    OPT_DIR   PARAMETERS\n"
        "001  R2S_COP   R2S_GEN   CPU=ANY\n"
        "401  ADDNEQ2   R2S_FIN   CPU=ANY; WAIT=001\n"
        "402  HELMCHK   R2S_FIN   CPU=ANY; WAIT=401\n"
        "VARIABLE         DEFAULT           PARAMETERS\n"
        "V_X            = 1;  DESCRIPTION=not a process\n"
    )
    assert pcf_option_dirs(pcf) == ["R2S_GEN", "R2S_FIN"]
    (tmp_path / "R2S_FIN").mkdir()
    (tmp_path / "R2S_FIN" / "ADDNEQ2.INP").write_text('MSG_MAXPAR 1 "help"\nMAXPAR 1  "6000"\n')
    (tmp_path / "R2S_GEN").mkdir()
    (tmp_path / "R2S_GEN" / "ADDNEQ2.INP").write_text("no maxpar here\n")
    assert addneq2_maxpar(tmp_path, pcf_option_dirs(pcf)) == {"R2S_GEN": None, "R2S_FIN": 6000}


def test_check_pcf_reports_dangling_references():
    pcf = (
        "001  R2S_COP   R2S_GEN   CPU=ANY\n"
        "002  R2S_X     R2S_GEN   CPU=ANY; WAIT=003; NEXTJOB=009\n"
    )
    problems = check_pcf(pcf)
    assert any("WAIT names 003" in p for p in problems)
    assert any("NEXTJOB names 009" in p for p in problems)
    assert check_pcf("001  R2S_COP  R2S_GEN  CPU=ANY\n") == []


def test_fin_present_matches_any_fin_file(tmp_path: Path):
    assert not fin_present(tmp_path, 2025, 2)
    (tmp_path / "FIN_20250020.SNX.gz").write_bytes(b"x")
    assert fin_present(tmp_path, 2025, 2)
    assert not fin_present(tmp_path, 2025, 20)


_PHREF_DATA = Path("/home/gps3/GPSDATA/DATAPOOL/PHREF")
_IGS20_FIX = Path("/home/gps3/GPSDATA/DATAPOOL/REF54/IGS20.FIX")


@pytest.mark.skipif(
    not _PHREF_DATA.is_dir() or not _IGS20_FIX.is_file(), reason="needs gps3's datapool"
)
def test_phref_2025_matches_run_phref_year_sh():
    """Same blocks and exclusions as run_phref_year.sh --plan with nothing solved.

    That script's PHREF_EXCLUDE="058 059 060 061 345" was kept by hand; here it
    is derived from IGS20.FIX and the RINEX in $D/PHREF. Its blocks on an empty
    SOL/ are 1:57 62:344 346:365.
    """
    from pogf_geodetic_suite.qc.completeness import scan

    plan = build_plan(
        2025,
        1,
        365,
        done=lambda d: False,
        coverage=scan(_PHREF_DATA, 2025),
        references=fix_stations(_IGS20_FIX.read_text(errors="replace")),
    )
    assert [e.doy for e in plan.excluded] == [58, 59, 60, 61, 345]
    assert plan.blocks == [(1, 57), (62, 344), (346, 365)]
    # docs/bernese_maxpar_limit.md: "The busiest days of the year carry 41."
    assert plan.station_counts[plan.busiest] == 41


# --- where the data and the results are: the PCF says, not the campaign name ---

_ENV = {"D": "/data/DATAPOOL", "S": "/data/SAVEDISK", "P": "/data/CAMPAIGN54"}


def test_the_datapool_dir_comes_from_v_rnxdir_not_the_campaign_name():
    """LZFLT reads LUZON's RINEX: its V_RNXDIR is ${D}/LUZON."""
    pcf = "V_RNXDIR = ${D}/LUZON;       DESCRIPTION=Directory with the RINEX files\n"
    path, source = run_plan.rinex_dir(pcf, _ENV, 2025, fallback=Path("/data/DATAPOOL/LZFLT"))
    assert path == Path("/data/DATAPOOL/LUZON") and "V_RNXDIR" in source


def test_the_result_dir_comes_from_v_result_with_the_year_expanded():
    """EXAMPLE archives to ${S}/RNX2SNX/$Y+0, not ${S}/EXAMPLE."""
    pcf = "V_RESULT = ${S}/RNX2SNX/$Y+0;  DESCRIPTION=Directory name for the RNX2SNX results\n"
    path, source = run_plan.result_dir(pcf, _ENV, 2023, fallback=Path("/x"))
    assert path == Path("/data/SAVEDISK/RNX2SNX/2023") and "V_RESULT" in source


def test_a_variable_it_cannot_expand_falls_back_and_says_so():
    pcf = "V_RESULT = ${S}/PHREF/$Y-1;  DESCRIPTION=x\n"
    path, source = run_plan.result_dir(pcf, _ENV, 2025, fallback=Path("/data/SAVEDISK/PHREF/2025"))
    assert path == Path("/data/SAVEDISK/PHREF/2025") and "fallback" in source
    path, source = run_plan.rinex_dir("", _ENV, 2025, fallback=Path("/data/DATAPOOL/PHREF"))
    assert path == Path("/data/DATAPOOL/PHREF") and "fallback" in source
