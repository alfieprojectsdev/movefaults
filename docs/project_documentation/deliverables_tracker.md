# Deliverables Tracker

**Last updated:** 2026-07-01

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
| 2.1 | drive-archaeologist Integration | 🔄 | Q2 2026 | Scanner mechanics validated on a REAL mounted drive (a DOST media/movies drive — walk/dedup/checkpoint work). BUT the GNSS classification path (RINEX/Trimble/Hatanaka profiles — the tool's actual purpose) has ONLY synthetic/mock coverage (mock_drive/, test_data/, tmp_path). **Untested against a real legacy GNSS drive.** Also pending: Trimble profiles, pipeline handoff (ING-001) |
| 2.2 | Automated IGS Product Downloader | 🔄 | Q2 2026 | Partial; needs IGS20 naming + mirror fallback chain |
| 2.5 | RINEX QC Module | 🔄 | Q2 2026 | teqc wrapper exists (GPS-only RINEX-2). **gfzrnx migration trigger MET (2026-07-01, empirical):** teqc `2019Feb25` HARD-REFUSES the RINEX 3.04 IGS fiducials (`must be RINEX <= 2.11`); gfzrnx 2.2.0 QC's all constellations. Evidence: `gfzrnx_vs_teqc_rinex3_evidence.md`. Cass (MOVE Faults COS) has run gfzrnx for years. Next: dual-tool QC (teqc for RINEX-2 CORS, gfzrnx for RINEX-3 fiducials) or gfzrnx-primary; commercial license for the automated pipeline |
| 2.4 | Geodetic Post-Processing & Modeling Suite | 🔄 | Q3–Q4 2026 | `velocity-reviewer` complete (`bd743bb`); MATLAB port deferred |
| 1.3 | Automated Bernese Processing Workflow | 🔄 | Q3 2026 | **Core orchestrator BUILT** (BRN-002..006 done: BPEBackend+LinuxBPEBackend, campaign_builder, rinex_header_validator, pcf_context, PHIVOL_REL PCF template, velocity hook). NAMRIA training week (2026-06) PROVED the real PAGENET pipeline runs headless end-to-end on live data. **Frontier = R740-hardening**: 14 evidence-backed orchestrator gaps found in training, plan in `bernese_orchestrator_r740_readiness.md`. Only BRN-001 (R740 install) open on infra |
| 1.4 | Public Data Portal and API | ⏳ | Q4 2026 | Depends on 1.3, 2.4. Strategic target: AusPos-equivalent for PH (300-station network, 27yr archive) — needs NAMRIA partnership for PRS92 datum |
| 3.1 | Centralized Documentation Portal | ⏳ | Q3 2026 | MkDocs + GitHub Pages; low-risk, can start any time |
| 3.2 | Automated Processing Documentation | ⏳ | Q4 2026 | Depends on 3.1 |

---

## Near-Term Work Items

> Full ticket list with priorities, sizes, and dependency graph: [`ticket_backlog.md`](ticket_backlog.md)

**DONE since last update (2026-04/05):** IGS-001, BRN-002, BRN-003, BRN-004, BRN-005, BRN-006,
ING-001/002/003 — see `bernese_workflow_status` memory + commits `bead683`→`c002a88`.

**Critical path (P0 — R740 orchestrator hardening; blocks unattended production):**
> Source: `bernese_orchestrator_r740_readiness.md` (14 gaps found in NAMRIA training week, 2026-06).
> The core orchestrator is built; these close the un-happy paths before R740.
1. **Per-session RINEX station validator** — target DATAPOOL not empty RAW; run per session (intermittent stations); flag blank DOMES / RINEX2-3 mismatch / short baselines (gaps #1, #11, #12). Prevents the PLG2 hard-abort + PTAG tropo overflow hit in training.
2. **Parameterize backends.run()** — PCF_FILE/campaign/CPU_FILE; size MAXPAR from station count (gaps #3, #10).
3. **prepare_campaign() adds GEN/ + SESSIONS.SES** (gap #2).
4. **Panel/script sanitizer** — `\`→`/`, strip dangling WAIT PIDs, reject hardcoded sessions (gaps #8, #14).
5. **BRN-001** — Install Bernese 5.4 on R740 (easier than T420; no PPA/ISA fights). Gated on MIS access + disk policy.

**Production deployment (P1 — before R740 go-live):**
6. **CODSPP-QC + tropo auto-recovery gates** (gaps #9, #11) — cheapest auto-fix in the pipeline.
7. **Final-solution clustering tuning** (gap #13) — the 502 GPSCLU_P single-cluster bottleneck; the R740 multi-core win is a CONFIG task, not free hardware.
8. **VAD-001** — TimescaleDB compression + retention (DL-012; drives fill without this).
9. **DA-001 (NEW)** — drive-archaeologist GNSS-classification validation on a REAL legacy GNSS drive (currently only mock/synthetic; scanner mechanics proven on a media drive only).
10. **VAD-002** — TCPAdapter NTRIP handshake for Leica GR50.

---

## Recently Completed

| Date | Item | Detail |
|------|------|--------|
| 2026-06-26 | NAMRIA Bernese training week — full PAGENET pipeline run headless | Ran Modules 1-14 unattended on live 71-station data via `pagenet_pcs.pl` (parameterized stock `startBPE` driver) + idempotent `run_pagenet_week.sh`. Module 13/14 HELMCHK passed (RMS 8.64mm, 6 fiducials, 0 rejected). Proved the orchestrator execution contract on real data; surfaced 14 R740 gaps |
| 2026-06-26 | R740 orchestrator readiness eval | `bernese_orchestrator_r740_readiness.md` — P0/P1/P2 hardening plan + go-live checklist; commit `cf1cf2a` |
| 2026-05-05 | BRN-002..006 + ING-001/002/003 + IGS-001 built | BPEBackend+LinuxBPEBackend, campaign_builder, rinex_header_validator (BRN-006), pcf_context, velocity hook (BRN-005); commits `bead683`→`c002a88` |
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
