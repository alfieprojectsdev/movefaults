"""
Staff router — GET /api/v1/staff

Returns active field staff for the observer dropdown in the logsheet PWA.
Read-only endpoint — staff records are managed by admin users only.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from field_ops.database import get_db
from field_ops.models import Staff
from field_ops.routers.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["staff"])


class StaffOut(BaseModel):
    id: int
    full_name: str
    initials: str | None
    role: str | None

    model_config = {"from_attributes": True}


@router.get("/staff", response_model=list[StaffOut])
async def list_staff(
    db: AsyncSession = Depends(get_db),
    _current_user=Depends(get_current_user),
) -> list[StaffOut]:
    """Return all active staff members for the observer picker dropdown."""
    result = await db.execute(
        select(Staff).where(Staff.is_active.is_(True)).order_by(Staff.full_name)
    )
    return list(result.scalars().all())
