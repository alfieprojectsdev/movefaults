"""Tests for equipment_check: the .STA file against field-ops' equipment records.

Synthetic .STA text is built in the committed LUZON.STA's column layout, so
the rows go through the one TYPE 002 reader (sta_type002_rows) exactly as a
real file does. The committed LUZON.STA and equipment.csv are used as they are
for the whole-file run.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
import yaml
from bernese_workflow import equipment_check as ec
from bernese_workflow.rinex_header_validator import sta_type002_rows

REPO = Path(__file__).resolve().parents[3]
LUZON_STA = REPO / "config" / "bernese" / "gpsuser52-luzon" / "STA" / "LUZON.STA"
EQUIPMENT_CSV = REPO / "data" / "network_inventory" / "equipment.csv"
NAME_MAP = REPO / "config" / "bernese" / "equipment_names.yaml"

STA_HEAD = """\
TYPE 002: STATION INFORMATION
-----------------------------

STATION NAME          FLG          FROM                   TO         RECEIVER TYPE         RECEIVER SERIAL NBR   REC #   ANTENNA TYPE          ANTENNA SERIAL NBR    ANT #    NORTH      EAST      UP
****************      ***  YYYY MM DD HH MM SS  YYYY MM DD HH MM SS  ********************  ********************  ******  ********************  ********************  ******  ***.****  ***.****  ***.***
"""
STA_TAIL = "\n\nTYPE 003: HANDLING OF STATION PROBLEMS\n"
OPEN_2099 = "2099 12 31 00 00 00"


def sta_row(name: str, frm: str, to: str, receiver: str, antenna: str, radome: str = "NONE") -> str:
    """One TYPE 002 row in the column layout LUZON.STA uses."""
    ant = f"{antenna:<16}{radome:>4}"
    return (
        f"{name:<16}      001  {frm:<19}  {to:<19}  {receiver:<20}  {'':<20}  999999  "
        f"{ant:<20}  {'':<20}  999999    0.0000    0.0000    0.000"
    )


def sta_text(*rows: str) -> str:
    return STA_HEAD + "\n".join(rows) + STA_TAIL


def write_csv(path: Path, rows: list[dict]) -> Path:
    cols = ["station_code", "manufacturer", "model", "antenna_model", "radome_type"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return path


@pytest.fixture
def names() -> ec.NameMap:
    return ec.load_name_map(NAME_MAP)


# --- the name map ---------------------------------------------------------------------


def test_the_committed_name_map_has_the_documented_shape() -> None:
    raw = yaml.safe_load(NAME_MAP.read_text())
    assert set(raw) == {"version", "receiver", "antenna", "radome"}
    assert raw["version"] == 1
    for section in ("receiver", "antenna", "radome"):
        assert isinstance(raw[section], dict) and raw[section], section
        for key, value in raw[section].items():
            assert isinstance(key, str) and key == key.strip() and key, (section, key)
            assert isinstance(value, str) and value == value.strip().upper(), (section, value)
    # IGS antenna names carry no radome and no blanks; IGS radomes are 4 characters.
    assert all(" " not in v and len(v) <= 16 for v in raw["antenna"].values())
    assert all(len(v) == 4 for v in raw["radome"].values())
    assert all(len(v) <= 20 for v in raw["receiver"].values())
    ec.load_name_map(NAME_MAP)  # and the loader accepts it


def test_every_mapped_name_is_one_a_production_sta_already_uses() -> None:
    """The right-hand side must be an IGS rcvr_ant.tab name. The IGS table is not
    vendored, so the check is against the committed production capture, whose
    antennas Bernese checks against IGS names: a name not in it needs a
    reviewer's confirmation, and this test is what asks for it."""
    rows = sta_type002_rows(LUZON_STA.read_text(encoding="latin-1"))
    known = {
        "receiver": {r.receiver for r in rows},
        "antenna": {r.antenna[:16].strip() for r in rows},
        "radome": {r.antenna[16:].strip() for r in rows},
    }
    raw = yaml.safe_load(NAME_MAP.read_text())
    for section in ("receiver", "antenna", "radome"):
        unknown = sorted(set(raw[section].values()) - known[section])
        assert unknown == [], f"{section}: not in LUZON.STA, confirm against rcvr_ant.tab"


