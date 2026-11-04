"""station_files: a campaign's STA, BLQ, ATL and CRD read the way Bernese reads them.

Every case here is synthetic (station_fixtures.sta_text builds TYPE 002 rows in
Bernese's fixed columns), except the one test that reads the LUZON capture
already in config/bernese, which skips where that file is absent.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bernese_workflow import station_files as sf
from pogf_geodetic_suite.qc.completeness import Coverage

from .station_fixtures import sta_text

REPO = Path(__file__).resolve().parents[3]
LUZON = REPO / "config" / "bernese" / "gpsuser52-luzon" / "STA"

T0 = "1980 01 06 00 00 00"
OPEN = "2099 12 31 00 00 00"


def _kinds(findings) -> list[tuple[str, str]]:
    return sorted((f.kind, f.station) for f in findings)


# --- STA TYPE 002 ---------------------------------------------------------------------------

# One station per defect, plus one healthy history. S01R is the gps3 case: a
# row left open to 2099, a second row duplicating a third, and a new receiver
# started while the first row was still open.
EVERY_CASE = [
    # S01R: open row, duplicate pair, new receiver while the open row runs
    ("S01R S01R", "2017 11 16 00 00 00", OPEN, "TRIMBLE NETR9"),
    ("S01R S01R", "2017 11 16 00 00 00", "2025 04 14 23 59 59", "TRIMBLE NETR9"),
    ("S01R S01R", "2017 11 16 00 00 00", "2025 04 14 23 59 59", "TRIMBLE NETR9"),
    ("S01R S01R", "2025 04 15 00 00 00", OPEN, "TRIMBLE ALLOY"),
    # OVLP: two closed windows that share a day
    ("OVLP OVLP", T0, "2021 11 23 23 59 59"),
    ("OVLP OVLP", "2021 11 23 00 00 00", OPEN),
    # REVS: FROM after its own TO
    ("REVS REVS", "2020 05 01 00 00 00", "2019 05 01 00 00 00"),
    # GOOD: the IGS convention, each end exactly the next start
    ("GOOD 12345M001", T0, "2012 07 25 00 00 00"),
    ("GOOD 12345M001", "2012 07 25 00 00 00", "2021 01 25 00 30 00", "TRIMBLE NETR9"),
    ("GOOD 12345M001", "2021 01 25 00 30 00", "", "TRIMBLE ALLOY"),
]


@pytest.mark.parametrize("newline", ["\r\n", "\n"], ids=["CRLF", "LF"])
def test_each_sta_defect_is_found_and_the_igs_convention_is_not(newline):
    findings = sf.check_sta(sta_text(EVERY_CASE, newline), "X.STA")
    assert _kinds(findings) == [
        ("sta_duplicate", "S01R S01R"),
        ("sta_open_then_later", "S01R S01R"),
        ("sta_overlap", "OVLP OVLP"),
        ("sta_overlap", "S01R S01R"),  # the open row against each of the duplicates,
        ("sta_overlap", "S01R S01R"),  # which start the same day
        ("sta_reversed", "REVS REVS"),
    ]
    by_kind = {f.kind: f for f in findings}
    # Line numbers are the file's, so the row can be found in an editor.
    assert by_kind["sta_duplicate"].detail == "line 14 repeats line 13 exactly"
    assert "line 12 is open (TO 2099 12 31 00 00 00) but line 15 starts 2025 04 15" in str(
        by_kind["sta_open_then_later"]
    )
    assert all(f.blocking for f in findings if f.kind != "sta_reversed")
    assert not by_kind["sta_reversed"].blocking


def test_crlf_and_lf_give_identical_findings():
    """CRLF is what real files carry. Reading must not depend on it, and the
    row text a duplicate is compared on must not carry the \\r."""
    crlf = sf.check_sta(sta_text(EVERY_CASE, "\r\n"), "X.STA")
    lf = sf.check_sta(sta_text(EVERY_CASE, "\n"), "X.STA")
    assert [str(f) for f in crlf] == [str(f) for f in lf]
    assert not any("\r" in str(f) for f in crlf)


def test_an_end_equal_to_the_next_start_is_not_an_overlap():
    rows = [
        ("AIRA 21742S001", T0, "2012 07 25 00 00 00"),
        ("AIRA 21742S001", "2012 07 25 00 00 00", "", "TRIMBLE NETR9"),
    ]
    assert sf.check_sta(sta_text(rows, "\r\n"), "X.STA") == []


def test_one_second_of_overlap_is_an_overlap():
    """The boundary test above could pass because nothing is ever flagged.
    One second earlier must be."""
    rows = [
        ("AIRA 21742S001", T0, "2012 07 25 00 00 00"),
        ("AIRA 21742S001", "2012 07 24 23 59 59", "", "TRIMBLE NETR9"),
    ]
    assert _kinds(sf.check_sta(sta_text(rows), "X.STA")) == [("sta_overlap", "AIRA 21742S001")]


def test_a_blank_to_followed_by_a_later_row_is_open_too():
    rows = [("PIMO PIMO", T0, ""), ("PIMO PIMO", "2024 01 01 00 00 00", "", "TRIMBLE ALLOY")]
    assert _kinds(sf.check_sta(sta_text(rows), "X.STA")) == [("sta_open_then_later", "PIMO PIMO")]


def test_stations_are_keyed_on_the_full_name_not_the_code():
    """BILI BILI and BILI 12363M001 are two stations: both open is no overlap."""
    rows = [("BILI BILI", T0, OPEN), ("BILI 12363M001", T0, OPEN)]
    assert sf.check_sta(sta_text(rows), "X.STA") == []


def test_an_unreadable_date_is_reported_not_read_as_open():
    """_sta_time gives None for a date that does not parse, the same as for a
    blank one. Read as open, hour 24 would invent an overlap or hide one."""
    rows = [("HR24 HR24", T0, "2099 12 31 24 00 00")]
    (f,) = sf.check_sta(sta_text(rows), "X.STA")
    assert f.kind == "sta_bad_date" and "TO '2099 12 31 24 00 00'" in f.detail
    assert not f.blocking


def test_a_station_file_with_no_rows_is_a_finding_not_a_pass():
    (f,) = sf.check_sta(sta_text([]), "X.STA")
    assert f.kind == "sta_empty" and f.blocking


def test_the_luzon_capture_reproduces_s01r_and_three_more():
    """The 5.2 LUZON capture in config/bernese is the file the gps3 scan read.
    Pinned here because it is the real layout, CRLF and all; if the capture is
    ever corrected, this test should change with it."""
    sta = LUZON / "LUZON.STA"
    if not sta.is_file():
        pytest.skip("LUZON capture not in this checkout")
    findings = sf.check_sta(sf.read_text(sta), "LUZON.STA")
    assert sorted({f.station for f in findings}) == [
        "BTUN BTUN",
        "S01R S01R",
        "SNFO SNFO",
        "SPAB SPAB",
    ]
    s01r = _kinds(f for f in findings if f.station == "S01R S01R")
    assert s01r == [
        ("sta_duplicate", "S01R S01R"),
        ("sta_open_then_later", "S01R S01R"),
        ("sta_overlap", "S01R S01R"),
        ("sta_overlap", "S01R S01R"),
    ]
    # AIRA's history has an end equal to the next start (2012 07 25): clean.
    assert not any(f.station.startswith("AIRA") for f in findings)


# --- BLQ ------------------------------------------------------------------------------------

BLQ_DATA = "  .01857 .00725 .00385 .00179 .00805 .00787 .00267 .00170 .00125 .00058 .00057"


def _blq(*sections: list[str], newline: str = "\r\n") -> str:
    lines = ["$$ Ocean loading displacement", "$$"]
    for i, codes in enumerate(sections):
        if i:
            lines.append("$$ END TABLE")
        for code in codes:
            lines += [f"  {code}               {code}", "$$ comment", *[BLQ_DATA] * 6]
    return newline.join(lines) + newline


def test_blocks_after_end_table_are_found():
    text = _blq(["AGUS", "PTAG"], ["CUSV", "PTAG"])
    findings = sf.check_blq(text, "X.BLQ")
    assert _kinds(findings) == [("blq_after_end_table", "CUSV"), ("blq_after_end_table", "PTAG")]
    assert all(f.blocking for f in findings)
    by_code = {f.station: f.detail for f in findings}
    assert "NOT FOUND" in by_code["CUSV"]
    assert "the block above the marker is the one Bernese reads" in by_code["PTAG"]


def test_a_blq_with_every_block_above_the_marker_is_clean():
    assert sf.check_blq(_blq(["AGUS", "CUSV"], []), "X.BLQ") == []


# --- ATL ------------------------------------------------------------------------------------


def _atl(*headers: str) -> str:
    body = "      0.2799      0.0188     -0.5784     -0.9437"
    return "".join(f"{h}\r\n{body}\r\n{body}\r\n{body}\r\n" for h in headers) + "\r\n"


def test_an_atl_header_that_is_not_the_sta_name_is_found():
    names = {"PTAG": {"PTAG 22006M005"}, "AGUS": {"AGUS AGUS"}}
    text = _atl("PTAG", "AGUS AGUS", "ZIMM 14001M004")
    (f,) = sf.check_atl(text, "X.ATL", names, active={"PTAG"})
    assert (f.kind, f.station, f.blocking) == ("atl_name", "PTAG", True)
    assert "header 'PTAG' is not the STA name 'PTAG 22006M005'" in f.detail
    # Not processed in this run: reported, but does not refuse it.
    (f,) = sf.check_atl(text, "X.ATL", names, active=())
    assert not f.blocking


def test_an_atl_header_naming_another_crd_station_is_not_a_mismatch():
    """LUZON.ATL's BILI 12363M001 is the IGS fiducial; the STA has BILI BILI."""
    names = {"BILI": {"BILI BILI"}}
    text = _atl("BILI 12363M001", "BILI BILI")
    assert sf.check_atl(text, "X.ATL", names) != []  # without the CRD it cannot tell
    assert sf.check_atl(text, "X.ATL", names, other_stations=["BILI 12363M001"]) == []


