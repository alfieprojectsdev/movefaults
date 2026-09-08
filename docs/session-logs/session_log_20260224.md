# Session Log: Phase 0 Database Foundation & Project Planning (2026-02-24)

## Overview

Three major threads completed this session:

1. **Project-wide status review** — honest assessment of all deliverables vs. roadmap estimates
2. **Jules PR triage** — 15 open PRs evaluated, 6 merged to main, 9 closed
3. **Phase 0 implementation** — centralized geodetic database foundation (Alembic + migrations + seed)

Additionally received a working Bernese PCF file (`temp/PHIVOL_REL.PCF`) which resolves a
critical open question for Phase 1B-iii and reveals the real complexity of the Bernese
workflow (127 lines vs. the 16-line placeholder currently in the codebase).

---

## 1. Project Status Review

Conducted a frank codebase-based assessment (not roadmap-based). Key gap vs. CLAUDE.md estimates:

| Component | CLAUDE.md Estimate | Actual |
|---|---|---|
| vadase-rt-monitor | ~80% | ~65% |
| pogf-geodetic-suite | ~70% | ~30% (legacy scripts not ported) |
| drive-archaeologist | ~60% | ~60% (accurate) |
| ingestion-pipeline | ~30% | ~30% (split across two locations) |
| bernese-workflow | ~10% | ~15% |

**Critical finding**: `pogf-geodetic-suite` was significantly over-estimated. The legacy
`analysis/` scripts contain the real domain logic but have not been ported into the package.

---

## 2. Deliverables Planning: 1.3 (Bernese) and 2.3 (Field Ops PWA)

### Dependency chains resolved

**Deliverable 2.3 (PWA)** — nearly unblocked:
- Only shared dependency: `stations` table in central DB (Phase 0)
- Uses a dedicated `field_ops` schema in the same PostgreSQL instance
- Frontend: React + Vite; Backend: FastAPI; Offline-first: IndexedDB + Service Worker

**Deliverable 1.3 (Bernese)** — four prerequisites in sequence:
1. Central DB schema (Phase 0) ← doing now
2. IGS downloader rewrite (broken filename conventions)
3. Ingestion pipeline consolidation (`src/ingestion/` → `services/ingestion-pipeline/`)
4. Bernese orchestrator with `BPEBackend` protocol (Linux R740 + Windows desktops)

### Key architectural decisions made

- **Bernese deployment**: Design for *both* Linux (Dell PowerEdge R740, `RUNBPE.sh`) and
  Windows desktops (`bpe.exe`) via a `BPEBackend` Protocol with swappable adapters.
- **RINEX QC tool**: `teqc` as primary backend. `gfzrnx` stub only (not yet acquired).
- **PWA database**: Same PostgreSQL instance as central POGF DB, but `field_ops` schema
  namespace — one less container to manage, logically isolated.

---

## 3. Jules PR Triage

All 15 open PRs reviewed for conflicts and value. **6 merged, 9 closed.**

### Merged to main

| PR | What | Why |
|---|---|---|
| #26 | DB Writer async batching + `write_event_detection` | 70→2 DB calls/sec for 35 stations; `write_event_detection` was a silent `pass` |
| #25 | Redis password authentication | Redis was unauthenticated (port 6380 wide open) |
| #23 | NMEA time parsing refactor (`_parse_nmea_time` helper) | DRY violation — 6-line block duplicated across two functions |
| #22 | `math.hypot` + `np.linalg.lstsq` in velocity estimator | Numerical stability improvements |
| #20 | Metrics unit tests | No test coverage for core detection math functions |
| #18 | Fix command injection in `campaign_v6.py` | CWE-78: user input into `os.system()` |

### Closed (superseded or conflicting)

#15 (superseded by #26), #16 (superseded by #23), #19 (superseded by #23),
#24 (superseded by #22+#20), #5 (superseded by #20), #7 (superseded by #22),
#17/#21/#3 (three-way conflict on `RUNX_kinematic.py`, deferred to analysis porting phase)

---

## 4. Phase 0: Database Foundation

### New files created

