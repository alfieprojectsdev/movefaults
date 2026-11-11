"""Stage 3: the run buttons queue requests for the run worker, behind one gate.

The gate's order is the contract (bsw_console/actions.py, THE GATE): actions
switched on, someone signed in, that someone an operator, a worker running.
Each test checks the answer and that nothing reached the queue when refused.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import fcntl
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from bernese_workflow import run_queue
from bsw_console import actions
from bsw_console.main import create_app
from bsw_console.settings import Settings
from fastapi.testclient import TestClient

YEAR = 2025
OPERATOR = {"X-Remote-User": "abc"}


@pytest.fixture
def on(bsw: Settings, tmp_path: Path) -> Settings:
    """Actions on, one operator, the test client trusted as the sign-in proxy."""
    return dataclasses.replace(
        bsw,
        actions_enabled=True,
        operators=frozenset({"abc"}),
        trusted_proxies=frozenset({"testclient"}),
        worker_state=tmp_path / "worker",
    )


@pytest.fixture
def worker(on: Settings) -> Iterator[run_queue.Queue]:
    """A live worker, as the console sees one: worker.lock held under flock."""
    q = run_queue.Queue(on.worker_state).ensure()
    with open(q.root / "worker.lock", "a+") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield q


@pytest.fixture
def checks_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    """The plan's checks pass. The synthetic tree has no products, so the real
    build marks it failing; test_failing_checks_refuse_start uses the real one."""
    monkeypatch.setattr(
        "bsw_console.actions.plans.build",
        lambda *a, **k: {"checks": [{"level": "ok", "title": "fine"}]},
    )


def preflight_ok(
    s: Settings, a: int = 35, b: int = 36, *, outcome: str = "ok", allowed: bool | None = None
) -> None:
    """A finished preflight for these days, as the worker leaves it in done/."""
    q = run_queue.Queue(s.worker_state).ensure()
    req = run_queue.make_request(
        run_queue.PREFLIGHT, "abc", campaign="LUZON", repr_prefix="LZY", pcf="LUZON_DLY",
        year=YEAR, allow_header_mismatches=allowed, **{"from": a, "to": b},
    )  # fmt: skip
    req.update(outcome=outcome, finished=run_queue.now_utc().isoformat())
    (q.done / f"{req['id']}.json").write_text(json.dumps(req))


def queued(s: Settings) -> list[dict]:
    return [json.loads(p.read_text()) for p in run_queue.Queue(s.worker_state).pending()]


def start_body(**over: object) -> dict:
    return {"campaign": "LUZON", "year": YEAR, "from": 35, "to": 36, **over}


def test_signed_out_is_refused_and_nothing_is_queued(on: Settings, worker) -> None:
    r = TestClient(create_app(on)).post("/api/runs/start", json=start_body())
    assert r.status_code == 403
    assert "signed in" in r.json()["detail"]
    assert queued(on) == []


def test_a_user_who_is_not_an_operator_is_refused(on: Settings, worker) -> None:
    r = TestClient(create_app(on)).post(
        "/api/runs/start", json=start_body(), headers={"X-Remote-User": "xyz"}
    )
    assert r.status_code == 403
    assert queued(on) == []


def test_an_empty_operator_list_lets_nobody_act(on: Settings, worker) -> None:
    s = dataclasses.replace(on, operators=frozenset())
    r = TestClient(create_app(s)).post("/api/runs/start", json=start_body(), headers=OPERATOR)
    assert r.status_code == 403
    assert queued(s) == []


def test_the_header_from_an_untrusted_address_signs_nobody_in(on: Settings, worker) -> None:
    s = dataclasses.replace(on, trusted_proxies=frozenset())
    r = TestClient(create_app(s)).post("/api/runs/start", json=start_body(), headers=OPERATOR)
    assert r.status_code == 403
    assert queued(s) == []


def test_no_worker_running_is_503_and_nothing_is_queued(on: Settings) -> None:
    r = TestClient(create_app(on)).post("/api/runs/start", json=start_body(), headers=OPERATOR)
    assert r.status_code == 503
    assert "No run worker" in r.json()["detail"]
    assert queued(on) == []


def test_start_queues_the_campaigns_daily_pcf_under_its_prefix(
    on: Settings, worker, checks_pass
) -> None:
    preflight_ok(on)
    r = TestClient(create_app(on)).post("/api/runs/start", json=start_body(), headers=OPERATOR)
    assert r.status_code == 202, r.text
    body = r.json()
    (req,) = queued(on)
    assert body["queued"] == req["id"] and body["by"] == "abc"
    assert req["kind"] == run_queue.START
    assert (req["campaign"], req["repr_prefix"], req["pcf"]) == ("LUZON", "LZY", "LUZON_DLY")
    assert (req["year"], req["from"], req["to"]) == (YEAR, 35, 36)
    assert req["submitted_by"] == "abc"


def test_preflight_queues_a_preflight(on: Settings, worker, checks_pass) -> None:
    r = TestClient(create_app(on)).post("/api/preflight", json=start_body(), headers=OPERATOR)
    assert r.status_code == 202, r.text
    assert queued(on)[0]["kind"] == run_queue.PREFLIGHT


@pytest.mark.parametrize(
    "over",
    [{"pcf": "LZFLT_DLY"}, {"skipped": [3]}, {"rnxgra": "short"}],
    ids=["another-pcf", "skipped-steps", "rnxgra-preset"],
)
def test_a_plan_the_worker_would_run_differently_is_refused(on: Settings, worker, over) -> None:
    r = TestClient(create_app(on)).post(
        "/api/runs/start", json=start_body(**over), headers=OPERATOR
    )
    assert r.status_code == 422
    assert "command line" in r.json()["detail"]
    assert queued(on) == []


def test_days_the_queue_would_reject_are_422(on: Settings, worker) -> None:
    r = TestClient(create_app(on)).post(
        "/api/runs/start", json=start_body(**{"from": 40, "to": 30}), headers=OPERATOR
    )
    assert r.status_code == 422
    assert queued(on) == []


def test_an_unknown_campaign_is_404(on: Settings, worker) -> None:
    r = TestClient(create_app(on)).post(
        "/api/runs/start", json=start_body(campaign="NOPE"), headers=OPERATOR
    )
    assert r.status_code == 404
    assert queued(on) == []


def test_redo_needs_a_reason_and_then_queues_one_day(on: Settings, worker) -> None:
    c = TestClient(create_app(on))
    bare = {"campaign": "LUZON", "year": YEAR, "doy": 35}
    assert c.post("/api/redo", json=bare, headers=OPERATOR).status_code == 422
    assert queued(on) == []
    r = c.post("/api/redo", json={**bare, "reason": "wrong STA row"}, headers=OPERATOR)
    assert r.status_code == 202, r.text
    (req,) = queued(on)
    assert (req["kind"], req["doy"], req["reason"]) == (run_queue.REDO, 35, "wrong STA row")


def test_a_campaign_that_allows_header_mismatches_sends_it_with_its_requests(
    on: Settings, worker
) -> None:
    flagged = [
        dataclasses.replace(c, allow_header_mismatches=c.name == "LUZON") for c in on.campaigns
    ]
    c = TestClient(create_app(dataclasses.replace(on, campaigns=flagged)))
    preview = c.get(f"/api/campaigns/LUZON/years/{YEAR}/days/35/redo").json()
    assert preview["allow_header_mismatches"] is True
    r = c.post("/api/redo", json={"campaign": "LUZON", "year": YEAR, "doy": 35, "reason": "r"},
               headers=OPERATOR)  # fmt: skip
    assert r.status_code == 202, r.text
    (req,) = queued(on)
    assert req["allow_header_mismatches"] is True


def test_any_other_campaign_sends_no_such_field(on: Settings, worker) -> None:
    c = TestClient(create_app(on))
    assert (
        c.get(f"/api/campaigns/LUZON/years/{YEAR}/days/35/redo").json()["allow_header_mismatches"]
        is False
    )
    r = c.post("/api/redo", json={"campaign": "LUZON", "year": YEAR, "doy": 35, "reason": "r"},
               headers=OPERATOR)  # fmt: skip
    assert r.status_code == 202, r.text
    (req,) = queued(on)
    assert "allow_header_mismatches" not in req


def _running(q: run_queue.Queue, campaign: str) -> str:
    """Put a request in active/ and name it in status.json, as a running worker does."""
    req = run_queue.make_request(
        run_queue.START, "abc", campaign=campaign, repr_prefix="LZY", pcf="LUZON_DLY",
        year=YEAR, **{"from": 35, "to": 36},
    )  # fmt: skip
    (q.active / f"{req['id']}.json").write_text(json.dumps(req))
    (q.root / "status.json").write_text(json.dumps({"state": "running", "active": req["id"]}))
    return req["id"]


def _ledger_run(s: Settings, run: str, request: str | None) -> None:
    """Append a run_start to LUZON 2025's ledger, tagged with ``request`` as the worker tags it."""
    from bsw_console import status

    path = status.ledger_path(s, s.campaign("LUZON"), YEAR)
    entry = {"v": 1, "ts": 1.0, "event": "run_start", "run": run, "campaign": "LUZON",
             "year": YEAR, "doys": [35, 36], "banked": []}  # fmt: skip
    if request:
        entry["request"] = request
    with path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")


