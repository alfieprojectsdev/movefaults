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
from collections.abc import Sequence
from datetime import date, datetime

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

    # ── Detail, added 2026-09-15 ────────────────────────────────────────────
    #
    # These columns already existed on `public.stations` and this endpoint was
    # not returning them, so the app could show a station's code and name and
    # nothing about the place. An observer deciding whether they are at the
    # right monument, or reading up before travelling to one, had no source
    # for it in the app.
    #
    # No migration: every field below is an existing column. `last_visit`,
    # `project` and `collaborator` appear in the seed CSV but NOT in the
    # table, so they are deliberately absent here. "When was this site last
    # visited" is a logsheets question and belongs to `GET /sheets`.
    #
    # Optional on both sources, because a proposal carries only what the
    # observer typed at the monument and the inventory is itself incomplete
    # for older sites.
    municipality: str | None = None
    province: str | None = None
    region: str | None = None

    #: `continuous` | `campaign`. The sheet's first question, so knowing it
    #: per-station lets the form preselect rather than ask.
    monitoring_method: str | None = None

    #: Inventory only — a proposal has no reconciled owner yet.
    land_owner: str | None = None
    date_installed: date | None = None
    agency: str | None = None
    #: Inventory only. With the date of the last sheet it answers "is this
    #: site overdue", which nothing in the app can currently express.
    maintenance_interval_days: int | None = None

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
    #: `inventory`, `proposal`, or None when the code was free. A marked row is
    #: a claim the office has to settle against another claim, not a row it can
    #: promote on its own — see `promote_proposal`.
    collides_with: str | None = None
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
                status,
                municipality,
                province,
                region,
                monitoring_method,
                land_owner,
                date_installed,
                agency,
                maintenance_interval_days
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
    proposals = await db.execute(
        select(StationProposal)
        .where(StationProposal.reconciled_at.is_(None))
        # Uncontested claims first within a code, so that when two teams claim
        # the same code the picker offers the one that got there first rather
        # than whichever row sorts first by accident. Settling which is right
        # is the reconcile screen's job; the picker only has to stop showing
        # one code twice, which would read as two sites.
        .order_by(
            StationProposal.station_code,
            StationProposal.collides_with.is_not(None),
            StationProposal.id,
        )
    )
    return _append_proposals(stations, proposals.scalars().all())


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

    **A taken code is accepted and marked, not refused** (#228). If the code
    already exists in `public.stations`, or an unreconciled proposal already
    claims it, the row is still created with `collides_with` set to
    `inventory` or `proposal`, and the office settles it on the reconcile
    screen.

    This used to be a 409, and the proposal never became a row at all — so a
    site somebody travelled to could sit unseen on one handset until the phone
    was wiped. The guard cannot reach a handset that has been offline for two
    days, so two teams proposing the same code is the expected outcome of
    working offline correctly, not observer error. The office can see both
    claims; the observer at the monument cannot.

    What still refuses: nothing here. The partial unique index (fo008) keeps
    at most one *uncontested* pending claim per code, so an unmarked duplicate
    that races past the checks below is caught and retried as a collision
    rather than lost.
    """
    # Idempotency first: a retry must not 409 against its own earlier write.
    existing = await db.execute(
        select(StationProposal).where(StationProposal.client_uuid == payload.client_uuid)
    )
    already = existing.scalar_one_or_none()
    if already is not None:
        return await _to_out(db, already)

    code = payload.station_code
    collides_with = await _what_the_code_collides_with(db, code)

    proposal = _build_proposal(payload, current_user, collides_with)
    db.add(proposal)
    try:
        await db.commit()
    except IntegrityError:
        # The unique index fired: another uncontested claim on this code
        # committed between the check above and this insert. The collision is
        # real, it simply happened a few milliseconds later than the read saw.
        # Record it as one and keep the row, which is the whole point of #228 —
        # losing a race is not a reason to strand a site on a handset.
        await db.rollback()
        proposal = _build_proposal(payload, current_user, "proposal")
        db.add(proposal)
        await db.commit()
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
    merge_into_existing: bool = Query(
        False,
        description=(
            "Required to promote onto a code the inventory already holds. "
            "Says: I have compared both claims and this proposal describes "
            "the same monument."
        ),
    ),
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

    **`merge_into_existing` guards the upsert half** (#228). That `ON CONFLICT
    DO UPDATE ... COALESCE` is safe for the case it was written for — filling
    gaps in a row this proposal is the origin of — and quietly destructive for
    the case #228 introduced. Promoting a *colliding* claim would move the
    existing station's name and location to wherever the second team stood,
    with no record that it had ever been anywhere else. Two teams disagreeing
    about what a code names is precisely when that must not happen silently.

    So promotion onto an occupied code refuses unless the reviewer passes the
    flag, which asserts they compared both claims and these are one monument.
    The alternative — the second team's site is genuinely different — is a
    reject with a reason, after which the observer can re-propose under a free
    code and the rejected row keeps the trail.

    The check reads `public.stations` rather than the proposal's
    `collides_with`, deliberately. That marker records what was true when the
    server heard, possibly days ago: an unmarked proposal's code may have been
    promoted by somebody else since, and a marked one's rival may have been
    rejected. Only the inventory answers "is this code occupied right now".
    """
    proposal = await _get_pending(db, proposal_id)

    if not merge_into_existing:
        occupied = await db.execute(
            text("SELECT 1 FROM stations WHERE upper(station_code) = :code LIMIT 1"),
            {"code": proposal.station_code},
        )
        if occupied.first() is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Station code {proposal.station_code} is already in the central "
                    "inventory. Promoting would overwrite that station with this "
                    "proposal's details. If both describe the same monument, retry "
                    "with merge_into_existing=true; if they are different sites, "
                    "reject this one with a reason so the observer can re-propose "
                    "under a free code."
                ),
            )

    row = await db.execute(
        text("""
            INSERT INTO stations (
                station_code, name, location, elevation,
                monitoring_method, status, municipality, province, region
            )
            VALUES (
                :code, :name,
                -- The casts are load-bearing, not decoration.
                --
                -- :lat and :lon appear nowhere else in this statement, and
                -- neither position gives Postgres a type to infer: IS NULL
                -- says nothing about its operand, and ST_MakePoint is
                -- overloaded. asyncpg uses the EXTENDED query protocol, so it
                -- must ask the server to describe the parameters before
                -- binding, and the server answers AmbiguousParameterError --
                -- "could not determine data type of parameter $3".
                --
                -- This statement succeeds in psql, which substitutes literals
                -- over the SIMPLE protocol where no parameter is ever typed.
                -- So running it by hand proves nothing about the endpoint.
                -- Found on gps3, 2026-09-16, the first time these tests met a
                -- real database.
                CASE WHEN CAST(:lat AS double precision) IS NULL
                       OR CAST(:lon AS double precision) IS NULL THEN NULL
                     ELSE ST_SetSRID(
                            ST_MakePoint(CAST(:lon AS double precision),
                                         CAST(:lat AS double precision)),
                            4326)
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


def _append_proposals(
    stations: list[StationOut], proposals: Sequence[StationProposal]
) -> list[StationOut]:
    """Add field-proposed sites to the inventory list, one entry per code.

    A separate function because nothing else in `list_stations` is testable
    without PostGIS — the inventory read uses ST_Y/ST_X, so an HTTP-level test
    of this merge cannot run on the SQLite conftest. The dedupe is the part
    that has a bug in it if anyone gets it wrong, so it lives where a test can
    reach it.

    Two codes are dropped:
      * one the inventory already lists — the reconciled row wins;
      * a second pending claim on a code already added here (#228). Both
        claims are real and both are kept in the database; showing both in the
        picker would read as two different sites with one code, which is the
        collision handed back to the observer instead of to the office.

    Caller ordering decides which claim survives — see `list_stations`.
    """
    known = {s.station_code for s in stations}
    for p in proposals:
        if p.station_code in known:
            continue
        known.add(p.station_code)
        stations.append(
            StationOut(
                station_code=p.station_code,
                name=p.name,
                latitude=p.latitude,
                longitude=p.longitude,
                elevation=p.elevation,
                fault_segment=None,
                status=p.status,
                municipality=p.municipality,
                province=p.province,
                region=p.region,
                monitoring_method=p.monitoring_method,
                # Absent by construction rather than by omission: a proposal
                # has no reconciled owner, no install date and no agency until
                # somebody promotes it. Returning None says "not known yet",
                # which is the true state.
                land_owner=None,
                date_installed=None,
                agency=None,
                maintenance_interval_days=None,
                source="field",
            )
        )
    return stations


def _build_proposal(
    payload: StationProposalIn, user: User, collides_with: str | None
) -> StationProposal:
    """One place that maps the handset's payload onto a row.

    Called twice — once optimistically, once after losing a race to the unique
    index — so the two paths cannot drift into storing different things.
    """
    return StationProposal(
        client_uuid=payload.client_uuid,
        station_code=payload.station_code,
        name=payload.name,
        latitude=payload.latitude,
        longitude=payload.longitude,
        elevation=payload.elevation,
        monitoring_method=payload.monitoring_method,
        status="active",
        municipality=payload.municipality,
        province=payload.province,
        region=payload.region,
        created_by=user.id,
        proposed_at=payload.proposed_at,
        notes=payload.notes,
        collides_with=collides_with,
    )


async def _what_the_code_collides_with(db: AsyncSession, code: str) -> str | None:
    """`inventory`, `proposal`, or None if the code is free.

    The inventory read is raw SQL for the boundary reason the read path
    explains, and is guarded: on SQLite (unit tests) `public.stations` does not
    exist. A missing inventory must not be reported as a collision — that would
    mark every proposal in the test suite — nor as a 500. Treat it as "cannot
    check here" and fall through to the proposal check, which works everywhere.

    The inventory is checked first because it is the more specific answer: a
    code held by a reconciled station is a different conversation from two
    field teams disagreeing, and the reviewer reads this field to tell them
    apart.
    """
    try:
        clash = await db.execute(
            text("SELECT 1 FROM stations WHERE upper(station_code) = :code LIMIT 1"),
            {"code": code},
        )
        if clash.first() is not None:
            return "inventory"
    except Exception:  # noqa: BLE001 - see the docstring
        pass

    pending = await db.execute(
        select(StationProposal).where(
            StationProposal.station_code == code,
            StationProposal.reconciled_at.is_(None),
        )
    )
    if pending.first() is not None:
        return "proposal"
    return None


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
