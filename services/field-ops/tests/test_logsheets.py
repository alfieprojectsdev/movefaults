"""
Tests for POST/GET /api/v1/logsheets.

Key behaviours verified:
  - Batch submit inserts all records and returns them with IDs + synced_at set
  - Duplicate client_uuid submission does not create a second row (idempotent sync)
  - GET /logsheets returns records; station_code filter works
  - Unauthenticated requests are rejected with 401
  - Observers are validated BEFORE any logsheet is written, so an out-of-date
    staff list on a device cannot wedge the offline queue
  - Re-uploading identical photo bytes yields one row and one stored object
"""

import uuid

import pytest
from field_ops.models import LogSheet, LogSheetObserver, LogSheetPhoto, Staff
from sqlalchemy import func, select


@pytest.mark.asyncio
async def test_submit_logsheets(client, auth_headers):
    records = [
        {
            "client_uuid": str(uuid.uuid4()),
            "station_code": "PBIS",
            "visit_date": "2026-02-24",
            "equipment_status": "ok",
        },
        {
            "client_uuid": str(uuid.uuid4()),
            "station_code": "BOST",
            "visit_date": "2026-02-24",
            "equipment_status": "issue_found",
            "notes": "Antenna connector loose",
        },
    ]
    resp = await client.post("/api/v1/logsheets", json=records, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 2
    assert all(r["synced_at"] is not None for r in data)
    assert {r["station_code"] for r in data} == {"PBIS", "BOST"}


@pytest.mark.asyncio
async def test_submit_duplicate_uuid_is_idempotent(client, auth_headers):
    """Submitting the same client_uuid twice must not create a duplicate row."""
    shared_uuid = str(uuid.uuid4())
    record = [{"client_uuid": shared_uuid, "station_code": "PBIS", "visit_date": "2026-02-24"}]

    resp1 = await client.post("/api/v1/logsheets", json=record, headers=auth_headers)
    resp2 = await client.post("/api/v1/logsheets", json=record, headers=auth_headers)

    assert resp1.status_code == 201
    assert resp2.status_code == 201

    # Both responses should reference the same DB row (same id)
    assert resp1.json()[0]["id"] == resp2.json()[0]["id"]


@pytest.mark.asyncio
async def test_list_logsheets_with_filter(client, auth_headers):
    records = [
        {"client_uuid": str(uuid.uuid4()), "station_code": "PBIS", "visit_date": "2026-02-24"},
        {"client_uuid": str(uuid.uuid4()), "station_code": "BTU2", "visit_date": "2026-02-24"},
    ]
    await client.post("/api/v1/logsheets", json=records, headers=auth_headers)

    resp = await client.get("/api/v1/logsheets?station_code=PBIS", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert all(r["station_code"] == "PBIS" for r in data)


@pytest.mark.asyncio
async def test_unauthenticated_returns_401(client):
    resp = await client.get("/api/v1/logsheets")
    assert resp.status_code == 401


# ── Observers ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_observers_are_recorded(client, auth_headers, db_session):
    """The happy path: observer_ids that exist become junction rows."""
    staff = Staff(full_name="A. Pelicano", initials="AP")
    db_session.add(staff)
    await db_session.commit()

    record = [
        {
            "client_uuid": str(uuid.uuid4()),
            "station_code": "PBIS",
            "visit_date": "2026-02-24",
            # Duplicated on purpose — the endpoint de-dups before insert.
            "observer_ids": [staff.id, staff.id],
        }
    ]
    resp = await client.post("/api/v1/logsheets", json=record, headers=auth_headers)
    assert resp.status_code == 201

    links = (
        await db_session.execute(
            select(LogSheetObserver).where(
                LogSheetObserver.logsheet_id == resp.json()[0]["id"]
            )
        )
    ).scalars().all()
    assert [link.staff_id for link in links] == [staff.id]


@pytest.mark.asyncio
async def test_unknown_staff_id_rejects_batch_before_writing(
    client, auth_headers, db_session
):
    """
    An observer id the server does not know must fail the request atomically.

    The junction rows are written after the logsheets are committed, because
    they need the server-side ids. Validating there meant a stale staff_id —
    ordinary after a week offline — raised an FK error *after* the commit, so
    the client saw a 500 for records that had actually landed. runFlush() then
    left everything pending and replayed the same doomed batch on every sync:
    the queue wedged permanently with no visible cause.

    So the contract this pins down is not just "422" — it is that NOTHING is
    written when the batch is refused, which is what makes the retry safe.
    """
    good = Staff(full_name="R. Real", initials="RR")
    db_session.add(good)
    await db_session.commit()

    bad_uuid = str(uuid.uuid4())
    records = [
        {
            "client_uuid": str(uuid.uuid4()),
            "station_code": "PBIS",
            "visit_date": "2026-02-24",
            "observer_ids": [good.id],
        },
        {
            "client_uuid": bad_uuid,
            "station_code": "BOST",
            "visit_date": "2026-02-24",
            "observer_ids": [good.id, 999_999],  # 999999 does not exist
        },
    ]
    resp = await client.post("/api/v1/logsheets", json=records, headers=auth_headers)

    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "unknown_staff_ids"
    # The offending record is named, so the client can quarantine that one sheet
    # rather than stalling the whole queue.
    assert [r["client_uuid"] for r in detail["records"]] == [bad_uuid]
    assert detail["records"][0]["unknown_staff_ids"] == [999_999]

    written = await db_session.execute(select(func.count()).select_from(LogSheet))
    assert written.scalar_one() == 0


# ── Photos ──────────────────────────────────────────────────────────────────


class _CountingStorage:
    """Records every save/delete so a test can assert on object count, not just rows."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.saves = 0

    async def save(self, logsheet_id: int, filename: str, content: bytes) -> str:
        self.saves += 1
        ref = f"test://{logsheet_id}/{self.saves}_{filename}"
        self.objects[ref] = content
        return ref

    async def delete(self, ref: str) -> None:
        self.objects.pop(ref, None)


@pytest.fixture
def counting_storage(monkeypatch):
    from field_ops import storage as storage_mod
    from field_ops.routers import logsheets as logsheets_mod

    fake = _CountingStorage()
    monkeypatch.setattr(storage_mod, "_storage", fake)
    monkeypatch.setattr(logsheets_mod, "get_storage", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_reuploading_identical_photo_is_idempotent(
    client, auth_headers, db_session, counting_storage
):
    """
    A retry that sends the same bytes must not produce a second object.

    A device cannot tell "the upload failed" from "it succeeded and the reply
    was lost", which is the ordinary failure on a weak link — so the retry is
    guaranteed, and without a guard each one stored the image again. The cost is
    storage; the damage is provenance, because afterwards nobody can say which
    of several near-identical images was the one the observer meant.
    """
    record = [
        {
            "client_uuid": str(uuid.uuid4()),
            "station_code": "PBIS",
            "visit_date": "2026-02-24",
        }
    ]
    created = await client.post("/api/v1/logsheets", json=record, headers=auth_headers)
    logsheet_id = created.json()[0]["id"]

    photo = ("file", ("site.jpg", b"\xff\xd8\xff-not-really-a-jpeg", "image/jpeg"))
    first = await client.post(
        f"/api/v1/logsheets/{logsheet_id}/photos", files=[photo], headers=auth_headers
    )
    second = await client.post(
        f"/api/v1/logsheets/{logsheet_id}/photos", files=[photo], headers=auth_headers
    )

    assert first.status_code == 201
    assert first.json()["duplicate"] is False
    assert second.status_code == 201
    assert second.json()["duplicate"] is True
    assert second.json()["photo_id"] == first.json()["photo_id"]

    rows = await db_session.execute(select(func.count()).select_from(LogSheetPhoto))
    assert rows.scalar_one() == 1
    # The point of the SELECT-before-save ordering: the second request must not
    # have written bytes at all, not merely have been deduped in the database.
    assert len(counting_storage.objects) == 1
    assert counting_storage.saves == 1
