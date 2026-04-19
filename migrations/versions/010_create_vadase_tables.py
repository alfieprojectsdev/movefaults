"""create vadase_velocities, vadase_displacements, vadase_events tables

Revision ID: 010
Revises: 009
Create Date: 2026-04-18 UTC

Three tables for the VADASE real-time monitor hot-path writes:

  vadase_velocities     -- 1 Hz velocity measurements per station (hypertable).
  vadase_displacements  -- 1 Hz displacement measurements per station (hypertable).
  vadase_events         -- Event detection summaries (plain table, rare writes).

Design notes:
  - station_code is TEXT (denormalized), not an FK to stations.id.
    Hot-path writes at 35 stations x 1 Hz cannot afford FK lookups or PostGIS joins.
  - vadase_velocities and vadase_displacements are TimescaleDB hypertables with
    1-day chunk intervals (~6M rows/chunk -- tractable for compression and range scans).
  - vadase_events is a plain table; events are rare and benefit from indexed queries.
  - Units: velocity components in m/s; displacement components in metres;
    peak_velocity in mm/s and peak_displacement in mm for the events table.
  - quality column: stores Leica NMEA parser field 'cq' (3D component quality).
    See DL-010 for cq->quality mapping rationale.
  - Retention and compression policies are intentionally deferred. See DL-012.
    Tables will grow unbounded until a follow-up operations task provisions policies.
"""

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # -----------------------------------------------------------------
    # vadase_velocities -- 1 Hz velocity stream
    # -----------------------------------------------------------------
    op.execute("""
        CREATE TABLE vadase_velocities (
            time            TIMESTAMPTZ     NOT NULL,
            station_code    TEXT            NOT NULL,
            v_east          DOUBLE PRECISION,
            v_north         DOUBLE PRECISION,
            v_up            DOUBLE PRECISION,
            v_horizontal    DOUBLE PRECISION,
            quality         DOUBLE PRECISION
        )
    """)

    # Idempotent re-ingestion: NTRIP reconnects can replay overlapping windows.
    # ON CONFLICT DO NOTHING requires a UNIQUE constraint as the conflict target.
    op.execute(
        "ALTER TABLE vadase_velocities "
        "ADD CONSTRAINT uq_vadase_vel_time_station UNIQUE (time, station_code)"
    )

    op.execute(
        "SELECT create_hypertable('vadase_velocities', 'time', "
        "chunk_time_interval => INTERVAL '1 day')"
    )

    op.execute(
        "CREATE INDEX idx_vadase_vel_station "
        "ON vadase_velocities (station_code, time DESC)"
    )

    op.execute(
        "COMMENT ON COLUMN vadase_velocities.quality IS "
        "'Parser field cq (3D component quality from Leica NMEA LVM sentence) stored as quality. "
        "See DL-010 for cq->quality alias mapping.'"
    )

    op.execute(
        "COMMENT ON TABLE vadase_velocities IS "
        "'No retention or compression policy applied -- see DL-012 for follow-up operations task.'"
    )

    # -----------------------------------------------------------------
    # vadase_displacements -- 1 Hz displacement stream
    # -----------------------------------------------------------------
    op.execute("""
        CREATE TABLE vadase_displacements (
            time                 TIMESTAMPTZ      NOT NULL,
            station_code         TEXT             NOT NULL,
            d_east               DOUBLE PRECISION,
            d_north              DOUBLE PRECISION,
            d_up                 DOUBLE PRECISION,
            d_horizontal         DOUBLE PRECISION,
            overall_completeness DOUBLE PRECISION,
            quality              DOUBLE PRECISION
        )
    """)

    op.execute(
        "ALTER TABLE vadase_displacements "
        "ADD CONSTRAINT uq_vadase_disp_time_station UNIQUE (time, station_code)"
    )

    op.execute(
        "SELECT create_hypertable('vadase_displacements', 'time', "
        "chunk_time_interval => INTERVAL '1 day')"
    )

    op.execute(
        "CREATE INDEX idx_vadase_disp_station "
        "ON vadase_displacements (station_code, time DESC)"
    )

    op.execute(
        "COMMENT ON COLUMN vadase_displacements.quality IS "
        "'Parser field cq (3D component quality from Leica NMEA LDM sentence) stored as quality. "
        "See DL-010 for cq->quality alias mapping.'"
    )

    op.execute(
        "COMMENT ON TABLE vadase_displacements IS "
        "'No retention or compression policy applied -- see DL-012 for follow-up operations task.'"
    )

    # -----------------------------------------------------------------
    # vadase_events -- event detection summaries
    # -----------------------------------------------------------------
    op.execute("""
        CREATE TABLE vadase_events (
            id                          SERIAL           PRIMARY KEY,
            station_code                TEXT             NOT NULL,
            detection_time              TIMESTAMPTZ      NOT NULL,
            peak_velocity_horizontal    DOUBLE PRECISION,
            peak_displacement_horizontal DOUBLE PRECISION,
            duration_seconds            DOUBLE PRECISION
        )
    """)

    op.execute(
        "CREATE INDEX idx_vadase_events_station "
        "ON vadase_events (station_code, detection_time DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS vadase_events")
    op.execute("DROP TABLE IF EXISTS vadase_displacements")
    op.execute("DROP TABLE IF EXISTS vadase_velocities")