def test_stop_targets_the_request_the_worker_is_running(on: Settings, worker) -> None:
    rid = _running(worker, "LUZON")
    _ledger_run(on, "w0rkr0n1", rid)
    r = TestClient(create_app(on)).post(
        "/api/runs/stop",
        json={"campaign": "LUZON", "year": YEAR, "run": "w0rkr0n1"},
        headers=OPERATOR,
    )
    assert r.status_code == 202, r.text
    (req,) = queued(on)
    assert (req["kind"], req["target"]) == (run_queue.STOP, rid)


def test_stop_with_the_worker_idle_is_409(on: Settings, worker) -> None:
    (worker.root / "status.json").write_text(json.dumps({"state": "idle", "active": None}))
    r = TestClient(create_app(on)).post(
        "/api/runs/stop", json={"campaign": "LUZON", "year": YEAR, "run": "r"}, headers=OPERATOR
    )
    assert r.status_code == 409
    assert "command line" in r.json()["detail"]
    assert queued(on) == []


def test_stop_for_another_campaigns_run_is_409(on: Settings, worker) -> None:
    _running(worker, "PHREF")
    r = TestClient(create_app(on)).post(
        "/api/runs/stop", json={"campaign": "LUZON", "year": YEAR, "run": "r"}, headers=OPERATOR
    )
    assert r.status_code == 409
    assert queued(on) == []


