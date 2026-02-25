"""create ingestion_logs table

Revision ID: 006
Revises: 005
Create Date: 2026-02-25 UTC

Tracks the ingestion state of each RINEX file by its SHA-256 hash.

Design notes:
  - file_hash is the primary key (SHA-256 hex, 64 chars). A file's hash is
    content-addressed — the same physical bytes always produce the same hash,
    regardless of filename or path. This is the idempotency key.
  - status lifecycle: pending → processing → success | failed
    The scanner creates a 'pending' row; the Celery task updates it on
    completion or failure.
  - station_code is a loose TEXT reference to public.stations — consistent
    with the denormalization pattern used in field_ops and VADASE tables.
  - filepath records the source path at ingestion time for auditability.
"""

from alembic import op

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE ingestion_logs (
            file_hash       VARCHAR(64)     PRIMARY KEY,
            filename        VARCHAR(1024)   NOT NULL,
            filepath        TEXT            NOT NULL,
            station_code    VARCHAR(10),
            status          VARCHAR(20)     NOT NULL DEFAULT 'pending',
            -- valid values: pending | processing | success | failed
            queued_at       TIMESTAMPTZ     DEFAULT NOW(),
            ingested_at     TIMESTAMPTZ,
            error_message   TEXT
        )
    """)

    op.execute(
        "CREATE INDEX idx_ingestion_logs_status ON ingestion_logs (status)"
    )
    op.execute(
        "CREATE INDEX idx_ingestion_logs_station ON ingestion_logs (station_code)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingestion_logs")
