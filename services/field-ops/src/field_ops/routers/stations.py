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
    Return every station from the central stations table, whatever its status.

    Previously filtered to `status = 'active'`, which hid 15 sites the field
    team can legitimately be sent to: a station under maintenance is one they
    are visiting *because* it needs work, and a decommissioned site still gets
    occupied to recover equipment or close it out properly. An observer standing
    at a monument that is not in the picker cannot file a sheet at all.

    Status travels with each row so the picker can show it rather than imply
    everything is healthy — see StationPicker.tsx.

    Ordering puts active sites first, then under maintenance, then the closed
    ones, so the common case stays at the top of a 140-entry list; within each
    group, by code.

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
            ORDER BY
                CASE status
                    WHEN 'active'            THEN 0
                    WHEN 'under_maintenance' THEN 1
                    ELSE 2
                END,
                station_code
        """)
    )
    rows = result.mappings().all()
    return [StationOut(**dict(row)) for row in rows]
