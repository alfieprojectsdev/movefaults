"""
Tests for GET /api/v1/equipment and POST/GET /api/v1/inventory.

Key behaviours verified:
  - QR lookup returns correct equipment record
  - Unknown QR code returns 404
  - Field staff cannot access inventory management (403)
  - Admin can add equipment and retrieve inventory list
"""

import pytest


@pytest.mark.asyncio
async def test_lookup_unknown_qr_returns_404(client, auth_headers):
    resp = await client.get("/api/v1/equipment?qr_id=NONEXISTENT", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_field_staff_cannot_access_inventory(client, auth_headers):
    """field_staff role must be rejected from admin-only inventory endpoint."""
    resp = await client.get("/api/v1/inventory", headers=auth_headers)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_can_add_and_lookup_equipment(client, db_session, auth_headers):
    from field_ops.models import User
    from field_ops.routers.auth import hash_password
    from sqlalchemy import select

    # Promote the test user to admin
    result = await db_session.execute(select(User).where(User.username == "testuser"))
    user = result.scalar_one()
    user.role = "admin"
    await db_session.commit()

    # Add equipment via inventory endpoint
    payload = {
        "qr_code": "PHIV-ANT-001",
        "equipment_type": "Antenna",
        "serial_number": "SN123456",
        "station_code": "PBIS",
    }
    add_resp = await client.post("/api/v1/inventory", json=payload, headers=auth_headers)
    assert add_resp.status_code == 201
    assert add_resp.json()["qr_code"] == "PHIV-ANT-001"

    # Look it up via QR scan endpoint
    lookup_resp = await client.get(
        "/api/v1/equipment?qr_id=PHIV-ANT-001", headers=auth_headers
    )
    assert lookup_resp.status_code == 200
    assert lookup_resp.json()["serial_number"] == "SN123456"
