"""create timeseries_data hypertable and velocity_products

Revision ID: 003
Revises: 002
Create Date: 2026-02-24 UTC

Creates two tables that consume output from the Bernese processing workflow:

  timeseries_data   — Daily Bernese solution positions per station.
                      TimescaleDB hypertable (partitioned by time).
                      Feeds the public data portal time series charts.

  velocity_products — Inter-seismic velocity estimates per station per solution.
                      Plain table (not a hypertable — velocities are computed
                      monthly or per-campaign, not at 1 Hz stream rates).

These are managed with raw SQL via op.execute() because TimescaleDB's
create_hypertable() is not expressible through SQLAlchemy DDL.

Design notes:
  - timeseries_data uses station_id (Integer FK) not station_code TEXT so that
    spatial joins (PostGIS proximity queries) are efficient.
  - solution_id is a free-form tag linking rows to the Bernese campaign run
    that produced them (e.g. "2024-Q1-PHIV-FINAL").
  - Units: north_mm, east_mm, up_mm are millimetres relative to a reference
    position; sigma_*_mm are formal uncertainties in mm.
"""

from alembic import op

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure TimescaleDB extension is enabled
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # -----------------------------------------------------------------
    # timeseries_data — Bernese daily position solutions
    # -----------------------------------------------------------------
    op.execute("""
        CREATE TABLE timeseries_data (
            time            TIMESTAMPTZ     NOT NULL,
            station_id      INTEGER         NOT NULL REFERENCES stations(id),
            north_mm        FLOAT,
            east_mm         FLOAT,
            up_mm           FLOAT,
            sigma_n_mm      FLOAT,
            sigma_e_mm      FLOAT,
            sigma_u_mm      FLOAT,
            solution_id     VARCHAR(50)
        )
    """)

    # Convert to TimescaleDB hypertable, partitioned by time
    op.execute("SELECT create_hypertable('timeseries_data', 'time')")

    op.execute(
        "CREATE INDEX idx_timeseries_station "
        "ON timeseries_data (station_id, time DESC)"
    )

    # -----------------------------------------------------------------
    # velocity_products — Inter-seismic velocity estimates
    # -----------------------------------------------------------------
    op.execute("""
        CREATE TABLE velocity_products (
            id                  SERIAL      PRIMARY KEY,
            station_id          INTEGER     NOT NULL REFERENCES stations(id),
            vel_north_mm_yr     FLOAT,
            vel_east_mm_yr      FLOAT,
            vel_up_mm_yr        FLOAT,
            sigma_n             FLOAT,
            sigma_e             FLOAT,
            sigma_u             FLOAT,
            solution_id         VARCHAR(50),
            date_computed       TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    op.execute(
        "CREATE INDEX idx_velocity_station "
        "ON velocity_products (station_id, date_computed DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS velocity_products")
    op.execute("DROP TABLE IF EXISTS timeseries_data")