# --- stations with RINEX ----------------------------------------------------------------------

CRD = (
    "                                                                 11-AUG-26 22:56\r\n"
    "LOCAL GEODETIC DATUM: IGS20             EPOCH: 2026-01-01 00:00:00\r\n"
    "\r\n"
    "NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG\r\n"
    "\r\n"
    "  1  AGUS AGUS        -3442268.43853  5197451.98331  1343779.24890\r\n"
    "  2  PTAG             -3184318.48238  5291065.65065  1590418.29284    A\r\n"
)


def _coverage(by_day: dict[int, set[str]]) -> Coverage:
    cov = Coverage(year=2025)
    for doy, stations in by_day.items():
        for s in stations:
            cov.by_day[doy].add(s)
            cov.by_station[s].add(doy)
    return cov


def test_stations_with_rinex_missing_from_sta_crd_or_blq():
    sta = sta_text(
        [("AGUS AGUS", T0, OPEN), ("PTAG 22006M005", T0, OPEN), ("CUSV 21904S001", T0, OPEN)]
    )
    blq = _blq(["AGUS", "PTAG"], ["CUSV"])
    cov = _coverage({d: {"AGUS", "PTAG", "CUSV", "NEWS"} for d in (10, 11, 12, 20)})
    findings = sf.check_station_files(
        sta=("X.STA", sta), crd=("X.CRD", CRD), blq=("X.BLQ", blq), coverage=cov,
        days=[10, 11, 12],  # DOY 020 is not being run
    )  # fmt: skip
    got = {(f.kind, f.station): f.detail for f in findings if f.kind.startswith("missing")}
    assert got == {
        ("missing_sta", "NEWS"): "RINEX on DOY 010-012 but no TYPE 002 row",
        ("missing_crd", "NEWS"): "RINEX on DOY 010-012 but absent",
        ("missing_blq", "NEWS"): "RINEX on DOY 010-012 but absent",
        ("missing_crd", "CUSV"): "RINEX on DOY 010-012 but absent",
        ("missing_blq", "CUSV"): "RINEX on DOY 010-012 but after END TABLE",
        # In the CRD by code, under a name Bernese will not look up.
        ("missing_crd", "PTAG"): "RINEX on DOY 010-012 but CRD names 'PTAG', "
        "STA names 'PTAG 22006M005'",
    }
    assert all(f.blocking for f in findings)
    assert [f.file for f in findings if f.station == "NEWS"] == ["X.STA", "X.CRD", "X.BLQ"]


