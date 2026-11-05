"""Outlier decisions on the Time series page (outlier_review_design.md, #339).

A signed-in person confirms or overrides the rule's flag on one epoch; the
decision is appended to the console's state, carrying the reference and the
CRD file's hash, and drives only a side-by-side fit marked as not published.
The synthetic series (conftest) has one planted spike, 2021 DOY 196, which the
rule flags.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from bsw_console import outliers
from bsw_console.main import create_app
from bsw_console.settings import Settings
from fastapi.testclient import TestClient

BASE = "/api/campaigns/LUZON/years/2021/time-series/SYN1"
SPIKE = "2021-196"  # flagged by the rule
QUIET = "2021-016"  # not flagged
ME = {"X-Remote-User": "abc"}


@pytest.fixture
def signed(bsw: Settings) -> TestClient:
    """The console behind a sign-in proxy (the test client's address)."""
    return TestClient(
        create_app(dataclasses.replace(bsw, trusted_proxies=frozenset({"testclient"})))
    )


def decide(
    c: TestClient, epoch: str, decision: str, *, flag: bool, reason: str = "", ref: str = "REF0"
):
    body = {
        "epoch": epoch,
        "decision": decision,
        "reason": reason,
        "reference": ref,
        "auto_flag": flag,
    }
    return c.post(f"{BASE}/decisions", json=body, headers=ME)


def test_recording_needs_someone_signed_in(bsw: Settings) -> None:
    r = TestClient(create_app(bsw)).post(
        f"{BASE}/decisions",
        json={"epoch": SPIKE, "decision": "outlier", "reference": "REF0", "auto_flag": True},
        headers=ME,  # no trusted proxy, so the header proves nothing
    )
    assert r.status_code == 403
    assert not outliers.path(bsw).exists()


def test_confirming_a_flag_is_recorded_with_who_and_what_it_was_made_on(signed, bsw) -> None:
    r = decide(signed, SPIKE, "outlier", flag=True)
    assert r.status_code == 201, r.text
    (row,) = [json.loads(x) for x in outliers.path(bsw).read_text().splitlines()]
    assert (row["by"], row["epoch"], row["decision"], row["reference"]) == (
        "abc",
        SPIKE,
        "outlier",
        "REF0",
    )
    assert row["source"]["file"] == "F1_21196.CRD" and len(row["source"]["sha256"]) == 64


def test_going_against_the_flag_needs_a_reason(signed) -> None:
    assert decide(signed, QUIET, "outlier", flag=False).status_code == 422
    assert decide(signed, SPIKE, "not_outlier", flag=True).status_code == 422
    assert decide(signed, QUIET, "outlier", flag=False, reason="multipath").status_code == 201


@pytest.mark.parametrize(
    "body, code",
    [
        ({"epoch": "2021-1", "decision": "outlier", "reference": "REF0", "auto_flag": True}, 422),
        ({"epoch": SPIKE, "decision": "delete", "reference": "REF0", "auto_flag": True}, 422),
        ({"epoch": SPIKE, "decision": "outlier", "reference": "../x", "auto_flag": True}, 422),
        ({"epoch": SPIKE, "decision": "outlier", "reference": "REF0"}, 422),
        ({"epoch": "2021-200", "decision": "outlier", "reference": "REF0", "auto_flag": True}, 404),
    ],
    ids=["bad-epoch", "bad-decision", "bad-reference", "no-flag", "no-crd-that-day"],
)
def test_malformed_decisions_are_refused(signed, bsw, body, code) -> None:
    assert signed.post(f"{BASE}/decisions", json=body, headers=ME).status_code == code
    assert not outliers.path(bsw).exists()


def test_the_latest_decision_wins_and_clearing_removes_it(signed) -> None:
    decide(signed, SPIKE, "outlier", flag=True)
    decide(signed, SPIKE, "not_outlier", flag=True, reason="a real step, not noise")
    (d,) = signed.get(f"{BASE}/decisions?reference=REF0").json()["decisions"]
    assert (d["decision"], d["history"]) == ("not_outlier", 2)
    decide(signed, SPIKE, "cleared", flag=True, reason="undo")
    assert signed.get(f"{BASE}/decisions?reference=REF0").json()["decisions"] == []


def test_a_confirmed_outlier_drives_only_the_side_by_side_fit(signed) -> None:
    before = signed.get(f"{BASE}?reference=REF0").json()
    assert before["decided_fit"] is None and before["decisions"] == []
    decide(signed, SPIKE, "outlier", flag=True)
    after = signed.get(f"{BASE}?reference=REF0").json()
    assert after["velocity"] == before["velocity"], "the published fit never changes"
    fit = after["decided_fit"]
    assert fit["available"] is True and fit["excluded"] == [SPIKE]
    assert (
        sum(s["n_fit"] for s in fit["segments"]) == sum(s["n_fit"] for s in before["segments"]) - 1
    )


def test_a_decision_on_a_reprocessed_day_is_marked_and_not_applied(signed, bsw) -> None:
    decide(signed, SPIKE, "outlier", flag=True)
    crd = bsw.savedisk / "LUZON" / "2021" / "STA" / "F1_21196.CRD"
    crd.write_text(crd.read_text() + "\n")  # the day was re-solved: different bytes
    body = signed.get(f"{BASE}?reference=REF0").json()
    (d,) = body["decisions"]
    assert d["superseded"] is True
    assert body["decided_fit"] is None


def test_a_decision_made_against_another_reference_is_marked_and_not_applied(signed, bsw) -> None:
    decide(signed, SPIKE, "outlier", flag=True)
    from bsw_console import timeseries

    c = bsw.campaign("LUZON")
    (d,) = outliers.current(bsw, c, 2021, "SYN1", timeseries.crd_dir(bsw, c, 2021), "XXXX")
    assert d["other_reference"] is True
    assert outliers.excluded_sessions([d]) == []
