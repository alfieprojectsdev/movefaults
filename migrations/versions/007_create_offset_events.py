"""create offset_events table

Revision ID: 007
Revises: 006
Create Date: 2026-03-02 UTC

Stores co-seismic and equipment-change offset epochs for the velocity pipeline.

Design notes:
  - Replaces the manual flat `offsets` text file maintained in PLOTS/.
    The Bernese orchestrator materializes this table to an `offsets` file
    before invoking vel_line_v8.m. MATLAB reads the file; the DB is the
    source of truth.

  - event_date is DATE (not FLOAT decimal_year). The decimal year used by
    vel_line_v8.m is computed at materialisation time:
        decimal_year = year + (day_of_year - 1) / days_in_year
    Storing a proper DATE avoids float precision drift and keeps the record
    timezone-safe.

  - event_type mirrors the tag vocabulary in the existing offsets file:
        EQ  — co-seismic step (earthquake)
        VE  — volcanic event
        CE  — calibration or equipment change (antenna swap, etc.)
        UK  — unknown / unclassified
    Enforced by a CHECK constraint to prevent silent misspellings.

  - UNIQUE (station_code, event_date, event_type) prevents duplicate entries
    for the same event. Two distinct event types on the same day for the same
    station are allowed (e.g. a CE and an EQ on the same date).

  - station_code is a loose TEXT reference to public.stations, consistent
    with the denormalization pattern used in processing_status, field_ops,
    and ingestion_logs.

Relationship to velocity pipeline:
  Before vel_line_v8.m runs, the orchestrator queries:
      SELECT station_code, event_date, event_type
      FROM offset_events
      WHERE station_code = :site
      ORDER BY event_date
  and writes the PLOTS/offsets file from the result. This replaces the
  manual Step 3 (check and update offsets file) in the PHIVOLCS work
  instruction.
"""

from alembic import op

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE offset_events (
            id              SERIAL          PRIMARY KEY,
            station_code    VARCHAR(10)     NOT NULL,
            event_date      DATE            NOT NULL,

            -- Tag vocabulary matches PHIVOLCS offsets file convention
            event_type      VARCHAR(10)     NOT NULL DEFAULT 'UK',
            -- valid values: EQ (earthquake), VE (volcanic event),
            --               CE (calibration/equipment change), UK (unknown)

            description     TEXT,
            created_at      TIMESTAMPTZ     DEFAULT NOW(),

            CONSTRAINT uq_offset_events UNIQUE (station_code, event_date, event_type),
            CONSTRAINT chk_offset_event_type
                CHECK (event_type IN ('EQ', 'VE', 'CE', 'UK'))
        )
    """)

    # Fast lookup when materialising the offsets file for a single station
    op.execute("""
        CREATE INDEX idx_offset_events_station
            ON offset_events (station_code, event_date)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS offset_events")
