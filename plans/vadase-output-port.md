# Plan

## Overview

IngestionCore (the VADASE hexagonal domain core) has no concrete OutputPort implementation. The legacy DatabaseWriter in src/database/writer.py has working asyncpg batch-write logic but lives outside the hexagonal adapter boundary. No Alembic migration defines the VADASE-specific hypertables.

**Approach**: Three milestones: (1) Alembic migration 010 creating vadase_velocities, vadase_displacements, vadase_events with TimescaleDB hypertables. (2) TimescaleDBAdapter porting proven asyncpg batch-buffering into src/adapters/outputs/, plus NullOutputPort. (3) Wire adapters into run_ingestor.py and add test coverage.

### VADASE Output Adapter Data Flow

[Diagram pending Technical Writer rendering: DIAG-001]

## Planning Context

### Decision Log

| ID | Decision | Reasoning Chain |
|---|---|---|
| DL-001 | Raw asyncpg with batch buffering for TimescaleDB adapter | Existing DatabaseWriter uses asyncpg executemany at 70 writes/sec proven throughput -> SQLAlchemy async adds ORM overhead without benefit on denormalized hot-path tables -> port existing pattern into hexagonal adapter |
| DL-002 | Three VADASE-specific tables: vadase_velocities, vadase_displacements, vadase_events | timeseries_data table has Bernese schema shape (sigma fields, solution_id, daily cadence) -> VADASE is 1Hz with velocity/displacement components and quality -> separate tables with TEXT station_code per architecture decision |
| DL-003 | NullOutputPort as a first-class adapter replacing ad-hoc mocks | MockDbWriter in run_ingestor.py and MockOutputPort in test_processor.py duplicate the same no-op pattern -> single NullOutputPort in adapters/outputs/ serves both dry-run mode and tests -> eliminates duplication and makes no-DB mode a supported runtime configuration |
| DL-004 | Velocity and displacement hypertables partitioned by time; events as plain table | 1Hz * 35 stations = 70 rows/sec sustained write rate -> hypertable partitioning enables retention policies and parallel queries -> event_detections are rare (earthquake summaries) so plain table suffices |
| DL-005 | DSN constructed from environment variables matching existing DatabaseWriter pattern | DatabaseWriter already uses DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME env vars -> consistent configuration across deployment modes -> no new config mechanism needed |
| DL-006 | ON CONFLICT DO NOTHING for idempotent re-ingestion | NTRIP reconnects can replay overlapping data windows -> duplicate (time, station) pairs cause insert failures -> ON CONFLICT DO NOTHING makes re-ingestion safe without data corruption |
| DL-007 | Bounded asyncpg pool acquire timeout with structlog error, allow backpressure to propagate to IngestionCore | At 70 writes/sec a stalled DB can exhaust pool silently -> default asyncpg acquire waits forever and deadlocks write_velocity/write_displacement -> adapter passes timeout=5.0s to pool.acquire(), logs pool_acquire_timeout with pool.get_idle_size()/get_size(), and raises; process_sentence error handler in domain layer logs the failure but loop continues (no crash) |
| DL-008 | Fail-fast on connect() errors: adapter raises; run_ingestor prints human DSN-diagnostic and exits non-zero | Undefined startup behavior leaves operator with no signal when PostgreSQL is unreachable -> adapter connect() lets asyncpg.CannotConnectNowError / OSError propagate -> run_ingestor catches at startup, logs DSN host/port (never password) + underlying error, exits with code 2; operator can explicitly opt into offline mode via --dry-run selecting NullOutputPort |
| DL-009 | Mid-flight flush errors are logged, batch is restored to buffer tail, periodic flush continues | DatabaseWriter pattern used bare except: pass at writer.py:51-53 causing invisible data loss -> replace with logger.error(flush_failed, ...) and push the in-flight batch back to the front of the buffer before re-raising for the caller; periodic loop catches, logs, waits flush_interval*2 (simple backoff), retries; never silently drops rows |
| DL-010 | SQL columns use snake_case; adapter performs explicit dict->tuple mapping using parser keys | Parser returns camelCase vE/vN/vU/dE/dN/dU + cq (3D component quality, not quality); SQL columns follow migration 003 snake_case convention (v_east, v_north, quality) -> adapter write_velocity builds tuple (data[timestamp], station_id, data[vE], data[vN], data[vU], data[vH_magnitude], data[cq]) and maps positionally in executemany; schema comment documents cq->quality alias; prevents KeyError and codifies mapping in one place |
| DL-011 | Hypertable chunk_time_interval = 1 day for vadase_velocities and vadase_displacements | 1Hz * 35 stations * 2 tables -> ~6M rows/day -> default 7-day chunks mean 42M rows/chunk (unwieldy for compression jobs and range scans) -> 1-day chunks align with daily operational cadence (ingestion cycles, QC reviews) and keep per-chunk row count tractable (~6M) |
| DL-012 | Defer retention and compression policies to a dedicated operations task; document placeholder in migration comment | Retention decisions depend on PHIVOLCS data-keeping policy (likely indefinite for seismic record) and compression on TimescaleDB license tier availability -> no stakeholder input captured in this plan iteration -> migration 010 creates hypertables with no retention policy (unbounded growth explicitly acknowledged); follow-up ticket references this decision |
| DL-013 | Pool sizing min=2, max=10 sized to actual workload not DatabaseWriter defaults | Peak concurrent connections under batch flush = 2 (velocity + displacement flush in parallel via asyncio.gather) + occasional single-row event insert -> min=5/max=20 from DatabaseWriter was unsubstantiated carry-over -> min=2 warm connections absorb flush burst, max=10 ceiling prevents pool exhaustion while leaving headroom for ad-hoc queries and event_detection inserts |
| DL-014 | Single flush-at-a-time guard via _flushing boolean; batch-size trigger fires only when guard is free | DatabaseWriter has race at writer.py:62-77: create_task triggered from write_velocity while _periodic_flush also calls flush_all -> two coroutines can swap buffer concurrently and half-insert same batch -> adapter adds self._velocity_flushing / self._displacement_flushing bool flags set at start of _flush_X and cleared in finally; write_velocity creates flush task only if not _velocity_flushing; _periodic_flush skips when flush already running |
| DL-015 | VADASE tables live in the default public schema (not a dedicated vadase schema) | Central DB convention (migrations 001-009) places all cross-service tables in public; field_ops uses a dedicated schema because it is a self-contained subsystem; VADASE tables will be read alongside public.stations by analytics and velocity pipeline -> using public avoids cross-schema joins in queries and matches the established convention; tables are prefixed vadase_ for logical grouping |
| DL-016 | Bounded buffers with drop-oldest on overflow; buffer_max_size = batch_size * 100 = 10000 tuples per buffer | Sustained DB outage with fire-and-forget flush tasks causes unbounded _velocity_buffer/_displacement_buffer growth -> OOM after ~10 minutes at 70 rows/sec -> cap each buffer at 10000 tuples (~2.3 minutes of data); when write_velocity/write_displacement would exceed cap, pop oldest tuple, log buffer_overflow_drop with dropped_count+buffer_size counter (rate-limited 1/sec); rationale for drop-oldest vs drop-newest: recent data more valuable for event detection; absolute OOM bound takes precedence over completeness when DB is unreachable; documented as intentional bounded-loss mode distinct from the no-silent-drop guarantee which applies only when pool is reachable |
| DL-017 | Backpressure propagation is best-effort via periodic_flush_error log + buffer overflow counter, NOT via exception raised into process_sentence | Original DL-007 claim that PoolTimeoutError propagates to IngestionCore is architecturally false because flush is fire-and-forget via asyncio.create_task -> exceptions in background tasks are isolated from write_velocity caller -> correct semantics: hot path never blocks or raises on DB issues (preserves 1Hz real-time contract); operator observability comes via (a) periodic_flush_error structlog events, (b) buffer_overflow_drop counter, (c) pool metrics in /metrics health endpoint (future); DL-007 remains valid only for synchronous write_event_detection which is not fire-and-forget |
| DL-018 | SQL column naming: snake_case (v_east, v_north, v_up, d_east, d_north, d_up); Python dict keys remain parser camelCase (vE, vN, vU, dE, dN, dU); translation is positional in executemany tuple construction | Postgres convention and migrations 001-009 all use snake_case (e.g. timeseries_data.station_id, field_ops.observation_type) -> aligning with existing schema convention is mandatory; parser camelCase (vE) is a Leica NMEA convention we preserve in the Python layer to avoid renaming everywhere -> translation happens exactly once in the adapter at tuple construction (DL-010); this decision supersedes any implicit naming choice and makes the convention auditable |

### Rejected Alternatives

| Alternative | Why Rejected |
|---|---|
| Writing VADASE data to timeseries_data | that table is for Bernese daily position solutions (sigma fields, solution_id campaign tag, daily cadence); VADASE is 1Hz with different schema shape (ref: DL-002) |
| Synchronous SQLAlchemy SessionLocal | VADASE is fully async; mixing sync DB calls in async event loop causes blocking (ref: DL-001) |
| FK from vadase tables to stations.id | established architecture decision (hot-path writes use denormalized station_code TEXT for performance) (ref: DL-002) |

### Constraints

- MUST: implement all 5 OutputPort Protocol methods — connect(), close(), write_velocity(), write_displacement(), write_event_detection()
- MUST: keep adapter in src/adapters/outputs/ — domain (processor.py) must not import adapter directly (hexagonal isolation)
- MUST: async throughout — IngestionCore.consume() is an asyncio loop; all OutputPort methods are async
- MUST: VADASE tables use station_code TEXT (denormalized, not FK to stations.id) — hot-path write performance; PostGIS overhead excluded from hot path
- MUST: new Alembic migration (010) for vadase_velocities, vadase_displacements, vadase_events tables
- MUST: implement NullOutputPort (no-op) for tests and no-DB operation mode
- SHOULD: use asyncpg or SQLAlchemy async engine (create_async_engine) — not synchronous SessionLocal used by ingestion-pipeline workers
- MUST-NOT: use synchronous sqlalchemy.orm.sessionmaker in async context
- MUST-NOT: add PostGIS or station FK to VADASE hot-path tables (architecture decision 2026-04-15)