| File | Purpose |
|---|---|
| `pyproject.toml` | Added `alembic>=1.13.0` to dev deps |
| `src/db/__init__.py` | Package init |
| `src/db/models.py` | `Station` + `RinexFile` ORM models (SQLAlchemy, 105 lines) |
| `alembic.ini` | Alembic config (URL via env vars in env.py, not hardcoded) |
| `migrations/env.py` | Online + offline migration runners (101 lines) |
| `migrations/script.py.mako` | Template for new revision files |
| `migrations/versions/001_create_stations.py` | Unified stations table + PostGIS extension |
| `migrations/versions/002_create_rinex_files.py` | RINEX file catalogue + index |
| `migrations/versions/003_create_timeseries.py` | TimescaleDB hypertables (raw SQL via op.execute) |
| `scripts/seed_stations.py` | Idempotent YAML-to-DB loader (152 lines, dry-run support) |

### Modified files

| File | Change |
|---|---|
| `services/vadase-rt-monitor/scripts/init_database.sql` | Removed conflicting `stations` table block; replaced with comment pointing to Alembic |

### Key design decisions

- **Unified stations table**: Merges VADASE's `host/port` fields with tech spec's `id/agency/metadata_json` fields into one table. VADASE's asyncpg hot-path stores `station TEXT` denormalized (no FK lookup at 35×1Hz insert rate).
- **PostGIS GEOMETRY(Point, 4326)**: Live DB inspection revealed the tech spec had already chosen PostGIS geometry. Adopted this (added `geoalchemy2>=0.18.1` dev dep — no GDAL required). Migration 001 rewrote to raw `op.execute()` SQL because `op.create_table()` can't express PostGIS column types natively.
- **JSONB for metadata_json**: Live DB used JSONB (not TEXT). Adopted — enables GIN index queries on antenna/receiver fields.
- **date_added column**: Present in live DB schema, added to our model.
- **GIST index on location**: Added `idx_stations_location USING GIST (location)` for future `ST_DWithin` proximity queries (e.g. stations near an epicenter).
- **Alembic URL via env vars**: `env.py` reads `POGF_DB_*` environment variables; defaults match `docker-compose.yml` values so no config needed for local dev.
- **TimescaleDB hypertables via raw SQL**: `create_hypertable()` is not expressible in SQLAlchemy DDL, so migration 003 uses `op.execute()`.
- **Seed script idempotency**: Uses PostgreSQL `INSERT ... ON CONFLICT (station_code) DO UPDATE` so re-running after adding stations is safe. Uses `WKTElement("POINT(lon lat)", 4326)` — PostGIS WKT is X (lon) first, Y (lat) second.

### Schema reconciliation (live DB vs. initial migrations)

The live DB had been created manually from the tech spec SQL dump — no `alembic_version` table.
Differences found and resolved:

| Column | Live DB | Initial migration | Resolution |
|---|---|---|---|
| `stations.location` | `GEOMETRY(Point,4326)` | `latitude FLOAT` + `longitude FLOAT` | Adopted PostGIS |
| `stations.metadata_json` | `JSONB` | `TEXT` | Adopted JSONB |
| `stations.date_added` | Present | Missing | Added |
| `stations.fault_segment/host/port` | Missing | Present | Kept our additions |
| `velocity_products.sigma_*` | Missing | Present | Kept our additions |

Dropped 4 empty tables individually (TimescaleDB rejects multi-table CASCADE on hypertables),
then ran fresh `alembic upgrade head` 001→002→003.

### Verified working (live DB)

```bash
uv run alembic upgrade head
# INFO Running upgrade  -> 001, create stations table
# INFO Running upgrade 001 -> 002, create rinex_files table
# INFO Running upgrade 002 -> 003, create timeseries_data hypertable and velocity_products

uv run python scripts/seed_stations.py
# Loaded 4 station(s) from .../stations.yml
# Upserted 4 station(s) into the database.
# BOST  Boston, Davao Oriental          7.8556, 126.3639
# BTU2  Butuan City, Agusan del Norte   8.9478, 125.5406
# PAPI  Aparri, Cagayan                18.3556, 121.6417
# PBIS  Bislig City, Surigao del Sur    8.1956, 126.3919
```

`alembic_version = 003`. All FK constraints and GIST index confirmed present.

