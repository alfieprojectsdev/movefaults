"""The console reads the service's records and refuses everything else.

The BSW tree every test reads is built in conftest.py.
"""

from __future__ import annotations

import dataclasses
import json
import os

from bernese_workflow.bpe_scanner import kind_of
from bsw_console import plan as plans
from bsw_console import stations, status
from bsw_console.main import create_app
from bsw_console.settings import Campaign, parse_campaigns, read_setvar
from fastapi.testclient import TestClient

YEAR = 2025
HELM = f"HELMR1: {kind_of('NO REDUNDANCY. NO VERIFICATION OF SITES POSSIBLE')}"


def test_calendar_states_come_from_savedisk_and_the_ledger(client):
    cal = client.get(f"/api/campaigns/LUZON/years/{YEAR}/days").json()
    by = {d["doy"]: d for d in cal["days"]}
    assert by[35]["state"] == "fixed"
    assert by[36]["state"] == "failed"
    assert by[36]["note"] == HELM
    # The run halted, so DOY 037 was never started: not run, not "queued".
    assert by[37]["state"] == "none"
    assert cal["counts"]["fixed"] == 1 and cal["counts"]["failed"] == 1
    assert by[36]["date"] == "2025-02-05" and by[36]["gps_week"] == 2352 and by[36]["gps_day"] == 3


def test_run_grid_names_the_failed_pid_from_the_protocol_file(client):
    r = client.get(f"/api/campaigns/LUZON/years/{YEAR}/runs").json()
    rows = {x["doy"]: x for x in r["rows"]}
    assert rows[35]["cells"] == ["done"] * 7
    assert rows[36]["pid"] == 513
    assert rows[36]["cells"] == ["done"] * 5 + ["failed", "wait"]
    assert rows[37]["outcome"] == "not started (halted)"
    assert r["run"]["state"] == "halted"
    assert r["breaker"]["identical"] == 1 and r["breaker"]["identical_limit"] == 3


def test_failure_matches_the_known_errors_list(client):
    f = client.get(f"/api/campaigns/LUZON/years/{YEAR}/days/36/failure").json()
    assert f["pid"] == 513 and f["script"] == "HELMCHK"
    assert f["program"] == "HELMR1"
    assert f["entry"]["scope"] == "session"
    assert f["verdict"]["kind"] == "session"
    assert any("***" in line for line in f["lines"])


def test_a_day_with_no_failure_is_404(client):
    assert client.get(f"/api/campaigns/LUZON/years/{YEAR}/days/35/failure").status_code == 404


def test_day_lists_results_with_52_names_and_quality(client):
    d = client.get(f"/api/campaigns/LUZON/years/{YEAR}/days/35").json()
    names = {r["name"]: r for r in d["results"]}
    assert names["FIN_20250350.SNX.gz"]["v52"] == "F1_250350.SNX"
    assert names["R2S_20250350.PRC"]["v52"] == "R2S250350.PRC"
    assert d["present"] == 7
    assert d["quality"]["stations"] == 2
    assert d["quality"]["helmert_rms_mm"] == 6.53
    # Not recorded by the ledger: reported as missing, not invented.
    assert d["provenance"]["started_by"] is None


def test_file_viewer_serves_only_names_it_listed(client):
    base = f"/api/campaigns/LUZON/years/{YEAR}/days"
    ok = client.get(f"{base}/35/file", params={"path": "OUT/R2S_20250350.PRC"})
    assert ok.status_code == 200 and "RMS OF TRANSFORMATION" in ok.json()["lines"][0]
    assert (
        client.get(f"{base}/36/file", params={"path": "BPE/RP250360_513_000.PRT"}).status_code
        == 200
    )
    for bad in (
        "../../../etc/passwd",
        "/etc/passwd",
        "OUT/../ledger.jsonl",
        "SOL/FIN_20250360.NQ0.gz",
    ):
        assert client.get(f"{base}/35/file", params={"path": bad}).status_code == 404


def test_known_errors_count_what_fired(client):
    k = client.get("/api/known-errors").json()
    helm = next(e for e in k["entries"] if e["emitter"] == "HELMR1")
    assert helm["fired"] == 1 and helm["last"]["doy"] == 36
    assert k["unknown"] == []