### Known Risks

- **PostgreSQL unreachable at startup -- IngestionCore cannot start; operator must detect and remediate**: DL-008: fail-fast with operator-readable DSN diagnostic and exit code 2
- **asyncpg pool exhausted under sustained 70 writes/sec if DB latency spikes -- write calls hang indefinitely**: DL-007 + DL-017: bounded 5.0s acquire timeout with structured pool_acquire_timeout log; because flush is fire-and-forget via asyncio.create_task (DL-017), PoolTimeoutError does NOT propagate into IngestionCore.process_sentence -- hot path never blocks/raises on DB issues to preserve 1Hz real-time contract; observability comes from structlog events + buffer_overflow_drop counter (DL-016); synchronous write_event_detection is the only exception that surfaces to the caller
- **Mid-flight DB outage causes silent data loss (existing DatabaseWriter bug at writer.py:51-53)**: DL-009: log flush errors, restore batch to buffer head, never silent-drop; periodic flush backs off and retries
- **Unbounded table growth -- ~6M rows/day across velocity+displacement hypertables exhausts storage over months/years**: DL-012: explicitly deferred to operations ticket; documented in migration comment so it is not forgotten
- **KeyError on data[quality] would be caught by process_sentence broad except and silently drop all writes**: DL-010: explicit cq->quality mapping in code_intent; adapter code must reference data[cq] not data[quality]

## Invisible Knowledge

### System

VADASE real-time monitor is the mature hexagonal core of the monorepo. Domain (processor.py, IngestionCore) coordinates velocity/displacement/event-detection writes via a single OutputPort Protocol. The adapter being added here is the first concrete OutputPort implementation; all prior code paths used ad-hoc mocks (MockDbWriter, MockOutputPort). The legacy DatabaseWriter at src/database/writer.py contains proven asyncpg batch logic but lives outside the adapter boundary and has three silent-failure bugs that must NOT be ported verbatim (bare except, unlatched race, no acquire timeout).

### Invariants

- IngestionCore (services/vadase-rt-monitor/src/domain/processor.py) MUST NOT import from src/adapters/ -- OutputPort Protocol is the only coupling point (hexagonal invariant).
- VADASE hot-path tables use station_code TEXT denormalized (no FK to stations.id) -- architecture decision 2026-04-15 for write performance.
- timeseries_data (Bernese) uses station_id Integer FK; VADASE is the deliberate inverse -- do not align schemas.
- A NullOutputPort that silently drops all writes is essential -- it enables test mode and --dry-run without requiring a running database.

### Tradeoffs

- Cross-schema read convention (established by field-ops): services can SELECT from public.stations for read-only lookups, but each service writes to its own tables. VADASE tables live in public (see DL-015) alongside stations to avoid schema prefixing in analytics queries.
- conftest.py puts repo root on sys.path -- cross-service module-level imports in the adapter will resolve in tests without additional path fiddling.

## Milestones

### Milestone 1: Alembic migration 010 — VADASE tables

**Files**: migrations/versions/010_create_vadase_tables.py

**Acceptance Criteria**:

- alembic upgrade head applies migration 010 without error on a clean database;alembic downgrade -1 drops vadase_velocities vadase_displacements vadase_events cleanly;psql \d+ vadase_velocities shows TimescaleDB hypertable with 1-day chunk_time_interval (DL-011);INSERT INTO vadase_velocities with duplicate (time station_code) pair does not raise (ON CONFLICT works per DL-006);SELECT from information_schema.columns confirms quality column has comment documenting cq->quality mapping (DL-010);tables created in public schema (not vadase schema) per DL-015;migration down_revision=009 chains correctly

#### Code Intent

- **CI-M-001-001** `migrations/versions/010_create_vadase_tables.py`: Raw SQL Alembic migration creating three tables in the public schema: vadase_velocities (time TIMESTAMPTZ NOT NULL, station_code TEXT NOT NULL, v_east DOUBLE PRECISION, v_north DOUBLE PRECISION, v_up DOUBLE PRECISION, v_horizontal DOUBLE PRECISION, quality DOUBLE PRECISION -- parser cq mapped to quality); vadase_displacements (time TIMESTAMPTZ NOT NULL, station_code TEXT NOT NULL, d_east DOUBLE PRECISION, d_north DOUBLE PRECISION, d_up DOUBLE PRECISION, d_horizontal DOUBLE PRECISION, overall_completeness DOUBLE PRECISION, quality DOUBLE PRECISION -- parser cq mapped to quality); vadase_events (id SERIAL PRIMARY KEY, station_code TEXT NOT NULL, detection_time TIMESTAMPTZ NOT NULL, peak_velocity_horizontal DOUBLE PRECISION, peak_displacement_horizontal DOUBLE PRECISION, duration_seconds DOUBLE PRECISION). Convert vadase_velocities and vadase_displacements to hypertables via create_hypertable(table, time, chunk_time_interval => INTERVAL 1 day). Composite index on (station_code, time DESC) for both hypertables. UNIQUE constraint on (time, station_code) supports ON CONFLICT DO NOTHING. Index on vadase_events(station_code, detection_time DESC). Schema comment on quality column documents: parser field cq (3D component quality from Leica NMEA) stored as quality. Schema comment on table documents: no retention policy applied -- see DL-012 for follow-up. Downgrade drops all three tables. revision=010, down_revision=009. (refs: DL-002, DL-004, DL-006, DL-010, DL-011, DL-012, DL-015)

#### Code Changes

**CC-M-001-001** (migrations/versions/010_create_vadase_tables.py) - implements CI-M-001-001

**Code:**

```diff
--- /dev/null
+++ migrations/versions/010_create_vadase_tables.py
@@ -0,0 +1,103 @@
+"""create vadase_velocities, vadase_displacements, vadase_events tables
+
+Revision ID: 010
+Revises: 009
+Create Date: 2026-04-18 UTC
+
+Three tables for the VADASE real-time monitor hot-path writes:
+
+  vadase_velocities     -- 1 Hz velocity measurements per station (hypertable).
+  vadase_displacements  -- 1 Hz displacement measurements per station (hypertable).
+  vadase_events         -- Event detection summaries (plain table, rare writes).
+
+Design notes:
+  - station_code is TEXT (denormalized), not an FK to stations.id.
+    Hot-path writes at 35 stations x 1 Hz cannot afford FK lookups or PostGIS joins.
+  - vadase_velocities and vadase_displacements are TimescaleDB hypertables with
+    1-day chunk intervals (~6M rows/chunk -- tractable for compression and range scans).
+  - vadase_events is a plain table; events are rare and benefit from indexed queries.
+  - Units: velocity components in m/s; displacement components in metres;
+    peak_velocity in mm/s and peak_displacement in mm for the events table.
+  - quality column: stores Leica NMEA parser field cq (3D component quality).
+    See DL-010 for cq->quality mapping rationale.
+  - Retention and compression policies are deferred. See DL-012.
+"""
+
+from alembic import op
+
+revision = "010"
+down_revision = "009"
+branch_labels = None
+depends_on = None
+
+
+def upgrade() -> None:
+    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")
+
+    op.execute("""
+        CREATE TABLE vadase_velocities (
+            time            TIMESTAMPTZ     NOT NULL,
+            station_code    TEXT            NOT NULL,
+            v_east          DOUBLE PRECISION,
+            v_north         DOUBLE PRECISION,
+            v_up            DOUBLE PRECISION,
+            v_horizontal    DOUBLE PRECISION,
+            quality         DOUBLE PRECISION
+        )
+    """)
+
+    op.execute(
+        "ALTER TABLE vadase_velocities "
+        "ADD CONSTRAINT uq_vadase_vel_time_station UNIQUE (time, station_code)"
+    )
+
+    op.execute(
+        "SELECT create_hypertable('vadase_velocities', 'time', "\n+        "chunk_time_interval => INTERVAL '1 day')"\n+    )\n+\n+    op.execute(\n+        "CREATE INDEX idx_vadase_vel_station "\n+        "ON vadase_velocities (station_code, time DESC)"\n+    )\n+\n+    op.execute(\n+        "COMMENT ON COLUMN vadase_velocities.quality IS "\n+        "'Parser field cq (3D component quality from Leica NMEA LVM sentence) stored as quality.'"\n+    )\n+\n+    op.execute(\n+        "COMMENT ON TABLE vadase_velocities IS "\n+        "'No retention or compression policy applied -- see DL-012 for follow-up operations task.'"\n+    )\n+\n+    op.execute("""\n+        CREATE TABLE vadase_displacements (\n+            time                 TIMESTAMPTZ      NOT NULL,\n+            station_code         TEXT             NOT NULL,\n+            d_east               DOUBLE PRECISION,\n+            d_north              DOUBLE PRECISION,\n+            d_up                 DOUBLE PRECISION,\n+            d_horizontal         DOUBLE PRECISION,\n+            overall_completeness DOUBLE PRECISION,\n+            quality              DOUBLE PRECISION\n+        )\n+    """)\n+\n+    op.execute(\n+        "ALTER TABLE vadase_displacements "\n+        "ADD CONSTRAINT uq_vadase_disp_time_station UNIQUE (time, station_code)"\n+    )\n+\n+    op.execute(\n+        "SELECT create_hypertable('vadase_displacements', 'time', "\n+        "chunk_time_interval => INTERVAL '1 day')"\n+    )\n+\n+    op.execute(\n+        "CREATE INDEX idx_vadase_disp_station "\n+        "ON vadase_displacements (station_code, time DESC)"\n+    )\n+\n+    op.execute(\n+        "COMMENT ON COLUMN vadase_displacements.quality IS "\n+        "'Parser field cq (3D component quality from Leica NMEA LDM sentence) stored as quality.'"\n+    )\n+\n+    op.execute(\n+        "COMMENT ON TABLE vadase_displacements IS "\n+        "'No retention or compression policy applied -- see DL-012 for follow-up operations task.'"\n+    )\n+\n+    op.execute("""\n+        CREATE TABLE vadase_events (\n+            id                          SERIAL           PRIMARY KEY,\n+            station_code                TEXT             NOT NULL,\n+            detection_time              TIMESTAMPTZ      NOT NULL,\n+            peak_velocity_horizontal    DOUBLE PRECISION,\n+            peak_displacement_horizontal DOUBLE PRECISION,\n+            duration_seconds            DOUBLE PRECISION\n+        )\n+    """)\n+\n+    op.execute(\n+        "CREATE INDEX idx_vadase_events_station "\n+        "ON vadase_events (station_code, detection_time DESC)"\n+    )\n+\n+\n+def downgrade() -> None:\n+    op.execute("DROP TABLE IF EXISTS vadase_events")\n+    op.execute("DROP TABLE IF EXISTS vadase_displacements")\n+    op.execute("DROP TABLE IF EXISTS vadase_velocities")
```

