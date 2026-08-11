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

import hashlib
import logging
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from field_ops.database import get_db
from field_ops.models import LogSheet, LogSheetObserver, LogSheetPhoto, Staff, User
from field_ops.routers.auth import get_current_user
from field_ops.storage import get_storage

logger = logging.getLogger(__name__)

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

    # Staff present for this visit. Pydantic ignores unknown keys by
    # default, so before this field existed the PWA sent observer_ids and
    # the server discarded them silently — a 201 with zero observers
    # recorded, and no warning at any layer.
    observer_ids: list[int] | None = None

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

    # ── Validate observers BEFORE writing anything ──────────────────────────
    #
    # The junction rows used to be inserted after the logsheets were already
    # committed, because they need the server-side ids. A staff_id the device
    # cached and the server has since deleted — normal after a week offline —
    # then raised IntegrityError on the FK *after* that commit, which FastAPI
    # turned into a 500.
    #
    # The client cannot recover from that. runFlush() sees a failed batch and
    # leaves every record pending, so the next flush replays the same batch,
    # hits the same id, and 500s again: the queue wedges permanently and the
    # only symptom is a Sync button that appears to do nothing.
    #
    # Checking first makes the failure atomic and diagnosable. Nothing is
    # committed, the response names the offending record, and the client can
    # quarantine that one sheet instead of stalling the whole day's work.
    requested_staff = {
        sid for r in records if r.observer_ids for sid in r.observer_ids
    }
    if requested_staff:
        known = await db.execute(select(Staff.id).where(Staff.id.in_(requested_staff)))
        unknown = requested_staff - set(known.scalars().all())
        if unknown:
            offenders = [
                {
                    "client_uuid": str(r.client_uuid),
                    "unknown_staff_ids": sorted(set(r.observer_ids) & unknown),
                }
                for r in records
                if r.observer_ids and set(r.observer_ids) & unknown
            ]
            raise HTTPException(
                # 422, spelled without the constant: starlette renamed it to
                # HTTP_422_UNPROCESSABLE_CONTENT and deprecated the old name, so
                # either constant warns on one version or breaks on the other.
                status_code=422,
                detail={
                    "error": "unknown_staff_ids",
                    "message": (
                        "These observer ids do not exist on the server. The staff "
                        "list on this device is out of date — refresh it, correct "
                        "the affected records, and sync again."
                    ),
                    "records": offenders,
                },
            )

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
    rows = list(fetched.scalars().all())

    # Observers. Written after the logsheets exist, because the junction needs
    # their server-side ids. ON CONFLICT DO NOTHING keeps this idempotent under
    # the same retry the logsheet upsert already tolerates. Every staff_id here
    # was checked against the staff table above, before the commit — see the
    # note there for why validating afterwards wedged the offline queue.
    id_by_uuid = {str(row.client_uuid): row.id for row in rows}
    observer_values = [
        {"logsheet_id": id_by_uuid[str(r.client_uuid)], "staff_id": sid}
        for r in records
        if r.observer_ids and str(r.client_uuid) in id_by_uuid
        for sid in dict.fromkeys(r.observer_ids)  # de-dup, preserve order
    ]
    if observer_values:
        await db.execute(
            pg_insert(LogSheetObserver)
            .values(observer_values)
            .on_conflict_do_nothing(index_elements=["logsheet_id", "staff_id"])
        )
        await db.commit()

    return rows


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

    Storage backend is configured, not hardcoded: local disk in development,
    Cloudflare R2 in deployment. See field_ops/storage.py — a container's
    filesystem does not survive a restart, so a deployed instance writing to
    disk would leave rows pointing at files that no longer exist.
    """
    result = await db.execute(select(LogSheet).where(LogSheet.id == logsheet_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Logsheet not found")

    contents = await file.read()
    digest = hashlib.sha256(contents).hexdigest()

    # ── Idempotency ─────────────────────────────────────────────────────────
    #
    # A client cannot tell "the upload failed" from "the upload succeeded and
    # the response was lost coming back" — the ordinary failure on a weak field
    # link. Without a guard here, every retry of the second case stored the same
    # image again: several R2 objects and several rows for one observation, and
    # no way afterwards to say which was the photo the observer meant.
    #
    # Content hash rather than a client-supplied id, because it needs no
    # cooperation from the client and it catches exactly the case that matters:
    # a retry sends identical bytes.
    existing = await db.execute(
        select(LogSheetPhoto).where(
            LogSheetPhoto.logsheet_id == logsheet_id,
            LogSheetPhoto.content_sha256 == digest,
        )
    )
    already = existing.scalar_one_or_none()
    if already is not None:
        # Return the original, and do NOT touch storage — writing the bytes
        # again would create a second object even though the row is deduped.
        return {
            "photo_id": already.id,
            "storage_path": already.storage_path,
            "duplicate": True,
        }

    # Store the bytes BEFORE the row. If this raises, the request fails and the
    # device keeps the photo queued for retry. The reverse order would commit a
    # row referencing an object that was never written — the DB would look
    # correct and the photo would be gone.
    storage_ref = await get_storage().save(
        logsheet_id, file.filename or "photo.jpg", contents
    )

    photo = LogSheetPhoto(
        logsheet_id=logsheet_id,
        filename=file.filename,
        storage_path=storage_ref,
        content_sha256=digest,
    )
    db.add(photo)
    try:
        await db.commit()
    except IntegrityError:
        # Two concurrent uploads of the same bytes both passed the SELECT above.
        # The unique index is the actual arbiter; the loser resolves to the
        # winner's row rather than failing the operator's request.
        await db.rollback()
        winner = await db.execute(
            select(LogSheetPhoto).where(
                LogSheetPhoto.logsheet_id == logsheet_id,
                LogSheetPhoto.content_sha256 == digest,
            )
        )
        row = winner.scalar_one_or_none()
        if row is None:
            # The constraint fired but no row is visible — that is a genuine
            # invariant violation, not a duplicate. Surface it.
            raise

        # This request lost the race, so the object it wrote a moment ago is now
        # referenced by nothing: the winner's row points at the winner's object.
        # Unreferenced objects are invisible in the database, unbounded, and
        # billed, so remove what this request created.
        #
        # Best effort by design. The operator's upload has already succeeded —
        # failing it now over a storage cleanup would be a worse outcome than
        # leaving one stray object behind, so this only logs.
        try:
            await get_storage().delete(storage_ref)
        except Exception:  # noqa: BLE001 — cleanup must never fail the request
            logger.warning(
                "Could not remove orphaned photo object %s after a duplicate-upload "
                "race on logsheet %s; it is unreferenced and safe to delete manually.",
                storage_ref,
                logsheet_id,
            )

        return {
            "photo_id": row.id,
            "storage_path": row.storage_path,
            "duplicate": True,
        }

    return {"photo_id": photo.id, "storage_path": storage_ref, "duplicate": False}