**Committed**: `bafa06b` on `feat/phase0-database-foundation` (12 files, 733 insertions). Not yet pushed.

---

## 5. Bernese PCF Analysis (Critical for Phase 1B-iii)

Received working production PCF: `temp/PHIVOL_REL.PCF` (127 lines, PHIVOLCS relative positioning).

### Real workflow stages (vs. the 16-line placeholder in `services/bernese-workflow/`)

| Stage | PIDs | Key programs | What it does |
|---|---|---|---|
| Init | 000–099 | `FTP_DWLD`, `R2S_COP`, `ATX2PCV`, `COOVEL`, `CRDMERGE`, `RNX_COP` | Download IGS products, copy RINEX, update a-priori coords |
| Orbits | 100–199 | `POLUPDH`, `ORBMRGH`, `PRETAB`, `ORBGENH` | Build tabular orbits from precise ephemerides |
| RINEX proc | 200–299 | `RNXSMTAP`, `RXOBV3AP`, `CODSPPAP`, `CODXTR` | Smooth, extract obs, code SPP for initial positions |
| Float solution | 300–399 | `INIT_BSL`, `SNGDIF`, `MAUPRPAP`, `GPSEDTAP`, `ADDNEQ2` | Single-differences, phase editing, ambiguity-float NEQ |
| Ambiguity resolution | 400–499 | `GNSAMBAP`, `GNSL53AP`, `GNSQIFAP`, `GNSL12AP`, `AMBXTR` | MW/L3 → QIF → L5/L3 → L1&L2 (stratified by baseline length) |
| Final solution | 500–599 | `GPSCLUAP`, `ADDNEQ2`, `COMPARF`, `HELMCHK`, `ADD_WK`, `ADD_MON` | Cluster solution, Helmert check, weekly+monthly combination |
| Cleanup | 900–999 | `R2S_SUM`, `R2S_SAV`, `R2S_DEL`, `BPE_CLN` | Save results, delete temp files |

### Jinja2-templatable variables (the `VARIABLE` section of the PCF)

| Variable | Default in PCF | What to template |
|---|---|---|
| `V_B` | `IGS` | Orbit/clock file prefix (IGS, COD, GFZ…) |
| `V_CRDINF` | `PIVSMIND` | Campaign coordinate/STA/BLQ file name |
| `V_RNXDIR` | `PIVSMIND` | RINEX input folder name |
| `V_REFINF` | `IGS14` | Reference frame (IGS14, IGS20/ITRF20) |
| `V_REFDIR` | `REF52` | Bernese reference files folder |
| `V_SAMPL` | `180` | Solution sampling interval (seconds) |
| `V_SATSYS` | `GPS` | GNSS constellation (GPS, GLO, ALL) |
| `V_CLU` | `10` | Max stations per cluster |
| `V_BL_L12` | `20` | Max baseline for L1&L2 narrow-lane AR (km) |
| `V_BL_L53` | `200` | Max baseline for L5/L3 AR (km) |
| `V_BL_QIF` | `2000` | Max baseline for QIF AR (km) |

### Critical orchestrator implications

1. **`FTP_DWLD` (step 000) downloads IGS products within BPE**. Decision needed:
   - Option A: Let BPE handle its own download (simpler orchestrator, but requires internet access on processing machine and correct FTP config)
   - Option B: Pre-download via our IGS downloader service, disable/skip step 000, pre-stage files in the Bernese `ORB` directory → orchestrator controls exactly which products are used
   - **Recommendation**: Option B — gives us version-controlled reproducibility and lets the IGS downloader handle retry/fallback across CDDIS/IGN/BKG mirrors

2. **`PARALLEL` keyword in the params section** — BPE's own parallelism (not ours). Steps like `211` (`PARALLEL $201`) run multiple baseline subsets concurrently within the BPE process. The orchestrator does not need to manage this.

3. **`NEXTJOB 301` at step 331** — BPE loop: if more baseline subsets remain, jump back to 301. Again managed internally by BPE.

4. **BPE invocation on Linux (R740)**: NOT `bpe.exe`. Uses:
   ```bash
   source ${C}/LOADGPS.setvar
   ${BPE}/RUNBPE.sh CAMPAIGN SESSION PCF_NAME
   ```
   Requires Perl on the R740. `RUNBPE.sh` wraps `RUNBPE.pm`.

