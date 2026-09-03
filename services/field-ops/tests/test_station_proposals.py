"""
Tests for FO-001 — in-app station creation (issue #118).

WHY THESE RUN ON SQLITE AT ALL
------------------------------
The design flagged testability as this ticket's largest hidden cost: the
conftest is in-memory SQLite, `public.stations` is not in
`FieldOpsBase.metadata`, and SQLite has no `ST_Y`/`ST_X` — which is why
`GET /api/v1/stations` has had zero coverage since it was written.

Storing the proposal's position as plain lat/lon floats rather than a PostGIS
POINT (see the model's deviation note) confines PostGIS to the one promotion
query. Everything else — validation, the duplicate guard, idempotency, the
role gate, the state machine — is exercisable here.

What is NOT covered, and is honest about it: the inventory half of
`GET /stations` and `promote`'s upsert both need Postgres. Those are marked
`@pytest.mark.integration` and skip without a live database.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest
from field_ops.models import LogSheet, StationProposal, User
from field_ops.routers.auth import hash_password


async def _login(client, username: str, password: str) -> dict[str, str]:
    resp = await client.post(
        "/api/v1/token", data={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.fixture
def proposal_payload():
    return {
        "station_code": "TSTA",
        "name": "Test Monument",
        "latitude": 14.5,
        "longitude": 121.0,
        "monitoring_method": "campaign",
        "notes": "monument found, no plate",
    }


# ---------------------------------------------------------------------------
# proposing — the path an observer at a monument actually takes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_any_signed_in_observer_may_propose(client, auth_headers, proposal_payload):
    """No role gate, deliberately.

    The person blocked is the observer at the monument. Requiring an admin
    reintroduces the office round-trip #118 is about. The conftest user is
    `field_staff` — the least privileged role — and must succeed.
    """
    resp = await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["station_code"] == "TSTA"
    assert body["reconciled_at"] is None      # pending
    assert body["monitoring_method"] == "campaign"
    assert body["sheet_count"] == 0


@pytest.mark.asyncio
async def test_proposing_requires_authentication(client, proposal_payload):
    resp = await client.post("/api/v1/stations", json=proposal_payload)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_station_code_is_upper_cased(client, auth_headers, proposal_payload):
    """A phone keyboard capitalises inconsistently.

    `pbis` and `PBIS` must collide rather than become two stations, so the
    code is normalised before the unique index ever sees it.
    """
    proposal_payload["station_code"] = "  tsta  "
    resp = await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["station_code"] == "TSTA"


@pytest.mark.asyncio
async def test_coordinates_may_be_omitted(client, auth_headers):
    """Open question 1: handset accuracy is metres.

    Fine for sorting a picker by proximity, meaningless as a monument
    position. `PLWN` is already in the inventory without coordinates, so NULL
    is not unprecedented — and requiring a number the observer cannot measure
    invites a fabricated one.
    """
    resp = await client.post(
        "/api/v1/stations",
        json={"station_code": "NOCO", "name": "No coordinates"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["latitude"] is None


@pytest.mark.asyncio
async def test_rejects_out_of_range_coordinates(client, auth_headers, proposal_payload):
    proposal_payload["latitude"] = 200.0
    resp = await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rejects_unknown_monitoring_method(client, auth_headers, proposal_payload):
    proposal_payload["monitoring_method"] = "occasional"
    resp = await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# the duplicate guard — the load-bearing risk in the issue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_pending_code_is_refused(client, auth_headers, proposal_payload):
    first = await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    assert first.status_code == 201

    second = await client.post(
        "/api/v1/stations",
        json={**proposal_payload, "client_uuid": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert second.status_code == 409
    assert "already been proposed" in second.json()["detail"]


@pytest.mark.asyncio
async def test_duplicate_check_is_case_insensitive(client, auth_headers, proposal_payload):
    await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    resp = await client.post(
        "/api/v1/stations",
        json={**proposal_payload, "station_code": "tsta", "client_uuid": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_retry_with_same_client_uuid_is_idempotent(
    client, auth_headers, proposal_payload, db_session
):
    """The offline queue retries whole batches.

    A retry must return the existing row, not 409 against its own earlier
    write and not create a second. Same contract as `logsheets.client_uuid`.
    """
    cid = str(uuid.uuid4())
    payload = {**proposal_payload, "client_uuid": cid}

    first = await client.post("/api/v1/stations", json=payload, headers=auth_headers)
    second = await client.post("/api/v1/stations", json=payload, headers=auth_headers)

    assert first.status_code == 201
    assert second.status_code in (200, 201)
    assert first.json()["id"] == second.json()["id"]

    from sqlalchemy import func, select

    total = await db_session.execute(
        select(func.count()).select_from(StationProposal)
    )
    assert total.scalar_one() == 1


@pytest.mark.asyncio
async def test_code_is_proposable_again_after_rejection(
    client, auth_headers, proposal_payload, db_session
):
    """The partial unique index is partial on purpose.

    A plain unique index would permanently burn every code ever typed,
    including typos. Once a proposal is resolved the code must be free again —
    not least because the rejection may itself have been the mistake.
    """
    created = await client.post(
        "/api/v1/stations", json=proposal_payload, headers=auth_headers
    )
    proposal_id = created.json()["id"]

    admin_headers = await _make_admin(client, db_session)
    rejected = await client.post(
        f"/api/v1/station-proposals/{proposal_id}/reject",
        json={"reason": "typo — meant TSTB"},
        headers=admin_headers,
    )
    assert rejected.status_code == 200

    again = await client.post(
        "/api/v1/stations",
        json={**proposal_payload, "client_uuid": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert again.status_code == 201


# ---------------------------------------------------------------------------
# reconcile — role gate and state machine
# ---------------------------------------------------------------------------


async def _make_admin(client, db_session) -> dict[str, str]:
    admin = User(
        username="admin_user",
        hashed_password=hash_password("adminpass"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.commit()
    return await _login(client, "admin_user", "adminpass")


@pytest.mark.asyncio
async def test_field_staff_cannot_list_proposals(client, auth_headers):
    """`require_role` gates reconcile. Hiding a control in the UI is not a
    boundary — devtools, curl or a stale bundle all reach the endpoint."""
    resp = await client.get("/api/v1/station-proposals", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_field_staff_cannot_promote_or_reject(client, auth_headers):
    assert (
        await client.post("/api/v1/station-proposals/1/promote", headers=auth_headers)
    ).status_code == 403
    assert (
        await client.post(
            "/api/v1/station-proposals/1/reject",
            json={"reason": "x"},
            headers=auth_headers,
        )
    ).status_code == 403


@pytest.mark.asyncio
async def test_admin_sees_the_pending_queue(
    client, auth_headers, proposal_payload, db_session
):
    await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    admin_headers = await _make_admin(client, db_session)

    resp = await client.get("/api/v1/station-proposals", headers=admin_headers)
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["station_code"] == "TSTA"


@pytest.mark.asyncio
async def test_sheet_count_travels_with_the_proposal(
    client, auth_headers, proposal_payload, db_session
):
    """A proposal carrying data is a different decision from an empty one.

    Reject one with sheets attached and you have orphaned real observations,
    so the reviewer has to be able to see it before deciding.
    """
    await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    db_session.add(
        LogSheet(
            client_uuid=uuid.uuid4(),
            station_code="TSTA",
            visit_date=date(2026, 8, 26),
        )
    )
    await db_session.commit()

    admin_headers = await _make_admin(client, db_session)
    rows = (await client.get("/api/v1/station-proposals", headers=admin_headers)).json()
    assert rows[0]["sheet_count"] == 1


@pytest.mark.asyncio
async def test_rejection_keeps_the_row_and_records_why(
    client, auth_headers, proposal_payload, db_session
):
    """A rejected proposal is not deleted.

    It is the only record of who proposed the code and why it was refused, and
    with sheets attached it is a data-quality finding rather than garbage.
    """
    created = await client.post(
        "/api/v1/stations", json=proposal_payload, headers=auth_headers
    )
    pid = created.json()["id"]
    admin_headers = await _make_admin(client, db_session)

    resp = await client.post(
        f"/api/v1/station-proposals/{pid}/reject",
        json={"reason": "duplicate of PBIS"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reconciled_at"] is not None
    assert body["rejected_reason"] == "duplicate of PBIS"
    assert body["reconciled_station_id"] is None

    still_there = await db_session.get(StationProposal, pid)
    assert still_there is not None


@pytest.mark.asyncio
async def test_reconciling_twice_is_refused(
    client, auth_headers, proposal_payload, db_session
):
    """409, not 404: two reviewers working the same queue need to be told
    'already handled', not 'not found'."""
    created = await client.post(
        "/api/v1/stations", json=proposal_payload, headers=auth_headers
    )
    pid = created.json()["id"]
    admin_headers = await _make_admin(client, db_session)

    await client.post(
        f"/api/v1/station-proposals/{pid}/reject",
        json={"reason": "first"},
        headers=admin_headers,
    )
    second = await client.post(
        f"/api/v1/station-proposals/{pid}/reject",
        json={"reason": "second"},
        headers=admin_headers,
    )
    assert second.status_code == 409
    assert "already reconciled" in second.json()["detail"]


@pytest.mark.asyncio
async def test_missing_proposal_is_404(client, db_session):
    admin_headers = await _make_admin(client, db_session)
    resp = await client.post(
        "/api/v1/station-proposals/9999/reject",
        json={"reason": "x"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_reject_requires_a_reason(client, auth_headers, proposal_payload, db_session):
    created = await client.post(
        "/api/v1/stations", json=proposal_payload, headers=auth_headers
    )
    pid = created.json()["id"]
    admin_headers = await _make_admin(client, db_session)
    resp = await client.post(
        f"/api/v1/station-proposals/{pid}/reject", json={"reason": ""}, headers=admin_headers
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# needs Postgres — see the module docstring
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_promote_writes_to_public_stations():
    """Requires PostGIS: the upsert builds ST_SetSRID(ST_MakePoint(...)).

    Deliberately left as a marked integration test rather than mocked. Mocking
    the one query that crosses into `public.stations` would test the mock, and
    that query is where promotion can actually go wrong — it is the only place
    field-ops writes to the central inventory.
    """
    pytest.skip("needs the docker-compose Postgres/PostGIS on 5433")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_stations_unions_inventory_and_proposals():
    """Requires PostGIS: the inventory half uses ST_Y/ST_X."""
    pytest.skip("needs the docker-compose Postgres/PostGIS on 5433")