def test_stage3_actions_are_stubs(client, bsw):
    for route in ("/api/runs/start", "/api/runs/stop", "/api/preflight", "/api/redo"):
        r = client.post(route, json={})
        assert r.status_code == 501 and r.json()["enabled"] is False
    # And nothing in SAVEDISK moved.
    assert (bsw.savedisk / "LUZON" / str(YEAR) / "SOL" / "FIN_20250350.NQ0.gz").exists()


def test_redo_preview_lists_every_result_without_moving_any(client, bsw):
    r = client.get(f"/api/campaigns/LUZON/years/{YEAR}/days/35/redo").json()
    assert len(r["files"]) == 7
    assert "SUPERSEDED" in r["to"]
    assert not (bsw.savedisk / "LUZON" / str(YEAR) / "SUPERSEDED").exists()


PLAN = {"campaign": "LUZON", "year": YEAR, "from": 37, "to": 40, "pcf": "LUZON_DLY"}


def test_saving_a_plan_writes_one_file(client, bsw):
    r = client.post("/api/plans", json={**PLAN, "skipped": [3, 3, 1], "name": "x"})
    assert r.status_code == 200 and r.json()["by"] == "not signed in"
    assert r.json()["skipped"] == [1, 3]
    assert len(list((bsw.state_dir / "plans").glob("*.json"))) == 1
    assert client.get("/api/plans").json()["plans"][0]["from"] == 37
    assert client.post("/api/plans", json={**PLAN, "campaign": "NOPE"}).status_code == 404


def test_remote_user_is_believed_only_from_a_trusted_proxy(bsw):
    forged = {"X-Remote-User": "the-project-leader"}
    # TestClient connects from the address "testclient".
    untrusted = TestClient(create_app(bsw))
    assert untrusted.get("/api/session", headers=forged).json()["user"] is None
    r = untrusted.post("/api/plans", json=PLAN, headers=forged)
    assert r.json()["by"] == "not signed in"
    proxied = TestClient(
        create_app(dataclasses.replace(bsw, trusted_proxies=frozenset({"testclient"})))
    )
    assert proxied.get("/api/session", headers=forged).json()["user"] == "the-project-leader"


def test_a_plan_cannot_be_written_cross_site(client, bsw):
    body = json.dumps(PLAN)
    # text/plain is a CORS "simple request": a page on any site can send it with no preflight.
    for ctype in ("text/plain", "application/x-www-form-urlencoded", "multipart/form-data", None):
        headers = {"Content-Type": ctype} if ctype else {}
        r = client.post("/api/plans", content=body, headers=headers)
        assert r.status_code == 415, ctype
    evil = {"Content-Type": "application/json", "Origin": "https://evil.example"}
    assert client.post("/api/plans", content=body, headers=evil).status_code == 403
    cross = {"Content-Type": "application/json", "Sec-Fetch-Site": "cross-site"}
    assert client.post("/api/plans", content=body, headers=cross).status_code == 403
    same = {"Content-Type": "application/json", "Origin": "http://testserver"}
    assert client.post("/api/plans", content=body, headers=same).status_code == 200
    assert len(list((bsw.state_dir / "plans").glob("*.json"))) == 1


def test_a_plan_is_typed_and_bounded(client, bsw):
    bad = [
        {**PLAN, "name": "n" * 101},
        {**PLAN, "year": "2025"},
        {**PLAN, "year": True},
        {**PLAN, "from": 0},
        {**PLAN, "to": 366},
        {**PLAN, "from": 40, "to": 37},
        {**PLAN, "skipped": "3"},
        {**PLAN, "skipped": [10]},
        {**PLAN, "skipped": list(range(11))},
        {**PLAN, "pcf": "../../etc/x"},
        {**PLAN, "rnxgra": "anything"},
        {**PLAN, "extra": 1},
        [PLAN],
    ]
    for b in bad:
        assert client.post("/api/plans", json=b).status_code == 422, b
    big = {**PLAN, "name": "n" * 90, "padding": "x" * 5000}
    assert client.post("/api/plans", json=big).status_code == 413
    assert (
        client.post(
            "/api/plans", content=b"{not json", headers={"Content-Type": "application/json"}
        ).status_code
        == 422
    )
    assert not (bsw.state_dir / "plans").exists() or not list(
        (bsw.state_dir / "plans").glob("*.json")
    )


