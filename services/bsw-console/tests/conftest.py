"""A small synthetic BSW tree for the console's tests.

A PCF, a SAVEDISK year with FIN files and a ledger, and the real HELMR1
failure captured from LZY250360 (bernese-workflow's fixture) in a per-day
campaign's BPE folder. `build` is also what make_frontend_fixture.py renders
the frontend smoke test from, so the two never drift apart.
"""

from __future__ import annotations

import gzip
import json
import os
import shutil
import time
from pathlib import Path

import pytest
from bernese_workflow.bpe_scanner import kind_of
from bsw_console.main import create_app
from bsw_console.settings import Campaign, Settings
from fastapi.testclient import TestClient

FIXTURES = (
    Path(__file__).resolve().parents[2] / "bernese-workflow" / "tests" / "fixtures" / "bpe_errors"
)
YEAR = 2025
# The label run_year records: Diagnosis.label, "emitter: KIND".
HELM = f"HELMR1: {kind_of('NO REDUNDANCY. NO VERIFICATION OF SITES POSSIBLE')}"

PCF = """\
PID  SCRIPT    OPT_DIR   PARAMETERS
#
001  R2S_COP   R2S_GEN   CPU=ANY
101  POLUPD    R2S_GEN   CPU=ANY; WAIT=001
199  DUMMY     NO_OPT    CPU=ANY; WAIT=101
201  RNXGRA    R2S_GEN   CPU=ANY; WAIT=199
299  DUMMY     NO_OPT    CPU=ANY; WAIT=201
301  INIT_BSL  R2S_GEN   CPU=ANY; WAIT=299
399  DUMMY     NO_OPT    CPU=ANY; WAIT=301
401  SATMRK    R2S_GEN   CPU=ANY; WAIT=399
499  DUMMY     NO_OPT    CPU=ANY; WAIT=401
511  ADDNEQ2   R2S_FIN   CPU=ANY; WAIT=499
513  HELMCHK   R2S_GEN   CPU=ANY; WAIT=511
599  DUMMY     NO_OPT    CPU=ANY; WAIT=513
901  R2S_SUM   R2S_GEN   CPU=ANY; WAIT=599
902  R2S_SAV   R2S_GEN   CPU=ANY; WAIT=901

VARIABLE DESCRIPTION                              DEFAULT
V_RESULT = ${S}/LUZON/$Y+0;  DESCRIPTION=results
V_RNXDIR = ${D}/LUZON;       DESCRIPTION=rinex
V_REFDIR = ${D}/REF54;       DESCRIPTION=ref
V_REFINF = IGS20;            DESCRIPTION=ref set
V_CRDINF = LUZON;            DESCRIPTION=crd
V_STAINF = LUZON;            DESCRIPTION=sta
V_BLQINF = LUZON;            DESCRIPTION=blq
V_ATLINF = LUZON;            DESCRIPTION=atl
"""


def _ledger(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps({"v": 1, **r}) + "\n" for r in rows))


def _ledger(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps({"v": 1, **r}) + "\n" for r in rows))


