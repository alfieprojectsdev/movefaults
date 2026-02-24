"""
Equipment router — GET/POST /api/v1/equipment, /api/v1/inventory

The QR scan flow:
  1. Field technician scans QR sticker on equipment
  2. PWA calls GET /api/v1/equipment?qr_id=<value>
  3. Response pre-fills equipment fields in the logsheet form

The inventory endpoints (/api/v1/inventory) are admin-only — field staff
can look up equipment but only admins can add/modify records.

QR code generation (POST /api/v1/inventory/{id}/qr) produces a PNG
that can be printed and laminated for field attachment.
"""

import io

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from field_ops.database import get_db
from field_ops.models import EquipmentInventory, User
from field_ops.routers.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["equipment"])


# ── Pydantic schemas ────────────────────────────────────────────────────────


class EquipmentOut(BaseModel):
    id: int
    qr_code: str
    equipment_type: str | None
    serial_number: str | None
    station_code: str | None
    status: str | None
    notes: str | None

    model_config = {"from_attributes": True}


class EquipmentIn(BaseModel):
    qr_code: str
    equipment_type: str | None = None
    serial_number: str | None = None
    station_code: str | None = None
    notes: str | None = None


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.get("/equipment", response_model=EquipmentOut)
async def lookup_equipment(
    qr_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> EquipmentOut:
    """Resolve a scanned QR code to an equipment record."""
    result = await db.execute(
        select(EquipmentInventory).where(EquipmentInventory.qr_code == qr_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail=f"No equipment found for QR: {qr_id}")
    return item


@router.get("/inventory", response_model=list[EquipmentOut])
async def list_inventory(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[EquipmentOut]:
    """Full equipment inventory — admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await db.execute(
        select(EquipmentInventory).order_by(EquipmentInventory.equipment_type)
    )
    return list(result.scalars().all())


@router.post("/inventory", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
async def add_equipment(
    item: EquipmentIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> EquipmentOut:
    """Register a new equipment item — admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    stmt = (
        pg_insert(EquipmentInventory)
        .values(**item.model_dump())
        .on_conflict_do_nothing(index_elements=["qr_code"])
        .returning(EquipmentInventory)
    )
    result = await db.execute(stmt)
    await db.commit()
    new_item = result.scalar_one_or_none()
    if new_item is None:
        raise HTTPException(status_code=409, detail="QR code already registered")
    return new_item


@router.post("/inventory/{item_id}/qr", response_class=Response)
async def generate_qr(
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Generate a QR code PNG for an equipment item — admin only."""
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(
        select(EquipmentInventory).where(EquipmentInventory.id == item_id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Equipment not found")

    import qrcode

    qr = qrcode.make(item.qr_code)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="image/png",
        headers={"Content-Disposition": f'attachment; filename="qr-{item.qr_code}.png"'},
    )
