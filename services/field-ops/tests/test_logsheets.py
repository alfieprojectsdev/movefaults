"""
Tests for POST/GET /api/v1/logsheets.

Key behaviours verified:
  - Batch submit inserts all records and returns them with IDs + synced_at set
  - Duplicate client_uuid submission does not create a second row (idempotent sync)
  - GET /logsheets returns records; station_code filter works
  - Unauthenticated requests are rejected with 401
"""

import uuid
from datetime import date

import pytest


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