**Documentation:**

```diff
--- a/migrations/versions/010_create_vadase_tables.py
+++ b/migrations/versions/010_create_vadase_tables.py
@@ -6,12 +6,14 @@
 Three tables for the VADASE real-time monitor hot-path writes:
 
   vadase_velocities     -- 1 Hz velocity measurements per station (hypertable).
   vadase_displacements  -- 1 Hz displacement measurements per station (hypertable).
   vadase_events         -- Event detection summaries (plain table, rare writes).
 
 Design notes:
-  - station_code is TEXT (denormalized), not an FK to stations.id.
-    Hot-path writes at 35 stations x 1 Hz cannot afford FK lookups or PostGIS joins.
-  - vadase_velocities and vadase_displacements are TimescaleDB hypertables with
-    1-day chunk intervals (~6M rows/chunk -- tractable for compression and range scans).
-  - vadase_events is a plain table; events are rare and benefit from indexed queries.
-  - Units: velocity components in m/s; displacement components in metres;
-    peak_velocity in mm/s and peak_displacement in mm for the events table.
-  - quality column: stores Leica NMEA parser field cq (3D component quality).
-    See DL-010 for cq->quality mapping rationale.
-  - Retention and compression policies are deferred. See DL-012.
+  - station_code is TEXT (denormalized), not an FK to stations.id. (ref: DL-002, RA-003)
+    Hot-path writes at 35 stations x 1 Hz cannot afford FK lookups or PostGIS joins.
+  - vadase_velocities and vadase_displacements are TimescaleDB hypertables with (ref: DL-004)
+    1-day chunk intervals (~6M rows/chunk). (ref: DL-011)
+  - vadase_events is a plain table; events are rare (earthquake summaries, not continuous).
+  - Units: velocity components in m/s; displacement components in metres;
+    peak_velocity in mm/s and peak_displacement in mm for the events table.
+  - quality column: stores Leica NMEA parser field cq (3D component quality). (ref: DL-010)
+    Adapter maps cq->quality exactly once in tuple construction.
+  - Retention and compression policies are deferred. (ref: DL-012)
+    No stakeholder input on PHIVOLCS data-keeping policy captured; growth is unbounded.
+  - ON CONFLICT DO NOTHING on (time, station_code) makes NTRIP-reconnect re-ingestion
+    safe. (ref: DL-006)
+  - Tables live in public schema (prefixed vadase_) consistent with migrations 001-009.
+    (ref: DL-015)

```


### Milestone 2: TimescaleDB output adapter and NullOutputPort

**Files**: services/vadase-rt-monitor/src/adapters/outputs/__init__.py, services/vadase-rt-monitor/src/adapters/outputs/timescaledb.py, services/vadase-rt-monitor/src/adapters/outputs/null.py

**Acceptance Criteria**:

- TimescaleDBAdapter satisfies OutputPort Protocol (mypy --strict passes);connect() raises on unreachable PostgreSQL (no silent fallback);write_velocity and write_displacement never silently drop rows while pool is reachable (mid-flight failure restores batch to buffer);buffer_max_size cap prevents unbounded growth under sustained DB outage (drop-oldest with counter per DL-016);pool acquire timeout surfaces as logged pool_acquire_timeout event not a hang;write_event_detection exceptions propagate to caller (synchronous contract);NullOutputPort all 5 methods are callable no-ops;no imports from src/adapters into src/domain (hexagonal invariant preserved)

#### Code Intent

- **CI-M-002-001** `services/vadase-rt-monitor/src/adapters/outputs/__init__.py`: Package init exporting TimescaleDBAdapter and NullOutputPort for clean imports. (refs: DL-003)
- **CI-M-002-002** `services/vadase-rt-monitor/src/adapters/outputs/timescaledb.py`: TimescaleDBAdapter class implementing all 5 OutputPort Protocol methods with explicit failure-mode handling. Constructor accepts dsn (str, optional; defaults to building from DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/DB_NAME env vars), batch_size (int, default 100), flush_interval (float, default 1.0), acquire_timeout (float, default 5.0), buffer_max_size (int, default batch_size*100 = 10000). connect() calls asyncpg.create_pool(dsn, min_size=2, max_size=10) -- lets asyncpg exceptions propagate so run_ingestor can fail-fast (DL-008) -- then starts _periodic_flush background task. close() sets _closing, cancels flush task, runs final flush_all(), closes pool. write_velocity(station_id, data) acquires asyncio.Lock; if len(_velocity_buffer) >= buffer_max_size pops _velocity_buffer[0] and increments _velocity_dropped counter (log buffer_overflow_drop rate-limited once per second with dropped_total + current_buffer_size per DL-016); appends tuple (data[timestamp], station_id, data[vE], data[vN], data[vU], data[vH_magnitude], data[cq]) to _velocity_buffer -- NOTE: parser returns cq (3D component quality), mapped positionally to SQL column quality; do NOT use data[quality] (KeyError); Python dict keys are camelCase (vE) by parser convention but SQL columns are snake_case (v_east) by migration convention -- translation is positional in this tuple construction per DL-018; if len(buffer) >= batch_size and not _velocity_flushing, creates flush task (fire-and-forget: exceptions isolated from caller per DL-017 -- hot path never blocks/raises on DB issues to preserve 1Hz contract). write_displacement(station_id, data) same pattern for _displacement_buffer with tuple (data[timestamp], station_id, data[dE], data[dN], data[dU], data[dH_magnitude], data[overall_completeness], data[cq]) and same buffer_max_size + overflow drop logic. write_event_detection performs immediate single-row insert (events are rare; synchronous call path -- exceptions DO propagate to caller). _flush_velocity/_flush_displacement set self._{type}_flushing=True at entry, call pool.acquire(timeout=self.acquire_timeout), executemany INSERT ... ON CONFLICT (time, station_code) DO NOTHING, clear flag in finally; on asyncpg.PoolTimeoutError log pool_acquire_timeout with pool.get_idle_size()/get_size() and re-raise; on other Exception log flush_failed with batch_size and exception, push batch back to front of buffer (batch + self._{type}_buffer, subject to buffer_max_size cap -- if cap exceeded drop oldest entries and increment overflow counter), re-raise -- NEVER silent drop while pool is reachable (replaces DatabaseWriter writer.py:51-53 bare except; distinct from bounded-loss overflow mode per DL-016). _periodic_flush wraps flush_all in try/except, logs periodic_flush_error and sleeps flush_interval*2 as simple backoff, then continues; on CancelledError breaks cleanly. Uses structlog with component=timescaledb_adapter binding. (refs: DL-001, DL-005, DL-006, DL-007, DL-008, DL-009, DL-010, DL-013, DL-014, DL-016, DL-017, DL-018)
- **CI-M-002-003** `services/vadase-rt-monitor/src/adapters/outputs/null.py`: NullOutputPort class implementing all 5 OutputPort Protocol methods as no-ops. connect() and close() log at debug level via structlog. write_velocity(), write_displacement(), write_event_detection() silently return None. No state, no buffers, no locks. (refs: DL-003)

#### Code Changes

**CC-M-002-001** (services/vadase-rt-monitor/src/adapters/outputs/timescaledb.py) - implements CI-M-002-002

**Code:**

