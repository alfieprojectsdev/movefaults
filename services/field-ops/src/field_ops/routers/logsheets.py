"""
Logsheets router — POST/GET /api/v1/logsheets

POST /api/v1/logsheets accepts a *list* of logsheet records (not a single object).
This is intentional: the PWA's offline queue may accumulate multiple records while
the field team is out of signal range. When connectivity returns, the queue flushes
as a single batch request rather than N sequential requests.

Idempotency: each record carries a client_uuid generated on the device before it
ever leaves the browser. The server inserts with ON CONFLICT (client_uuid) DO NOTHING,
so duplicate submissions (retry after partial network failure) are safe.
"""

import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from field_ops.config import settings
from field_ops.database import get_db
from field_ops.models import LogSheet, LogSheetPhoto, User
from field_ops.routers.auth import get_current_user

router = APIRouter(prefix="/api/v1", tags=["logsheets"])


# ── Pydantic schemas ────────────────────────────────────────────────────────

_VALID_SOURCE_VALUES = {"manual", "sensor"}
_CAMPAIGN_REQUIRED = ("antenna_model", "slant_n_m", "slant_s_m", "slant_e_m", "slant_w_m")


class LogSheetIn(BaseModel):
    client_uuid: uuid.UUID
    station_code: str
    visit_date: date
    arrival_time: datetime | None = None
    departure_time: datetime | None = None
    weather_conditions: str | None = None
    maintenance_performed: str | None = None
    equipment_status: str | None = None   # ok | issue_found | repaired
    notes: str | None = None

    # Mode discriminator
    monitoring_method: str | None = None  # "campaign" | "continuous"

    # Continuous-only
    power_notes: str | None = None
    battery_voltage_v: float | None = None
    battery_voltage_source: str | None = None  # "manual" | "sensor"
    temperature_c: float | None = None
    temperature_source: str | None = None  # "manual" | "sensor"

    # Campaign-only
    antenna_model: str | None = None
    slant_n_m: float | None = None
    slant_s_m: float | None = None
    slant_e_m: float | None = None
    slant_w_m: float | None = None
    avg_slant_m: float | None = None
    rinex_height_m: float | None = None
    session_id: str | None = None
    utc_start: datetime | None = None
    utc_end: datetime | None = None
    bubble_centred: bool | None = None
    plumbing_offset_mm: float | None = None

    @model_validator(mode="after")
    def _validate_method_fields(self) -> "LogSheetIn":
        if self.monitoring_method == "campaign":
            missing = [f for f in _CAMPAIGN_REQUIRED if getattr(self, f) is None]
            if missing:
                raise ValueError(
                    f"monitoring_method='campaign' requires: {', '.join(missing)}"
                )

        if self.battery_voltage_v is not None and self.battery_voltage_source not in (
            None,
            *_VALID_SOURCE_VALUES,
        ):
            raise ValueError(
                f"battery_voltage_source must be one of {_VALID_SOURCE_VALUES} when battery_voltage_v is set"
            )

        if self.temperature_c is not None and self.temperature_source not in (
            None,
            *_VALID_SOURCE_VALUES,
        ):
            raise ValueError(
                f"temperature_source must be one of {_VALID_SOURCE_VALUES} when temperature_c is set"
            )

        return self


class LogSheetOut(BaseModel):
    id: int
    client_uuid: uuid.UUID
    station_code: str
    visit_date: date
    equipment_status: str | None
    synced_at: datetime | None
    created_at: datetime | None
    monitoring_method: str | None
    rinex_height_m: float | None
    session_id: str | None
    battery_voltage_v: float | None

    model_config = {"from_attributes": True}


# ── Endpoints ───────────────────────────────────────────────────────────────


@router.post("/logsheets", response_model=list[LogSheetOut], status_code=status.HTTP_201_CREATED)
async def submit_logsheets(
    records: list[LogSheetIn],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LogSheetOut]:
    """
    Batch upsert logsheets from the offline queue.

    ON CONFLICT (client_uuid) DO NOTHING means retries are safe.
    Returns the server-side rows (with assigned IDs and synced_at timestamp).
    """
    if not records:
        return []

    now = datetime.now(UTC)

    values = [
        {
            "client_uuid": r.client_uuid,
            "station_code": r.station_code,
            "submitted_by": current_user.id,
            "visit_date": r.visit_date,
            "arrival_time": r.arrival_time,
            "departure_time": r.departure_time,
            "weather_conditions": r.weather_conditions,
            "maintenance_performed": r.maintenance_performed,
            "equipment_status": r.equipment_status,
            "notes": r.notes,
            "synced_at": now,
            "monitoring_method": r.monitoring_method,
            "power_notes": r.power_notes,
            "battery_voltage_v": r.battery_voltage_v,
            "battery_voltage_source": r.battery_voltage_source,
            "temperature_c": r.temperature_c,
            "temperature_source": r.temperature_source,
            "antenna_model": r.antenna_model,
            "slant_n_m": r.slant_n_m,
            "slant_s_m": r.slant_s_m,
            "slant_e_m": r.slant_e_m,
            "slant_w_m": r.slant_w_m,
            "avg_slant_m": r.avg_slant_m,
            "rinex_height_m": r.rinex_height_m,
            "session_id": r.session_id,
            "utc_start": r.utc_start,
            "utc_end": r.utc_end,
            "bubble_centred": r.bubble_centred,
            "plumbing_offset_mm": r.plumbing_offset_mm,
        }
        for r in records
    ]

    stmt = (
        pg_insert(LogSheet)
        .values(values)
        .on_conflict_do_nothing(index_elements=["client_uuid"])
        .returning(LogSheet)
    )
    await db.execute(stmt)
    await db.commit()

    # Fetch all submitted records (including any that were already present)
    client_uuids = [r.client_uuid for r in records]
    fetched = await db.execute(
        select(LogSheet).where(LogSheet.client_uuid.in_(client_uuids))
    )
    return list(fetched.scalars().all())


@router.get("/logsheets", response_model=list[LogSheetOut])
async def list_logsheets(
    station_code: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[LogSheetOut]:
    query = select(LogSheet).order_by(LogSheet.visit_date.desc()).limit(limit)
    if station_code:
        query = query.where(LogSheet.station_code == station_code)
    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/logsheets/{logsheet_id}", response_model=LogSheetOut)
async def get_logsheet(
    logsheet_id: int,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> LogSheetOut:
    result = await db.execute(select(LogSheet).where(LogSheet.id == logsheet_id))
    logsheet = result.scalar_one_or_none()
    if logsheet is None:
        raise HTTPException(status_code=404, detail="Logsheet not found")
    return logsheet


@router.post("/logsheets/{logsheet_id}/photos", status_code=status.HTTP_201_CREATED)
async def upload_photo(
    logsheet_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> dict:
    """
    Attach a photo to a logsheet (antenna install, equipment, site conditions).
    Saves to disk at settings.field_ops_upload_dir.
    """
    from pathlib import Path

    result = await db.execute(select(LogSheet).where(LogSheet.id == logsheet_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Logsheet not found")

    upload_dir = Path(settings.field_ops_upload_dir) / str(logsheet_id)
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{uuid.uuid4().hex}_{file.filename}"
    dest = upload_dir / safe_name

    contents = await file.read()
    dest.write_bytes(contents)

    photo = LogSheetPhoto(
        logsheet_id=logsheet_id,
        filename=file.filename,
        storage_path=str(dest),
    )
    db.add(photo)
    await db.commit()

    return {"photo_id": photo.id, "filename": safe_name}
