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


def test_stage3_is_off_by_default_and_says_why(client) -> None:
    """Actions default to off: every stage-3 route answers 501 with the reason and
    queues nothing. The body keeps the shape it had before the worker was wired."""
    for route in ("/api/runs/start", "/api/runs/stop", "/api/preflight", "/api/redo"):
        r = client.post(route, json={})
        body = r.json()
        assert r.status_code == 501
        assert set(body) == {"enabled", "reason"}
        assert body["enabled"] is False
        assert "bernese-worker" in body["reason"]
        assert "switched off" in body["reason"]


# --- run provenance on the Day page (ledger run_start, #318) ---------------------------


def _append_new_run(bsw) -> None:
    """A second run, written after #318: its run_start carries who, the command,
    the code, the PCF and products. It re-attempts DOY 035, so the day has one
    attempt from an old run (r1, no provenance) and one from a new one (r2)."""
    import json as _json
    import time as _time

    from bsw_console.status import ledger_path

    t = _time.time() - 60
    rows = [
        {"ts": t, "event": "run_start", "run": "r2", "host": "gps3", "pid": 2,
         "campaign": "LUZON", "year": YEAR, "doys": [35], "banked": [], "config": "def",
         "user": "processing", "sudo_user": None,
         "command": ["bernese-run-year", "--campaign", "LUZON", "--run"],
         "code": {"commit": "0123456789abcdef0123", "dirty": False},
         "pcf": "LUZON_DLY", "products": "COD0OPSFIN", "product_tier": "final", "excluded": []},
        {"ts": t + 1, "event": "attempt_start", "run": "r2", "doy": 35, "session": "0350", "mode": "block"},
        {"ts": t + 30, "event": "attempt_end", "run": "r2", "doy": 35, "session": "0350",
         "outcome": "ok", "seconds": 29.0, "error": "", "note": "", "stations": 2, "mode": "block"},
        {"ts": t + 31, "event": "run_end", "run": "r2", "halt": None},
    ]  # fmt: skip
    path = ledger_path(bsw, bsw.campaign("LUZON"), YEAR)
    with open(path, "a") as f:
        f.write("".join(_json.dumps({"v": 1, **r}) + "\n" for r in rows))


def test_each_attempt_carries_its_own_runs_provenance(bsw) -> None:
    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    _append_new_run(bsw)
    d = TestClient(create_app(bsw)).get(f"/api/campaigns/LUZON/years/{YEAR}/days/35").json()
    new, old = d["attempts"]  # newest first
    assert (new["run"], old["run"]) == ("r2", "r1")
    p = new["provenance"]
    assert p["recorded"] is True
    assert p["started_by"] == "processing"
    assert p["command"] == "bernese-run-year --campaign LUZON --run"
    assert p["code_version"] == "0123456789"
    assert (p["pcf"], p["products"], p["product_tier"], p["config_hash"]) == (
        "LUZON_DLY", "COD0OPSFIN", "final", "def",
    )  # fmt: skip
    # The old run predates provenance: nothing invented, for that attempt only.
    q = old["provenance"]
    assert q["recorded"] is False
    assert q["started_by"] is q["command"] is q["code_version"] is q["product_tier"] is None
    assert q["config_hash"] == "abc", "the config hash was recorded before #318"


def test_the_day_block_describes_the_latest_attempts_run(bsw) -> None:
    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    c = TestClient(create_app(bsw))
    before = c.get(f"/api/campaigns/LUZON/years/{YEAR}/days/35").json()["provenance"]
    assert (before["run"], before["recorded"], before["started_by"]) == ("r1", False, None)
    _append_new_run(bsw)
    after = c.get(f"/api/campaigns/LUZON/years/{YEAR}/days/35").json()["provenance"]
    assert (after["run"], after["recorded"]) == ("r2", True)
    assert after["started_by"] == "processing"
    assert after["code_version"] == "0123456789"
    assert after["product_tier"] == "final"
    assert after["config_hash"] == "def"
    assert after["pcf"] == "LUZON_DLY.PCF"


def test_code_version_says_when_the_tree_was_dirty_or_unknown() -> None:
    from bsw_console.status import run_provenance

    base = {"user": "u", "code": {"commit": "a" * 40, "dirty": True}}
    assert run_provenance(base)["code_version"] == "aaaaaaaaaa (dirty)"
    base["code"] = {"commit": "a" * 40, "dirty": None}
    assert run_provenance(base)["code_version"] == "aaaaaaaaaa (dirty unknown)"
    base["code"] = {"commit": "unknown", "dirty": None}
    assert run_provenance(base)["code_version"] == "unknown"
    assert run_provenance({"user": "u", "sudo_user": "x"})["started_by"] == "u (sudo from x)"
    assert run_provenance(None)["recorded"] is False


# --- the time series (stage 5): pogf_geodetic_suite.timeseries.status, in-process ---------


def test_time_series_lists_the_stations_and_the_outlier_mode(client) -> None:
    body = client.get("/api/campaigns/LUZON/time-series").json()
    assert body["configured"] is True and body["available"] is True
    assert body["stations"] == ["SYN1"], "the reference is the origin, not a station to plot"
    assert body["reference"] == "REF0"
    assert body["outlier_mode"] == "record", "status's default, kept"


