"""expand stations table with administrative and operational metadata

Revision ID: 004
Revises: 003
Create Date: 2026-02-25 UTC

Adds columns identified from PHIVOLCS SiteMetaData spreadsheets (via RAG analysis):

  monitoring_method       — continuous | campaign (cGPS vs episodic deployments)
  municipality            — administrative location for government reporting
  province                — Philippine province
  region                  — Philippine region (e.g. Region X – Northern Mindanao)
  land_owner              — entity owning the site property (MOA/access tracking)
  maintenance_interval_days — scheduled maintenance frequency in days (e.g. 180 = twice/year)

Design notes:
  - All new columns are nullable — existing rows are unaffected.
  - monitoring_method defaults to 'continuous' since the existing 35+ stations
    are all cGPS; campaign stations are added explicitly.
  - Administrative location is three separate columns (not JSONB) to support
    indexed equality queries for regional reporting (WHERE region = 'Region X').
"""

from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE stations
            ADD COLUMN IF NOT EXISTS monitoring_method        VARCHAR(20) DEFAULT 'continuous',
            ADD COLUMN IF NOT EXISTS municipality             TEXT,
            ADD COLUMN IF NOT EXISTS province                 TEXT,
            ADD COLUMN IF NOT EXISTS region                   TEXT,
            ADD COLUMN IF NOT EXISTS land_owner               TEXT,
            ADD COLUMN IF NOT EXISTS maintenance_interval_days INTEGER
    """)

    # Index for the most common reporting query: "all stations in region X"
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_stations_region ON stations (region)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_stations_region")
    op.execute("""
        ALTER TABLE stations
            DROP COLUMN IF EXISTS monitoring_method,
            DROP COLUMN IF EXISTS municipality,
            DROP COLUMN IF EXISTS province,
            DROP COLUMN IF EXISTS region,
            DROP COLUMN IF EXISTS land_owner,
            DROP COLUMN IF EXISTS maintenance_interval_days
    """)
