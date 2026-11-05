"""Stage 3: the run buttons queue requests for the run worker, behind one gate.

The gate's order is the contract (bsw_console/actions.py, THE GATE): actions
switched on, someone signed in, that someone an operator, a worker running.
Each test checks the answer and that nothing reached the queue when refused.
"""

from __future__ import annotations

import dataclasses
import fcntl
import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from bernese_workflow import run_queue
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


def queued(s: Settings) -> list[dict]:
    return [json.loads(p.read_text()) for p in run_queue.Queue(s.worker_state).pending()]


def start_body(**over: object) -> dict:
    return {"campaign": "LUZON", "year": YEAR, "from": 35, "to": 36, **over}


def test_signed_out_is_refused_and_nothing_is_queued(on: Settings, worker) -> None:
    r = TestClient(create_app(on)).post("/api/runs/start", json=start_body())
    assert r.status_code == 403
    assert "Sign in" in r.json()["detail"]
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


def test_start_queues_the_campaigns_daily_pcf_under_its_prefix(on: Settings, worker) -> None:
    r = TestClient(create_app(on)).post("/api/runs/start", json=start_body(), headers=OPERATOR)
    assert r.status_code == 202, r.text
    body = r.json()
    (req,) = queued(on)
    assert body["queued"] == req["id"] and body["by"] == "abc"
    assert req["kind"] == run_queue.START
    assert (req["campaign"], req["repr_prefix"], req["pcf"]) == ("LUZON", "LZY", "LUZON_DLY")
    assert (req["year"], req["from"], req["to"]) == (YEAR, 35, 36)
    assert req["submitted_by"] == "abc"


def test_preflight_queues_a_preflight(on: Settings, worker) -> None:
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


def _running(q: run_queue.Queue, campaign: str) -> str:
    """Put a request in active/ and name it in status.json, as a running worker does."""
    req = run_queue.make_request(
        run_queue.START, "abc", campaign=campaign, repr_prefix="LZY", pcf="LUZON_DLY",
        year=YEAR, **{"from": 35, "to": 36},
    )  # fmt: skip
    (q.active / f"{req['id']}.json").write_text(json.dumps(req))
    (q.root / "status.json").write_text(json.dumps({"state": "running", "active": req["id"]}))
    return req["id"]


def test_stop_targets_the_request_the_worker_is_running(on: Settings, worker) -> None:
    rid = _running(worker, "LUZON")
    r = TestClient(create_app(on)).post(
        "/api/runs/stop", json={"campaign": "LUZON", "year": YEAR, "run": "x"}, headers=OPERATOR
    )
    assert r.status_code == 202, r.text
    (req,) = queued(on)
    assert (req["kind"], req["target"]) == (run_queue.STOP, rid)


def test_stop_with_the_worker_idle_is_409(on: Settings, worker) -> None:
    (worker.root / "status.json").write_text(json.dumps({"state": "idle", "active": None}))
    r = TestClient(create_app(on)).post(
        "/api/runs/stop", json={"campaign": "LUZON", "year": YEAR}, headers=OPERATOR
    )
    assert r.status_code == 409
    assert "command line" in r.json()["detail"]
    assert queued(on) == []


def test_stop_for_another_campaigns_run_is_409(on: Settings, worker) -> None:
    _running(worker, "PHREF")
    r = TestClient(create_app(on)).post(
        "/api/runs/stop", json={"campaign": "LUZON", "year": YEAR}, headers=OPERATOR
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
    assert "nobody is signed in" in nobody["blocked_because"]


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