def test_a_cross_site_or_non_json_post_is_refused(on: Settings, worker) -> None:
    c = TestClient(create_app(on))
    r = c.post(
        "/api/runs/start",
        json=start_body(),
        headers={**OPERATOR, "Sec-Fetch-Site": "cross-site"},
    )
    assert r.status_code == 403
    r = c.post(
        "/api/runs/start",
        content=json.dumps(start_body()),
        headers={**OPERATOR, "Content-Type": "text/plain"},
    )
    assert r.status_code == 415
    assert queued(on) == []


def test_worker_endpoint_and_session_say_who_can_act(on: Settings, worker) -> None:
    c = TestClient(create_app(on))
    w = c.get("/api/worker", headers=OPERATOR).json()
    assert w["alive"] is True and w["blocked_because"] == []
    assert c.get("/api/session", headers=OPERATOR).json()["can_act"] is True
    nobody = c.get("/api/worker").json()
    assert any("nobody is signed in" in m for m in nobody["blocked_because"])


def test_off_by_default_even_with_a_worker_and_an_operator(bsw: Settings, tmp_path) -> None:
    s = dataclasses.replace(
        bsw,
        operators=frozenset({"abc"}),
        trusted_proxies=frozenset({"testclient"}),
        worker_state=tmp_path / "worker",
    )
    r = TestClient(create_app(s)).post("/api/runs/start", json=start_body(), headers=OPERATOR)
    assert r.status_code == 501
    assert queued(s) == []


def test_stop_leaves_a_command_line_run_alone(on: Settings, worker) -> None:
    """The page's run is a bernese-run-year run with the same campaign and year
    as the worker's request: the stop must not land on the worker's job."""
    rid = _running(worker, "LUZON")
    _ledger_run(on, "w0rkr0n1", rid)
    _ledger_run(on, "c0mmand1", None)
    r = TestClient(create_app(on)).post(
        "/api/runs/stop",
        json={"campaign": "LUZON", "year": YEAR, "run": "c0mmand1"},
        headers=OPERATOR,
    )
    assert r.status_code == 409
    assert queued(on) == []


def test_start_needs_a_finished_preflight_for_the_same_days(
    on: Settings, worker, checks_pass
) -> None:
    c = TestClient(create_app(on))
    assert c.post("/api/runs/start", json=start_body(), headers=OPERATOR).status_code == 409
    preflight_ok(on, 35, 40)  # other days
    preflight_ok(on, outcome="failed")  # these days, but failed
    r = c.post("/api/runs/start", json=start_body(), headers=OPERATOR)
    assert r.status_code == 409
    assert "preflight" in r.json()["detail"]
    assert queued(on) == []


def test_a_preflight_counts_only_under_the_same_header_rule(
    on: Settings, worker, checks_pass
) -> None:
    preflight_ok(on, allowed=True)  # passed only because mismatches were allowed
    c = TestClient(create_app(on))
    assert c.post("/api/runs/start", json=start_body(), headers=OPERATOR).status_code == 409
    flagged = [
        dataclasses.replace(x, allow_header_mismatches=x.name == "LUZON") for x in on.campaigns
    ]
    c = TestClient(create_app(dataclasses.replace(on, campaigns=flagged)))
    assert c.post("/api/runs/start", json=start_body(), headers=OPERATOR).status_code == 202


