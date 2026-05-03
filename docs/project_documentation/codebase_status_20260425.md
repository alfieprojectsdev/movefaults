# Codebase Status Survey — 2026-04-25

> Point-in-time survey conducted at the start of the April 2026 implementation sprint.
> Use this alongside [`roadmap.md`](roadmap.md) and [`ticket_backlog.md`](ticket_backlog.md).

---

## Summary Table

| Component | Maturity | Impl. State | Primary Gap |
|---|---|---|---|
| vadase-rt-monitor | 80% | Active | NTRIP handshake; DB compression policies |
| field-ops | 100% | Complete | — |
| ingestion-pipeline | 35% | teqc QC wired; handoff missing | Scanner→Celery handoff (ING-001); Trimble formats |
| bernese-workflow | 10% | Stub + placeholder | Full `LinuxBPEBackend`; INP templates |
| pogf-geodetic-suite | 75% | IGS20 + teqc QC done | Timeseries analysis complete; Bernese wiring pending |
| drive-archaeologist | 65% | Scanner hardened (PR #33) | Trimble raw classification; pipeline handoff (ING-001) |

---

## VADASE RT Monitor (`services/vadase-rt-monitor/`)

**What exists and works:**
- `IngestionCore` with `ReceiverMode` enum state machine (RECEIVER / MANUAL) — replaces the old one-way latch bool. Committed `a74c109`.
- Hexagonal ports/adapters: `TCPAdapter`, `DirectoryAdapter` (inputs); `TimescaleDBAdapter`, `NullOutputPort` (outputs). Both wired correctly in entrypoints.
- NMEA parsers: `$GNLVM` / `$GPLVM` (velocity) and `$GNLDM` / `$GPLDM` (displacement) with XOR checksum validation.
- `replay_events.py` with `--dry-run`, `--quiet`, `--plot`, `--mode replay|import` — verified against BOST Dec 2023 Mw 7.6 dataset.
- `run_demo.sh` — single-command director laptop demo; Python 3.11+ check; zero Postgres dependency on `--dry-run`.
- Grafana dashboard provisioned (`real_time_monitoring.json`): velocity + ENU + event table panels, 5 s refresh, station dropdown. `docker-compose.yml` updated.
- Migrations 010 (vadase tables) and 011 (`displacement_source` column) in place.
- 43 / 43 tests passing.

**Known gaps:**
- `TCPAdapter` opens a TCP socket but does not implement the NTRIP HTTP/1.0 handshake required by Leica GR50 casters. Live ingestion will silently read nothing without this.
- TimescaleDB compression + retention policies not yet configured (DL-012 deferred). At 35 stations × 1 Hz, uncompressed rows will fill the R740 within weeks.
- Trimble sentence parser stubs are dead code (GR50 is Leica). Should be removed.
- `roadmap.md` §6 still lists the one-way latch bug as open — it is resolved in `a74c109`.

**Roadmap note:** The roadmap maturity estimate of ~80% is accurate. The remaining ~20% is the NTRIP handshake, compression/retention ops, and integration testing against live casters.

---

## Field Operations (`services/field-ops/`)

**Status: complete.** FastAPI backend + React/Vite PWA. `field_ops` schema namespace. Offline-first IndexedDB queue + Service Worker sync. Station picker syncs from central `stations` table. No remaining work identified.

---

## Ingestion Pipeline (`services/ingestion-pipeline/src/`)

**What exists and works:**
- `tasks.py` (328 lines) — substantive implementation, not a stub:
  - Format standardisation: `.gz`, `.zip`, `.Z`, `.crx`/`.??d` (Hatanaka) decompression
  - Two-stage validation: header scan + optional `teqc` QC call
  - DB load: RINEX header parsing, station FK resolution, dedup by SHA-256, `IngestionLog` updates
- `celery.py`, `database.py`, `pipeline.py`, `models.py`, `scanner.py` — orchestration layer present

**Known gaps:**
- `drive-archaeologist` scanner output is not yet wired to `ingest_rinex.delay()`. The two systems are developed independently with no handoff.
- Trimble `.T01`/`.T02`/`.T04`/`.DAT`/`.TGD` files are not classified by the scanner; they require `runpkr00` or `teqc -tr d` conversion before RINEX ingestion.
- No integration tests covering the scanner → Celery → DB path end-to-end.

---

## Bernese Workflow (`services/bernese-workflow/src/`)

**What exists:**
- `orchestrator.py` with `generate_pcf()` and `_generate_config()` Jinja2 methods (16-line placeholder template).
- `run_bpe()` is present but body is `logger.info("STUB: BPE execution successful")` — no actual Perl invocation.
- Research is 100% complete (memory files: `bernese_bpe_phases.md`, `bernese_inp_settings.md`, `velocity_pipeline.md`, `bernese_install.md`).

**Known gaps (the full implementation):**
- No `BPEBackend` protocol class.
- No `LinuxBPEBackend` — the Perl `startBPE.pm` invocation, quality gate parsing, output collection.
- No Jinja2 INP templates (3 parameters confirmed to need overrides from the 5.2→5.4 diff: `RNXGRA MINOBS/MAXBAD`, `ADDNEQ2 MAXPAR`).
- No campaign file generation pipeline (8 steps: STA → CRD+ABB → ATL → PLD → VEL → CLU → BLQ).
- Bernese not yet installed on R740 (only verified on T420).
- `plot_v2.py` has an interactive `input()` prompt for reference station — blocks headless execution.

**Critical path note:** Bernese is the sole blocker for end-to-end campaign processing. IGS downloader correctness (see below) and R740 installation must precede the software implementation.

---

## pogf-geodetic-suite (`packages/pogf-geodetic-suite/`)

**What works:**
- `modeling/coordinates.py` — geodetic ↔ ENU ↔ ECEF conversions via `pymap3d`. Complete.
- `timeseries/analysis.py` — `VelocityEstimator` (least-squares regression) + IQR outlier detection. Complete.

**Partial / stubs:**
- `qc/rinex_qc.py` — **complete** (ING-003, PR #34): `teqc +qc` backend with structured `RINEXQCResult`, configurable timeout, QC metrics propagated to `IngestionLog` through the Celery chain. 12 unit tests.
- `igs_downloader.py` — **complete** (IGS-001, `f742571`): IGS20 long filenames, `.gz` decompression, IGN→BKG→CDDIS mirror fallback.

---

## drive-archaeologist (`tools/drive-archaeologist/`)

**What works (Phase 1):**
- `scanner.py` — **hardened** (PR #33): `on_classified` callback seam, per-file checkpoint, path traversal protection on all archive formats (ZIP/TAR/RAR/7z), error-count accuracy. 31 unit tests.
- `strategies/gnss.py` — RINEX filename pattern (`ssssdddh.yyt`) with tightened `.DDo` fallback.
- `classifier.py`, `profiles.py`, `archive_handler.py` — classification pipeline; extension conflicts resolved.

**Known gaps:**
- Trimble proprietary formats (`.T01`, `.T02`, `.T04`, `.DAT`, `.TGD`) not in `profiles.py`. PHIVOLCS has Trimble NetR9 receivers in the field; this is a real coverage gap.
- No `dispatch_to_pipeline()` call after classification — scanner and ingestion pipeline are disconnected (ING-001).
- Archive checkpoint uses ephemeral temp paths for extracted members; resume rescans archive contents (ING-004, deferred).

---

## Infrastructure

**What's in place:**
- `docker-compose.yml`: TimescaleDB (port 5433), Redis (port 6380), Grafana (port 3000).
- Alembic migrations 001–011 covering full schema history.
- All OSS images — $0 recurring software cost.

**Gap:**
- TimescaleDB compression + retention policies not configured. This is documented as DL-012 and intentionally deferred, but must be resolved before the R740 goes live with 35 stations.

---

## Stale Documentation

| Location | Stale Entry | Correct State |
|---|---|---|
| `roadmap.md` §6 | "Fix one-way latch bug in `domain/processor.py:130`" | Resolved in `a74c109` (2026-04-25) — `ReceiverMode` state machine replaces the bool |
| `deliverables_tracker.md` Near-Term | "VADASE latch bug fix" | Same — complete |
| `roadmap.md` §6 | Maturity listed as ~80% | Still accurate; NTRIP + compression are the remaining 20% |