def build(tmp_path: Path) -> Settings:
    """The synthetic BSW tree every console test reads."""
    u, d, s, p = (tmp_path / x for x in ("GPSUSER", "DATAPOOL", "SAVEDISK", "CAMPAIGN54"))
    (u / "PCF").mkdir(parents=True)
    (u / "PCF" / "LUZON_DLY.PCF").write_text(PCF)
    year = s / "LUZON" / str(YEAR)
    for sub in ("SOL", "OUT", "STA", "ATM"):
        (year / sub).mkdir(parents=True)
    # DOY 035 solved: all seven results, two stations in the SINEX.
    with gzip.open(year / "SOL" / "FIN_20250350.SNX.gz", "wt") as fh:
        fh.write("+SITE/ID\n*CODE PT\n ALBU  A ALBU M\n DARW  A 50134M001\n-SITE/ID\n")
    for name in (
        "SOL/FIN_20250350.NQ0.gz",
        "SOL/RED_20250350.NQ0.gz",
        "STA/FIN_20250350.CRD",
        "ATM/FIN_20250350.TRO",
        "ATM/FIN_20250350.TRP",
    ):
        (year / name).write_text("x\n")
    (year / "OUT" / "R2S_20250350.PRC").write_text(" RMS OF TRANSFORMATION :    6.53 MM\n")

    t0 = time.time() - 3600
    _ledger(
        year / "ledger.jsonl",
        [
            {
                "ts": t0,
                "event": "run_start",
                "run": "r1",
                "host": "elsewhere",
                "pid": 1,
                "campaign": "LUZON",
                "year": YEAR,
                "doys": [35, 36, 37],
                "banked": [],
                "config": "abc",
            },
            {
                "ts": t0 + 1,
                "event": "attempt_start",
                "run": "r1",
                "doy": 35,
                "session": "0350",
                "mode": "day",
            },
            {
                "ts": t0 + 300,
                "event": "attempt_end",
                "run": "r1",
                "doy": 35,
                "session": "0350",
                "outcome": "ok",
                "seconds": 299.0,
                "error": "",
                "note": "",
                "stations": 2,
                "mode": "day",
            },
            {
                "ts": t0 + 301,
                "event": "attempt_start",
                "run": "r1",
                "doy": 36,
                "session": "0360",
                "mode": "day",
            },
            {
                "ts": t0 + 600,
                "event": "attempt_end",
                "run": "r1",
                "doy": 36,
                "session": "0360",
                "outcome": "failed",
                "seconds": 299.0,
                "error": HELM,
                "note": "",
                "stations": None,
                "mode": "day",
            },
            {
                "ts": t0 + 601,
                "event": "run_end",
                "run": "r1",
                "halt": "configuration error (example)",
            },
        ],
    )
    bpe = p / "LZY250360" / "BPE"
    bpe.mkdir(parents=True)
    for src in FIXTURES.glob("LZY250360_RP250360_513_000.*"):
        dst = bpe / src.name.removeprefix("LZY250360_")
        shutil.copy(src, dst)
        os.utime(dst, (t0 + 500, t0 + 500))

    ref = d / "REF54"
    ref.mkdir(parents=True)
    crd_head = "TITLE\n----\nDATUM\nNUM  STATION NAME\n"
    (ref / "LUZON.CRD").write_text(
        crd_head + "  1  BILI 12363M001  1 2 3\n  2  BILI BILI  1 2 3\n  3  ALBU ALBU  1 2 3\n"
    )
    (ref / "LUZON.STA").write_text(
        "TYPE 001: RENAMING OF STATIONS\n\nSTATION NAME\n*****\nBILI BILI  001\nALBU ALBU  001\n\nTYPE 002: STATION INFORMATION\n"
    )
    (ref / "LUZON.BLQ").write_text(
        "$$ header\n  ALBU               ALBU\n  .01 .02\n$$ END TABLE\n  BILI   after the table, unread\n"
    )
    # The time series reads <V_RESULT>/STA of every year: LUZON 2020 and 2021
    # here. The 2025 day fixtures hold no estimated station, so they add nothing.
    ts_offsets = time_series_inputs(s / "LUZON")
    return Settings(
        gpsuser=u,
        datapool=d,
        savedisk=s,
        campaigns_dir=p,
        campaigns=[Campaign("LUZON", "LUZON_DLY", "LZY")],
        lock_path=tmp_path / "bpe.lock",
        state_dir=tmp_path / "state",
        ts_reference="REF0",
        ts_offsets=ts_offsets,
        equipment_report=equipment_report(tmp_path / "equipment"),
    )


EXPORTED_AT = "2026-11-05T17:41:00+00:00"


def _sta_row(name: str, frm: str, to: str, receiver: str, antenna: str, radome: str) -> str:
    """One TYPE 002 row in the committed LUZON.STA's column layout."""
    ant = f"{antenna:<16}{radome:>4}"
    return (
        f"{name:<16}      001  {frm:<19}  {to:<19}  {receiver:<20}  {'':<20}  999999  "
        f"{ant:<20}  {'':<20}  999999    0.0000    0.0000    0.000"
    )


