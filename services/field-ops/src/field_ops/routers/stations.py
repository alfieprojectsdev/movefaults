"""
Stations router — GET /api/v1/stations

Reads from the central public.stations table (managed by Phase 0 migrations).
The PWA caches this list in IndexedDB for offline station picker use.

The station list changes infrequently (new installs, decommissions) so a simple
full-list endpoint is sufficient — no pagination needed at 35 stations.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from field_ops.database import get_db
from field_ops.routers.auth import get_current_user
from field_ops.models import User

router = APIRouter(prefix="/api/v1", tags=["stations"])


class StationOut(BaseModel):
    station_code: str
    name: str | None
    latitude: float | None
    longitude: float | None
    elevation: float | None
    fault_segment: str | None
    status: str | None

    model_config = {"from_attributes": True}


@router.get("/stations", response_model=list[StationOut])
async def list_stations(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[StationOut]:
    """
    Return all active stations from the central stations table.

    Uses raw SQL with ST_Y/ST_X to extract lat/lon from the PostGIS geometry
    column — the ORM model for public.stations lives in src/db/models.py,
    not here, so we use a text query rather than importing across service boundaries.
    """
    result = await db.execute(
        text("""
            SELECT
                station_code,
                name,
                ST_Y(location::geometry) AS latitude,
                ST_X(location::geometry) AS longitude,
                elevation,
                fault_segment,
                status
            FROM stations
            WHERE status = 'active'
            ORDER BY station_code
        """)
    )
    rows = result.mappings().all()
    return [StationOut(**dict(row)) for row in rows]
