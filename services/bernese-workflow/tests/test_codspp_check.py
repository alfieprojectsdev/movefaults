"""The CODSPP check, on summaries shaped like the CODXTR section of a real PRC."""

from __future__ import annotations

from pathlib import Path

import pytest
from bernese_workflow import codspp_check as cc

YEAR = 2023

# Copied from PHSUP 2023 DOY 029 (superseded), the day the misdating was found.
CODXTR = """\
 *** SR cdcomp: NOT ENOUGH OBSERVATIONS
 ### PG CODXTR: NO RESULTS ARE AVAILABLE FOR STATION: ORAS ORAS
                FILE: ${P}/PSU230290/OBS/ORAS0290.CZO
 ### PG CODXTR: NO RESULTS ARE AVAILABLE FOR STATION: ORAS ORAS
                FILE: ${P}/PSU230290/OBS/ORAS0290.CZO
 ### PG CODXTR: NUMBER OF BAD OBS LARGER THAN 50% FOR STATION: ISAB ISAB
                FILE   : ${P}/PSU230290/OBS/ISAB0290.CZO
                BAD OBS:    57.10 %
  77 FILES, MAX. RMS:******** M    FOR STATION: ISAB ISAB
"""


def _write(year_dir: Path, doy: int, prc: str | None, estimated: list[str] | None) -> None:
    if prc is not None:
        (year_dir / "OUT").mkdir(parents=True, exist_ok=True)
        (year_dir / "OUT" / f"R2S_{YEAR}{doy:03d}0.PRC").write_text(prc)
    if estimated is not None:
        lines = ["title", "-" * 80, "LOCAL GEODETIC DATUM: IGS20", "", "NUM  STATION NAME", ""]
        for i, name in enumerate(estimated):
            lines.append(
                f"{i + 1:3d}  {name} {name}  -3214233.54976  5272149.55563  1595513.41369    A"
            )
        # ISAB and ORAS carried along, as CODSPP's rejection leaves them: no flag.
        lines.append(" 98  ISAB ISAB        -3000000.00000  5000000.00000  1600000.00000")
        lines.append(" 99  ORAS ORAS        -3000001.00000  5000001.00000  1600001.00000")
        (year_dir / "STA").mkdir(parents=True, exist_ok=True)
        (year_dir / "STA" / f"FIN_{YEAR}{doy:03d}0.CRD").write_text("\n".join(lines) + "\n")


@pytest.fixture
def year_dir(tmp_path: Path) -> Path:
    return tmp_path / "PHSUP" / str(YEAR)


def test_reads_both_messages_and_the_bad_share(tmp_path: Path) -> None:
    prc = tmp_path / "R2S.PRC"
    prc.write_text("header\n" + CODXTR + "PART 4\n")
    assert cc.read_rejections(prc) == {
        "ORAS": (cc.NO_RESULTS, None),
        "ISAB": (cc.BAD_OBS, 57.10),
    }


def test_no_results_outranks_bad_obs_in_either_order(tmp_path: Path) -> None:
    prc = tmp_path / "R2S.PRC"
    bad = " ### PG CODXTR: NUMBER OF BAD OBS LARGER THAN 50% FOR STATION: BATU BATU\n"
    none = " ### PG CODXTR: NO RESULTS ARE AVAILABLE FOR STATION: BATU BATU\n"
    for text in (bad + "   BAD OBS:  99.85 %\n" + none, none + bad + "   BAD OBS:  99.85 %\n"):
        prc.write_text(text)
        assert cc.read_rejections(prc) == {"BATU": (cc.NO_RESULTS, None)}


def test_a_clean_summary_rejects_nobody(tmp_path: Path) -> None:
    prc = tmp_path / "R2S.PRC"
    prc.write_text("  77 FILES, MAX. RMS:    3.12 M    FOR STATION: PTAG 22006M005\n")
    assert cc.read_rejections(prc) == {}


def test_a_year_reports_each_station_with_its_days_and_whether_it_was_dropped(
    year_dir: Path,
) -> None:
    for doy in (1, 2, 3, 5):
        _write(year_dir, doy, CODXTR, ["PTAG", "TANY"])
    _write(year_dir, 4, "nothing rejected\n", ["PTAG", "TANY", "ISAB", "ORAS"])

    result = cc.check_year(year_dir, YEAR)

    assert result.checked == [1, 2, 3, 4, 5]
    assert result.not_checked == []
    assert list(result.by_station()) == ["ISAB", "ORAS"]
    assert all(r.estimated is False for r in result.rejections)
    lines = result.station_lines()
    assert lines[0] == (
        "ISAB: rejected by CODSPP on 4 days (DOY 001-003, 005): "
        "over 50% bad observations on 4, 57% bad; not in the solution on 4 of 4"
    )
    assert lines[1].startswith("ORAS: rejected by CODSPP on 4 days (DOY 001-003, 005): ")
    assert "no code solution on 4" in lines[1]
    assert result.summary() == (
        "CODSPP check: 2 station(s) rejected over 5 days: ISAB (4), ORAS (4)"
    )


def test_a_day_without_a_summary_is_not_checked_never_clean(year_dir: Path) -> None:
    _write(year_dir, 10, "nothing rejected\n", ["PTAG"])
    result = cc.check_year(year_dir, YEAR, [10, 11])
    assert result.checked == [10]
    assert result.not_checked == [11]
    assert result.summary() == "CODSPP check: 1 day checked, no station rejected; 1 day not checked"


def test_nothing_checked_says_so(year_dir: Path) -> None:
    result = cc.check_year(year_dir, YEAR, [20])
    assert result.summary() == "CODSPP check: none of 1 day could be checked"


def test_without_coordinates_whether_it_was_dropped_is_unknown(year_dir: Path) -> None:
    _write(year_dir, 7, CODXTR, None)
    result = cc.check_year(year_dir, YEAR)
    assert {r.estimated for r in result.rejections} == {None}
    assert "not in the solution" not in result.station_lines()[0]


def test_the_cli_exits_by_what_it_found(year_dir: Path, capsys: pytest.CaptureFixture) -> None:
    _write(year_dir, 1, "nothing rejected\n", ["PTAG"])
    assert cc.main(["--campaign", "X", "--year", str(YEAR), "--year-dir", str(year_dir)]) == 0
    _write(year_dir, 2, CODXTR, ["PTAG"])
    assert cc.main(["--campaign", "X", "--year", str(YEAR), "--year-dir", str(year_dir)]) == 1
    assert "ISAB: rejected by CODSPP on 1 day (DOY 002)" in capsys.readouterr().out
    empty = year_dir.parent / "1999"
    assert cc.main(["--campaign", "X", "--year", "1999", "--year-dir", str(empty)]) == 2