def test_one_stations_status_is_what_station_status_returns(client, bsw) -> None:
    import hashlib

    from bsw_console import timeseries
    from pogf_geodetic_suite.timeseries.status import station_status

    body = client.get("/api/campaigns/LUZON/time-series/syn1").json()
    assert body["configured"] is True and body["available"] is True
    dirs = timeseries.crd_dirs(bsw, bsw.campaign("LUZON"))
    direct = station_status(dirs, "SYN1", "REF0", offsets_catalog=bsw.ts_offsets)
    for key in ("schema", "station", "velocity", "segments", "outlier_rule", "offsets", "warnings"):
        assert body[key] == direct[key], key
    assert body["outlier_rule"]["mode"] == "record"
    assert (
        body["offsets_catalog"]["sha256"] == hashlib.sha256(bsw.ts_offsets.read_bytes()).hexdigest()
    )
    assert len(body["segments"]) == 2, "split at the catalog's earthquake"
    assert sum(seg["n_outliers"] for seg in body["segments"]) >= 1, "the spike is flagged"
    assert set(body["velocity"]["sigma_mm_yr"]) == {"e", "n", "u"}


def test_time_series_not_configured_says_so_and_names_the_settings(bsw) -> None:
    import dataclasses

    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    c = TestClient(create_app(dataclasses.replace(bsw, ts_offsets=None)))
    for url in (
        "/api/campaigns/LUZON/time-series",
        "/api/campaigns/LUZON/time-series/SYN1",
    ):
        r = c.get(url)
        assert r.status_code == 200
        body = r.json()
        assert body["configured"] is False
        assert "not configured" in body["message"]
        assert body["missing"] == ["BSW_CONSOLE_TS_OFFSETS"]


def test_a_station_status_cannot_compute_is_explained_not_raised(client) -> None:
    body = client.get("/api/campaigns/LUZON/time-series/NOPE").json()
    assert body["configured"] is True and body["available"] is False
    assert "NOPE" in body["message"]
    ref = client.get("/api/campaigns/LUZON/time-series/REF0").json()
    assert ref["available"] is False and "reference" in ref["message"]


def test_time_series_station_is_four_characters_never_a_path(client) -> None:
    for code in ("SYN12", "S", "..%2F.."):
        assert client.get(f"/api/campaigns/LUZON/time-series/{code}").status_code in (
            404,
            422,
        )
    assert client.post("/api/campaigns/LUZON/time-series/SYN1").status_code == 405


def test_a_worker_run_credits_who_asked_not_the_service_account() -> None:
    """bernese-worker runs as the service account and tags run_start with the
    request's submitted_by. The person who asked is who started it."""
    from bsw_console.status import run_provenance

    start = {"user": "gps3", "code": {"commit": "a" * 40, "dirty": False},
             "pcf": "LUZON_DLY", "submitted_by": "abc", "request": "20261105T021500.000000Z-0a1b2c3d"}  # fmt: skip
    who = run_provenance(start)["started_by"]
    assert who.startswith("abc")
    assert "gps3" in who and "20261105T021500.000000Z-0a1b2c3d" in who


def test_odd_ledger_field_types_do_not_break_the_day_page() -> None:
    """A hand-edited or foreign run_start (code not an object) is shown, not a 500."""
    from bsw_console.status import run_provenance

    p = run_provenance({"user": "u", "code": "abc123", "pcf": "X", "command": 5})
    assert p["recorded"] is True and p["code_version"] == "unknown"


# --- the reference station is chosen on the page -----------------------------------------


def test_the_reference_is_chosen_per_request_and_the_setting_is_only_the_default(client) -> None:
    default = client.get("/api/campaigns/LUZON/time-series").json()
    assert default["reference"] == "REF0" and default["default_reference"] == "REF0"
    assert default["all_stations"] == ["REF0", "SYN1"], "every candidate, the default included"
    flipped = client.get("/api/campaigns/LUZON/time-series?reference=syn1").json()
    assert flipped["available"] is True and flipped["reference"] == "SYN1"
    assert flipped["stations"] == ["REF0"], "relative to SYN1, REF0 is the one to plot"
    one = client.get("/api/campaigns/LUZON/time-series/REF0?reference=SYN1").json()
    assert one["available"] is True and one["reference"] == "SYN1"


def test_without_a_default_the_page_is_asked_to_choose(bsw) -> None:
    import dataclasses

    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    c = TestClient(create_app(dataclasses.replace(bsw, ts_reference=None)))
    body = c.get("/api/campaigns/LUZON/time-series").json()
    assert body["configured"] is True and body["available"] is True
    assert body["reference"] is None and body["stations"] == []
    assert body["all_stations"] == ["REF0", "SYN1"]
    assert "Choose a reference" in body["message"]
    one = c.get("/api/campaigns/LUZON/time-series/SYN1").json()
    assert one["available"] is False and "reference" in one["message"]