def test_failing_checks_refuse_start_and_preflight(on: Settings, worker) -> None:
    """The server re-runs the plan's checks; a stale page or a direct POST
    cannot queue a plan whose checks fail (the synthetic tree has no products)."""
    preflight_ok(on)
    c = TestClient(create_app(on))
    for route in ("/api/runs/start", "/api/preflight"):
        r = c.post(route, json=start_body(), headers=OPERATOR)
        assert r.status_code == 409
        assert "checks fail" in r.json()["detail"]
    assert queued(on) == []


def test_the_gate_runs_before_the_campaign_or_body_is_read(on: Settings, worker) -> None:
    c = TestClient(create_app(on))
    r = c.post("/api/runs/start", json=start_body(campaign="NOPE"))
    assert r.status_code == 403
    r = c.post("/api/runs/start", content="not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 403


def test_a_chunked_body_over_the_limit_is_cut_off(on: Settings, worker) -> None:
    def chunks():
        for _ in range(100):
            yield b" " * 1024

    r = TestClient(create_app(on)).post(
        "/api/runs/start",
        content=chunks(),
        headers={**OPERATOR, "Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert queued(on) == []


def test_a_header_that_is_not_a_bare_username_signs_nobody_in(on: Settings, worker) -> None:
    s = dataclasses.replace(on, operators=frozenset({"abc@example.org"}))
    r = TestClient(create_app(s)).post(
        "/api/runs/start", json=start_body(), headers={"X-Remote-User": "abc@example.org"}
    )
    assert r.status_code == 403
    assert "signed in" in r.json()["detail"]


def test_the_plan_page_lists_the_missing_preflight_and_the_gate(on: Settings, worker) -> None:
    c = TestClient(create_app(on))
    why = c.get(f"/api/campaigns/LUZON/years/{YEAR}/plan?start=35&end=36", headers=OPERATOR).json()[
        "start_blocked_because"
    ]
    assert "the preflight for these days has not finished ok" in why
    signed_out = c.get(f"/api/campaigns/LUZON/years/{YEAR}/plan?start=35&end=36").json()
    assert any("nobody is signed in" in m for m in signed_out["start_blocked_because"])


def _notify_status(
    s: Settings, *, age_min: float, errors: int = 0, operators: tuple[str, ...] = ()
) -> dt.datetime:
    now = dt.datetime(2026, 11, 6, 12, 0, tzinfo=dt.UTC)
    d = s.worker_state / "notify"
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(
        json.dumps(
            {
                "last_pass": (now - dt.timedelta(minutes=age_min)).isoformat(),
                "sent": 0,
                "errors": ["smtp said no to someone@example.org"] * errors,
                "operators": list(operators),
            }
        )
    )
    return now


def test_email_alerts_say_when_nobody_will_be_told(on: Settings) -> None:
    assert actions.email_alerts(on)["state"] == "off"
    now = _notify_status(on, age_min=5)
    assert actions.email_alerts(on, now=now)["state"] == "ok"
    now = _notify_status(on, age_min=31)
    assert actions.email_alerts(on, now=now)["state"] == "stale"
    now = _notify_status(on, age_min=5, errors=2)
    failing = actions.email_alerts(on, now=now)
    assert failing["state"] == "failing"
    assert "example.org" not in failing["text"]


def test_email_alerts_say_when_the_person_looking_has_no_address(on: Settings) -> None:
    now = _notify_status(on, age_min=5, operators=("AB",))
    assert actions.email_alerts(on, "ab", now)["state"] == "ok"
    missing = actions.email_alerts(on, "ZZ", now)
    assert missing["state"] == "no-address"
    assert "ZZ" in missing["text"]
    assert actions.email_alerts(on, "", now)["state"] == "ok"


def test_the_server_trusts_the_connecting_address_not_x_forwarded_for(monkeypatch) -> None:
    """Behind Caddy the peer is 127.0.0.1 and X-Forwarded-For names the browser.
    If uvicorn rewrote the client address from that header, X-Remote-User from
    the sign-in proxy would be ignored and nobody could sign in."""
    import uvicorn
    from bsw_console import main

    seen: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: seen.update(kw))
    monkeypatch.setattr(main, "create_app", lambda: object())
    main.start()
    assert seen["proxy_headers"] is False


def test_email_alerts_read_a_time_with_no_zone_as_off(on: Settings) -> None:
    d = on.worker_state / "notify"
    d.mkdir(parents=True, exist_ok=True)
    (d / "status.json").write_text(json.dumps({"last_pass": "2026-11-06T12:00:00", "errors": []}))
    assert actions.email_alerts(on)["state"] == "off"
