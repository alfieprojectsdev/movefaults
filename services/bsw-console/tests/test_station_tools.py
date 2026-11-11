"""Station files, the read-only helpers: the Onsala request, the reply check and
the a priori preview. Each test writes its own REF54 files over the synthetic
tree in conftest.py; nothing the helpers do may write a file."""

from __future__ import annotations

import math
from pathlib import Path

import pytest
from bsw_console import station_tools as t
from bsw_console.main import create_app
from fastapi.testclient import TestClient

YEAR = 2025

CRD_HEAD = (
    "TITLE\n" + "-" * 80 + "\nLOCAL GEODETIC DATUM: {datum}             EPOCH: {epoch}\n\n"
    "NUM  STATION NAME           X (M)          Y (M)          Z (M)     FLAG\n\n"
)
APRIORI = CRD_HEAD.format(datum="IGS14", epoch="2021-09-01 12:00:00") + (
    "  1  BTNG 22601M001   -3674585.91533  5210904.36615   159093.31172\n"
    "  2  ALBU ALBU        -3233466.00000  5093450.00000  1446420.00000\n"
    "  3  CLAV CLAV        -3100000.00000  5200000.00000  1500000.00000\n"
)
STA = (
    "TYPE 001: RENAMING OF STATIONS\n\nSTATION NAME\n*****\n"
    "BTNG 22601M001  001\nALBU ALBU  001\nNOXY NOXY  001\n\nTYPE 002: STATION INFORMATION\n"
)
HEADER = (
    "$$ Ocean loading displacement\n$$\n$$ Gutenberg-Bullen Greens function is used.\n"
    "$$ CMC:  NO   (corr.tide centre of mass)\n$$\n$$ Ocean tide model: FES2004\n$$\n$$ END HEADER\n$$\n"
)
ROWS = "\n".join(["  " + " ".join([".01000"] * 11)] * 3 + ["  " + " ".join(["10.0"] * 11)] * 3)


def block(code: str, key_at: int = 3, rows: str = ROWS) -> str:
    """A station block as Onsala writes it, with the key line ``key_at`` lines
    after the name line."""
    comments = ["$$ FES2004_PP ID: 2026-09-30", "$$ Computed by OLMPP"][: key_at - 1]
    return (
        "\n".join([f"  {code}", *comments, f"$$ {code},  RADI TANG  lon/lat: 1 2 3", rows]) + "\n"
    )


@pytest.fixture
def ref(bsw) -> Path:
    r = bsw.datapool / "REF54"
    (r / "LUZON.CRD").write_text(APRIORI)
    (r / "LUZON.STA").write_text(STA)
    (r / "LUZON.BLQ").write_text(HEADER + block("ALBU") + "$$ END TABLE\n")
    return r


def test_the_onsala_request_lists_sta_stations_missing_from_the_blq(bsw, ref):
    r = t.onsala_request(bsw, bsw.campaigns[0], YEAR)
    # The PHDEN request of 2026-09-30 had exactly this form: code, X, Y, Z, 5 decimals.
    assert r["lines"] == ["BTNG -3674585.91533 5210904.36615 159093.31172"]
    assert r["no_coordinates"] == ["NOXY"]
    assert r["settings"] == {
        "ocean tide model": "FES2004",
        "centre of mass correction (CMC)": "NO",
        "Green's function": "Gutenberg-Bullen",
    }
    assert (r["crd_datum"], r["crd_epoch"]) == ("IGS14", "2021-09-01 12:00:00")


def test_a_good_reply_is_ready_and_nothing_is_written(bsw, ref):
    before = {p: p.read_bytes() for p in ref.iterdir()}
    reply = HEADER + block("BTNG") + "$$ END TABLE\n-- \nsent from the service\n"
    r = t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, reply)
    assert r["ready"] and r["new"] == ["BTNG"]
    assert r["stations"][0]["key_line"] == "ok"
    assert "merge_blq.py --blq" in r["command"]
    assert {p: p.read_bytes() for p in ref.iterdir()} == before


def test_reply_problems_are_each_named(bsw, ref):
    reply = (
        HEADER.replace("FES2004", "TPXO9")
        + block("ALBU")  # already in the BLQ
        + block("BTNG", rows="\n".join(ROWS.splitlines()[:5]))  # a row short
        + block("ZZZZ")  # not in the STA
        + "  NOXY\n" + ROWS + "\n"  # no key line
    )  # fmt: skip
    r = t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, reply)
    by = {x["station"]: x for x in r["stations"]}
    assert by["ALBU"]["status"].startswith("already in the BLQ")
    assert "5 rows of 11 numbers" in by["BTNG"]["problems"][0]
    assert by["ZZZZ"]["status"].startswith("not in LUZON.STA")
    assert by["NOXY"]["key_line"] == "missing"
    assert r["settings_differ"] == ["ocean tide model: the reply has TPXO9, LUZON.BLQ has FES2004"]
    assert not r["ready"]