def test_a_blq_block_indented_one_column_is_named_as_such():
    sta = sta_text([("CALU CALU", T0, OPEN)])
    blq = _blq(["AGUS"], []).replace("$$ Ocean", " CALU               CALU\r\n$$ Ocean")
    (f,) = sf.check_station_files(
        sta=("X.STA", sta), blq=("X.BLQ", blq), coverage=_coverage({5: {"CALU"}}), days=[5]
    )
    assert (f.kind, f.detail) == ("missing_blq", "RINEX on DOY 005 but indented 1 column")


# --- the command line -----------------------------------------------------------------------


def test_the_cli_prints_findings_and_never_rewrites_a_file(tmp_path: Path, capsys):
    paths = {
        "sta": tmp_path / "X.STA",
        "blq": tmp_path / "X.BLQ",
        "atl": tmp_path / "X.ATL",
        "crd": tmp_path / "X.CRD",
    }
    paths["sta"].write_bytes(sta_text(EVERY_CASE, "\r\n").encode("ascii"))
    paths["blq"].write_bytes(_blq(["AGUS"], ["CUSV"]).encode("ascii"))
    paths["atl"].write_bytes(_atl("OVLP").encode("ascii"))
    paths["crd"].write_bytes(CRD.encode("ascii"))
    before = {k: (p.read_bytes(), p.stat().st_mtime_ns) for k, p in paths.items()}

    argv = [a for k, p in paths.items() for a in (f"--{k}", str(p))]
    assert sf.main(argv) == 1
    out = capsys.readouterr().out
    assert "PROBLEM: X.STA: S01R S01R: line 14 repeats line 13 exactly" in out
    assert "PROBLEM: X.BLQ: CUSV: line" in out
    assert "WARNING: X.ATL: OVLP: line 1: header 'OVLP' is not the STA name 'OVLP OVLP'" in out
    after = {k: (p.read_bytes(), p.stat().st_mtime_ns) for k, p in paths.items()}
    assert after == before, "a check must not touch the files it reads (CRLF included)"


def test_the_cli_exits_0_on_clean_files(tmp_path: Path, capsys):
    sta = tmp_path / "X.STA"
    sta.write_text(sta_text([("AGUS AGUS", T0, OPEN)]))
    assert sf.main(["--sta", str(sta)]) == 0
    assert "0 problem(s), 0 warning(s)" in capsys.readouterr().out