```diff
--- /dev/null
+++ services/vadase-rt-monitor/src/adapters/outputs/timescaledb.py
@@ -0,0 +1,220 @@
+"""TimescaleDB OutputPort adapter for VADASE real-time monitor.
+
+Batch-buffers velocity and displacement rows and flushes via asyncpg executemany.
+All write_velocity/write_displacement calls are fire-and-forget (flush via
+asyncio.create_task) to preserve the 1 Hz real-time contract. write_event_detection
+is synchronous -- exceptions propagate to the caller (DL-017).
+"""
+
+import asyncio
+import os
+import time
+from collections import deque
+from datetime import datetime
+from typing import Any, Deque, Dict, Optional, Tuple
+
+import asyncpg
+import structlog
+
+logger = structlog.get_logger()
+
+_INSERT_VELOCITY = """
+    INSERT INTO vadase_velocities
+        (time, station_code, v_east, v_north, v_up, v_horizontal, quality)
+    VALUES ($1, $2, $3, $4, $5, $6, $7)
+    ON CONFLICT (time, station_code) DO NOTHING
+"""
+
+_INSERT_DISPLACEMENT = """
+    INSERT INTO vadase_displacements
+        (time, station_code, d_east, d_north, d_up, d_horizontal, overall_completeness, quality)
+    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
+    ON CONFLICT (time, station_code) DO NOTHING
+"""
+
+_INSERT_EVENT = """
+    INSERT INTO vadase_events
+        (station_code, detection_time, peak_velocity_horizontal,
+         peak_displacement_horizontal, duration_seconds)
+    VALUES ($1, $2, $3, $4, $5)
+"""
+
+
+class TimescaleDBAdapter:
+    def __init__(
+        self,
+        dsn: Optional[str] = None,
+        batch_size: int = 100,
+        flush_interval: float = 1.0,
+        acquire_timeout: float = 5.0,
+        buffer_max_size: int = 10_000,
+    ) -> None:
+        if dsn is None:
+            user = os.environ.get("DB_USER", "pogf_user")
+            password = os.environ.get("DB_PASSWORD", "pogf_password")
+            host = os.environ.get("DB_HOST", "localhost")
+            port = os.environ.get("DB_PORT", "5433")
+            name = os.environ.get("DB_NAME", "pogf_db")
+            dsn = f"postgresql://{user}:{password}@{host}:{port}/{name}"
+        self._dsn = dsn
+        self._batch_size = batch_size
+        self._flush_interval = flush_interval
+        self._acquire_timeout = acquire_timeout
+        self._buffer_max_size = buffer_max_size
+        self._pool: Optional[asyncpg.Pool] = None
+        self._flush_task = None
+        self._closing = False
+        self._velocity_buffer: Deque = deque()
+        self._displacement_buffer: Deque = deque()
+        self._velocity_lock = asyncio.Lock()
+        self._displacement_lock = asyncio.Lock()
+        self._velocity_flushing = False
+        self._displacement_flushing = False
+        self._velocity_dropped: int = 0
+        self._displacement_dropped: int = 0
+        self._last_overflow_log: float = 0.0
+        self.log = logger.bind(component="timescaledb_adapter")
+
+    async def connect(self) -> None:
+        dsn_parts = self._dsn.split("@")
+        dsn_host = dsn_parts[-1] if "@" in self._dsn else "<no-host-in-dsn>"
+        self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=2, max_size=10)
+        self._flush_task = asyncio.create_task(self._periodic_flush())
+        self.log.info("connected", dsn_host=dsn_host)
+
+    async def close(self) -> None:
+        self._closing = True
+        if self._flush_task is not None:
+            self._flush_task.cancel()
+            try:
+                await self._flush_task
+            except asyncio.CancelledError:
+                pass
+        await self._flush_all()
+        if self._pool is not None:
+            await self._pool.close()
+            self._pool = None
+        self.log.info("closed")
+
+    async def write_velocity(self, station_id: str, data: Dict[str, Any]) -> None:
+        row = (
+            data["timestamp"],
+            station_id,
+            data["vE"],
+            data["vN"],
+            data["vU"],
+            data["vH_magnitude"],
+            data["cq"],
+        )
+        async with self._velocity_lock:
+            self._maybe_drop_oldest(self._velocity_buffer, "velocity")
+            self._velocity_buffer.append(row)
+            should_flush = (
+                len(self._velocity_buffer) >= self._batch_size
+                and not self._velocity_flushing
+            )
+        if should_flush:
+            asyncio.create_task(self._flush_velocity())
+
+    async def write_displacement(self, station_id: str, data: Dict[str, Any]) -> None:
+        row = (
+            data["timestamp"],
+            station_id,
+            data["dE"],
+            data["dN"],
+            data["dU"],
+            data["dH_magnitude"],
+            data.get("overall_completeness"),
+            data["cq"],
+        )
+        async with self._displacement_lock:
+            self._maybe_drop_oldest(self._displacement_buffer, "displacement")
+            self._displacement_buffer.append(row)
+            should_flush = (
+                len(self._displacement_buffer) >= self._batch_size
+                and not self._displacement_flushing
+            )
+        if should_flush:
+            asyncio.create_task(self._flush_displacement())
+
+    async def write_event_detection(
+        self,
+        station: str,
+        detection_time: datetime,
+        peak_velocity: float,
+        peak_displacement: float,
+        duration: float,
+    ) -> None:
+        if self._pool is None:
+            self.log.error("write_event_called_before_connect")
+            return
+        async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
+            await conn.execute(
+                _INSERT_EVENT, station, detection_time,
+                peak_velocity, peak_displacement, duration,
+            )
+        self.log.info("event_written", station=station, detection_time=detection_time,
+                      peak_velocity=peak_velocity)
+
+    def _maybe_drop_oldest(self, buf, buf_name: str) -> None:
+        if len(buf) >= self._buffer_max_size:
+            buf.popleft()
+            if buf_name == "velocity":
+                self._velocity_dropped += 1
+                dropped = self._velocity_dropped
+            else:
+                self._displacement_dropped += 1
+                dropped = self._displacement_dropped
+            now = time.monotonic()
+            if now - self._last_overflow_log >= 1.0:
+                self._last_overflow_log = now
+                self.log.warning("buffer_overflow_drop", buffer=buf_name,
+                                 dropped_total=dropped, current_buffer_size=len(buf))
+
+    async def _flush_velocity(self) -> None:
+        self._velocity_flushing = True
+        batch = []
+        try:
+            async with self._velocity_lock:
+                batch = [self._velocity_buffer.popleft() for _ in range(len(self._velocity_buffer))]
+            if not batch:
+                return
+            async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
+                await conn.executemany(_INSERT_VELOCITY, batch)
+        except asyncpg.exceptions.TooManyConnectionsError as exc:
+            self.log.error("pool_acquire_timeout",
+                           pool_idle=self._pool.get_idle_size() if self._pool else -1,
+                           pool_size=self._pool.get_size() if self._pool else -1,
+                           error=str(exc))
+            async with self._velocity_lock:
+                self._velocity_buffer.extendleft(reversed(batch))
+            raise
+        except Exception as exc:
+            self.log.error("flush_failed", buffer="velocity", batch_size=len(batch), error=str(exc))
+            async with self._velocity_lock:
+                combined = list(batch) + list(self._velocity_buffer)
+                self._velocity_buffer.clear()
+                for row in combined[:self._buffer_max_size]:
+                    self._velocity_buffer.append(row)
+            raise
+        finally:
+            self._velocity_flushing = False
+
+    async def _flush_displacement(self) -> None:
+        self._displacement_flushing = True
+        batch = []
+        try:
+            async with self._displacement_lock:
+                batch = [self._displacement_buffer.popleft() for _ in range(len(self._displacement_buffer))]
+            if not batch:
+                return
+            async with self._pool.acquire(timeout=self._acquire_timeout) as conn:
+                await conn.executemany(_INSERT_DISPLACEMENT, batch)
+        except asyncpg.exceptions.TooManyConnectionsError as exc:
+            self.log.error("pool_acquire_timeout",
+                           pool_idle=self._pool.get_idle_size() if self._pool else -1,
+                           pool_size=self._pool.get_size() if self._pool else -1,
+                           error=str(exc))
+            async with self._displacement_lock:
+                self._displacement_buffer.extendleft(reversed(batch))
+            raise
+        except Exception as exc:
+            self.log.error("flush_failed", buffer="displacement", batch_size=len(batch), error=str(exc))
+            async with self._displacement_lock:
+                combined = list(batch) + list(self._displacement_buffer)
+                self._displacement_buffer.clear()
+                for row in combined[:self._buffer_max_size]:
+                    self._displacement_buffer.append(row)
+            raise
+        finally:
+            self._displacement_flushing = False
+
+    async def _flush_all(self) -> None:
+        if self._velocity_buffer:
+            try:
+                await self._flush_velocity()
+            except Exception:
+                pass
+        if self._displacement_buffer:
+            try:
+                await self._flush_displacement()
+            except Exception:
+                pass
+
+    async def _periodic_flush(self) -> None:
+        while not self._closing:
+            await asyncio.sleep(self._flush_interval)
+            try:
+                await self._flush_all()
+            except asyncio.CancelledError:
+                break
+            except Exception as exc:
+                self.log.error("periodic_flush_error", error=str(exc))
+                await asyncio.sleep(self._flush_interval * 2)
```

**Documentation:**

