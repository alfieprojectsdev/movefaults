"""create stations table

Revision ID: 001
Revises: (none — this is the initial migration)
Create Date: 2026-02-24 UTC

Creates the canonical CORS station inventory table.

Design notes:
  - PostGIS GEOMETRY(Point, 4326) for location — WGS84 geographic coordinates.
    Enables ST_DWithin proximity queries (e.g. "stations within 50 km of epicentre").
    Using raw SQL because op.create_table() can't express PostGIS column types natively.
  - JSONB for metadata_json — allows GIN index queries on antenna/receiver metadata.
  - host/port are VADASE TCP connection fields merged here so one table serves all consumers.
  - fault_segment is PHIVOLCS-specific context linking stations to named fault structures.
  - date_added tracks when the row was inserted (default NOW()); date_installed is the
    physical antenna installation date (may differ, entered manually).
  - uq_stations_station_code constraint is named explicitly (not auto-named) so the seed
    script's ON CONFLICT clause can reference it by name.
"""

from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Enable PostGIS (no-op if already enabled)
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.execute("""
        CREATE TABLE stations (
            id              SERIAL          PRIMARY KEY,
            station_code    VARCHAR(10)     NOT NULL,
            name            VARCHAR(255),
            location        GEOMETRY(Point, 4326),
            elevation       FLOAT,
            agency          VARCHAR(50)     DEFAULT 'PHIVOLCS',
            status          VARCHAR(50)     DEFAULT 'active',
            date_installed  DATE,
            fault_segment   TEXT,
            host            TEXT,
            port            INTEGER,
            metadata_json   JSONB,
            date_added      TIMESTAMPTZ     DEFAULT NOW(),
            CONSTRAINT uq_stations_station_code UNIQUE (station_code)
        )
    """)

    op.execute(
        "CREATE INDEX idx_stations_location ON stations USING GIST (location)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stations")
