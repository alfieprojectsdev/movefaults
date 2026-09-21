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

import pathlib
import uuid
from datetime import date

import field_ops
import pytest
from field_ops.models import LogSheet, StationProposal, User
from field_ops.routers.auth import hash_password

# The router's own source, so the integration tests below can execute the real
# queries rather than copies of them.
ROUTER_SRC = (
    pathlib.Path(field_ops.__file__).parent / "routers" / "stations.py"
)


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
async def test_a_second_claim_on_a_code_is_kept_and_marked(
    client, auth_headers, proposal_payload, db_session
):
    """#228. This test used to assert the opposite:

        assert second.status_code == 409
        assert "already been proposed" in second.json()["detail"]

    That 409 was the bug. The proposal never became a row, so the reconcile
    screen — which reads `field_ops.station_proposals` — could not see it, and
    a site an observer travelled to sat on one handset until the phone was
    wiped. The guard cannot reach a handset that has been offline for two
    days, so both teams were working correctly.
    """
    first = await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    assert first.status_code == 201
    assert first.json()["collides_with"] is None

    second = await client.post(
        "/api/v1/stations",
        json={**proposal_payload, "client_uuid": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert second.status_code == 201
    assert second.json()["collides_with"] == "proposal"
    assert second.json()["id"] != first.json()["id"]

    from sqlalchemy import func, select

    total = await db_session.execute(select(func.count()).select_from(StationProposal))
    assert total.scalar_one() == 2, "both claims must survive; the office settles them"


@pytest.mark.asyncio
async def test_both_claims_reach_the_reconcile_queue(
    client, auth_headers, proposal_payload, db_session
):
    """The row existing is not the point — the office *seeing* it is.

    `test_a_second_claim_on_a_code_is_kept_and_marked` would still pass if the
    reconcile listing filtered collisions out, which is the same dead end one
    layer down.
    """
    await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    await client.post(
        "/api/v1/stations",
        json={**proposal_payload, "client_uuid": str(uuid.uuid4()), "name": "Other team"},
        headers=auth_headers,
    )

    admin_headers = await _make_admin(client, db_session)
    queue = await client.get("/api/v1/station-proposals", headers=admin_headers)
    assert queue.status_code == 200

    claims = [r for r in queue.json() if r["station_code"] == "TSTA"]
    assert len(claims) == 2, "the reviewer cannot settle a disagreement they cannot see"
    assert sorted(c["collides_with"] or "" for c in claims) == ["", "proposal"]


def test_the_picker_offers_a_contested_code_once():
    """Two claims, one code, one entry.

    Showing both would read to the observer as two different sites sharing a
    code — the collision handed back to the handset instead of to the office.

    Tested against `_append_proposals` rather than over HTTP because
    `GET /stations` reads the inventory with ST_Y/ST_X, so the endpoint cannot
    run on the SQLite conftest at all.
    """
    from field_ops.routers.stations import StationOut, _append_proposals

    def claim(name: str, collides_with: str | None, pid: int) -> StationProposal:
        return StationProposal(
            id=pid,
            station_code="TSTA",
            name=name,
            monitoring_method="campaign",
            status="active",
            collides_with=collides_with,
            created_by=1,
        )

    # Caller order: uncontested first within a code (see `list_stations`).
    merged = _append_proposals([], [claim("First team", None, 1), claim("Other team", "proposal", 2)])

    assert [s.station_code for s in merged] == ["TSTA"]
    assert merged[0].name == "First team"
    assert merged[0].source == "field"

    # And the inventory still wins over any field claim on the same code.
    inventory = StationOut(
        station_code="TSTA",
        name="Catalogued",
        latitude=14.5,
        longitude=121.0,
        elevation=None,
        fault_segment=None,
        status="active",
        source="inventory",
    )
    merged = _append_proposals(
        [inventory], [claim("First team", None, 1), claim("Other team", "proposal", 2)]
    )
    assert [s.name for s in merged] == ["Catalogued"]


@pytest.mark.asyncio
async def test_collision_check_is_case_insensitive(client, auth_headers, proposal_payload):
    """`tsta` and `TSTA` are the same code, so the second is a collision.

    Previously this asserted 409. The normalisation it is really testing —
    codes upper-cased before comparison — is unchanged; only the answer to a
    collision moved.
    """
    await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    resp = await client.post(
        "/api/v1/stations",
        json={**proposal_payload, "station_code": "tsta", "client_uuid": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["collides_with"] == "proposal"


@pytest.mark.asyncio
async def test_a_free_code_is_not_marked(client, auth_headers, proposal_payload):
    """The marker has to mean something.

    Every assertion above would hold if `collides_with` were set on every row,
    which would tell the reviewer nothing.
    """
    resp = await client.post("/api/v1/stations", json=proposal_payload, headers=auth_headers)
    assert resp.status_code == 201
    assert resp.json()["collides_with"] is None


@pytest.mark.asyncio
async def test_a_resolved_claim_frees_the_code_again(
    client, auth_headers, proposal_payload, db_session
):
    """A collision is against *pending* claims only.

    Once the first claim is rejected, the next proposal is uncontested — the
    marker must not stick to the code itself.
    """
    first = await client.post(
        "/api/v1/stations", json=proposal_payload, headers=auth_headers
    )
    admin_headers = await _make_admin(client, db_session)
    await client.post(
        f"/api/v1/station-proposals/{first.json()['id']}/reject",
        json={"reason": "wrong monument"},
        headers=admin_headers,
    )

    again = await client.post(
        "/api/v1/stations",
        json={**proposal_payload, "client_uuid": str(uuid.uuid4())},
        headers=auth_headers,
    )
    assert again.status_code == 201
    assert again.json()["collides_with"] is None


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


# A code no real station uses, for the rows these tests create and delete.
# The pg fixtures deliberately do not create or drop schemas -- pointing a
# destructive fixture at a URL that might be someone's real database is how
# test infrastructure eats production data -- so a test that writes is
# responsible for its own rows.
_TEST_CODE = "ZZTE"


def _sql_from_router(pattern: str) -> str:
    """Pull a raw query out of the router rather than restating it here.

    A test that copies the SQL it is meant to guard drifts into passing while
    the endpoint is broken. Reading the real text means a change to the query
    is a change to what is executed here.
    """
    import re

    src = ROUTER_SRC.read_text(encoding="utf-8")
    m = re.search(pattern, src, re.S)
    assert m, f"could not find the query matching {pattern!r} in stations.py"
    return m.group(1)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_promote_writes_to_public_stations(pg_session):
    """The promotion upsert, executed against real PostGIS.

    Deliberately not mocked. Mocking the one query that crosses into
    `public.stations` would test the mock, and that query is where promotion
    can actually go wrong — it is the only place field-ops writes to the
    central inventory.

    Three claims, and the third is the one the endpoint's docstring says is not
    hypothetical:

      1. The statement executes at all. ST_SetSRID(ST_MakePoint(...)) exists in
         no other test environment, and SQLite cannot parse it.
      2. A proposal with coordinates lands with a geometry that reads back as
         the coordinates it was given.
      3. Re-promoting the same code with NULL fields does NOT null what is
         already there. A proposal made at a monument carries whatever the
         observer could see, which is usually less than the office has, and the
         COALESCE in the ON CONFLICT clause is what stops the sparse one
         overwriting the full one.
    """
    from sqlalchemy import text as sa_text

    sql = _sql_from_router(r"text\(\"\"\"\s*(INSERT INTO stations.*?)\"\"\"\)")
    assert "ON CONFLICT (station_code) DO UPDATE" in sql
    assert "ST_SetSRID" in sql

    params = {
        "code": _TEST_CODE,
        "name": "Integration fixture site",
        "lat": 14.6537,
        "lon": 121.0584,
        "elevation": 55.0,
        "method": "campaign",
        "status": "active",
        "municipality": "Quezon City",
        "province": "Metro Manila",
        "region": "NCR",
    }

    # Never touch a row this test did not create.
    pre = await pg_session.execute(
        sa_text("SELECT 1 FROM stations WHERE station_code = :code"), {"code": _TEST_CODE}
    )
    assert pre.first() is None, (
        f"{_TEST_CODE} already exists in this database; refusing to write over it"
    )

    try:
        # 1 — it executes, and PostGIS resolves.
        first = await pg_session.execute(sa_text(sql), params)
        station_id = first.scalar_one()
        assert station_id is not None

        # 2 — the geometry reads back as what went in.
        row = (
            await pg_session.execute(
                sa_text(
                    "SELECT name, elevation, municipality, "
                    "ST_Y(location::geometry) AS lat, ST_X(location::geometry) AS lon "
                    "FROM stations WHERE station_code = :code"
                ),
                {"code": _TEST_CODE},
            )
        ).mappings().one()
        assert row["lat"] == pytest.approx(params["lat"], abs=1e-9)
        assert row["lon"] == pytest.approx(params["lon"], abs=1e-9)
        assert row["name"] == params["name"]

        # 3 — a sparse re-promotion preserves what the office already had.
        sparse = {**params, "name": None, "elevation": None, "municipality": None}
        await pg_session.execute(sa_text(sql), sparse)
        after = (
            await pg_session.execute(
                sa_text(
                    "SELECT name, elevation, municipality FROM stations "
                    "WHERE station_code = :code"
                ),
                {"code": _TEST_CODE},
            )
        ).mappings().one()
        assert after["name"] == params["name"], "COALESCE did not protect name"
        assert after["elevation"] == params["elevation"], "COALESCE did not protect elevation"
        assert after["municipality"] == params["municipality"]
    finally:
        # ROLL BACK FIRST. This is not tidiness -- it is the difference between
        # a test that tells you why it failed and one that cannot.
        #
        # When the statement under test raises, the transaction is aborted and
        # every later statement on it raises InFailedSQLTransactionError. A
        # cleanup DELETE issued on that aborted transaction therefore raises
        # from inside `finally`, and Python REPLACES the original exception
        # with it. The traceback then contains no trace of the real failure.
        #
        # That is exactly what happened on the first real run: the endpoint was
        # raising AmbiguousParameterError and the pytest output showed only the
        # cleanup error. gps3 found the real cause by reading the postgres
        # container log, because the test had destroyed it.
        await pg_session.rollback()
        await pg_session.execute(
            sa_text("DELETE FROM stations WHERE station_code = :code"), {"code": _TEST_CODE}
        )
        await pg_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_promote_through_the_router_puts_the_monument_where_it_belongs(pg_session):
    """Promote via the ENDPOINT, not via the extracted SQL.

    The test above executes the router's query with its own params dict, which
    covers the ordering inside the SQL — `ST_MakePoint(:lon, :lat)` is the
    thing PostGIS gets wrong most often — and covers nothing about the CALLER.

    Swap these two lines in `promote_proposal`:

        "lat": proposal.latitude,
        "lon": proposal.longitude,

    and every other test still passes. Measured, not asserted: with them
    swapped the suite reports 82 passed, 3 skipped. The regex still matches so
    the extraction succeeds, the integration test builds its own correctly
    ordered params so it still sees ST_Y == lat, and the 403 test never reaches
    the query. A promoted monument would land on the other side of the world
    with nothing red.

    The two orderings look identical reading the file top to bottom, which is
    probably why it read as covered. Found by gps3.

    This one takes no regex, because the endpoint is the thing under test.
    """
    import uuid as _uuid

    from field_ops.database import get_db
    from field_ops.main import app
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text as sa_text

    # These tables live in the field_ops schema and this fixture creates
    # nothing, so say plainly which migration is missing rather than failing
    # with a driver error three frames down.
    try:
        await pg_session.execute(sa_text("SELECT 1 FROM field_ops.station_proposals LIMIT 1"))
        await pg_session.execute(sa_text("SELECT 1 FROM field_ops.users LIMIT 1"))
    except Exception as exc:  # noqa: BLE001
        await pg_session.rollback()
        pytest.skip(
            f"field_ops schema not migrated in {type(exc).__name__}; "
            "run `alembic -c services/field-ops/alembic.ini upgrade head` against this database"
        )

    code = "ZZTR"
    pre = await pg_session.execute(
        sa_text("SELECT 1 FROM stations WHERE station_code = :c"), {"c": code}
    )
    assert pre.first() is None, f"{code} already exists here; refusing to write over it"

    reviewer = User(
        username=f"zz-int-{_uuid.uuid4().hex[:8]}",
        hashed_password=hash_password("testpass"),
        role="admin",
    )
    pg_session.add(reviewer)
    await pg_session.flush()
    # Captured NOW, as a plain int, while the instance is still live.
    #
    # The cleanup below rolls back before deleting, and ROLLBACK EXPIRES EVERY
    # LOADED ATTRIBUTE unconditionally — `expire_on_commit=False` on the
    # session factory suppresses expiry on commit and has no effect on
    # rollback, and there is no setting that does. So `reviewer.id` read inside
    # `finally` is not a field access, it is a lazy refresh: IO, attempted
    # outside greenlet context, raising
    #
    #   MissingGreenlet: greenlet_spawn has not been called
    #
    # from `sqlalchemy/orm/attributes.py __get__`, with the instance's __dict__
    # holding nothing but `_sa_instance_state`. The traceback reads like a sync
    # ORM execute and is not one.
    #
    # `station_code` is fine in the same block because it is a plain string.
    # This is the only ORM attribute the cleanup touches, and "just use the
    # object" is the obvious spelling, so it will be reintroduced by anyone who
    # does not know the rollback is above it. Diagnosed by gps3, 2026-09-16.
    reviewer_id = reviewer.id

    # Deliberately asymmetric: a latitude that is not a plausible longitude for
    # the Philippines and vice versa, so a swap cannot coincidentally survive.
    lat, lon = 14.6537, 121.0584
    proposal = StationProposal(
        client_uuid=_uuid.uuid4(),
        station_code=code,
        name="Router integration site",
        latitude=lat,
        longitude=lon,
        monitoring_method="campaign",
        status="active",
        created_by=reviewer.id,
    )
    pg_session.add(proposal)
    await pg_session.commit()
    await pg_session.refresh(proposal)

    app.dependency_overrides[get_db] = lambda: pg_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            token = await ac.post(
                "/api/v1/token",
                data={"username": reviewer.username, "password": "testpass"},
            )
            assert token.status_code == 200, token.text
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

            resp = await ac.post(
                f"/api/v1/station-proposals/{proposal.id}/promote", headers=headers
            )
            assert resp.status_code == 200, resp.text

        row = (
            await pg_session.execute(
                sa_text(
                    "SELECT ST_Y(location::geometry) AS lat, "
                    "ST_X(location::geometry) AS lon "
                    "FROM stations WHERE station_code = :c"
                ),
                {"c": code},
            )
        ).mappings().one()

        # The assertion the swap breaks.
        assert row["lat"] == pytest.approx(lat, abs=1e-9), (
            "latitude did not survive promotion -- check the lat/lon mapping in "
            "promote_proposal, not the SQL"
        )
        assert row["lon"] == pytest.approx(lon, abs=1e-9)
    finally:
        app.dependency_overrides.clear()
        # See the note on the test above: without this, a failure inside the
        # try block is replaced by InFailedSQLTransactionError from the first
        # cleanup statement, and the real cause is lost.
        await pg_session.rollback()
        await pg_session.execute(
            sa_text("DELETE FROM stations WHERE station_code = :c"), {"c": code}
        )
        await pg_session.execute(
            sa_text("DELETE FROM field_ops.station_proposals WHERE station_code = :c"),
            {"c": code},
        )
        await pg_session.execute(
            sa_text("DELETE FROM field_ops.users WHERE id = :i"), {"i": reviewer_id}
        )
        await pg_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_promoting_onto_an_occupied_code_leaves_the_station_alone(pg_session):
    """#228's sharp edge, and the reason the accept half is not enough.

    `promote_proposal` upserts with `ON CONFLICT (station_code) DO UPDATE ...
    COALESCE(EXCLUDED.col, stations.col)`. That is right for the case it was
    written for — a sparse proposal filling gaps in the row it is the origin
    of — and destructive for the case accepting collisions creates: the
    losing team's coordinates would silently replace a catalogued station's,
    with nothing recording that it had ever been anywhere else.

    Postgres, because the whole mechanism is the upsert and the geometry.
    The assertion that matters is not the 409 — it is that the station is
    still where it was afterwards.
    """
    import uuid as _uuid

    from field_ops.database import get_db
    from field_ops.main import app
    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text as sa_text

    try:
        await pg_session.execute(sa_text("SELECT 1 FROM field_ops.station_proposals LIMIT 1"))
        await pg_session.execute(sa_text("SELECT 1 FROM field_ops.users LIMIT 1"))
    except Exception as exc:  # noqa: BLE001
        await pg_session.rollback()
        pytest.skip(
            f"field_ops schema not migrated in {type(exc).__name__}; "
            "run `alembic -c services/field-ops/alembic.ini upgrade head` against this database"
        )

    code = "ZZTC"
    pre = await pg_session.execute(
        sa_text("SELECT 1 FROM stations WHERE station_code = :c"), {"c": code}
    )
    assert pre.first() is None, f"{code} already exists here; refusing to write over it"

    reviewer = User(
        username=f"zz-col-{_uuid.uuid4().hex[:8]}",
        hashed_password=hash_password("testpass"),
        role="admin",
    )
    pg_session.add(reviewer)
    await pg_session.flush()
    reviewer_id = reviewer.id  # before any rollback expires it — see the test above

    # The catalogued station, and a second team's claim on the same code from
    # 300 km away. Far enough apart that an overwrite cannot hide in rounding.
    kept_lat, kept_lon = 14.6537, 121.0584
    other_lat, other_lon = 10.3157, 123.8854

    await pg_session.execute(
        sa_text("""
            INSERT INTO stations (station_code, name, location, monitoring_method, status)
            VALUES (:c, :n,
                    ST_SetSRID(ST_MakePoint(CAST(:lon AS double precision),
                                            CAST(:lat AS double precision)), 4326),
                    'continuous', 'active')
        """),
        {"c": code, "n": "Catalogued monument", "lat": kept_lat, "lon": kept_lon},
    )

    proposal = StationProposal(
        client_uuid=_uuid.uuid4(),
        station_code=code,
        name="Second team's site",
        latitude=other_lat,
        longitude=other_lon,
        monitoring_method="campaign",
        status="active",
        created_by=reviewer_id,
        collides_with="inventory",
    )
    pg_session.add(proposal)
    await pg_session.commit()
    await pg_session.refresh(proposal)
    proposal_id = proposal.id

    async def where_is_it() -> tuple[float, float, str]:
        row = (
            await pg_session.execute(
                sa_text(
                    "SELECT ST_Y(location::geometry) AS lat, "
                    "ST_X(location::geometry) AS lon, name "
                    "FROM stations WHERE station_code = :c"
                ),
                {"c": code},
            )
        ).mappings().one()
        return row["lat"], row["lon"], row["name"]

    app.dependency_overrides[get_db] = lambda: pg_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            token = await ac.post(
                "/api/v1/token",
                data={"username": reviewer.username, "password": "testpass"},
            )
            assert token.status_code == 200, token.text
            headers = {"Authorization": f"Bearer {token.json()['access_token']}"}

            refused = await ac.post(
                f"/api/v1/station-proposals/{proposal_id}/promote", headers=headers
            )
            assert refused.status_code == 409, refused.text
            assert "already in the central inventory" in refused.json()["detail"]

            lat, lon, name = await where_is_it()
            assert (lat, lon) == pytest.approx((kept_lat, kept_lon), abs=1e-9), (
                "the catalogued station MOVED on a refused promote -- the upsert ran "
                "anyway"
            )
            assert name == "Catalogued monument"

            # The reviewer who has compared both claims can still say so, and
            # then the merge is the documented COALESCE behaviour.
            merged = await ac.post(
                f"/api/v1/station-proposals/{proposal_id}/promote",
                params={"merge_into_existing": "true"},
                headers=headers,
            )
            assert merged.status_code == 200, merged.text

        lat, lon, _ = await where_is_it()
        assert (lat, lon) == pytest.approx((other_lat, other_lon), abs=1e-9), (
            "merge_into_existing=true did nothing, so the refusal above proves "
            "nothing about the guard"
        )
    finally:
        app.dependency_overrides.clear()
        await pg_session.rollback()
        await pg_session.execute(
            sa_text("DELETE FROM stations WHERE station_code = :c"), {"c": code}
        )
        await pg_session.execute(
            sa_text("DELETE FROM field_ops.station_proposals WHERE station_code = :c"),
            {"c": code},
        )
        await pg_session.execute(
            sa_text("DELETE FROM field_ops.users WHERE id = :i"), {"i": reviewer_id}
        )
        await pg_session.commit()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_list_stations_unions_inventory_and_proposals(pg_session):
    """The inventory half of GET /stations, executed against real PostGIS.

    ST_Y/ST_X on a geography column exist nowhere else, so this query has never
    run under any other test. Asserts the SHAPE rather than the content: an
    empty stations table is a legitimate state for a fresh database, and a
    test that needs seeded rows is a test that will be disabled the first time
    someone runs it somewhere clean.
    """
    from sqlalchemy import text as sa_text

    sql = _sql_from_router(r"text\(\"\"\"\s*(SELECT.*?FROM stations.*?)\"\"\"\)")
    assert "ST_Y" in sql and "ST_X" in sql

    rows = (await pg_session.execute(sa_text(sql))).mappings().all()

    expected = {"station_code", "name", "latitude", "longitude"}
    if rows:
        assert expected <= set(rows[0].keys())
    else:
        # Executing without raising is the claim when the table is empty, and
        # it is the claim that matters: a broken ST_Y reference raises here and
        # nowhere else in the suite.
        assert rows == []