```diff
--- a/services/vadase-rt-monitor/src/adapters/outputs/timescaledb.py
+++ b/services/vadase-rt-monitor/src/adapters/outputs/timescaledb.py
@@ -1,7 +1,15 @@
 """TimescaleDB OutputPort adapter for VADASE real-time monitor.
 
-Batch-buffers velocity and displacement rows and flushes via asyncpg executemany.
-All write_velocity/write_displacement calls are fire-and-forget (flush via
-asyncio.create_task) to preserve the 1 Hz real-time contract. write_event_detection
-is synchronous -- exceptions propagate to the caller (DL-017).
+Implements the OutputPort Protocol for IngestionCore (ref: DL-001).
+
+Batch-buffers velocity and displacement rows in bounded deques and flushes via
+asyncpg executemany. Flush is fire-and-forget (asyncio.create_task) to preserve
+the 1 Hz real-time contract -- DB latency never blocks process_sentence (ref: DL-017).
+write_event_detection is synchronous; exceptions propagate to the caller.
+
+Pool sizing: min=2, max=10 -- 2 warm connections absorb concurrent flush burst;
+ceiling of 10 prevents pool exhaustion (ref: DL-013).
+
+Buffer overflow: each buffer is capped at buffer_max_size (default 10000) tuples.
+Drop-oldest preserves recent data for event detection during sustained DB outage
+(ref: DL-016).
 """
 
 import asyncio
@@ -45,6 +53,19 @@ class TimescaleDBAdapter:
     def __init__(
         self,
         dsn: Optional[str] = None,
         batch_size: int = 100,
         flush_interval: float = 1.0,
         acquire_timeout: float = 5.0,
         buffer_max_size: int = 10_000,
     ) -> None:
+        """Configure the adapter without opening a connection.
+
+        dsn: asyncpg DSN string. When None, constructed from DB_USER/DB_PASSWORD/
+             DB_HOST/DB_PORT/DB_NAME env vars matching existing DatabaseWriter
+             convention (ref: DL-005).
+        batch_size: row count that triggers an immediate fire-and-forget flush.
+        flush_interval: seconds between periodic flush sweeps.
+        acquire_timeout: asyncpg pool.acquire() timeout in seconds. Pool exhaustion
+                         under sustained write load raises TooManyConnectionsError;
+                         bounded timeout prevents indefinite hangs (ref: DL-007).
+        buffer_max_size: per-buffer tuple cap. Drop-oldest fires at this limit
+                         with a rate-limited structlog warning (ref: DL-016).
+        """
         if dsn is None:
             user = os.environ.get("DB_USER", "pogf_user")
             password = os.environ.get("DB_PASSWORD", "pogf_password")
@@ -75,6 +96,12 @@ class TimescaleDBAdapter:
         self.log = logger.bind(component="timescaledb_adapter")
 
     async def connect(self) -> None:
+        """Create the asyncpg connection pool and start the periodic flush task.
+
+        Raises asyncpg.CannotConnectNowError / OSError on unreachable DB.
+        run_ingestor catches these at startup and exits with code 2 (ref: DL-008).
+        DSN host is logged; password is never emitted.
+        """
         dsn_parts = self._dsn.split("@")
         dsn_host = dsn_parts[-1] if "@" in self._dsn else "<no-host-in-dsn>"
         self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=2, max_size=10)
@@ -83,6 +110,10 @@ class TimescaleDBAdapter:
         self.log.info("connected", dsn_host=dsn_host)
 
     async def close(self) -> None:
+        """Cancel the periodic flush task, drain remaining buffers, and close the pool.
+
+        Final flush is best-effort: errors are swallowed so close() always completes.
+        """
         self._closing = True
         if self._flush_task is not None:
             self._flush_task.cancel()
@@ -98,6 +129,15 @@ class TimescaleDBAdapter:
         self.log.info("closed")
 
     async def write_velocity(self, station_id: str, data: Dict[str, Any]) -> None:
+        """Buffer one velocity row and trigger a flush when batch_size is reached.
+
+        Never raises. Flush is fire-and-forget via asyncio.create_task (ref: DL-017).
+        Row tuple maps parser camelCase keys to SQL snake_case columns (ref: DL-010, DL-018):
+          data["vE"] -> v_east, data["vN"] -> v_north, data["vU"] -> v_up,
+          data["vH_magnitude"] -> v_horizontal, data["cq"] -> quality.
+        _velocity_flushing guard prevents concurrent flush races (ref: DL-014).
+        Buffer overflow drops oldest tuple with a rate-limited log (ref: DL-016).
+        """
         row = (
             data["timestamp"],
             station_id,
@@ -120,6 +160,15 @@ class TimescaleDBAdapter:
             asyncio.create_task(self._flush_velocity())
 
     async def write_displacement(self, station_id: str, data: Dict[str, Any]) -> None:
+        """Buffer one displacement row and trigger a flush when batch_size is reached.
+
+        Never raises. Flush is fire-and-forget via asyncio.create_task (ref: DL-017).
+        Row tuple maps parser camelCase keys to SQL snake_case columns (ref: DL-010, DL-018):
+          data["dE"] -> d_east, data["dN"] -> d_north, data["dU"] -> d_up,
+          data["dH_magnitude"] -> d_horizontal, data["cq"] -> quality.
+        overall_completeness is optional (get with default None).
+        _displacement_flushing guard prevents concurrent flush races (ref: DL-014).
+        """
         row = (
             data["timestamp"],
             station_id,
@@ -145,6 +194,13 @@ class TimescaleDBAdapter:
     async def write_event_detection(
         self,
         station: str,
         detection_time: datetime,
         peak_velocity: float,
         peak_displacement: float,
         duration: float,
     ) -> None:
+        """Write one event detection record immediately (synchronous, not buffered).
+
+        Exceptions propagate to the caller (IngestionCore.process_sentence) unlike
+        write_velocity/write_displacement which are fire-and-forget. Events are rare
+        (earthquake detections); latency is acceptable (ref: DL-004, DL-017).
+        Raises on pool == None (adapter not connected).
+        """
         if self._pool is None:
             self.log.error("write_event_called_before_connect")
             return
@@ -160,6 +216,12 @@ class TimescaleDBAdapter:
                       peak_velocity=peak_velocity)
 
     def _maybe_drop_oldest(self, buf, buf_name: str) -> None:
+        """Drop the oldest tuple from buf when buffer_max_size is reached.
+
+        Rate-limits the buffer_overflow_drop structlog warning to once per second
+        to avoid log flooding during sustained DB outage. Tracks cumulative dropped
+        count per buffer. (ref: DL-016)
+        """
         if len(buf) >= self._buffer_max_size:
             buf.popleft()
             if buf_name == "velocity":
@@ -178,6 +240,15 @@ class TimescaleDBAdapter:
                                  dropped_total=dropped, current_buffer_size=len(buf))
 
     async def _flush_velocity(self) -> None:
+        """Drain velocity buffer and executemany to vadase_velocities.
+
+        _velocity_flushing flag is set on entry and cleared in finally -- write_velocity
+        creates a flush task only when this flag is False, preventing concurrent flushes
+        of the same buffer (ref: DL-014).
+        On exception: batch is restored to buffer front (prepend) so rows are retried
+        on next flush cycle -- no silent drop (ref: DL-009).
+        ON CONFLICT DO NOTHING in SQL handles duplicate (time, station_code) from
+        NTRIP reconnect replay (ref: DL-006).
+        """
         self._velocity_flushing = True
         batch = []
         try:
@@ -207,6 +278,10 @@ class TimescaleDBAdapter:
             self._velocity_flushing = False
 
     async def _flush_displacement(self) -> None:
+        """Drain displacement buffer and executemany to vadase_displacements.
+
+        Identical error-handling and flush-guard semantics as _flush_velocity.
+        (ref: DL-009, DL-014)
+        """
         self._displacement_flushing = True
         batch = []
         try:
@@ -235,6 +310,11 @@ class TimescaleDBAdapter:
             self._displacement_flushing = False
 
     async def _flush_all(self) -> None:
+        """Flush both velocity and displacement buffers sequentially.
+
+        Used by close() for drain-on-shutdown and by _periodic_flush.
+        Errors are swallowed individually so one buffer failure does not
+        prevent the other from flushing.
+        """
         if self._velocity_buffer:
             try:
                 await self._flush_velocity()
@@ -248,6 +328,11 @@ class TimescaleDBAdapter:
                 pass
 
     async def _periodic_flush(self) -> None:
+        """Run _flush_all on a fixed interval until close() sets _closing.
+
+        On flush error: logs periodic_flush_error and backs off for flush_interval*2
+        before retrying. CancelledError on task cancel exits the loop cleanly.
+        (ref: DL-009, DL-017)
+        """
         while not self._closing:
             await asyncio.sleep(self._flush_interval)
             try:

```


**CC-M-002-002** (services/vadase-rt-monitor/src/adapters/outputs/null.py) - implements CI-M-002-003

**Code:**

```diff
--- /dev/null
+++ services/vadase-rt-monitor/src/adapters/outputs/null.py
@@ -0,0 +1,30 @@
+from datetime import datetime
+from typing import Any, Dict
+
+
+class NullOutputPort:
+    """
+    No-op OutputPort for tests and dry-run mode.
+
+    All writes are silently discarded.  connect() and close() are no-ops.
+    Satisfies the OutputPort Protocol without a real database.
+    """
+
+    async def connect(self) -> None:
+        pass
+
+    async def close(self) -> None:
+        pass
+
+    async def write_velocity(self, station_id: str, data: Dict[str, Any]) -> None:
+        pass
+
+    async def write_displacement(self, station_id: str, data: Dict[str, Any]) -> None:
+        pass
+
+    async def write_event_detection(
+        self,
+        station: str,
+        detection_time: datetime,
+        peak_velocity: float,
+        peak_displacement: float,
+        duration: float,
+    ) -> None:
+        pass
```

**Documentation:**

```diff
--- a/services/vadase-rt-monitor/src/adapters/outputs/null.py
+++ b/services/vadase-rt-monitor/src/adapters/outputs/null.py
@@ -1,3 +1,8 @@
+"""Canonical no-op OutputPort for dry-run mode and tests.
+
+Accepts all OutputPort method calls and discards data silently. Lets
+IngestionCore run without a live database connection. (ref: DL-003)
+"""
 from datetime import datetime
 from typing import Any, Dict

```


**CC-M-002-003** (services/vadase-rt-monitor/src/adapters/outputs/__init__.py) - implements CI-M-002-001

**Code:**

```diff
--- /dev/null
+++ services/vadase-rt-monitor/src/adapters/outputs/__init__.py
@@ -0,0 +1,5 @@
+from src.adapters.outputs.timescaledb import TimescaleDBAdapter
+from src.adapters.outputs.null import NullOutputPort
+
+__all__ = ["TimescaleDBAdapter", "NullOutputPort"]
```

**Documentation:**

```diff
--- a/services/vadase-rt-monitor/src/adapters/outputs/__init__.py
+++ b/services/vadase-rt-monitor/src/adapters/outputs/__init__.py
@@ -1,4 +1,8 @@
+"""Output adapters for the VADASE OutputPort Protocol.
+
+TimescaleDBAdapter: hot-path async writes to PostgreSQL/TimescaleDB. (ref: DL-001)
+NullOutputPort: no-op adapter for dry-run mode and tests. (ref: DL-003)
+"""
 from src.adapters.outputs.timescaledb import TimescaleDBAdapter
 from src.adapters.outputs.null import NullOutputPort
 

```


