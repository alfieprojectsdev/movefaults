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

from .station_fixtures import abb_text, atl_text, sta_text

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
    """check_atl names the stray header and never blocks: whether the run can
    read PTAG is check_atl_presence's question (tests below)."""
    names = {"PTAG": {"PTAG 22006M005"}, "AGUS": {"AGUS AGUS"}}
    text = _atl("PTAG", "AGUS AGUS", "ZIMM 14001M004")
    (f,) = sf.check_atl(text, "X.ATL", names)
    assert (f.kind, f.station, f.blocking) == ("atl_name", "PTAG", False)
    assert "header 'PTAG' is not the STA name 'PTAG 22006M005'" in f.detail


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
    # No --rinex-dir: a station with no full-name ATL block blocks, as overlaps
    # do, and the bare header is its reason rather than a second finding.
    assert "PROBLEM: X.ATL: OVLP: no block under the STA name: header 'OVLP' != 'OVLP OVLP'" in out
    assert "is not the STA name 'OVLP OVLP'" not in out
    after = {k: (p.read_bytes(), p.stat().st_mtime_ns) for k, p in paths.items()}
    assert after == before, "a check must not touch the files it reads (CRLF included)"


def test_the_cli_exits_0_on_clean_files(tmp_path: Path, capsys):
    sta = tmp_path / "X.STA"
    sta.write_text(sta_text([("AGUS AGUS", T0, OPEN)]))
    assert sf.main(["--sta", str(sta)]) == 0
    assert "0 problem(s), 0 warning(s)" in capsys.readouterr().out


# --- review round ---------------------------------------------------------------------------


def test_a_0x85_byte_does_not_split_a_row(tmp_path: Path):
    """read_text decodes latin-1, where cp1252's ellipsis 0x85 becomes U+0085,
    and str.splitlines() breaks a line there. In a description column (past
    column 141) that shifts every later line number, so findings point at the
    wrong row; in a serial-number column (before 141) the row is dropped and
    its overlap goes unreported."""
    rows = [("NEL1 NEL1", T0, OPEN), ("NEL1 NEL1", "2024 01 01 00 00 00", "", "TRIMBLE ALLOY")]
    text = sta_text(rows, "\r\n")
    described = text.replace("    0.0000\r\n", "    0.0000  Brgy. Sto. Ni\x85o\r\n", 1)
    serial = text.replace(
        "LEICA GR50" + " " * 12 + " " * 20, "LEICA GR50" + " " * 12 + "12\x85" + " " * 17, 1
    )
    for variant in (described, serial):
        assert variant.count("\x85") == 1
        path = tmp_path / "X.STA"
        path.write_bytes(variant.encode("latin-1"))
        (f,) = sf.check_sta(sf.read_text(path), "X.STA")
        assert f.kind == "sta_open_then_later"
        assert f.detail.startswith("line 12 is open") and "but line 13 starts" in f.detail


def test_a_rinex_dir_that_does_not_exist_is_an_error_not_a_clean_scan(tmp_path: Path, capsys):
    sta = tmp_path / "X.STA"
    sta.write_text(sta_text([("AGUS AGUS", T0, OPEN)]))
    with pytest.raises(SystemExit) as e:
        sf.main(["--sta", str(sta), "--rinex-dir", str(tmp_path / "typo"), "--year", "2025"])
    assert e.value.code == 2
    assert "is not a directory" in capsys.readouterr().err


def test_an_empty_sta_is_one_finding_not_one_per_station():
    cov = _coverage({5: {"AGUS", "PTAG", "CUSV"}})
    findings = sf.check_station_files(sta=("X.STA", sta_text([])), coverage=cov, days=[5])
    assert _kinds(findings) == [("sta_empty", "-")]


def test_an_open_row_followed_by_several_is_one_finding_at_the_first_start():
    """PHNAT.STA's BTUN: one row open to 2099 and three later rows. Closing it at
    the first later start ends all three overlaps; a finding per later row would
    also advise closing it at the second and the third."""
    rows = [
        ("BTUN BTUN", T0, OPEN),
        ("BTUN BTUN", "2016 08 26 00 00 00", "2017 04 17 23 59 59", "TRIMBLE NETR9"),
        ("BTUN BTUN", "2017 04 18 00 00 00", "2019 08 19 23 59 59", "TRIMBLE ALLOY"),
        ("BTUN BTUN", "2019 08 20 00 00 00", OPEN, "LEICA GR50"),
    ]
    (f,) = sf.check_sta(sta_text(rows), "X.STA")
    assert f.kind == "sta_open_then_later" and f.blocking
    assert "but line 13 starts 2016 08 26 00 00 00; close line 12 there" in f.detail


