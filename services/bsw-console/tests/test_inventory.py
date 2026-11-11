"""The inventory: per station, RINEX on disk against the final CRDs that estimated it."""

from __future__ import annotations

from bsw_console import inventory as inv

YEAR = 2025
HEAD = "TITLE\n----\nLOCAL GEODETIC DATUM: IGS20  EPOCH: 2025-02-09 12:00:00\n\nNUM  STATION NAME  X Y Z FLAG\n\n"


def crd(*rows: str) -> str:
    return HEAD + "".join(rows)


def test_inventory_counts_rinex_against_estimated_stations(bsw):
    rnx = bsw.datapool / "LUZON"
    rnx.mkdir(parents=True, exist_ok=True)
    for doy in (40, 41, 42):
        (rnx / f"albu{doy:03d}0.25d.gz").write_bytes(b"")
    (rnx / "NOTS00PHL_R_20250400000_01D_30S_MO.crx.gz").write_bytes(b"")  # not in the STA
    sta = bsw.savedisk / "LUZON" / str(YEAR) / "STA"
    (sta / "FIN_20250400.CRD").write_text(crd(
        "  1  ALBU ALBU   -3233466.0 5093450.0 1446420.0    A\n",
        "  2  BILI BILI   -3233467.0 5093451.0 1446421.0\n",  # a priori carried, not estimated
    ))  # fmt: skip
    (sta / "FIN_20250410.CRD").write_text(
        crd("  1  ALBU ALBU   -3233466.0 5093450.0 1446420.0    A\n")
    )
    r = inv.inventory(bsw, bsw.campaigns[0], YEAR)
    rows = {x["station"]: x for x in r["rows"]}
    assert rows["ALBU"]["rinex_days"] == 3 and rows["ALBU"]["processed_days"] == 2
    assert rows["ALBU"]["waiting_first"] == [42]
    assert "BILI" not in rows or rows["BILI"]["processed_days"] == 0
    assert rows["NOTS"]["in_sta"] is False
    assert r["totals"]["waiting_in_sta"] == 1 and r["totals"]["waiting_not_in_sta"] == 1
    # One day apart is far under a year: no velocity yet.
    assert rows["ALBU"]["velocity"] is False and r["totals"]["short_for_velocity"] >= 1
    assert set(r["not_connected"]) == {"field_visits", "raw_data", "rinex_qc"}


def test_the_span_runs_across_the_campaign_years(bsw):
    for y, doy in ((2023, 10), (YEAR, 41)):
        sta = bsw.savedisk / "LUZON" / str(y) / "STA"
        sta.mkdir(parents=True, exist_ok=True)
        (sta / f"FIN_{y}{doy:03d}0.CRD").write_text(
            crd("  1  ALBU ALBU   -3233466.0 5093450.0 1446420.0    A\n")
        )
    rows = {x["station"]: x for x in inv.inventory(bsw, bsw.campaigns[0], YEAR)["rows"]}
    assert rows["ALBU"]["span_years"] > 2 and rows["ALBU"]["velocity"] is True


def test_inventory_endpoint(client):
    r = client.get(f"/api/campaigns/LUZON/years/{YEAR}/inventory")
    assert r.status_code == 200 and "totals" in r.json()


def test_an_unreadable_sta_says_not_known_rather_than_never_processed(bsw):
    (bsw.datapool / "REF54" / "LUZON.STA").unlink()
    rnx = bsw.datapool / "LUZON"
    rnx.mkdir(parents=True, exist_ok=True)
    (rnx / "albu0400.25d.gz").write_bytes(b"")
    r = inv.inventory(bsw, bsw.campaigns[0], YEAR)
    rows = {x["station"]: x for x in r["rows"]}
    assert r["sta"] is None and rows["ALBU"]["in_sta"] is None
    assert r["totals"]["waiting_not_in_sta"] == 0 and r["totals"]["waiting_in_sta"] >= 1


def test_a_float_only_day_is_processed_but_not_in_the_series(bsw):
    import dataclasses

    pcf = (bsw.gpsuser / "PCF" / f"{bsw.campaigns[0].pcf}.PCF").read_text()
    (bsw.gpsuser / "PCF" / "LZFLT.PCF").write_text(
        pcf.replace("${S}/LUZON/$Y+0", "${S}/LZFLT/$Y+0")
    )
    sta = bsw.savedisk / "LZFLT" / str(YEAR) / "STA"
    sta.mkdir(parents=True, exist_ok=True)
    (sta / "FIN_20250400.CRD").write_text(
        crd("  1  FLTO FLTO   -3233466.0 5093450.0 1446420.0    A\n")
    )
    c = dataclasses.replace(bsw.campaigns[0], float_pcf="LZFLT")
    rows = {x["station"]: x for x in inv.inventory(bsw, c, YEAR)["rows"]}
    assert rows["FLTO"]["processed_days"] == 1
    assert rows["FLTO"]["span_years"] is None and rows["FLTO"]["velocity"] is None
