# Deliverables Tracker

**Last updated:** 2026-04-25

> Quick-reference status and date targets for all project deliverables.
> For architectural context and dependency rationale, see [`roadmap.md`](roadmap.md).

---

## Status Key

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete — implemented, tested, committed |
| 🔄 | In progress |
| 🔬 | Research complete; implementation not started |
| ⏳ | Not started |
| 🚧 | Blocked |

---

## Deliverables

| ID | Deliverable | Status | Completed / Target | Notes |
|----|-------------|--------|-------------------|-------|
| 1.1 | Centralized Geodetic Database | ✅ | 2026-01-30 | Alembic 001–008; commit `bafa06b` + migrations 007/008 |
| 2.3 | Digital Field Operations PWA | ✅ | 2026-02-24 | `services/field-ops/`; schema extended (migration 008) |
| 1.2 | Unified Data Ingestion Pipeline | 🔄 | Q2 2026 | 1B-i consolidation done (PR #32); teqc + Trimble step pending |
| 2.1 | drive-archaeologist Integration | 🔄 | Q2 2026 | Scanner works; Trimble profiles + pipeline handoff pending |
| 2.2 | Automated IGS Product Downloader | 🔄 | Q2 2026 | Partial; needs IGS20 naming + mirror fallback chain |
| 2.5 | RINEX QC Module | 🔄 | Q2 2026 | teqc wrapper exists; confirmed commands (Trimble `-tr d`, Leica `-lei mdb`) |
| 2.4 | Geodetic Post-Processing & Modeling Suite | 🔄 | Q3–Q4 2026 | `velocity-reviewer` complete (`bd743bb`); MATLAB port deferred |
| 1.3 | Automated Bernese Processing Workflow | 🔬 | Q3 2026 | INP diff (5.2→5.4) complete; Jinja2 templates next |
| 1.4 | Public Data Portal and API | ⏳ | Q4 2026 | Depends on 1.3, 2.4. Strategic target: AusPos-equivalent for PH (300-station network, 27yr archive) — needs NAMRIA partnership for PRS92 datum |
| 3.1 | Centralized Documentation Portal | ⏳ | Q3 2026 | MkDocs + GitHub Pages; low-risk, can start any time |
| 3.2 | Automated Processing Documentation | ⏳ | Q4 2026 | Depends on 3.1 |

---

## Near-Term Work Items

> Full ticket list with priorities, sizes, and dependency graph: [`ticket_backlog.md`](ticket_backlog.md)

**Critical path (P0 — blocks Bernese end-to-end):**
1. **IGS-001** — IGS downloader rewrite: correct IGS20 naming + CDDIS/IGN/BKG fallback chain
2. **BRN-001** — Install Bernese 5.4 on R740 (same procedure as T420; no ISA mismatch)
3. **BRN-002** — `BPEBackend` protocol + `LinuxBPEBackend` implementation (Perl `startBPE.pm` invocation)
4. **BRN-003** — Jinja2 INP templates from completed 5.2→5.4 diff (3 parameters to override)
5. **BRN-004** — Campaign file generation pipeline (8-step: STA→CRD→ATL→PLD→VEL→CLU→BLQ)

**Production deployment (P1 — needed before R740 go-live):**
6. **VAD-001** — TimescaleDB compression + retention policies (DL-012 gap; drives will fill without this)
7. **VAD-002** — TCPAdapter NTRIP client handshake for Leica GR50
8. **ING-001** — drive-archaeologist → ingestion-pipeline Celery handoff
9. **BRN-005** — `plot_v2.py` headless parameterization

---

## Recently Completed

| Date | Item | Detail |
|------|------|--------|
| 2026-04-25 | VADASE director demo — full stack | `run_demo.sh` launcher; BOST Mw 7.6 fast-import replay; ANSI event banner; `--quiet` flag; Python 3.11+ check |
| 2026-04-25 | Grafana dashboard provisioned | `real_time_monitoring.json`: velocity + ENU + event table; 5 s refresh; docker-compose wired |
| 2026-04-25 | TimescaleDBAdapter wired as OutputPort | Migration 011 (`displacement_source`); lazy asyncpg import on dry-run; legacy `DatabaseWriter` deleted |
| 2026-04-25 | `ReceiverMode` state machine | Replaces one-way `manual_integration_active` bool; velocity-gated hysteresis; `GOOD_THRESHOLD=30` for Philippine scintillation — commit `a74c109` |
| 2026-03-03 | `velocity-reviewer` — PLOT file stripping | `write_cleaned_plots()` in `reader.py`; `POST /api/export` strips PLOT files with `.bak` backup/restore for idempotency; commit `bd743bb` |
| 2026-03-03 | Velocity pipeline primary source verification | PLOT format confirmed from `RUNX_v2.py:137`; offsets format from production file; `vel_line_v8.m` confirmed does NOT read `OUTLIERS.txt`; `00_CRD_*.bat` exclusion logic mapped; teqc commands confirmed from §4.2.3/§4.2.4 |
| 2026-03-03 | INP file diff (5.2 PHIVOLCS vs 5.4 EXAMPLE) | ADDNEQ2, MAUPRP, RNXGRA, RXOBV3, CODSPP compared; minimal Jinja2 strategy confirmed (3 parameters differ: RNXGRA MINOBS/MAXBAD, ADDNEQ2 MAXPAR) |
| 2026-03-02 | Migration 008 — field ops schema | `staff` table, `logsheet_observers` junction, campaign/continuous logsheet columns |
| 2026-03-02 | Migration 007 — `offset_events` table | Feeds velocity pipeline; replaces manual `offsets` flat file |
| 2026-02-27 | `velocity-reviewer` tool (initial) | Web-based GNSS outlier review UI; replaces Windows-only `outlier_input-site.py` |
| 2026-02-27 | Bernese orchestration explainer | Staff-facing document at `docs/bernese_orchestration_explainer.md` |
| 2026-02-26 | Bernese 5.4 installed + verified (T420) | 47-step BPE, solutions ≤0.09 mm from reference |
| 2026-02-26 | BPE phase map + INP settings documented | Memory files: `bernese_bpe_phases.md`, `bernese_inp_settings.md`, `velocity_pipeline.md` |
| 2026-02-24 | Phase 1B-i ingestion consolidation | PR #32 merged |
| 2026-01-30 | Phase 0 database foundation | commit `bafa06b` |