def test_a_blq_header_with_an_underscore_name_is_read():
    """PHNAT.BLQ heads LORE and MONT as `  LORE_LORE` (OLMPP's form), and
    PHREF's GPSEST read both from it without a NOT FOUND."""
    text = _blq(["AGUS"], []).replace("  AGUS               AGUS", "  LORE_LORE")
    assert sf.blq_status(text, "LORE") == "ok"
    assert sf.check_blq(text + "$$ END TABLE\r\n  MONT_MONT\r\n", "X.BLQ")[0].station == "MONT"


def test_an_overlap_blocks_only_a_station_with_data_over_the_days_to_run() -> None:
    """LUZON 2026 solved 31/31 with BTUN, SNFO and SPAB overlaps in its STA; S01R's blocked.

    S01R's open row overlaps 2025-04-15 onward and S01R has RINEX in the run:
    it blocks. OVLP's overlap ended in 2021: warning. S01R in a run where it
    has no data: warning. No days to run at all: nothing can be affected.
    """
    sta = ("T.STA", sta_text(EVERY_CASE))

    def blocking(cov: dict[int, set[str]], days: list[int], year: int = 2025) -> set[str]:
        c = _coverage(cov)
        found = sf.check_station_files(sta=sta, coverage=c, days=days, year=year)
        return {f.station for f in found if f.blocking and f.kind.startswith("sta_")}

    assert blocking({152: {"S01R", "OVLP"}}, [152]) == {"S01R S01R"}
    assert blocking({152: {"OVLP"}}, [152]) == set()
    assert blocking({}, []) == set()
    # Without a datapool scan, every overlap still blocks (the CLI with no --rinex-dir).
    unscoped = sf.check_station_files(sta=sta, days=[152], year=2025)
    assert {f.station for f in unscoped if f.blocking} >= {"S01R S01R", "OVLP OVLP"}
    # A warning says why it is not blocking.
    c = _coverage({152: {"OVLP"}})
    ovlp = [
        f
        for f in sf.check_station_files(sta=sta, coverage=c, days=[152], year=2025)
        if f.station == "OVLP OVLP"
    ]
    assert ovlp and all("warning only" in f.detail for f in ovlp)


# --- ATL and ABB presence ---------------------------------------------------------------------

PRESENCE_STA = [
    ("AGUS AGUS", T0, OPEN),
    ("PTAG 22006M005", T0, OPEN),
    ("IDLE IDLE", T0, OPEN),  # in the STA, no RINEX in the run
]
NEWLINES = pytest.mark.parametrize("newline", ["\r\n", "\n"], ids=["CRLF", "LF"])


def _presence(newline, atl=None, abb=None, coverage=True):
    cov = _coverage({d: {"AGUS", "PTAG"} for d in (10, 11)}) if coverage else None
    return sf.check_station_files(
        sta=("X.STA", sta_text(PRESENCE_STA, newline)),
        atl=None if atl is None else ("X.ATL", atl_text(atl, newline)),
        abb=None if abb is None else ("X.ABB", abb_text(abb, newline)),
        coverage=cov,
        days=[10, 11],
        year=2025,
    )


@NEWLINES
def test_a_station_with_data_and_no_atl_block_blocks(newline):
    findings = _presence(newline, atl=["AGUS AGUS", "IDLE IDLE"])
    (f,) = [f for f in findings if f.blocking]
    assert (f.file, f.kind, f.station) == ("X.ATL", "missing_atl", "PTAG")
    assert f.detail == "RINEX on DOY 010-011 but absent"


@NEWLINES
def test_the_same_station_without_data_only_warns(newline):
    findings = _presence(newline, atl=["AGUS AGUS", "PTAG 22006M005"])
    (f,) = findings
    assert (f.kind, f.station, f.blocking) == ("missing_atl", "-", False)
    assert f.detail.endswith("(warning only): IDLE")