5. **`V_CRDINF = PIVSMIND`** ties the PCF to the PHIVOLCS-specific campaign directory. This is the primary parameter to template — it links to the campaign's `.CRD`, `.VEL`, `.STA`, `.BLQ`, `.ATL` files.

### Immediate action for Phase 1B-iii

Replace the 16-line placeholder `templates/basic_processing.pcf.j2` with a Jinja2-templated version of `PHIVOL_REL.PCF`, parametrizing the `VARIABLE` section. The execution graph (PID/SCRIPT/WAIT FOR lines) stays fixed.

---

## 6. Phase 1A: Field Ops PWA Scaffold (Deliverable 2.3)

Branch: `feat/phase1a-field-ops`

### Key decisions made

- **PWA over Flutter**: Flutter considered (mixed iOS/Android field teams, sideloading feasible) but deferred — deployment friction outweighs benefit at this stage. Revisit if iOS background sync becomes a real-world problem.
- **passlib → bcrypt direct**: `passlib[bcrypt]` is incompatible with bcrypt ≥ 4.x (unmaintained). Dropped in favour of `bcrypt` library directly.
- **`CURRENT_TIMESTAMP` not `now()`**: PostgreSQL-specific `now()` breaks SQLite test DB. `CURRENT_TIMESTAMP` is ANSI SQL and portable.
- **`schema_translate_map`**: SQLite has no schema namespacing. `execution_options={"schema_translate_map": {"field_ops": None}}` strips the prefix for test engines.

### New files

| File | Purpose |
|---|---|
| `services/field-ops/src/field_ops/config.py` | Pydantic settings (DB URL, JWT secret, upload dir) |
| `services/field-ops/src/field_ops/database.py` | Async SQLAlchemy engine + session factory (asyncpg) |
| `services/field-ops/src/field_ops/models.py` | ORM: User, LogSheet, EquipmentInventory, LogSheetPhoto |
| `services/field-ops/src/field_ops/routers/auth.py` | POST /api/v1/token (OAuth2 + JWT, bcrypt) |
| `services/field-ops/src/field_ops/routers/logsheets.py` | POST/GET /api/v1/logsheets (batch, idempotent via client_uuid) |
| `services/field-ops/src/field_ops/routers/equipment.py` | QR lookup + admin inventory + QR PNG generation |
| `services/field-ops/src/field_ops/routers/stations.py` | GET /api/v1/stations (reads central public.stations via ST_X/ST_Y) |
| `services/field-ops/src/field_ops/main.py` | FastAPI app factory + CORS middleware |
| `services/field-ops/alembic.ini` | Field-ops Alembic config |
| `services/field-ops/migrations/env.py` | Async env.py (asyncpg); creates field_ops schema before version table |
| `services/field-ops/migrations/versions/001_field_ops_schema.py` | Creates field_ops schema + 4 tables |
| `services/field-ops/tests/conftest.py` | SQLite in-memory fixtures with schema_translate_map |
| `services/field-ops/tests/test_logsheets.py` | Batch submit, idempotency, filter, 401 |
| `services/field-ops/tests/test_equipment.py` | QR lookup, role-based access, admin CRUD |
| `services/field-ops/frontend/package.json` | React 18, Vite 5, vite-plugin-pwa, react-hook-form, idb |
| `services/field-ops/frontend/vite.config.ts` | PWA config + /api proxy to FastAPI |
| `services/field-ops/frontend/src/App.tsx` | Top-level nav (Log Sheet / Offline Queue views) |
| `services/field-ops/frontend/src/components/LogSheetForm.tsx` | Main form: offline-first submit with fallback to IndexedDB |
| `services/field-ops/frontend/src/components/StationPicker.tsx` | Dropdown from central stations table |
| `services/field-ops/frontend/src/hooks/useOfflineQueue.ts` | IndexedDB queue; auto-flushes batch on online event |
| `services/field-ops/frontend/src/hooks/useStations.ts` | React Query wrapper for /api/v1/stations |
| `services/field-ops/frontend/src/services/api.ts` | Typed API client with JWT token management |
| `services/field-ops/Dockerfile` | Two-stage: Node (Vite build) → Python (FastAPI) |
| `services/field-ops/config/default.yml` | Default config values |

