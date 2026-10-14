# Database schema

The monitor stores 1 Hz data in **TimescaleDB** (PostgreSQL with the time-series
extension). The tables are created by Alembic migrations in the **repo-root**
`migrations/versions/`, not in this service:

| migration | what it does |
|---|---|
| `010_create_vadase_tables.py` | creates `vadase_velocities`, `vadase_displacements` (hypertables, 1-day chunks) and `vadase_events` |
| `011_add_displacement_source.py` | adds `vadase_displacements.displacement_source` |
| `012_add_timescaledb_policies.py` | compression, retention and continuous aggregates |

Apply them from the repository root with `uv run alembic upgrade head`.
`scripts/init_database.sql` in this service is the pre-Alembic schema (singular
table names, a `station` column); it is not what the adapter writes to.

Writes go through `src/adapters/outputs/timescaledb.py` (`TimescaleDBAdapter`).
Its `_INSERT_*` statements are the exact live column lists.

## Tables

### `vadase_velocities` (hypertable)

| column | type | meaning |
|---|---|---|
| `time` | TIMESTAMPTZ | GNSS epoch |
| `station_code` | TEXT | station ID; deliberately not a foreign key, to keep the 1 Hz write path free of lookups |
| `v_east`, `v_north`, `v_up` | DOUBLE | velocity, m/s |
| `v_horizontal` | DOUBLE | `sqrt(vE² + vN²)`, m/s |
| `quality` | DOUBLE | the parser's `cq` field (3D component quality) |

`UNIQUE (time, station_code)`; index `(station_code, time DESC)`.

### `vadase_displacements` (hypertable)

| column | type | meaning |
|---|---|---|
| `time`, `station_code` | | as above |
| `d_east`, `d_north`, `d_up` | DOUBLE | displacement, m |
| `d_horizontal` | DOUBLE | horizontal displacement, m |
| `overall_completeness` | DOUBLE | from the LDM sentence |
| `quality` | DOUBLE | the parser's `cq` field |
| `displacement_source` | TEXT, nullable | `RECEIVER`, `RECEIVER_SUSPECT` or `INTEGRATOR`: which `ReceiverMode` decision produced the row. NULL for rows written before migration 011 |

`UNIQUE (time, station_code)`; index `(station_code, time DESC)`.

### `vadase_events` (plain table)

| column | type | meaning |
|---|---|---|
| `id` | SERIAL | primary key |
| `station_code` | TEXT | |
| `detection_time` | TIMESTAMPTZ | first epoch over the threshold |
| `peak_velocity_horizontal` | DOUBLE | **mm/s** |
| `peak_displacement_horizontal` | DOUBLE | **mm** |
| `duration_seconds` | DOUBLE | |

Note the units: the stream tables are in m/s and m, the events table in mm/s and mm.

## Policies (migration 012)

| | `vadase_velocities` | `vadase_displacements` |
|---|---|---|
| compression | after 7 days, segment by `station_code`, order by `time DESC` | same |
| retention of raw 1 Hz rows | 60 days | 60 days |
| continuous aggregates | `vadase_velocities_1min` (refreshed every minute over a trailing 2 days) and `vadase_velocities_1hr` (every hour over a trailing 7 days), both kept permanently | none |

The aggregates are created `WITH NO DATA`. On a database that already holds
data, backfill with `CALL refresh_continuous_aggregate(...)`.

## How the adapter writes

- Velocity and displacement rows are buffered in memory and flushed with
  `executemany` when `batch_size` (100) rows are waiting or every
  `flush_interval` (1.0 s).
- Inserts use `ON CONFLICT (time, station_code) DO NOTHING`, so an NTRIP
  reconnect that replays an overlapping window does not duplicate rows.
- The 1 Hz path never blocks or raises on a database problem. A failed flush
  puts its batch back at the front of the buffer. Each buffer is bounded at
  `buffer_max_size` (10,000); past that the oldest rows are dropped and a
  `buffer_overflow_drop` warning is logged, at most once a second.
- Event rows are inserted immediately, and their errors do propagate to the caller.
- Connection settings come from `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
  and `DB_NAME`.