@NEWLINES
def test_a_full_name_mismatch_blocks_with_the_header_as_its_reason(newline):
    """The PHNAT.ATL of 2026-09-30: `PTAG` where GTATML looks up
    `PTAG 22006M005`, NOT FOUND at GPSEDT_P."""
    findings = _presence(newline, atl=["AGUS AGUS", "PTAG", "IDLE IDLE"])
    (f,) = findings
    assert (f.kind, f.station, f.blocking) == ("missing_atl", "PTAG", True)
    assert f.detail == "RINEX on DOY 010-011 but header 'PTAG' != 'PTAG 22006M005'"


@NEWLINES
def test_a_missing_abb_line_warns_and_never_blocks(newline):
    findings = _presence(newline, abb=["AGUS AGUS"])
    (f,) = findings
    assert (f.file, f.kind, f.station, f.blocking) == ("X.ABB", "missing_abb", "PTAG", False)
    assert f.detail == "RINEX on DOY 010-011 but no line for 'PTAG 22006M005' (warning only)"
    # A bare-code ABB line is not the station either: name_listed's rule.
    assert _presence(newline, abb=["AGUS AGUS", "PTAG"])[0].station == "PTAG"
    assert _presence(newline, abb=["AGUS AGUS", "PTAG 22006M005"]) == []


def test_a_stray_atl_header_beside_a_correct_block_only_warns():
    findings = _presence("\r\n", atl=["AGUS AGUS", "PTAG", "PTAG 22006M005", "IDLE IDLE"])
    (f,) = findings
    assert (f.kind, f.station, f.blocking) == ("atl_name", "PTAG", False)


def test_without_a_datapool_scan_every_station_missing_from_the_atl_blocks():
    findings = _presence("\n", atl=["AGUS AGUS"], abb=["AGUS AGUS"], coverage=False)
    assert sorted((f.kind, f.station, f.blocking) for f in findings) == [
        ("missing_abb", "IDLE", False),
        ("missing_abb", "PTAG", False),
        ("missing_atl", "IDLE", True),
        ("missing_atl", "PTAG", True),
    ]


def test_a_code_with_two_sta_names_needs_a_block_under_one():
    rows = [("BILI BILI", T0, OPEN), ("BILI 12363M001", T0, OPEN)]
    findings = sf.check_station_files(
        sta=("X.STA", sta_text(rows)),
        atl=("X.ATL", atl_text(["BILI BILI"])),
        coverage=_coverage({10: {"BILI"}}),
        days=[10],
        year=2025,
    )
    assert findings == []


def test_the_luzon_capture_has_no_atl_or_abb_gaps():
    """All 151 STA names have a full-name ATL block and an ABB line."""
    if not (LUZON / "LUZON.ATL").is_file():
        pytest.skip("LUZON capture not in this checkout")
    findings = sf.check_station_files(
        sta=("LUZON.STA", sf.read_text(LUZON / "LUZON.STA")),
        atl=("LUZON.ATL", sf.read_text(LUZON / "LUZON.ATL")),
        abb=("LUZON.ABB", sf.read_text(LUZON / "LUZON.ABB")),
        crd=("LUZON.CRD", sf.read_text(LUZON / "LUZON.CRD")),
    )
    assert [f for f in findings if f.file in ("LUZON.ATL", "LUZON.ABB")] == []


# --- single-instant rows (FROM == TO) ---------------------------------------------------------


def test_a_single_instant_overlap_at_the_runs_first_midnight_blocks():
    """Two rows of one name valid only at 2025-04-15 00:00:00 (DOY 105), with
    RINEX that day. Their common window is that one instant; scoping must
    count it as inside DOY 105, not as ending where the run begins."""
    instant = "2025 04 15 00 00 00"
    rows = [("S01R S01R", instant, instant), ("S01R S01R", instant, instant, "TRIMBLE ALLOY")]
    findings = sf.check_station_files(
        sta=("X.STA", sta_text(rows)), coverage=_coverage({105: {"S01R"}}), days=[105], year=2025
    )
    (f,) = [f for f in findings if f.kind == "sta_overlap"]
    assert f.blocking, f
    # The day before is not touched by it.
    findings = sf.check_station_files(
        sta=("X.STA", sta_text(rows)), coverage=_coverage({104: {"S01R"}}), days=[104], year=2025
    )
    (f,) = [f for f in findings if f.kind == "sta_overlap"]
    assert not f.blocking, f