### Milestone 3: Wire adapter into run_ingestor and tests

**Files**: services/vadase-rt-monitor/scripts/run_ingestor.py, services/vadase-rt-monitor/tests/test_output_adapter.py, services/vadase-rt-monitor/tests/test_processor.py

**Acceptance Criteria**:

- run_ingestor --dry-run exits cleanly with NullOutputPort and no DB connection attempt;run_ingestor against running DB writes rows to vadase_velocities vadase_displacements within 2 seconds of first sentence;run_ingestor against unreachable DB exits non-zero (code 2) with operator-readable DSN diagnostic showing host/port (never password) per DL-008;pytest services/vadase-rt-monitor/tests/test_output_adapter.py -v passes including buffer-overflow-drop test;pytest test_processor.py still passes after MockOutputPort replaced with NullOutputPort;grep -r MockDbWriter services/vadase-rt-monitor returns no matches

#### Code Intent

- **CI-M-003-001** `services/vadase-rt-monitor/scripts/run_ingestor.py`: Replace inline MockDbWriter class with import of NullOutputPort from src.adapters.outputs.null. Replace DatabaseWriter import from src.database.writer with TimescaleDBAdapter import from src.adapters.outputs.timescaledb. dry_run flag selects NullOutputPort(); normal mode selects TimescaleDBAdapter(). Wrap ingestor.start() in try/except catching (asyncpg.CannotConnectNowError, asyncpg.InvalidCatalogNameError, OSError, ConnectionRefusedError) at connect time: log startup_db_connect_failed with dsn_host/dsn_port (masking password) and exc_info, print operator guidance (check DB_HOST/DB_PORT env vars, confirm docker compose up -d), sys.exit(2). Remove MockDbWriter class entirely. (refs: DL-003, DL-008)
- **CI-M-003-002** `services/vadase-rt-monitor/tests/test_output_adapter.py`: Test suite for TimescaleDBAdapter and NullOutputPort. Tests for NullOutputPort: verify all 5 methods are callable and return None without error. Tests for TimescaleDBAdapter (all with pytest-asyncio + mocked asyncpg.create_pool): (a) connect() creates pool and starts periodic flush task; (b) connect() propagates asyncpg.CannotConnectNowError (no silent fallback per DL-008); (c) write_velocity() buffers tuple and does NOT flush when below batch_size; (d) write_velocity() triggers fire-and-forget flush task at batch_size threshold; (e) write_velocity() with buffer_max_size reached drops oldest tuple and increments overflow counter per DL-016; (f) write_displacement() same buffer-and-flush behavior; (g) write_event_detection() performs immediate single-row insert and propagates exceptions (synchronous contract per DL-017); (h) mid-flight flush failure restores batch to buffer front per DL-009 (no silent drop while pool reachable); (i) pool acquire timeout logs pool_acquire_timeout with pool metrics per DL-007; (j) close() runs final flush and closes pool; (k) ON CONFLICT DO NOTHING SQL is present in executemany calls per DL-006; (l) snake_case SQL columns paired with camelCase dict keys at correct positional indices per DL-018. (refs: DL-001, DL-003, DL-006, DL-007, DL-008, DL-009, DL-016, DL-017, DL-018)
- **CI-M-003-003** `services/vadase-rt-monitor/tests/test_processor.py`: Replace inline MockOutputPort class with import of NullOutputPort from src.adapters.outputs.null. Update test_processor_redundant_calculation to use NullOutputPort() instead of MockOutputPort(). (refs: DL-003)

#### Code Changes

**CC-M-003-001** (services/vadase-rt-monitor/scripts/run_ingestor.py) - implements CI-M-003-001

**Code:**

```diff
--- a/services/vadase-rt-monitor/scripts/run_ingestor.py
+++ b/services/vadase-rt-monitor/scripts/run_ingestor.py
@@ -1,30 +1,16 @@
 import asyncio
+import sys
 import yaml
 import structlog
 import typer
+import asyncpg
 from src.adapters.inputs.tcp import TCPAdapter
+from src.adapters.outputs import TimescaleDBAdapter, NullOutputPort
 from src.domain.processor import IngestionCore
-from src.database.writer import DatabaseWriter
-from src.ports.outputs import OutputPort
 
 logger = structlog.get_logger()
 app = typer.Typer()
 
-class MockDbWriter(OutputPort):
-    async def connect(self):
-        logger.info("MOCK DB: Connected.")
-
-    async def close(self):
-        logger.info("MOCK DB: Closed.")
-
-    async def write_velocity(self, station_id, data):
-        logger.info("MOCK: VEL", time=data['timestamp'], vH=data.get('vH_magnitude'))
-
-    async def write_displacement(self, station_id, data):
-        logger.info("MOCK: DSP", time=data['timestamp'], dH=data.get('dH_magnitude'))
-
-    async def write_event_detection(self, station, detection_time, peak_velocity, peak_displacement, duration):
-        logger.warning(f"MOCK: EVENT DETECTED: {detection_time} PeakV={peak_velocity}")
 
 async def run_service(config_path: str, dry_run: bool):
     """
@@ -38,38 +24,60 @@ async def run_service(config_path: str, dry_run: bool):
     except FileNotFoundError:
         print(f"Config file {config_path} not found.")
         return
-    
+
     if not stations:
         print(f"No stations defined in {config_path}")
         return
 
     # Initialize Output Port
     if dry_run:
-        db_writer = MockDbWriter()
+        db_writer = NullOutputPort()
     else:
-        db_writer = DatabaseWriter()
-    
-    await db_writer.connect()
+        dsn = config.get("database", {}).get("dsn")
+        db_writer = TimescaleDBAdapter(dsn=dsn)
 
-    tasks = []
-    stop_events = []
-
-    print(f"Starting ingestor for {len(stations)} stations (Dry Run: {dry_run})...")
+    # Fail-fast on DB connect failure: operator needs host/port diagnostic, not a traceback.
+    # Exits with code 2 so systemd/supervisord can distinguish DB-unavailable from
+    # config errors (exit 1) and clean shutdown (exit 0). Never logs the password (DL-008).
+    try:
+        await db_writer.connect()
+    except (
+        asyncpg.CannotConnectNowError,
+        asyncpg.InvalidCatalogNameError,
+        OSError,
+        ConnectionRefusedError,
+    ) as exc:
+        import os
+        db_host = os.environ.get("DB_HOST", "localhost")
+        db_port = os.environ.get("DB_PORT", "5433")
+        logger.error(
+            "startup_db_connect_failed",
+            dsn_host=db_host,
+            dsn_port=db_port,
+            exc_info=True,
+        )
+        print(
+            f"ERROR: Cannot connect to database at {db_host}:{db_port}.\n"
+            "Check DB_HOST / DB_PORT env vars and confirm 'docker compose up -d' is running.\n"
+            f"Underlying error: {exc}",
+            file=sys.stderr,
+        )
+        sys.exit(2)
 
     tasks = []
     stop_events = []
 
-    print(f"Starting ingestor for {len(stations)} stations...")
+    print(f"Starting ingestor for {len(stations)} stations (Dry Run: {dry_run})...")
 
     for s in stations:
         station_id = s['id']
-        
+
         # 1. Setup Hexagon Components
         adapter = TCPAdapter(
             host=s['host'],
             port=s['port'],
             station_id=station_id,
-            mountpoint=s.get('mountpoint'), # Optional NTRIP fields
+            mountpoint=s.get('mountpoint'),  # Optional NTRIP fields
             user=s.get('user'),
             password=s.get('password')
         )
@@ -93,7 +101,7 @@ async def run_service(config_path: str, dry_run: bool):
         # 3. Launch Tasks
         # Producer (NTRIP -> Queue)
         tasks.append(asyncio.create_task(adapter.start(queue, stop_event)))
-        
+
         # Consumer (Queue -> Processing -> DB)
         tasks.append(asyncio.create_task(core.consume(queue, stop_event)))
 
@@ -110,15 +118,17 @@ async def run_service(config_path: str, dry_run: bool):
         await asyncio.sleep(1)
         await db_writer.close()
 
+
 @app.command()
 def main(
     config: str = typer.Option("config/stations.yml", "--config", "-c", help="Path to station config file"),
-    dry_run: bool = typer.Option(False, "--dry-run", help="Use Mock DB instead of Postgres")
+    dry_run: bool = typer.Option(False, "--dry-run", help="Use NullOutputPort instead of Postgres")
 ):
     try:
         asyncio.run(run_service(config, dry_run))
     except KeyboardInterrupt:
         pass
 
+
 if __name__ == '__main__':
     app()

```

**Documentation:**

```diff
--- a/services/vadase-rt-monitor/scripts/run_ingestor.py
+++ b/services/vadase-rt-monitor/scripts/run_ingestor.py
@@ -21,7 +21,10 @@ async def run_service(config_path: str, dry_run: bool):
 
     # Initialize Output Port
     if dry_run:
+        # NullOutputPort silently discards all writes -- no DB connection required.
+        # Prefer --dry-run over commenting out DB config for offline development. (ref: DL-003)
         db_writer = NullOutputPort()
     else:
+        # DSN may be None; TimescaleDBAdapter falls back to DB_* env vars. (ref: DL-005)
         dsn = config.get("database", {}).get("dsn")
         db_writer = TimescaleDBAdapter(dsn=dsn)

```


**CC-M-003-002** (services/vadase-rt-monitor/tests/test_output_adapter.py) - implements CI-M-003-002

**Code:**

