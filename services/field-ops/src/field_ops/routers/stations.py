"""
Stations router — the picker's list, plus field-created sites (FO-001).

Two sources, one list:

  * `public.stations` — the central inventory, seeded from
    `data/network_inventory/stations.csv` and shared with VADASE and the
    Bernese chain. 138 rows, **all of them `monitoring_method = continuous`**.
  * `field_ops.station_proposals` — sites an observer created at the monument
    because they were not in the inventory. Unreconciled until someone with
    the role promotes them.

WHY THE SECOND SOURCE EXISTS (issue #118)
------------------------------------------
The field reported the list as stale. It is worse: `seed_network_inventory.py`
states that campaign occupations "must be seeded from another source", and no
such source has ever existed. **Campaign sites have never had an ingest path.**
An observer sent to one could not select it, so could not file a sheet from the
app at all.

A sheet naming an unknown code is *accepted* today — `logsheets.station_code`
is a loose column with no FK and the submit validator never inspects it. The
damage was never rejection; it was silence. The site is simply absent from the
picker, from the `/sheets` joins and from equipment history.

Design: docs/project_documentation/field_ops_station_creation_design.md
"""

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from field_ops.database import get_db
from field_ops.models import LogSheet, StationProposal, User
from field_ops.routers.auth import get_current_user, require_role

router = APIRouter(prefix="/api/v1", tags=["stations"])

#: Values `public.stations.monitoring_method` uses.
MONITORING_METHODS = ("campaign", "continuous")


class StationOut(BaseModel):
    station_code: str
    name: str | None
    latitude: float | None
    longitude: float | None
    elevation: float | None
    fault_segment: str | None
    status: str | None
    #: `inventory` (central, reconciled) or `field` (proposed here, unverified).
    #: The picker groups on this; it is not cosmetic. A row tagged `field` has
    #: not been checked by anyone and may be a typo'd duplicate.
    source: str = "inventory"

    model_config = {"from_attributes": True}