def test_a_duplicate_key_is_refused_not_last_one_wins(tmp_path: Path) -> None:
    p = tmp_path / "names.yaml"
    p.write_text(
        'version: 1\nreceiver:\n  "Leica GR50": "LEICA GR50"\n  "Leica GR50": "LEICA GR25"\n'
        'antenna:\n  "Leica AR20": "LEIAR20"\nradome:\n  "NONE": "NONE"\n'
    )
    with pytest.raises(ec.NameMapError, match="duplicate key 'Leica GR50'"):
        ec.load_name_map(p)


@pytest.mark.parametrize(
    "body, match",
    [
        ("version: 2\nreceiver: {a: B}\nantenna: {a: B}\nradome: {a: NONE}\n", "version"),
        ("version: 1\nreceiver: {a: B}\nantenna: {a: B}\n", "radome"),
        ("version: 1\nreceiver: {a: B}\nantenna: {a: B}\nradome: {a: NONE}\nextra: {}\n", "extra"),
        ("version: 1\nreceiver: {a: b}\nantenna: {a: B}\nradome: {a: NONE}\n", "upper"),
        ("version: 1\nreceiver: {a: 5}\nantenna: {a: B}\nradome: {a: NONE}\n", "text"),
    ],
)
def test_a_malformed_name_map_is_refused(tmp_path: Path, body: str, match: str) -> None:
    p = tmp_path / "names.yaml"
    p.write_text(body)
    with pytest.raises(ec.NameMapError, match=match):
        ec.load_name_map(p)


# --- 2a: current equipment, every category --------------------------------------------