def test_a_reference_the_files_do_not_hold_is_explained(client) -> None:
    body = client.get("/api/campaigns/LUZON/time-series?reference=NOPE").json()
    assert body["available"] is False and "NOPE" in body["message"]


def test_a_reference_is_four_characters_never_a_path(client) -> None:
    for ref in ("REF00", "..%2F..", "R-F0"):
        assert (
            client.get(f"/api/campaigns/LUZON/time-series?reference={ref}").status_code
            == 422
        )
        assert (
            client.get(
                f"/api/campaigns/LUZON/time-series/SYN1?reference={ref}"
            ).status_code
            == 422
        )


def test_a_station_only_in_an_undated_crd_is_not_offered_as_a_reference(bsw) -> None:
    """An a priori or combined CRD sits in the same directory with no YYDDD in its
    name. The ENU pipeline skips it, so its stations must not be candidates
    either: a reference the pipeline would then refuse."""
    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    some = next(iter(sorted(_ts_dir(bsw).glob("*.CRD"))))
    (_ts_dir(bsw) / "APRIORI.CRD").write_text(some.read_text().replace("SYN1", "XTRA"))
    body = TestClient(create_app(bsw)).get("/api/campaigns/LUZON/time-series").json()
    assert body["all_stations"] == ["REF0", "SYN1"]


def test_candidates_follow_the_directory_when_a_file_is_added(bsw) -> None:
    from bsw_console import timeseries

    assert timeseries.stations_in([_ts_dir(bsw)]) == ["REF0", "SYN1"]
    some = next(iter(sorted(_ts_dir(bsw).glob("*.CRD"))))
    (_ts_dir(bsw) / "F1_22001.CRD").write_text(some.read_text().replace("SYN1", "NEW1"))
    assert timeseries.stations_in([_ts_dir(bsw)]) == ["NEW1", "REF0", "SYN1"]


# --- the time series is the campaign's whole history -------------------------------------


def test_time_series_reads_every_year_of_the_campaign_as_one_series(client, bsw) -> None:
    body = client.get("/api/campaigns/LUZON/time-series").json()
    assert body["campaign"] == "LUZON"
    assert body["crd_dirs"][:2] == [
        str(bsw.savedisk / "LUZON" / "2020" / "STA"),
        str(bsw.savedisk / "LUZON" / "2021" / "STA"),
    ], "oldest first"
    one = client.get("/api/campaigns/LUZON/time-series/SYN1").json()
    t = one["series"]["t"]
    assert t == sorted(t) and int(t[0]) == 2020 and int(t[-1]) == 2021
    assert one["velocity"]["span_yr"] > 0.5
    assert len(one["segments"]) == 2, "the earthquake splits the whole series, not a year"


def test_a_campaign_with_no_sta_folder_says_so(client, bsw) -> None:
    import dataclasses

    from bsw_console.main import create_app
    from bsw_console.settings import Campaign
    from fastapi.testclient import TestClient

    other = dataclasses.replace(bsw, campaigns=[Campaign("EMPTY", "NO_SUCH_PCF", "EMP")])
    c = TestClient(create_app(other))
    body = c.get("/api/campaigns/EMPTY/time-series").json()
    assert body["available"] is False and "EMPTY" in body["message"]
    assert "STA" in body["message"] and body["crd_dirs"] == []


def test_a_year_folder_with_no_usable_file_does_not_hide_the_others(client, bsw) -> None:
    sta = bsw.savedisk / "LUZON" / "2019" / "STA"
    sta.mkdir(parents=True)
    body = client.get("/api/campaigns/LUZON/time-series").json()
    assert body["available"] is True and body["stations"] == ["SYN1"]
    assert str(sta) in body["crd_dirs"]
    assert client.get("/api/campaigns/LUZON/time-series/SYN1").json()["available"] is True


def test_the_year_routes_are_gone(client) -> None:
    assert client.get("/api/campaigns/LUZON/years/2021/time-series").status_code in (404, 405)


def _ts_dir(bsw):
    """Where conftest files the second year of the synthetic series."""
    return bsw.savedisk / "LUZON" / "2021" / "STA"


def test_the_summary_says_where_stations_are_and_how_far_from_the_reference(client) -> None:
    body = client.get("/api/campaigns/LUZON/time-series").json()
    assert set(body["positions"]) == {"REF0", "SYN1"}
    assert -90 <= body["positions"]["SYN1"]["lat"] <= 90
    assert body["reference_warn_deg"] == 5.0
    assert set(body["distances"]) == {"SYN1"}, "the reference has no distance from itself"
    one = client.get("/api/campaigns/LUZON/time-series/SYN1").json()
    assert abs(body["distances"]["SYN1"] - one["reference_distance_deg"]) < 0.01


def test_with_no_reference_positions_are_given_and_distances_are_not(bsw) -> None:
    import dataclasses

    from bsw_console.main import create_app
    from fastapi.testclient import TestClient

    c = TestClient(create_app(dataclasses.replace(bsw, ts_reference=None)))
    body = c.get("/api/campaigns/LUZON/time-series").json()
    assert set(body["positions"]) == {"REF0", "SYN1"} and body["distances"] == {}