def test_an_early_key_line_is_fine_because_merge_blq_moves_it(bsw, ref):
    r = t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, HEADER + block("BTNG", key_at=2))
    assert r["stations"][0]["key_line"] == "early" and r["ready"]


def test_a_quoted_printable_paste_is_named(bsw, ref):
    r = t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, "$$ Ocean=20loading=3D\n")
    assert "quoted-printable" in r["problems"][0] and not r["ready"]


def test_apriori_preview_compares_estimated_stations_in_north_east_up(bsw, ref):
    sta = bsw.savedisk / "LUZON" / str(YEAR) / "STA"
    (sta / f"FIN_{YEAR}0400.CRD").write_text(
        CRD_HEAD.format(datum="IGS20", epoch="2025-02-09 12:00:00")
        # BTNG 1 m up, along its own radius; ALBU unchanged; CLAV carried, not estimated.
        + "  1  BTNG 22601M001   {:.5f}  {:.5f}   {:.5f}    A\n".format(
            *(v * (1 + 1 / math.dist((0, 0, 0), (-3674585.91533, 5210904.36615, 159093.31172)))
              for v in (-3674585.91533, 5210904.36615, 159093.31172))
        )
        + "  2  ALBU ALBU        -3233466.00000  5093450.00000  1446420.00000    A\n"
        + "  3  CLAV CLAV        -3100000.00000  5200000.00000  1500000.00000\n"
        + "  4  NEWS NEWS        -3100001.00000  5200001.00000  1500001.00000    A\n"
    )  # fmt: skip
    p = t.apriori_preview(bsw, bsw.campaigns[0], YEAR)
    assert p["final"]["file"] == f"FIN_{YEAR}0400.CRD"
    rows = {r["station"]: r for r in p["rows"]}
    n, e, u = rows["BTNG 22601M001"]["neu_mm"]
    # Geocentric radius and ellipsoidal up differ by the deflection: under 0.4%.
    assert abs(u - 1000) < 4 and math.hypot(n, e) < 10
    assert rows["ALBU ALBU"]["neu_mm"] == [0.0, 0.0, 0.0]
    assert rows["NEWS NEWS"]["change"] == "added"
    assert "CLAV CLAV" in p["not_estimated"]
    assert len(p["warnings"]) == 2  # frame and epoch both differ


def test_endpoints(bsw, ref):
    c = TestClient(create_app(bsw))
    base = f"/api/campaigns/LUZON/years/{YEAR}/station-files"
    assert c.get(f"{base}/onsala-request").json()["lines"]
    r = c.post(f"{base}/blq-check", json={"reply": HEADER + block("BTNG")})
    assert r.status_code == 200 and r.json()["ready"]
    assert c.post(f"{base}/blq-check", json={"text": "x"}).status_code == 422
    assert c.get(f"{base}/apriori-preview", params={"final": "FIN_20259990.CRD"}).status_code == 404


def test_a_station_after_end_table_in_the_blq_is_not_ready(bsw, ref):
    # merge_blq.py counts it as present and skips it (or replaces it in place,
    # still after the marker), so the merge would leave it invisible to Bernese.
    (ref / "LUZON.BLQ").write_text(HEADER + block("ALBU") + "$$ END TABLE\n" + block("BTNG"))
    r = t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, HEADER + block("BTNG"))
    assert "after '$$ END TABLE'" in r["stations"][0]["status"]
    assert r["stations"][0]["problems"] and not r["ready"] and r["new"] == []


def test_a_reply_with_nothing_new_is_not_ready(bsw, ref):
    r = t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, HEADER + block("ALBU"))
    assert r["new"] == [] and not r["ready"]


def test_a_different_greens_function_is_named(bsw, ref):
    reply = HEADER.replace("Gutenberg-Bullen", "PREM") + block("BTNG")
    r = t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, reply)
    assert r["settings_differ"] == [
        "Green's function: the reply has PREM, LUZON.BLQ has Gutenberg-Bullen"
    ]
    assert not r["ready"]


def test_the_key_line_is_matched_as_gtocnl_reads_it(bsw, ref):
    # A key line carrying the DOMES after the code still has the code in
    # columns 4-7, which is all GTOCNL compares.
    reply = HEADER + block("BTNG").replace("$$ BTNG,", "$$ BTNG 22601M001,")
    assert t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, reply)["stations"][0]["key_line"] == "ok"


def test_stray_lines_in_a_block_are_named_apart_from_the_row_count(bsw, ref):
    reply = HEADER + block("BTNG") + "sent from the service\n"
    why = t.check_blq_reply(bsw, bsw.campaigns[0], YEAR, reply)["stations"][0]["problems"]
    assert why == ["1 other line(s) inside the block that are not 11 numbers"]


def test_blq_check_refuses_a_cross_site_post(bsw, ref):
    c = TestClient(create_app(bsw))
    url = f"/api/campaigns/LUZON/years/{YEAR}/station-files/blq-check"
    r = c.post(url, json={"reply": "x"}, headers={"Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert (
        c.post(url, content='{"reply": "x"}', headers={"Content-Type": "text/plain"}).status_code
        == 415
    )