SYNTHETIC_STA = sta_text(
    sta_row("EQUL EQUL", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM57971.00"),
    sta_row("MAPD MAPD", "2015 01 01 00 00 00", OPEN_2099, "LEICA GR50", "LEIAR20", "LEIM"),
    sta_row("DIFF DIFF", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM57971.00"),
    sta_row("ONLS ONLS", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM57971.00"),
    sta_row("UNMP UNMP", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM57971.00"),
    sta_row("RADO RADO", "2015 01 01 00 00 00", OPEN_2099, "LEICA GR50", "LEIAR20", "LEIM"),
    sta_row("TYPO TYPO", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM115000.00"),
    # A history whose latest row is open with a BLANK end ...
    sta_row(
        "OPNB OPNB", "2010 01 01 00 00 00", "2015 06 30 23 59 59", "TRIMBLE 5700", "TRM41249.00"
    ),
    sta_row("OPNB OPNB", "2015 07 01 00 00 00", "", "LEICA GR50", "LEIAR20", "LEIM"),
    # ... and one whose latest row ends 2099-12-31, written first in the file.
    sta_row("OPN9 OPN9", "2015 07 01 00 00 00", OPEN_2099, "LEICA GR50", "LEIAR20", "LEIM"),
    sta_row(
        "OPN9 OPN9", "2010 01 01 00 00 00", "2015 06 30 23 59 59", "TRIMBLE 5700", "TRM41249.00"
    ),
)

SYNTHETIC_SHEET = [
    {
        "station_code": "EQUL",
        "model": "TRIMBLE NETR9",
        "antenna_model": "TRM57971.00",
        "radome_type": "NONE",
    },
    {
        "station_code": "MAPD",
        "model": "Leica GR50",
        "antenna_model": "Leica AR20",
        "radome_type": "LEIM",
    },
    # ATIM's case: the antenna is a different model, by known names on both sides.
    {
        "station_code": "DIFF",
        "model": "Trimble NetR9",
        "antenna_model": "AT504GG",
        "radome_type": "NONE",
    },
    {
        "station_code": "ONLC",
        "model": "Trimble NetR9",
        "antenna_model": "TRM57971.00",
        "radome_type": "NONE",
    },
    {
        "station_code": "UNMP",
        "model": "MG700",
        "antenna_model": "TRM57971.00",
        "radome_type": "NONE",
    },
    {
        "station_code": "RADO",
        "model": "Leica GR50",
        "antenna_model": "Leica AR20",
        "radome_type": "NONE",
    },
    # BASC's case: a likely typo in the sheet is reported, never corrected.
    {
        "station_code": "TYPO",
        "model": "Trimble NetR9",
        "antenna_model": "TRM11500.00",
        "radome_type": "NONE",
    },
    {
        "station_code": "OPNB",
        "model": "Leica GR50",
        "antenna_model": "Leica AR20",
        "radome_type": "LEIM",
    },
    {
        "station_code": "OPN9",
        "model": "Leica GR50",
        "antenna_model": "Leica AR20",
        "radome_type": "LEIM",
    },
]


@pytest.fixture
def current(tmp_path: Path, names: ec.NameMap) -> dict[str, ec.CurrentResult]:
    rows = sta_type002_rows(SYNTHETIC_STA)
    source = ec.read_equipment_csv(write_csv(tmp_path / "eq.csv", SYNTHETIC_SHEET))
    return {r.station: r for r in ec.compare_current(rows, source, names)}


@pytest.mark.parametrize(
    "station, category",
    [
        ("EQUL", ec.EQUAL),
        ("MAPD", ec.EQUAL_AFTER_MAP),
        ("DIFF", ec.DIFFERENT),
        ("ONLS", ec.ONLY_IN_STA),
        ("ONLC", ec.ONLY_IN_SOURCE),
        ("UNMP", ec.UNMAPPED),
        ("RADO", ec.DIFFERENT),
        ("TYPO", ec.UNMAPPED),
        ("OPNB", ec.EQUAL_AFTER_MAP),
        ("OPN9", ec.EQUAL_AFTER_MAP),
    ],
)
def test_each_station_gets_its_category(current, station: str, category: str) -> None:
    assert current[station].category == category


def test_different_says_which_field_and_keeps_both_names(current) -> None:
    f = current["DIFF"].fields
    assert f["receiver"].status == ec.EQUAL_AFTER_MAP
    assert f["antenna"].status == ec.DIFFERENT
    assert (f["antenna"].sta, f["antenna"].source, f["antenna"].source_igs) == (
        "TRM57971.00",
        "AT504GG",
        "LEIAT504GG",
    )


def test_antenna_and_radome_are_compared_separately(current) -> None:
    """The STA antenna field is MODEL(16) + RADOME(4); a radome-only change is
    still a difference, and is reported as the radome's."""
    f = current["RADO"].fields
    assert f["antenna"].status == ec.EQUAL_AFTER_MAP
    assert (f["radome"].sta, f["radome"].source, f["radome"].status) == (
        "LEIM",
        "NONE",
        ec.DIFFERENT,
    )


def test_an_open_end_blank_or_2099_is_the_latest_row(current) -> None:
    assert current["OPNB"].sta_to == ""
    assert current["OPNB"].fields["receiver"].sta == "LEICA GR50"
    assert current["OPN9"].sta_to == OPEN_2099
    assert current["OPN9"].fields["receiver"].sta == "LEICA GR50", (
        "latest by FROM, not by file order"
    )


def test_a_likely_typo_is_listed_unmapped_not_corrected(current, names) -> None:
    a = current["TYPO"].fields["antenna"]
    assert (a.sta, a.source, a.status, a.source_igs) == (
        "TRM115000.00",
        "TRM11500.00",
        ec.UNMAPPED,
        None,
    )
    assert "TRM11500.00" in ec.unmapped_names(current.values())["antenna"]


def test_unmapped_names_are_listed_by_kind(current) -> None:
    un = ec.unmapped_names(current.values())
    assert un["receiver"] == ["MG700"]
    assert un["antenna"] == ["TRM11500.00"]
    assert un["radome"] == []


def test_a_blank_field_in_the_source_is_unmapped_not_equal(tmp_path, names) -> None:
    rows = sta_type002_rows(SYNTHETIC_STA)
    sheet = [
        {"station_code": "EQUL", "model": "", "antenna_model": "TRM57971.00", "radome_type": "NONE"}
    ]
    [r] = [
        x
        for x in ec.compare_current(
            rows, ec.read_equipment_csv(write_csv(tmp_path / "e.csv", sheet)), names
        )
        if x.station == "EQUL"
    ]
    assert r.category == ec.UNMAPPED
    assert r.fields["receiver"].note == "blank in the source"


# --- 2a on the committed files ----------------------------------------------------------


def test_the_committed_luzon_sta_against_the_committed_sheet(names) -> None:
    rows = sta_type002_rows(LUZON_STA.read_text(encoding="latin-1"))
    results = {
        r.station: r for r in ec.compare_current(rows, ec.read_equipment_csv(EQUIPMENT_CSV), names)
    }
    cats = [r.category for r in results.values()]
    assert cats.count(ec.ONLY_IN_STA) == 59
    assert cats.count(ec.ONLY_IN_SOURCE) == 25
    assert len(results) == 92 + 59 + 25
    # AGUS: TRIMBLE 5700 / TRM41249.00 NONE in both, the receiver as "Trimble 5700".
    assert results["AGUS"].category == ec.EQUAL_AFTER_MAP


# --- 2b: per visit ------------------------------------------------------------------------


def export(
    tmp_path: Path, logsheets: list[dict], exported_at: str = "2026-11-05T17:00:00+00:00"
) -> Path:
    p = tmp_path / "export.json"
    p.write_text(
        json.dumps(
            {
                "format": ec.EXPORT_FORMAT,
                "version": 1,
                "exported_at": exported_at,
                "counts": {"logsheets": len(logsheets), "equipment_history": 0},
                "logsheets": logsheets,
                "equipment_history": [],
            }
        )
    )
    return p


VISIT_STA = sta_text(
    # SWAP: the swap at the 2026-03-10 visit is in the STA (a row from that day).
    sta_row(
        "SWAP SWAP", "2015 01 01 00 00 00", "2026 03 10 03 59 59", "TRIMBLE NETR9", "TRM57971.00"
    ),
    sta_row("SWAP SWAP", "2026 03 10 04 00 00", "", "LEICA GR50", "LEIAR20", "LEIM"),
    # MISS: a swap at the 2026-03-10 visit that the STA never got.
    sta_row("MISS MISS", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM57971.00"),
)


def visit(code: str, **kw) -> dict:
    base = {
        "station_code": code,
        "visit_date": "2026-03-10",
        "arrival_time": "2026-03-10T09:30:00+08:00",
        "departure_time": None,
        "equipment_changed": False,
        "receiver_model_before": None,
        "receiver_model_after": None,
        "antenna_type_before": None,
        "antenna_type_after": None,
    }
    base.update(kw)
    return base


def test_a_swap_with_no_matching_sta_row_is_reported_missing(tmp_path, names) -> None:
    ex = ec.read_logsheet_export(
        export(
            tmp_path,
            [
                visit(
                    "MISS",
                    equipment_changed=True,
                    receiver_model_before="Trimble NetR9",
                    antenna_type_before="TRM57971.00",
                    receiver_model_after="Leica GR50",
                    antenna_type_after="Leica AR20",
                )
            ],
        )  # fmt: skip
    )
    [v] = ec.compare_visits(sta_type002_rows(VISIT_STA), ex, names)
    assert v.before_status == ec.EQUAL_AFTER_MAP
    assert v.after_status == ec.AFTER_MISSING


def test_a_swap_that_has_its_sta_row_is_found(tmp_path, names) -> None:
    ex = ec.read_logsheet_export(
        export(
            tmp_path,
            [
                visit(
                    "SWAP",
                    equipment_changed=True,
                    receiver_model_before="Trimble NetR9",
                    antenna_type_before="TRM57971.00",
                    receiver_model_after="Leica GR50",
                    antenna_type_after="Leica AR20",
                )
            ],
        )  # fmt: skip
    )
    [v] = ec.compare_visits(sta_type002_rows(VISIT_STA), ex, names)
    # Arrival 09:30 PHT is 01:30 UTC: the old row was still valid then.
    assert v.visit_time == "2026-03-10T01:30:00"
    assert v.before_status == ec.EQUAL_AFTER_MAP
    assert v.after_status == ec.AFTER_FOUND
    assert v.after_row_from == "2026 03 10 04 00 00"


def test_a_visit_whose_before_disagrees_with_the_row_valid_then(tmp_path, names) -> None:
    ex = ec.read_logsheet_export(
        export(
            tmp_path,
            [visit("MISS", receiver_model_before="Leica GR50", antenna_type_before="TRM57971.00")],
        )
    )
    [v] = ec.compare_visits(sta_type002_rows(VISIT_STA), ex, names)
    assert v.before_status == ec.DIFFERENT
    assert v.after_status is None  # nothing was changed


def test_a_change_with_nothing_written_after_says_so(tmp_path, names) -> None:
    ex = ec.read_logsheet_export(export(tmp_path, [visit("MISS", equipment_changed=True)]))
    [v] = ec.compare_visits(sta_type002_rows(VISIT_STA), ex, names)
    assert v.after_status == ec.AFTER_NOT_RECORDED


def test_a_visit_without_an_arrival_time_uses_its_date(tmp_path, names) -> None:
    ex = ec.read_logsheet_export(export(tmp_path, [visit("MISS", arrival_time=None)]))
    [v] = ec.compare_visits(sta_type002_rows(VISIT_STA), ex, names)
    assert (v.visit_time, v.visit_time_source) == ("2026-03-10T00:00:00", "visit_date")


def test_an_unmapped_after_name_cannot_be_checked_and_says_so(tmp_path, names) -> None:
    ex = ec.read_logsheet_export(
        export(tmp_path, [visit("MISS", equipment_changed=True, receiver_model_after="MG700")])
    )
    [v] = ec.compare_visits(sta_type002_rows(VISIT_STA), ex, names)
    assert v.after_status == ec.UNMAPPED


# --- 2c: station names --------------------------------------------------------------------


def test_codes_with_no_sta_name_or_several_are_reported(names) -> None:
    rows = sta_type002_rows(
        sta_text(
            sta_row("BILI BILI", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM57971.00"),
            sta_row(
                "BILI 22001M001", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM57971.00"
            ),
            sta_row("ONE1 ONE1", "2015 01 01 00 00 00", OPEN_2099, "TRIMBLE NETR9", "TRM57971.00"),
        )
    )
    found = {p.station: p for p in ec.check_names(rows, {"BILI", "ONE1", "NONE"})}
    assert set(found) == {"BILI", "NONE"}
    assert found["BILI"].problem == ec.SEVERAL_NAMES
    assert found["BILI"].sta_names == ["BILI 22001M001", "BILI BILI"]
    assert found["NONE"].problem == ec.NO_NAME


# --- the command line ------------------------------------------------------------------


def test_cli_prints_a_table_with_the_export_time_and_exits_0_on_disagreement(
    tmp_path, capsys
) -> None:
    sta = tmp_path / "X.STA"
    sta.write_text(VISIT_STA)
    ex = export(
        tmp_path, [visit("MISS", equipment_changed=True, receiver_model_after="Leica GR50")]
    )
    eq = write_csv(
        tmp_path / "eq.csv",
        [
            {
                "station_code": "MISS",
                "model": "MG700",
                "antenna_model": "TRM57971.00",
                "radome_type": "NONE",
            }
        ],
    )
    assert (
        ec.main(["--sta", str(sta), "--equipment-csv", str(eq), "--logsheet-export", str(ex)]) == 0
    )
    out = capsys.readouterr().out
    assert "exported_at 2026-11-05T17:00:00+00:00" in out
    assert "not recorded in the file" in out  # the CSV has no export time
    assert "MISS" in out and ec.UNMAPPED in out and ec.AFTER_MISSING in out
    assert "advisory" in out


def test_cli_json_carries_every_section_and_the_export_time(tmp_path, capsys) -> None:
    sta = tmp_path / "X.STA"
    sta.write_text(VISIT_STA)
    ex = export(tmp_path, [visit("SWAP")])
    assert ec.main(["--sta", str(sta), "--logsheet-export", str(ex), "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["sources"]["logsheet_export"]["exported_at"] == "2026-11-05T17:00:00+00:00"
    assert set(doc) >= {"sta", "sources", "current", "visits", "names", "unmapped", "summary"}
    assert doc["visits"][0]["station"] == "SWAP"
    assert doc["current"] == []  # no equipment CSV: no current-equipment check


@pytest.mark.parametrize("problem", ["missing", "not_json", "wrong_format"])
def test_cli_exits_2_only_for_unreadable_input(tmp_path, capsys, problem: str) -> None:
    sta = tmp_path / "X.STA"
    sta.write_text(VISIT_STA)
    ex = tmp_path / "export.json"
    if problem == "not_json":
        ex.write_text("{not json")
    elif problem == "wrong_format":
        ex.write_text(json.dumps({"format": "something else"}))
    assert ec.main(["--sta", str(sta), "--logsheet-export", str(ex)]) == 2
    assert "cannot read" in capsys.readouterr().err


def test_cli_needs_at_least_one_source(tmp_path) -> None:
    sta = tmp_path / "X.STA"
    sta.write_text(VISIT_STA)
    with pytest.raises(SystemExit) as exc:
        ec.main(["--sta", str(sta)])
    assert exc.value.code == 2


def test_without_a_csv_the_exports_equipment_history_is_the_current_source(
    tmp_path, capsys
) -> None:
    """Stage 2 will keep equipment_history; the report reads its current rows
    (date_removed null) and merges a station's receiver and antenna rows."""
    sta = tmp_path / "X.STA"
    sta.write_text(VISIT_STA)
    p = export(tmp_path, [])
    doc = json.loads(p.read_text())
    doc["equipment_history"] = [
        {
            "station_code": "MISS",
            "model": "Trimble NetR9",
            "antenna_model": None,
            "radome_type": None,
            "date_removed": None,
        },
        {
            "station_code": "MISS",
            "model": None,
            "antenna_model": "TRM57971.00",
            "radome_type": "NONE",
            "date_removed": None,
        },
        {
            "station_code": "MISS",
            "model": "Trimble 5700",
            "antenna_model": None,
            "radome_type": None,
            "date_removed": "2020-01-01",
        },
        {
            "station_code": "SWAP",
            "model": "Leica GR50",
            "antenna_model": "Leica AR20",
            "radome_type": "LEIM",
            "date_removed": None,
        },
        {
            "station_code": "SWAP",
            "model": "Trimble NetR9",
            "antenna_model": None,
            "radome_type": None,
            "date_removed": None,
        },
    ]
    p.write_text(json.dumps(doc))
    assert ec.main(["--sta", str(sta), "--logsheet-export", str(p), "--json"]) == 0
    rep = json.loads(capsys.readouterr().out)
    cur = {r["station"]: r for r in rep["current"]}
    assert "equipment_history" in rep["sources"]["current_equipment_from"]
    assert cur["MISS"]["category"] == ec.EQUAL_AFTER_MAP, (
        "the removed 5700 row is history, not current"
    )
    # Two current receivers for SWAP: shown together, matching nothing, and said why.
    assert cur["SWAP"]["fields"]["receiver"]["source"] == "Leica GR50 / Trimble NetR9"
    assert cur["SWAP"]["category"] == ec.UNMAPPED
    assert "several current equipment_history rows" in cur["SWAP"]["note"]


def test_a_visit_to_a_code_the_sta_does_not_have(tmp_path, names) -> None:
    ex = ec.read_logsheet_export(
        export(tmp_path, [visit("ZZZZ", receiver_model_before="Leica GR50")])
    )
    [v] = ec.compare_visits(sta_type002_rows(VISIT_STA), ex, names)
    assert v.before_status == ec.ONLY_IN_SOURCE
