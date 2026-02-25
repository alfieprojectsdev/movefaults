"""create processing_status table

Revision ID: 005
Revises: 004
Create Date: 2026-02-25 UTC

Creates public.processing_status — a year-by-year tracking table for Bernese
data processing status per station. Mirrors the BERN52 Inventory spreadsheet
that PHIVOLCS currently maintains manually.

Key design choices:
  - UNIQUE(station_code, processing_year) enforces one row per station per year.
    The Bernese orchestrator (Phase 1B-iii) will use ON CONFLICT DO UPDATE to
    upsert status as processing progresses.
  - available_days is int4range[] — an array of PostgreSQL integer ranges.
    This models non-contiguous day availability naturally:
      '{[1,37],[141,365]}'::int4range[]
    Range containment query (day 200 available?):
      WHERE '[200,200]'::int4range <@ ANY(available_days)
  - status enum: pending | retrieving | processing | data_complete
    Matches the legend colors from the BERN52 inventory sheets.
  - updated_at is refreshed by an UPDATE trigger so the orchestrator can
    detect stale rows without a separate audit log.

Relationship to Phase 1B-iii (Bernese orchestrator):
  This table becomes the orchestrator's job queue. Before launching a BPE run,
  the orchestrator queries for rows WHERE status IN ('pending', 'retrieving')
  and status_year = <target_year>.
"""

from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE processing_status (
            id                  SERIAL          PRIMARY KEY,
            station_code        VARCHAR(10)     NOT NULL,
            processing_year     INTEGER         NOT NULL,

            -- Workflow state
            status              VARCHAR(50)     NOT NULL DEFAULT 'pending',
            -- valid values: pending | retrieving | processing | data_complete

            -- Available data expressed as non-contiguous Julian day ranges
            -- e.g. '{[1,37],[141,365]}'::int4range[] means days 1-37 and 141-365 are present
            available_days      int4range[],

            staff_assigned      TEXT,
            notes               TEXT,

            updated_at          TIMESTAMPTZ     DEFAULT NOW(),

            CONSTRAINT uq_processing_status UNIQUE (station_code, processing_year)
        )
    """)

    # Trigger to auto-refresh updated_at on every UPDATE
    op.execute("""
        CREATE OR REPLACE FUNCTION set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute("""
        CREATE TRIGGER trg_processing_status_updated_at
        BEFORE UPDATE ON processing_status
        FOR EACH ROW EXECUTE FUNCTION set_updated_at()
    """)

    # Index for orchestrator job queue query: pending rows for a given year
    op.execute("""
        CREATE INDEX idx_processing_status_queue
            ON processing_status (processing_year, status)
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_processing_status_updated_at ON processing_status")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at")
    op.execute("DROP TABLE IF EXISTS processing_status")