def test_bad_days_and_campaigns_are_refused(client):
    plan = f"/api/campaigns/LUZON/years/{YEAR}/plan"
    for bad in ("../../etc/LUZON_DLY", "LUZON_DLY.PCF", "NOPE"):
        assert client.get(plan, params={"start": 35, "end": 36, "pcf": bad}).status_code == 404
    assert client.get(f"/api/campaigns/LUZON/years/{YEAR}/days/366").status_code == 422
    assert client.get(f"/api/campaigns/NOPE/years/{YEAR}/days").status_code == 404


def test_lock_is_read_not_taken(bsw, tmp_path):
    bsw.lock_path.write_text(
        json.dumps({"pid": 999999, "user": "u", "host": "h", "started": "x", "purpose": "LUZON"})
    )
    fake = tmp_path / "locks"
    st = bsw.lock_path.stat()
    fake.write_text(
        f"1: FLOCK  ADVISORY  WRITE 123 {os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino} 0 EOF\n"
    )
    held = status.lock_status(bsw, proc_locks=fake)
    assert held["held"] and "LUZON" in held["holder"]
    fake.write_text("")
    assert status.lock_status(bsw, proc_locks=fake)["held"] is False


# ----------------------------------------------------------------------------- plan


def test_pcf_steps_and_skips(bsw):
    steps = plans.pcf_steps((bsw.gpsuser / "PCF" / "LUZON_DLY.PCF").read_text())
    assert [s["pid"] for s in steps][:3] == [1, 101, 199]
    assert steps[3]["waits"] == [199]
    # Skipping 3xx strands 401, which waits on 399.
    assert plans.dangling_from_skips(steps, {3}) == ["401 SATMRK waits on 399, which is skipped"]
    # Groups before the first one left on are "start with": no finding.
    assert plans.dangling_from_skips(steps, {0, 1}) == []
    assert plans.dangling_from_skips(steps, set(range(7))) == [
        "every group is skipped: nothing would run"
    ]


def test_products_missing_are_named(bsw):
    p = plans.products(bsw, YEAR, [35])
    assert set(p["missing"]) == {"orbits", "clocks", "ERP", "DCB/OSB", "ionosphere"}


# ----------------------------------------------------------------------------- stations


def test_station_coverage_flags_two_names_and_the_blq_gap(bsw):
    cov = stations.coverage(bsw, bsw.campaigns[0], YEAR)
    rows = {r["station"]: r for r in cov["rows"]}
    assert rows["BILI"]["cells"]["CRD"] == 2
    # BILI is after $$ END TABLE in the BLQ, where the BPE never reads it.
    assert rows["BILI"]["cells"]["BLQ"] == 0
    assert any("GTOCNL" in n for n in rows["BILI"]["notes"])
    assert rows["ALBU"]["cells"]["BLQ"] == 1


# ----------------------------------------------------------------------------- settings


def test_setvar_and_campaign_specs(tmp_path):
    f = tmp_path / "LOADGPS.setvar"
    f.write_text(
        'export C="/opt/BERN54"\nexport U="${HOME}/GPSUSER"\nexport X="$C/EXE"  # comment\n'
    )
    v = read_setvar(f, env={"HOME": "/home/x"})
    assert v == {"C": "/opt/BERN54", "U": "/home/x/GPSUSER", "X": "/opt/BERN54/EXE"}
    c = parse_campaigns("luzon:LUZON_DLY:lzy:LZFLT_DLY, PHREF")
    assert c[0] == Campaign("LUZON", "LUZON_DLY", "LZY", "LZFLT_DLY")
    assert c[1] == Campaign("PHREF", "PHREF_DLY", "", "")


# --- the equipment report panel (read-only) ----------------------------------------------

# conftest.equipment_report writes this into the synthetic export. A literal: under
# --import-mode=importlib, `import conftest` finds the repo-root conftest.py.
EXPORTED_AT = "2026-11-05T17:41:00+00:00"


