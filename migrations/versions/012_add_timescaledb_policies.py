"""Add TimescaleDB compression, retention, and continuous aggregate policies

Revision ID: 012
Revises: 011
Create Date: 2026-04-27 UTC

Resolves DL-012 from migration 010. Without these policies the R740 drives fill silently
at 35 stations x 1 Hz (~3 M rows/day uncompressed).

Policies applied
----------------
vadase_velocities:
  - Compression: segmentby=station_code, orderby=time DESC. Chunks compress after 7 days.
    Expected 90%+ reduction on GNSS/seismic time series (delta-of-delta on time,
    run-length on station_code).
  - Retention: raw 1 Hz rows dropped after 60 days. 60 days covers any missed reprocessing
    window and one monthly summary cycle; long-term drift uses the aggregates below.
  - 1-minute continuous aggregate: max/avg v_horizontal + avg ENU components.
    Refresh policy: trailing 2-day window, every 1 minute.
  - 1-hour continuous aggregate: same columns, built directly from the raw hypertable.
    Refresh policy: trailing 7-day window, every 1 hour.
  - Aggregates are retained permanently (no retention policy on the aggregate views).

vadase_displacements:
  - Compression + retention: same parameters as vadase_velocities.
  - No continuous aggregates: displacement is derivative; velocity is the primary seismic
    signal for long-term tectonic drift analysis.

Design notes
------------
- compress_segmentby='station_code' groups rows by station for efficient per-station range
  scans (Grafana dashboard, event queries).
- compress_orderby='time DESC' optimises recency-first access patterns.
- Both hypertables have UNIQUE(time, station_code) which is compatible with compression
  because the partition column (time) is included.
- WITH NO DATA: aggregates start empty; refresh policy backfills the trailing window on
  first run. For a fresh deployment this is fine; for an existing DB with data, run a
  manual CALL refresh_continuous_aggregate(...) to backfill further if needed.
"""

from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # vadase_velocities — compression
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE vadase_velocities SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'station_code',
            timescaledb.compress_orderby = 'time DESC'
        )
    """)
    op.execute(
        "SELECT add_compression_policy('vadase_velocities', INTERVAL '7 days')"
    )

    # vadase_velocities — retention (raw 1 Hz rows)
    op.execute(
        "SELECT add_retention_policy('vadase_velocities', INTERVAL '60 days')"
    )

    # vadase_velocities — 1-minute continuous aggregate
    op.execute("""
        CREATE MATERIALIZED VIEW vadase_velocities_1min
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 minute', time)  AS bucket,
            station_code,
            MAX(v_horizontal)              AS v_horizontal_max,
            AVG(v_horizontal)              AS v_horizontal_avg,
            AVG(v_east)                    AS v_east_avg,
            AVG(v_north)                   AS v_north_avg,
            AVG(v_up)                      AS v_up_avg,
            COUNT(*)                       AS sample_count
        FROM vadase_velocities
        GROUP BY bucket, station_code
        WITH NO DATA
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy(
            'vadase_velocities_1min',
            start_offset      => INTERVAL '2 days',
            end_offset        => INTERVAL '1 minute',
            schedule_interval => INTERVAL '1 minute'
        )
    """)

    # vadase_velocities — 1-hour continuous aggregate (built from raw table)
    op.execute("""
        CREATE MATERIALIZED VIEW vadase_velocities_1hr
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('1 hour', time)    AS bucket,
            station_code,
            MAX(v_horizontal)              AS v_horizontal_max,
            AVG(v_horizontal)              AS v_horizontal_avg,
            AVG(v_east)                    AS v_east_avg,
            AVG(v_north)                   AS v_north_avg,
            AVG(v_up)                      AS v_up_avg,
            COUNT(*)                       AS sample_count
        FROM vadase_velocities
        GROUP BY bucket, station_code
        WITH NO DATA
    """)
    op.execute("""
        SELECT add_continuous_aggregate_policy(
            'vadase_velocities_1hr',
            start_offset      => INTERVAL '7 days',
            end_offset        => INTERVAL '1 hour',
            schedule_interval => INTERVAL '1 hour'
        )
    """)

    # ------------------------------------------------------------------
    # vadase_displacements — compression
    # ------------------------------------------------------------------
    op.execute("""
        ALTER TABLE vadase_displacements SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'station_code',
            timescaledb.compress_orderby = 'time DESC'
        )
    """)
    op.execute(
        "SELECT add_compression_policy('vadase_displacements', INTERVAL '7 days')"
    )

    # vadase_displacements — retention (raw 1 Hz rows)
    op.execute(
        "SELECT add_retention_policy('vadase_displacements', INTERVAL '60 days')"
    )


def downgrade() -> None:
    op.execute("SELECT remove_retention_policy('vadase_displacements', if_exists => true)")
    op.execute("SELECT remove_compression_policy('vadase_displacements', if_exists => true)")
    op.execute("ALTER TABLE vadase_displacements SET (timescaledb.compress = false)")

    op.execute("DROP MATERIALIZED VIEW IF EXISTS vadase_velocities_1hr")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS vadase_velocities_1min")

    op.execute("SELECT remove_retention_policy('vadase_velocities', if_exists => true)")
    op.execute("SELECT remove_compression_policy('vadase_velocities', if_exists => true)")
    op.execute("ALTER TABLE vadase_velocities SET (timescaledb.compress = false)")