def equipment_report(root: Path) -> Path:
    """The report bernese-check-equipment --json writes, made by that code itself,
    so the console is tested against the producer's real shape.

    ALBU: the sheet's antenna is another model, and a swap at a visit has no
    STA row. BILI: equal after the name map. CORS: only in the sheet.
    """
    from bernese_workflow.equipment_check import (
        build_report,
        load_name_map,
        read_logsheet_export,
    )

    root.mkdir(parents=True)
    sta = root / "PHNAT.STA"
    sta.write_text(
        "TYPE 002: STATION INFORMATION\n-----------------------------\n\n"
        "STATION NAME          FLG          FROM                   TO\n"
        "****************      ***  YYYY MM DD HH MM SS  YYYY MM DD HH MM SS\n"
        + _sta_row("ALBU ALBU", "2015 01 01 00 00 00", "2099 12 31 00 00 00", "TRIMBLE NETR9", "TRM57971.00", "NONE") + "\n"
        + _sta_row("BILI BILI", "2015 01 01 00 00 00", "", "LEICA GR50", "LEIAR20", "LEIM") + "\n"
        + "\n\nTYPE 003: HANDLING OF STATION PROBLEMS\n"
    )  # fmt: skip
    sheet = root / "equipment.csv"
    sheet.write_text(
        "station_code,model,antenna_model,radome_type\n"
        "ALBU,Trimble NetR9,AT504GG,NONE\n"
        "BILI,Leica GR50,Leica AR20,LEIM\n"
        "CORS,Trimble NetR9,TRM57971.00,NONE\n"
    )
    export = root / "field_equipment.json"
    visit = {
        "station_code": "ALBU", "visit_date": "2026-03-10",
        "arrival_time": "2026-03-10T09:30:00+08:00", "departure_time": None,
        "equipment_changed": True, "receiver_model_before": "Trimble NetR9",
        "receiver_model_after": "Leica GR50", "antenna_type_before": "TRM57971.00",
        "antenna_type_after": None,
    }  # fmt: skip
    export.write_text(
        json.dumps(
            {
                "format": "field-ops-equipment-export",
                "version": 1,
                "exported_at": EXPORTED_AT,
                "counts": {"logsheets": 1, "equipment_history": 0},
                "logsheets": [visit],
                "equipment_history": [],
            }
        )
    )
    report = build_report(sta, load_name_map(), sheet, read_logsheet_export(export))
    out = root / "equipment_report.json"
    out.write_text(json.dumps(report))
    return out


@pytest.fixture
def bsw(tmp_path: Path) -> Settings:
    return build(tmp_path)


@pytest.fixture
def client(bsw: Settings) -> TestClient:
    return TestClient(create_app(bsw))


# --- the time-series inputs: daily final CRD files and an offsets catalog -------------

TS_REF_XYZ = (-3_150_000.0, 5_350_000.0, 1_600_000.0)
TS_STEP_T = 2021.0
TS_SPIKE = (2021, 196)  # the one epoch the IQR rule must flag


def _ts_crd_line(i: int, name: str, xyz: tuple[float, float, float]) -> str:
    x, y, z = xyz
    return f"  {i:3d}  {name} 00000S000  {x:>15.5f} {y:>15.5f}  {z:>15.5f}    A   G"


def time_series_inputs(root: Path) -> Path:
    """Two years of synthetic daily CRDs for REF0 and SYN1, each year in its own
    <year>/STA as a campaign's are, and an offsets catalog with one
    earthquake. SYN1 moves steadily, steps at the earthquake, and has one
    large spike. Deterministic: no random noise, a small alternating wobble."""
    header = (
        "SYNTHETIC TEST NETWORK                                          05-NOV-26 00:00\n"
        "--------------------------------------------------------------------------------\n"
        "LOCAL GEODETIC DATUM: IGS20                 EPOCH: 2020-01-01 00:00:00\n\n"
        " NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG     SYSTEM\n\n"
    )
    k = 0
    for year in (2020, 2021):
        crd = root / str(year) / "STA"
        crd.mkdir(parents=True)
        for doy in range(1, 366, 15):
            t = year + doy / 365.25
            wobble = 0.0008 if k % 2 else -0.0008
            k += 1
            dx = 0.030 * (t - 2020.0) + (0.010 if t >= TS_STEP_T else 0.0) + wobble
            dz = -0.012 * (t - 2020.0) + wobble
            if (year, doy) == TS_SPIKE:
                dx += 0.25
            sta = (TS_REF_XYZ[0] + 1200.0 + dx, TS_REF_XYZ[1] - 800.0, TS_REF_XYZ[2] + 500.0 + dz)
            (crd / f"F1_{year % 100:02d}{doy:03d}.CRD").write_text(
                header
                + _ts_crd_line(1, "REF0", TS_REF_XYZ)
                + "\n"
                + _ts_crd_line(2, "SYN1", sta)
                + "\n",
                encoding="ascii",
            )
    offsets = root / "offsets"
    offsets.write_text(f"# synthetic\nSYN1  {TS_STEP_T:.4f}  EQ\n", encoding="utf-8")
    return offsets