def test_equipment_report_summary_names_the_sta_and_the_export_time(client) -> None:
    r = client.get("/api/equipment-report")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True and body["available"] is True
    assert body["exported_at"] == EXPORTED_AT
    assert body["sta"]["path"].endswith("PHNAT.STA")
    assert body["summary"]["different"] == 1


def test_equipment_report_for_one_station_carries_only_that_station(client) -> None:
    body = client.get("/api/stations/albu/equipment").json()
    assert body["station"] == "ALBU"
    assert body["exported_at"] == EXPORTED_AT
    [cur] = body["current"]
    assert cur["category"] == "different"
    assert cur["fields"]["antenna"]["source_igs"] == "LEIAT504GG"
    [v] = body["visits"]
    assert v["after_status"] == "no STA row for the change"
    assert {c["station"] for c in body["current"] + body["visits"]} == {"ALBU"}


def test_a_station_the_report_does_not_mention_has_empty_lists(client) -> None:
    body = client.get("/api/stations/ZZZZ/equipment").json()
    assert body["available"] is True
    assert body["current"] == [] and body["visits"] == [] and body["names"] == []


def test_without_a_configured_report_the_console_says_so_plainly(bsw) -> None:
    import dataclasses

    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    c = TestClient(create_app(dataclasses.replace(bsw, equipment_report=None)))
    for url in ("/api/equipment-report", "/api/stations/ALBU/equipment"):
        r = c.get(url)
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is False
        assert "No equipment report is configured" in body["message"]
        assert "current" not in body


def test_an_unreadable_report_is_reported_not_raised(bsw) -> None:
    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    bsw.equipment_report.write_text("{not json")
    c = TestClient(create_app(bsw))
    body = c.get("/api/stations/ALBU/equipment").json()
    assert body["configured"] is True and body["available"] is False
    assert "could not be read" in body["message"]


def test_a_station_code_is_four_letters_or_digits_never_a_path(client) -> None:
    for code in ("ALBUX", "AL", "..%2F..", "AL-U"):
        assert client.get(f"/api/stations/{code}/equipment").status_code in (404, 422)


def test_the_equipment_endpoints_are_read_only(client) -> None:
    assert client.post("/api/equipment-report").status_code == 405
    assert client.post("/api/stations/ALBU/equipment").status_code == 405


def test_a_report_with_the_right_keys_but_wrong_shapes_is_reported_not_raised(bsw) -> None:
    """A report file with the five keys but values of the wrong type (a hand-edited
    or truncated-and-rewritten file) must still answer 200 and say it can't be read."""
    import json

    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    c = TestClient(create_app(bsw), raise_server_exceptions=False)
    for bad in (
        {"sta": {}, "sources": "x", "current": [], "visits": [], "names": []},
        {"sta": {}, "sources": {}, "current": ["ALBU"], "visits": [], "names": []},
        {"sta": {}, "sources": {}, "current": {"station": "ALBU"}, "visits": [], "names": []},
        {"sta": {}, "sources": {"logsheet_export": "x"}, "current": [], "visits": [], "names": []},
    ):
        bsw.equipment_report.write_text(json.dumps(bad))
        for url in ("/api/equipment-report", "/api/stations/ALBU/equipment"):
            r = c.get(url)
            assert r.status_code == 200, (bad, url, r.status_code)
            body = r.json()
            assert body["configured"] is True and body["available"] is False, (bad, url)


def test_a_report_removed_after_reading_does_not_raise(bsw, monkeypatch) -> None:
    """The report is read and its time taken in one step: a file replaced or removed
    by the nightly job between the two must not turn into a 500."""
    from pathlib import Path

    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    real = Path.read_text

    def read_then_remove(self, *a, **k):
        text = real(self, *a, **k)
        if self == bsw.equipment_report:
            self.unlink()
        return text

    monkeypatch.setattr(Path, "read_text", read_then_remove)
    c = TestClient(create_app(bsw), raise_server_exceptions=False)
    r = c.get("/api/stations/ALBU/equipment")
    assert r.status_code == 200
    assert r.json()["available"] is True