```diff
--- /dev/null
+++ services/vadase-rt-monitor/tests/test_output_adapter.py
@@ -0,0 +1,450 @@
+"""Tests for TimescaleDBAdapter and NullOutputPort.
+
+TimescaleDBAdapter tests use asyncpg mock to avoid a live database.
+NullOutputPort tests confirm all methods are callable and return None.
+
+CI-M-003-002 scenarios covered:
+  (a) connect() creates pool and starts periodic flush task
+  (b) connect() propagates asyncpg.CannotConnectNowError (no silent fallback)
+  (c) write_velocity() buffers tuple and does NOT flush when below batch_size
+  (d) write_velocity() triggers fire-and-forget flush task at batch_size threshold
+  (e) write_velocity() with buffer_max_size reached drops oldest tuple
+  (f) write_displacement() same buffer-and-flush behaviour
+  (g) write_event_detection() performs immediate insert and propagates exceptions
+  (h) mid-flight flush failure restores batch to buffer front (no silent drop)
+  (i) pool acquire timeout logs pool_acquire_timeout with pool metrics
+  (j) close() runs final flush and closes pool
+  (k) ON CONFLICT DO NOTHING SQL present in executemany calls
+  (l) snake_case SQL columns paired with camelCase dict keys at correct positions
+"""
+
+import asyncio
+import pytest
+from collections import deque
+from datetime import datetime, timezone
+from unittest.mock import AsyncMock, MagicMock, patch
+
+import asyncpg
+
+from src.adapters.outputs.null import NullOutputPort
+from src.adapters.outputs.timescaledb import (
+    TimescaleDBAdapter,
+    _INSERT_VELOCITY,
+    _INSERT_DISPLACEMENT,
+)
+
+
+# ---------------------------------------------------------------------------
+# Shared fixtures
+# ---------------------------------------------------------------------------
+
+def _sample_vel_data(ts=None):
+    return {
+        "timestamp": ts or datetime(2025, 10, 6, 15, 0, 1, tzinfo=timezone.utc),
+        "vE": 0.001,
+        "vN": 0.002,
+        "vU": -0.001,
+        "vH_magnitude": 0.00224,
+        "cq": 0.95,
+    }
+
+
+def _sample_disp_data(ts=None):
+    return {
+        "timestamp": ts or datetime(2025, 10, 6, 15, 0, 1, tzinfo=timezone.utc),
+        "dE": 0.002,
+        "dN": 0.003,
+        "dU": 0.001,
+        "dH_magnitude": 0.0036,
+        "overall_completeness": 0.98,
+        "cq": 0.92,
+    }
+
+
+def _make_mock_pool():
+    """Create a mock asyncpg pool with async context manager for acquire()."""
+    conn = MagicMock()
+    conn.execute = AsyncMock()
+    conn.executemany = AsyncMock()
+    conn.__aenter__ = AsyncMock(return_value=conn)
+    conn.__aexit__ = AsyncMock(return_value=False)
+
+    pool = MagicMock()
+    pool.acquire = MagicMock(return_value=conn)
+    pool.close = AsyncMock()
+    pool.get_idle_size = MagicMock(return_value=1)
+    pool.get_size = MagicMock(return_value=2)
+    return pool, conn
+
+
+# ---------------------------------------------------------------------------
+# NullOutputPort
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_null_output_port_lifecycle():
+    port = NullOutputPort()
+    await port.connect()
+    await port.close()
+
+
+@pytest.mark.asyncio
+async def test_null_output_port_write_velocity():
+    port = NullOutputPort()
+    result = await port.write_velocity("BOST", _sample_vel_data())
+    assert result is None
+
+
+@pytest.mark.asyncio
+async def test_null_output_port_write_displacement():
+    port = NullOutputPort()
+    result = await port.write_displacement("BOST", _sample_disp_data())
+    assert result is None
+
+
+@pytest.mark.asyncio
+async def test_null_output_port_write_event():
+    port = NullOutputPort()
+    result = await port.write_event_detection(
+        "BOST", datetime.now(timezone.utc), 25.3, 10.1, 12.5
+    )
+    assert result is None
+
+
+# ---------------------------------------------------------------------------
+# (a) connect() creates pool and starts periodic flush task
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_connect_creates_pool_and_starts_flush_task():
+    mock_pool, _ = _make_mock_pool()
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", flush_interval=60.0)
+
+    with patch("asyncpg.create_pool", AsyncMock(return_value=mock_pool)):
+        await adapter.connect()
+
+    assert adapter._pool is mock_pool
+    assert adapter._flush_task is not None
+    assert not adapter._flush_task.done()
+
+    # Cleanup: cancel background task
+    adapter._flush_task.cancel()
+    try:
+        await adapter._flush_task
+    except asyncio.CancelledError:
+        pass
+
+
+# ---------------------------------------------------------------------------
+# (b) connect() propagates asyncpg.CannotConnectNowError
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_connect_propagates_cannot_connect_error():
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db")
+
+    with patch(
+        "asyncpg.create_pool",
+        AsyncMock(side_effect=asyncpg.CannotConnectNowError()),
+    ):
+        with pytest.raises(asyncpg.CannotConnectNowError):
+            await adapter.connect()
+
+    # Pool must remain None -- no silent fallback.
+    assert adapter._pool is None
+
+
+# ---------------------------------------------------------------------------
+# (c) write_velocity() buffers tuple and does NOT flush when below batch_size
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_write_velocity_buffers_below_batch_size():
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=100)
+    mock_pool, _ = _make_mock_pool()
+    adapter._pool = mock_pool
+
+    await adapter.write_velocity("BOST", _sample_vel_data())
+
+    assert len(adapter._velocity_buffer) == 1
+    assert not adapter._velocity_flushing
+
+
+# ---------------------------------------------------------------------------
+# (d) write_velocity() triggers flush task at batch_size threshold
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_write_velocity_triggers_flush_at_batch_size():
+    batch_size = 3
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=batch_size)
+    mock_pool, conn = _make_mock_pool()
+    adapter._pool = mock_pool
+
+    # Fill to batch_size -- last write should trigger a flush task.
+    for _ in range(batch_size):
+        await adapter.write_velocity("BOST", _sample_vel_data())
+
+    # Allow the fire-and-forget task to run.
+    await asyncio.sleep(0)
+    await asyncio.sleep(0)
+
+    conn.executemany.assert_awaited()
+    call_args = conn.executemany.call_args
+    sql = call_args.args[0]
+    assert "ON CONFLICT" in sql
+
+
+# ---------------------------------------------------------------------------
+# (e) buffer overflow: drops oldest tuple and increments counter
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_write_velocity_overflow_drops_oldest():
+    max_size = 5
+    adapter = TimescaleDBAdapter(
+        dsn="postgresql://fake/db", batch_size=1000, buffer_max_size=max_size
+    )
+    mock_pool, _ = _make_mock_pool()
+    adapter._pool = mock_pool
+    # Disable flushing to observe buffer behaviour purely.
+    adapter._velocity_flushing = True
+
+    # Insert max_size rows to fill the buffer.
+    for i in range(max_size):
+        data = _sample_vel_data(ts=datetime(2025, 1, 1, 0, 0, i, tzinfo=timezone.utc))
+        data["vE"] = float(i)
+        await adapter.write_velocity("BOST", data)
+
+    # Insert one more -- should drop oldest.
+    overflow_data = _sample_vel_data(ts=datetime(2025, 1, 1, 0, 1, 39, tzinfo=timezone.utc))
+    overflow_data["vE"] = 99.0
+    await adapter.write_velocity("BOST", overflow_data)
+
+    assert len(adapter._velocity_buffer) == max_size
+    assert adapter._velocity_dropped == 1
+    # Oldest (vE=0.0) should be gone; newest (vE=99.0) should be present.
+    rows = list(adapter._velocity_buffer)
+    v_east_values = [r[2] for r in rows]
+    assert 0.0 not in v_east_values
+    assert 99.0 in v_east_values
+
+
+# ---------------------------------------------------------------------------
+# (f) write_displacement() same buffer-and-flush behaviour
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_write_displacement_buffers_and_flushes():
+    batch_size = 2
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=batch_size)
+    mock_pool, conn = _make_mock_pool()
+    adapter._pool = mock_pool
+
+    for _ in range(batch_size):
+        await adapter.write_displacement("BOST", _sample_disp_data())
+
+    await asyncio.sleep(0)
+    await asyncio.sleep(0)
+
+    conn.executemany.assert_awaited()
+    sql = conn.executemany.call_args.args[0]
+    assert "vadase_displacements" in sql
+    assert "ON CONFLICT" in sql
+
+
+# ---------------------------------------------------------------------------
+# (g) write_event_detection() immediate insert; exceptions propagate
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_write_event_detection_immediate_insert():
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db")
+    mock_pool, conn = _make_mock_pool()
+    adapter._pool = mock_pool
+
+    detection_time = datetime(2025, 10, 6, 15, 0, 5, tzinfo=timezone.utc)
+    await adapter.write_event_detection("BOST", detection_time, 28.5, 12.3, 15.0)
+
+    conn.execute.assert_awaited_once()
+    args = conn.execute.call_args.args
+    assert args[1] == "BOST"
+    assert args[3] == pytest.approx(28.5)  # peak_velocity_horizontal
+
+
+@pytest.mark.asyncio
+async def test_write_event_detection_propagates_exception():
+    """write_event_detection is synchronous -- exceptions must propagate (DL-017)."""
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db")
+    mock_pool, conn = _make_mock_pool()
+    conn.execute = AsyncMock(side_effect=asyncpg.PostgresError())
+    adapter._pool = mock_pool
+
+    with pytest.raises(asyncpg.PostgresError):
+        await adapter.write_event_detection(
+            "BOST", datetime.now(timezone.utc), 10.0, 5.0, 8.0
+        )
+
+
+# ---------------------------------------------------------------------------
+# (h) mid-flight flush failure restores batch to buffer front
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_flush_failure_restores_batch_to_buffer():
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=1000)
+    mock_pool, conn = _make_mock_pool()
+    conn.executemany = AsyncMock(side_effect=asyncpg.PostgresError("db gone"))
+    adapter._pool = mock_pool
+
+    # Pre-fill buffer with 3 rows.
+    for i in range(3):
+        data = _sample_vel_data(ts=datetime(2025, 1, 1, 0, 0, i, tzinfo=timezone.utc))
+        await adapter.write_velocity("BOST", data)
+
+    assert len(adapter._velocity_buffer) == 3
+
+    # Manually trigger a flush that will fail.
+    with pytest.raises(asyncpg.PostgresError):
+        await adapter._flush_velocity()
+
+    # Rows must be restored -- silent drop is forbidden while pool is reachable (DL-009).
+    assert len(adapter._velocity_buffer) == 3
+    assert not adapter._velocity_flushing  # guard must be cleared in finally
+
+
+# ---------------------------------------------------------------------------
+# (i) pool acquire timeout logs pool_acquire_timeout
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_pool_acquire_timeout_logs_metrics():
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=1000)
+
+    mock_pool = MagicMock()
+    mock_pool.get_idle_size = MagicMock(return_value=0)
+    mock_pool.get_size = MagicMock(return_value=10)
+
+    # Simulate acquire raising TooManyConnectionsError (closest to PoolTimeout in asyncpg).
+    conn_ctx = MagicMock()
+    conn_ctx.__aenter__ = AsyncMock(
+        side_effect=asyncpg.exceptions.TooManyConnectionsError()
+    )
+    conn_ctx.__aexit__ = AsyncMock(return_value=False)
+    mock_pool.acquire = MagicMock(return_value=conn_ctx)
+    adapter._pool = mock_pool
+
+    # Pre-fill buffer with one row.
+    data = _sample_vel_data()
+    await adapter.write_velocity("BOST", data)
+    # Clear the buffer's lock contention; manually prime for flush.
+    adapter._velocity_flushing = False
+
+    with patch.object(adapter.log, "error") as mock_error:
+        with pytest.raises(asyncpg.exceptions.TooManyConnectionsError):
+            await adapter._flush_velocity()
+
+        error_calls = [str(c) for c in mock_error.call_args_list]
+        assert any("pool_acquire_timeout" in c for c in error_calls)
+
+
+# ---------------------------------------------------------------------------
+# (j) close() runs final flush and closes pool
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_close_runs_final_flush_and_closes_pool():
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", flush_interval=60.0)
+    mock_pool, conn = _make_mock_pool()
+    adapter._pool = mock_pool
+    adapter._flush_task = asyncio.create_task(asyncio.sleep(9999))
+
+    # Place one row in the buffer to verify final flush.
+    await adapter.write_velocity("BOST", _sample_vel_data())
+    assert len(adapter._velocity_buffer) == 1
+
+    await adapter.close()
+
+    mock_pool.close.assert_awaited_once()
+    # Buffer should be drained by the final _flush_all.
+    assert len(adapter._velocity_buffer) == 0
+
+
+# ---------------------------------------------------------------------------
+# (k) ON CONFLICT DO NOTHING SQL in executemany INSERT statements
+# ---------------------------------------------------------------------------
+
+def test_insert_sql_has_on_conflict_velocity():
+    assert "ON CONFLICT" in _INSERT_VELOCITY
+    assert "DO NOTHING" in _INSERT_VELOCITY
+
+
+def test_insert_sql_has_on_conflict_displacement():
+    assert "ON CONFLICT" in _INSERT_DISPLACEMENT
+    assert "DO NOTHING" in _INSERT_DISPLACEMENT
+
+
+# ---------------------------------------------------------------------------
+# (l) camelCase dict keys -> snake_case SQL columns at correct positional indices
+# ---------------------------------------------------------------------------
+
+@pytest.mark.asyncio
+async def test_write_velocity_positional_mapping():
+    """Verify camelCase parser keys map to correct SQL positional parameters (DL-018)."""
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=1000)
+    mock_pool, _ = _make_mock_pool()
+    adapter._pool = mock_pool
+    adapter._velocity_flushing = True  # Prevent auto-flush; inspect buffer directly.
+
+    ts = datetime(2025, 10, 6, 15, 0, 1, tzinfo=timezone.utc)
+    data = {
+        "timestamp": ts,
+        "vE": 0.111,
+        "vN": 0.222,
+        "vU": 0.333,
+        "vH_magnitude": 0.444,
+        "cq": 0.888,
+    }
+    await adapter.write_velocity("PBIS", data)
+
+    row = adapter._velocity_buffer[0]
+    # Positional mapping: (time, station_code, v_east, v_north, v_up, v_horizontal, quality)
+    assert row[0] == ts           # $1 time
+    assert row[1] == "PBIS"       # $2 station_code
+    assert row[2] == 0.111        # $3 v_east <- vE
+    assert row[3] == 0.222        # $4 v_north <- vN
+    assert row[4] == 0.333        # $5 v_up <- vU
+    assert row[5] == 0.444        # $6 v_horizontal <- vH_magnitude
+    assert row[6] == 0.888        # $7 quality <- cq
+
+
+@pytest.mark.asyncio
+async def test_write_displacement_positional_mapping():
+    """Verify camelCase parser keys map to correct SQL positional parameters (DL-018)."""
+    adapter = TimescaleDBAdapter(dsn="postgresql://fake/db", batch_size=1000)
+    mock_pool, _ = _make_mock_pool()
+    adapter._pool = mock_pool
+    adapter._displacement_flushing = True
+
+    ts = datetime(2025, 10, 6, 15, 0, 2, tzinfo=timezone.utc)
+    data = {
+        "timestamp": ts,
+        "dE": 0.010,
+        "dN": 0.020,
+        "dU": 0.030,
+        "dH_magnitude": 0.040,
+        "overall_completeness": 0.99,
+        "cq": 0.77,
+    }
+    await adapter.write_displacement("BOST", data)
+
+    row = adapter._displacement_buffer[0]
+    # Positional: (time, station_code, d_east, d_north, d_up, d_horizontal, overall_completeness, quality)
+    assert row[0] == ts           # $1 time
+    assert row[1] == "BOST"       # $2 station_code
+    assert row[2] == 0.010        # $3 d_east <- dE
+    assert row[3] == 0.020        # $4 d_north <- dN
+    assert row[4] == 0.030        # $5 d_up <- dU
+    assert row[5] == 0.040        # $6 d_horizontal <- dH_magnitude
+    assert row[6] == 0.99         # $7 overall_completeness
+    assert row[7] == 0.77         # $8 quality <- cq

```