### Verified working

```
field_ops schema live: version_num = fo001
Tables: alembic_version, users, logsheets, equipment_inventory, logsheet_photos
Tests: 7/7 passed (SQLite in-memory)
```

### Key technical gotchas resolved

1. **field_ops schema bootstrapping**: Alembic tries to create `field_ops.alembic_version` before migration 001 runs. Fixed by `CREATE SCHEMA IF NOT EXISTS field_ops` in `env.py` before `context.run_migrations()`.
2. **Async Alembic runner**: Field-ops has asyncpg but not psycopg2. `env.py` uses `create_async_engine` + `conn.run_sync(do_run_migrations)` instead of the default sync `engine_from_config` pattern.

### Committed

Phase 1A: committed on `feat/phase1a-field-ops`. Not yet pushed.

---

## 7. Bernese PCF Domain Intelligence (Phase 1B-iii input)

Received RAG analysis comparing internal PHIVOLCS `BERN52 Guide` against official Bernese 5.2 docs. Key findings recorded in `.claude/implementation-plan.md` and memory. Summary:

| Gap | Current practice | Orchestrator fix |
|---|---|---|
| Pre-BPE prep (RXOBV3, GRDS1S2) | Manual GUI steps | Already in PHIVOL_REL.PCF — don't pre-run |
| .STA file editing | Manual Notepad++ (FORTRAN alignment) | `prepare_campaign()` calls STAMERGE |
| RNXGRA options | Interactive GUI edit before each run | Version-controlled .INP files in OPT_DIR |
| V_MYATX | Treated as passive string | Triggers ATX2PCV (PID 002) antenna model recompile |
| HELMCHK reference stations | Added ad-hoc when it errors | Pre-flight check: ≥ 4 reference stations in .STA |

---

## 8. Session Effort Estimate

Estimated manual effort if this session's work had been done without agentic aid,
assuming a senior developer with mastery of all relevant stacks:

| Section | Manual estimate |
|---|---|
| Project status review + honest assessment across 5 components | 3–4 h |
| Deliverable dependency chain analysis + architectural decisions | 2–3 h |
| Jules PR triage: 15 PRs reviewed, conflict clusters identified, 6 merged | 8–12 h |
| Phase 0: Alembic setup, 3 migrations, models, seed script | 6–8 h |
| Schema reconciliation (live DB diff, fixes, debugging) | 3–5 h |
| PCF analysis (127-line production file, 7 stages, orchestrator implications) | 3–5 h |
| Phase 1A backend (config, database, models, 4 routers, main.py) | 10–14 h |
| Phase 1A frontend (PWA scaffold, offline queue, Service Worker, components) | 8–12 h |
| Phase 1A debugging (schema_translate_map, passlib, now(), async Alembic) | 3–5 h |
| Documentation (session log, implementation plan, memory) | 2–3 h |
| **Total** | **~48–71 hours** |

**~6–9 developer-days** minimum for a full-stack developer already fluent in all
the technologies. For someone learning any part of the stack along the way: 3–5 weeks.

Largest time savings from agentic help:
1. **Parallel file creation** — 30+ files written simultaneously, not sequentially
2. **Debugging loops** — each compatibility issue (SQLite schema prefix, `now()`,
   passlib/bcrypt) would have required separate doc research + trial and error
3. **Cross-domain context retention** — holding Bernese PCF knowledge, VADASE
   architecture, DB schema decisions, and React PWA patterns in parallel

---

## Next Session

Both Phase 0 and Phase 1A committed; neither branch pushed yet.

1. Push both branches, open PRs, merge to main
2. Scan `packages/CORS-dashboard/` for domain patterns to inform LogSheetForm field completeness
3. Start Phase 1B-i: ingestion pipeline consolidation (`src/ingestion/` → `services/ingestion-pipeline/`)
   OR
   Phase 1B-ii: IGS downloader rewrite (self-contained, no upstream deps — good warm-up)
<!-- 2026-02-24 1542 -- Resume this session with:
claude --resume c2958969-417a-4e3d-b780-07d16b0716e1 -->