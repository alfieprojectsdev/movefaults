"""station_proposals — sites created in the field, awaiting reconciliation

Revision ID: fo007
Revises: fo006
Create Date: 2026-08-26 UTC

FO-001, issue #118. Design:
docs/project_documentation/field_ops_station_creation_design.md

WHAT THE FIELD REPORTED, AND WHAT IT ACTUALLY IS
------------------------------------------------
The report says the station list is stale — an old export nobody refreshed.
It is worse, and the difference decides what gets built.

`public.stations` is seeded from `data/network_inventory/stations.csv`: 138
rows, **every one `monitoring_method = continuous`**. `seed_network_inventory.py`
says outright that campaign occupations "must be seeded from another source",
and no such source exists. Campaign sites — the entire reason the campaign half
of the logsheet form exists — have never had an ingest path at all. Refreshing
the export more often would have fixed nothing.

WHY A NEW TABLE IN field_ops RATHER THAN A FLAG ON public.stations
-------------------------------------------------------------------
`public.stations` is read by VADASE and by the Bernese chain, not only by this
picker. A `verified` boolean there would mean every consumer has to remember to
filter on it, and the one that forgets pulls a field-proposed site into
processing. A separate table makes "unverified" structural instead.

It also keeps this migration in the field-ops tree. The root tree cannot reach
head on Neon — `012` sets `timescaledb.compress`, Neon reports
`timescaledb.license = apache` and refuses, and alembic's single transaction
rolls back everything behind it (see DEPLOY.md). Anything that must actually
deploy has to live here.

THE PARTIAL UNIQUE INDEX IS THE POINT
--------------------------------------
`uq_station_proposals_pending_code` is UNIQUE on `station_code` but **partial
on `reconciled_at IS NULL`**.

Partial, because a plain unique index would permanently burn every code ever
typed — including typos. Once a proposal is promoted or rejected, its code
must be proposable again: the rejected one because the reject may itself have
been the mistake, the promoted one because the row is kept for provenance and
a later re-proposal of the same code is a legitimate collision for a human to
look at, not something the schema should silently prevent.

WHAT THIS INDEX CANNOT DO
--------------------------
It is unreachable from a handset that has been offline for two days. Two teams
out of contact can independently propose the same code and both will sync
successfully — the index only sees them once they arrive.

That is unavoidable short of refusing offline work, and it is exactly why
promotion is a human decision rather than an automatic upsert. Reconcile is
where this class of collision is resolved; it is not a tidying step afterward.

DEVIATION FROM THE DESIGN
--------------------------
The design specifies a PostGIS POINT for the proposal's location. This uses
plain `latitude`/`longitude` doubles and builds the POINT at promotion time
with the same `ST_SetSRID(ST_MakePoint(lon, lat), 4326)` the seeder uses.

The design itself names testability as the largest hidden cost of this ticket:
there is no Postgres fixture, so nothing PostGIS-touching is testable. Floats
keep the whole proposal lifecycle exercisable on the existing SQLite conftest
and confine PostGIS to one promotion function — the "station-lookup seam" the
design offers as its second option. Nothing is lost; the picker consumes
lat/lon floats anyway, since `GET /stations` already extracts them via
ST_Y/ST_X.

Coordinates are NULLABLE. Open question 1 in the design asks whether they
should be required: handset accuracy is metres, which is fine for sorting a
picker by proximity and meaningless as a monument position. `PLWN` already
exists in the inventory with no coordinates, so NULL is not unprecedented, and
requiring a number the observer cannot measure invites a fabricated one.
"""

# UUID is imported explicitly rather than reached as `sa.dialects.postgresql`.
# `sqlalchemy.dialects` exposes a submodule only once something has imported it,
# so the attribute form happens to resolve during a real Postgres run -- the
# engine pulls the dialect in first -- and raises AttributeError anywhere that
# has not: offline `--sql` generation, or a SQLite target. Every other module in
# this service imports it this way.
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "fo007"
down_revision = "fo006"
branch_labels = None
depends_on = None

SCHEMA = "field_ops"


def upgrade() -> None:
    op.create_table(
        "station_proposals",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Idempotency key minted on the handset, same contract as
        # logsheets.client_uuid: a retried sync cannot double-insert.
        sa.Column("client_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("station_code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(200)),
        sa.Column("latitude", sa.Float()),
        sa.Column("longitude", sa.Float()),
        sa.Column("elevation", sa.Float()),
        sa.Column(
            "monitoring_method",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'campaign'"),
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default=sa.text("'active'")),
        sa.Column("municipality", sa.String(100)),
        sa.Column("province", sa.String(100)),
        sa.Column("region", sa.String(100)),
        sa.Column(
            "created_by",
            sa.Integer(),
            sa.ForeignKey(f"{SCHEMA}.users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("proposed_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("reconciled_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("reconciled_by", sa.Integer(), sa.ForeignKey(f"{SCHEMA}.users.id")),
        sa.Column("reconciled_station_id", sa.Integer()),
        sa.Column("rejected_reason", sa.Text()),
        sa.Column("notes", sa.Text()),
        sa.UniqueConstraint("client_uuid", name="uq_station_proposals_client_uuid"),
        schema=SCHEMA,
    )

    op.create_index(
        "ix_station_proposals_station_code",
        "station_proposals",
        ["station_code"],
        schema=SCHEMA,
    )

    # The load-bearing one. See the module docstring.
    op.create_index(
        "uq_station_proposals_pending_code",
        "station_proposals",
        ["station_code"],
        unique=True,
        schema=SCHEMA,
        postgresql_where=sa.text("reconciled_at IS NULL"),
    )

    # Reconcile queue: pending first, oldest first. The reviewer wants the
    # backlog, not the archive.
    op.create_index(
        "ix_station_proposals_pending",
        "station_proposals",
        ["reconciled_at", "created_at"],
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_station_proposals_pending", table_name="station_proposals", schema=SCHEMA)
    op.drop_index(
        "uq_station_proposals_pending_code", table_name="station_proposals", schema=SCHEMA
    )
    op.drop_index(
        "ix_station_proposals_station_code", table_name="station_proposals", schema=SCHEMA
    )
    op.drop_table("station_proposals", schema=SCHEMA)