**Documentation:**

```diff
--- a/services/vadase-rt-monitor/tests/test_output_adapter.py
+++ b/services/vadase-rt-monitor/tests/test_output_adapter.py
@@ -47,12 +47,21 @@ from src.adapters.outputs.timescaledb import (
 # Shared fixtures
 # ---------------------------------------------------------------------------
 
 def _sample_vel_data(ts=None):
+    """Return a minimal velocity data dict matching the parser output shape.
+
+    Keys match write_velocity expected camelCase parser keys (ref: DL-010).
+    """
     return {
         "timestamp": ts or datetime(2025, 10, 6, 15, 0, 1, tzinfo=timezone.utc),
         "vE": 0.001,
         "vN": 0.002,
         "vU": -0.001,
         "vH_magnitude": 0.00224,
         "cq": 0.95,
     }
 
 
 def _sample_disp_data(ts=None):
+    """Return a minimal displacement data dict matching the parser output shape.
+
+    Keys match write_displacement expected camelCase parser keys (ref: DL-010).
+    """
     return {
         "timestamp": ts or datetime(2025, 10, 6, 15, 0, 1, tzinfo=timezone.utc),
         "dE": 0.002,
@@ -68,7 +77,9 @@ def _sample_disp_data(ts=None):
 
 
 def _make_mock_pool():
-    """Create a mock asyncpg pool with async context manager for acquire()."""
+    """Build a mock asyncpg pool with a reusable async-context-manager connection.
+
+    pool.acquire() returns the same conn mock for all tests. conn.executemany and
+    conn.execute are AsyncMock so await works in async test bodies.
+    """
     conn = MagicMock()
     conn.execute = AsyncMock()

```


**CC-M-003-003** (services/vadase-rt-monitor/tests/test_processor.py) - implements CI-M-003-003

**Code:**

```diff
--- a/services/vadase-rt-monitor/tests/test_processor.py
+++ b/services/vadase-rt-monitor/tests/test_processor.py
@@ -1,22 +1,14 @@
 
 import pytest
 import asyncio
-from unittest.mock import AsyncMock, MagicMock
 from datetime import datetime, timedelta
 from src.domain.processor import IngestionCore
-from src.ports.outputs import OutputPort
-
-class MockOutputPort(OutputPort):
-    async def connect(self): pass
-    async def close(self): pass
-    async def write_velocity(self, station_id, data): pass
-    async def write_displacement(self, station_id, data): pass
-    async def write_event_detection(self, station_id, start_time, peak_v, peak_d, duration): pass
+from src.adapters.outputs.null import NullOutputPort
 
 @pytest.mark.asyncio
 async def test_processor_redundant_calculation():
     # Setup
-    output_port = MockOutputPort()
+    output_port = NullOutputPort()
     core = IngestionCore(
         station_id="TEST",
         output_port=output_port,

```

**Documentation:**

```diff
--- a/services/vadase-rt-monitor/tests/test_processor.py
+++ b/services/vadase-rt-monitor/tests/test_processor.py
@@ -1,4 +1,7 @@
 
+# NullOutputPort is the canonical no-op adapter; using it here ensures
+# test_processor exercises the same interface contract as production wiring.
+# (ref: DL-003)
 import pytest
 import asyncio
 from datetime import datetime, timedelta

```

