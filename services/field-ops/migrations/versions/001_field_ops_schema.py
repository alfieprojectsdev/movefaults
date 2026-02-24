"""create field_ops schema and tables

Revision ID: fo001
Revises: (none — first migration for field_ops schema)
Create Date: 2026-02-24 UTC

Creates the field_ops PostgreSQL schema and its four tables.
Uses raw SQL via op.execute() to keep the DDL explicit and handle the
schema-prefixed table names cleanly.

Design notes:
  - field_ops.alembic_version tracks this migration history separately from
    the public schema (set via version_table_schema in env.py).
  - client_uuid UNIQUE on logsheets enables ON CONFLICT (client_uuid) DO NOTHING
    for idempotent batch sync from the PWA's offline queue.
  - station_code is TEXT (not FK) to avoid cross-schema FK complexity.
    The same loose-reference pattern used in VADASE hot-path tables.
"""

from alembic import op

revision = "fo001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS field_ops")

    op.execute("""
        CREATE TABLE field_ops.users (
            id              SERIAL          PRIMARY KEY,
            username        VARCHAR(50)     NOT NULL,
            hashed_password TEXT            NOT NULL,
            role            VARCHAR(20)     DEFAULT 'field_staff',
            created_at      TIMESTAMPTZ     DEFAULT NOW(),
            CONSTRAINT uq_users_username UNIQUE (username)
        )
    """)

    op.execute("""
        CREATE TABLE field_ops.logsheets (
            id                      SERIAL          PRIMARY KEY,
            client_uuid             UUID            NOT NULL,
            station_code            VARCHAR(10)     NOT NULL,
            submitted_by            INTEGER         REFERENCES field_ops.users(id),
            visit_date              DATE            NOT NULL,
            arrival_time            TIMESTAMPTZ,
            departure_time          TIMESTAMPTZ,
            weather_conditions      TEXT,
            maintenance_performed   TEXT,
            equipment_status        VARCHAR(50),
            notes                   TEXT,
            synced_at               TIMESTAMPTZ,
            created_at              TIMESTAMPTZ     DEFAULT NOW(),
            CONSTRAINT uq_logsheets_client_uuid UNIQUE (client_uuid)
        )
    """)

    op.execute(
        "CREATE INDEX idx_logsheets_station ON field_ops.logsheets (station_code, visit_date DESC)"
    )

    op.execute("""
        CREATE TABLE field_ops.equipment_inventory (
            id              SERIAL          PRIMARY KEY,
            qr_code         TEXT            NOT NULL,
            equipment_type  VARCHAR(100),
            serial_number   VARCHAR(100),
            station_code    VARCHAR(10),
            status          VARCHAR(50)     DEFAULT 'active',
            last_seen       TIMESTAMPTZ,
            notes           TEXT,
            CONSTRAINT uq_equipment_qr_code UNIQUE (qr_code)
        )
    """)

    op.execute("""
        CREATE TABLE field_ops.logsheet_photos (
            id              SERIAL          PRIMARY KEY,
            logsheet_id     INTEGER         NOT NULL REFERENCES field_ops.logsheets(id),
            filename        TEXT            NOT NULL,
            storage_path    TEXT,
            taken_at        TIMESTAMPTZ,
            uploaded_at     TIMESTAMPTZ     DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS field_ops.logsheet_photos")
    op.execute("DROP TABLE IF EXISTS field_ops.equipment_inventory")
    op.execute("DROP TABLE IF EXISTS field_ops.logsheets")
    op.execute("DROP TABLE IF EXISTS field_ops.users")
    op.execute("DROP SCHEMA IF EXISTS field_ops")