class StationProposalIn(BaseModel):
    """What the handset sends. Everything optional except the code."""

    client_uuid: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        description="Minted on the handset before going offline; the idempotency key.",
    )
    station_code: str = Field(min_length=1, max_length=10)
    name: str | None = Field(default=None, max_length=200)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    elevation: float | None = None
    monitoring_method: str = "campaign"
    municipality: str | None = Field(default=None, max_length=100)
    province: str | None = Field(default=None, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    proposed_at: datetime | None = Field(
        default=None,
        description="Handset time at creation. May be days before the server sees it.",
    )
    notes: str | None = None

    @field_validator("station_code")
    @classmethod
    def _normalise_code(cls, v: str) -> str:
        """Upper-case and strip.

        A phone keyboard capitalises inconsistently, and the whole point of the
        duplicate guard is that `pbis` and `PBIS` must collide rather than
        become two stations. Normalising here means the unique index sees the
        same string the picker does.
        """
        return v.strip().upper()

    @field_validator("monitoring_method")
    @classmethod
    def _known_method(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in MONITORING_METHODS:
            raise ValueError(f"monitoring_method must be one of {MONITORING_METHODS}")
        return v


class StationProposalOut(BaseModel):
    id: int
    client_uuid: uuid.UUID
    station_code: str
    name: str | None
    latitude: float | None
    longitude: float | None
    elevation: float | None
    monitoring_method: str
    status: str
    municipality: str | None
    province: str | None
    region: str | None
    created_by: int
    created_at: datetime | None
    proposed_at: datetime | None
    reconciled_at: datetime | None
    reconciled_by: int | None
    reconciled_station_id: int | None
    rejected_reason: str | None
    notes: str | None
    #: Sheets already filed against this code. A proposal carrying data is a
    #: different decision from an empty one — reject the first and you have
    #: orphaned real observations.
    sheet_count: int = 0

    model_config = {"from_attributes": True}


class RejectIn(BaseModel):
    reason: str = Field(min_length=1, description="Why. Recorded; the row is kept.")


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


@router.get("/stations", response_model=list[StationOut])
async def list_stations(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
    include_proposals: bool = Query(
        True,
        description="Include unreconciled field-created sites. Off gives the inventory only.",
    ),
) -> list[StationOut]:
    """
    Every station the picker may offer, whatever its status.

    Status is NOT filtered. Filtering to `status = 'active'` hid 15 sites the
    field team can legitimately be sent to: a station under maintenance is one
    they are visiting *because* it needs work, and a decommissioned site still
    gets occupied to recover equipment or close it out. An observer at a
    monument that is not in the picker cannot file a sheet at all — which is
    the same failure #118 reported, from a different cause.

    Ordering puts active sites first, then under maintenance, then closed, so
    the common case stays at the top of a ~140-entry list; within each group,
    by code. Field proposals sort last: they are the least verified rows here
    and should not displace the inventory.

    Raw SQL with ST_Y/ST_X because the ORM model for `public.stations` lives in
    the repo-root `src/db/models.py`. Reading it by text query rather than
    importing across the service boundary is deliberate.
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
    stations = [StationOut(**dict(row), source="inventory") for row in result.mappings().all()]

    if not include_proposals:
        return stations

    # Deliberately a second query rather than a SQL UNION. The inventory read
    # needs PostGIS; this one does not, and keeping them separate means the
    # proposal half stays exercisable without a PostGIS fixture. It also costs
    # nothing: both are small, unpaginated reads on the same connection.
    known = {s.station_code for s in stations}
    proposals = await db.execute(
        select(StationProposal)
        .where(StationProposal.reconciled_at.is_(None))
        .order_by(StationProposal.station_code)
    )
    for p in proposals.scalars().all():
        # A proposal whose code has since appeared in the inventory is not
        # shown twice. The inventory row wins: it is the reconciled one.
        if p.station_code in known:
            continue
        stations.append(
            StationOut(
                station_code=p.station_code,
                name=p.name,
                latitude=p.latitude,
                longitude=p.longitude,
                elevation=p.elevation,
                fault_segment=None,
                status=p.status,
                source="field",
            )
        )
    return stations


# ---------------------------------------------------------------------------
# propose
# ---------------------------------------------------------------------------


@router.post("/stations", response_model=StationProposalOut, status_code=201)
async def propose_station(
    payload: StationProposalIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StationProposalOut:
    """
    Create a site from the field. Any signed-in observer may do this.

    **No role gate, deliberately.** The person blocked is the observer standing
    at the monument; requiring an admin reintroduces exactly the office
    round-trip #118 is about. Safety comes from the row being a *proposal*
    until someone reconciles it, not from refusing to accept it.

    Idempotent on `client_uuid`: a retried sync returns the existing row with
    200-equivalent semantics rather than creating a second. That matters more
    than usual here, because the offline queue retries whole batches.

    Duplicate guard, layer 2 of 3 (409):
      * the code already exists in `public.stations`, or
      * an unreconciled proposal already claims it.

    Layer 1 is on the handset before submit; layer 3 is the partial unique
    index in fo007. **Neither 2 nor 3 is reachable from a handset that has been
    offline for two days**, so two teams can independently propose the same
    code and both will sync. That is unavoidable if people are to work offline,
    and it is why promotion is a human decision — see the reconcile endpoints.
    """
    # Idempotency first: a retry must not 409 against its own earlier write.
    existing = await db.execute(
        select(StationProposal).where(StationProposal.client_uuid == payload.client_uuid)
    )
    already = existing.scalar_one_or_none()
    if already is not None:
        return await _to_out(db, already)

    code = payload.station_code

    # Layer 2a — the central inventory. Raw SQL for the boundary reason above.
    # Guarded: on SQLite (unit tests) `stations` does not exist, and a missing
    # inventory must not be reported to the observer as "code is free" nor as
    # a 500. Treat it as "cannot check here" and fall through to the layers
    # that do work — the partial unique index still backstops.
    try:
        clash = await db.execute(
            text("SELECT 1 FROM stations WHERE upper(station_code) = :code LIMIT 1"),
            {"code": code},
        )
        if clash.first() is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Station code {code} already exists in the central inventory.",
            )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 - see the comment above
        pass

    # Layer 2b — an unreconciled proposal.
    pending = await db.execute(
        select(StationProposal).where(
            StationProposal.station_code == code,
            StationProposal.reconciled_at.is_(None),
        )
    )
    if pending.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Station code {code} has already been proposed and is awaiting "
                "review. If this is a different site, use a different code and "
                "note the conflict."
            ),
        )

    proposal = StationProposal(
        client_uuid=payload.client_uuid,
        station_code=code,
        name=payload.name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        elevation=payload.elevation,
        monitoring_method=payload.monitoring_method,
        status="active",
        municipality=payload.municipality,
        province=payload.province,
        region=payload.region,
        created_by=current_user.id,
        proposed_at=payload.proposed_at,
        notes=payload.notes,
    )
    db.add(proposal)
    try:
        await db.commit()
    except IntegrityError:
        # Layer 3 fired — two requests raced past layer 2. Same answer as 2b.
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Station code {code} has already been proposed and is awaiting review.",
        ) from None
    await db.refresh(proposal)
    return await _to_out(db, proposal)


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


@router.get("/station-proposals", response_model=list[StationProposalOut])
async def list_proposals(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_role("admin", "data_processor")),
    pending_only: bool = Query(True, description="Hide already-reconciled rows."),
) -> list[StationProposalOut]:
    """
    The reconcile queue. Pending first, oldest first.

    Each row carries `sheet_count` — how many logsheets already name this code.
    A proposal carrying data is a different decision from an empty one:
    rejecting the first orphans real observations that were validly collected
    at *something*.

    `require_role` gates this. It was written alongside the roles and has had
    no call site since; these are its first genuine consumers, which is what it
    was added for.
    """
    stmt = select(StationProposal)
    if pending_only:
        stmt = stmt.where(StationProposal.reconciled_at.is_(None))
    stmt = stmt.order_by(
        StationProposal.reconciled_at.is_(None).desc(),
        StationProposal.created_at,
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [await _to_out(db, r) for r in rows]


@router.post("/station-proposals/{proposal_id}/promote", response_model=StationProposalOut)
async def promote_proposal(
    proposal_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "data_processor")),
) -> StationProposalOut:
    """
    Accept a proposal into `public.stations`.

    **The one place field-ops writes to the central inventory.** Kept in a
    single function, and in raw SQL, for the same boundary reason the read path
    uses raw SQL.

    The upsert copies the seeder's shape — `ON CONFLICT (station_code) DO
    UPDATE ... COALESCE(EXCLUDED.col, stations.col)` — so promoting a sparse
    proposal cannot null out a field the spreadsheet later filled. That is not
    hypothetical: a proposal made at a monument has whatever the observer could
    see, which is usually less than the office has.

    The geometry is built here, at promotion, with the same
    `ST_SetSRID(ST_MakePoint(lon, lat), 4326)` the seeder uses — see the
    deviation note on the model. Coordinates may be NULL; the proposal is still
    promotable, and `PLWN` is already in the inventory without them.
    """
    proposal = await _get_pending(db, proposal_id)

    row = await db.execute(
        text("""
            INSERT INTO stations (
                station_code, name, location, elevation,
                monitoring_method, status, municipality, province, region
            )
            VALUES (
                :code, :name,
                CASE WHEN :lat IS NULL OR :lon IS NULL THEN NULL
                     ELSE ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
                END,
                :elevation, :method, :status, :municipality, :province, :region
            )
            ON CONFLICT (station_code) DO UPDATE SET
                name              = COALESCE(EXCLUDED.name, stations.name),
                location          = COALESCE(EXCLUDED.location, stations.location),
                elevation         = COALESCE(EXCLUDED.elevation, stations.elevation),
                monitoring_method = COALESCE(EXCLUDED.monitoring_method,
                                             stations.monitoring_method),
                municipality      = COALESCE(EXCLUDED.municipality, stations.municipality),
                province          = COALESCE(EXCLUDED.province, stations.province),
                region            = COALESCE(EXCLUDED.region, stations.region)
            RETURNING id
        """),
        {
            "code": proposal.station_code,
            "name": proposal.name,
            "lat": proposal.latitude,
            "lon": proposal.longitude,
            "elevation": proposal.elevation,
            "method": proposal.monitoring_method,
            "status": proposal.status,
            "municipality": proposal.municipality,
            "province": proposal.province,
            "region": proposal.region,
        },
    )
    station_id = row.scalar_one()

    proposal.reconciled_at = datetime.now().astimezone()
    proposal.reconciled_by = user.id
    proposal.reconciled_station_id = station_id
    await db.commit()
    await db.refresh(proposal)
    return await _to_out(db, proposal)


@router.post("/station-proposals/{proposal_id}/reject", response_model=StationProposalOut)
async def reject_proposal(
    proposal_id: int,
    payload: RejectIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "data_processor")),
) -> StationProposalOut:
    """
    Decline a proposal. **The row is kept.**

    A rejected proposal with sheets filed against it is a data-quality finding,
    not garbage: the observer was somewhere, and those sheets are valid
    observations of *something*. Deleting the row destroys the only record of
    who proposed the code and why it was refused.

    Stamping `reconciled_at` also releases the code from the partial unique
    index, so a corrected proposal can be made — including by the same person,
    when the reject was itself the mistake.
    """
    proposal = await _get_pending(db, proposal_id)
    proposal.reconciled_at = datetime.now().astimezone()
    proposal.reconciled_by = user.id
    proposal.rejected_reason = payload.reason
    await db.commit()
    await db.refresh(proposal)
    return await _to_out(db, proposal)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _get_pending(db: AsyncSession, proposal_id: int) -> StationProposal:
    """Fetch a proposal that has not been reconciled, or explain why not.

    409 rather than 404 on an already-reconciled row: it exists, and telling
    the reviewer "already handled" is more useful than "not found" when two
    people are working the same queue.
    """
    proposal = await db.get(StationProposal, proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if proposal.reconciled_at is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Proposal {proposal_id} was already reconciled at "
                f"{proposal.reconciled_at.isoformat()}."
            ),
        )
    return proposal


async def _to_out(db: AsyncSession, p: StationProposal) -> StationProposalOut:
    """Attach the sheet count, which drives the reconciler's decision.

    Counted through the ORM rather than raw SQL on purpose. `logsheets` is a
    field_ops table, and the test session applies
    `schema_translate_map={"field_ops": None}` so SQLite can create it — a
    literal `FROM field_ops.logsheets` would work in production and fail under
    every test. The inventory reads above are raw SQL because `public.stations`
    is genuinely outside this service; this one is not.
    """
    count = await db.execute(
        select(func.count())
        .select_from(LogSheet)
        .where(func.upper(LogSheet.station_code) == p.station_code)
    )
    return StationProposalOut(
        **{c.name: getattr(p, c.name) for c in p.__table__.columns},
        sheet_count=count.scalar_one() or 0,
    )
