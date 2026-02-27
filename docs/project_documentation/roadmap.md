# Project Roadmap: Phased Implementation Based on Dependency Hierarchies

**Last updated:** 2026-02-27
**Original date:** 2026-01-26

> For per-deliverable status and projected dates, see [`deliverables_tracker.md`](deliverables_tracker.md).

---

## 1. Introduction

This document outlines the roadmap for the Philippine Open Geodesy Framework (POGF) monorepo,
structured around a phased implementation based on technical dependencies. Foundational components
are built before dependent systems to minimise rework.

---

## 2. Domain Terminology: The Nuance of "Campaign"

A key term requiring clarification is "campaign," which has distinct meanings within the project:

- **Campaign GPS (Observation Method):** Periodic, temporary GNSS deployments for measuring
  slow interseismic motion (hours to days in the field).
- **Continuous GPS (cGPS) (Observation Method):** Permanently installed GNSS receivers.
  - *Proprietary raw data:* High-rate observations for Bernese post-processing.
  - *VADASE real-time data:* NMEA streams for rapid displacement detection (`vadase-rt-monitor`).
- **Bernese Processing Campaign (Software Context):** A Bernese GNSS Software execution run
  on a defined set of observation data over a time window. Distinct from field "campaign GPS."

**Goal:** Automate the workflow for *both* observation methods, organising them into efficient
Bernese processing campaigns.

---

## 3. Overall Project Goal

Establish the POGF by consolidating disparate codebases and manual workflows into a single,
unified, maintainable monorepo — a cohesive system for ingesting, processing, analysing, and
distributing geodetic data from PHIVOLCS' GNSS network.

---

## 4. Current Repository Structure

```
movefaults_clean/
├── packages/
│   ├── pogf-geodetic-suite/     # Shared: coordinate transforms, RINEX QC, IGS downloader
│   └── CORS-dashboard/          # Legacy React/GraphQL dashboard (forensic reference only)
├── services/
│   ├── vadase-rt-monitor/       # Real-time NMEA earthquake detection (~80% complete)
│   ├── ingestion-pipeline/      # Celery-based RINEX ingestion (~30% complete)
│   ├── bernese-workflow/        # Bernese BPE orchestrator (~15% complete)
│   └── field-ops/               # Digital field logsheet PWA (Phase 1A — complete)
├── tools/
│   ├── drive-archaeologist/     # CLI: excavate legacy GNSS data from old drives (~60%)
│   └── velocity-reviewer/       # Web UI: interactive GNSS time series outlier review (new)
├── src/ingestion/               # Simplified local ingestion module (consolidation pending)
├── analysis/                    # Numbered research scripts 01–10 (legacy, not yet ported)
└── docs/
    ├── project_documentation/   # Roadmap, tracker, tech specs, ADRs
    └── bernese_orchestration_explainer.md
```

---

## 5. Phased Implementation Roadmap

### Legend
- ✅ **COMPLETE** — implemented, tested, committed
- 🔄 **IN PROGRESS** — partially implemented
- ⏳ **PENDING** — not yet started; blocked on earlier deliverable
- 🔬 **RESEARCH** — design/investigation work done; implementation not started

---

### Tier 1: Foundational Infrastructure

> Foundational components all other systems depend on.

**Deliverable 1.1: Centralized Geodetic Database** ✅ **COMPLETE**
- PostgreSQL + TimescaleDB + PostGIS via docker-compose
- Alembic migrations 001–006; 4 CORS stations seeded
- Schema: `stations`, `timeseries_data`, `velocity_products`, `ingestion_logs`
- Committed: `bafa06b` (branch `feat/phase0-database-foundation`)
- *Spec: `docs/project_documentation/pogf_infrastructure/tech_spec_database.md`*

**Deliverable 3.1: Centralized Documentation Portal** ⏳ **PENDING**
- MkDocs + GitHub Actions + GitHub Pages
- *Spec: `docs/project_documentation/documentation_portal/tech_spec_docs_portal.md`*

---

### Tier 2: Data Acquisition & Ingestion

> Build on Tier 1. Components can be developed in parallel once 1.1 is complete.

**Deliverable 2.3: Digital Field Operations System** ✅ **COMPLETE**
- FastAPI backend + React/Vite PWA; offline-first with IndexedDB queue + Service Worker sync
- Own `field_ops` schema namespace; station picker syncs from central `stations` table
- Location: `services/field-ops/`
- *Spec: `docs/project_documentation/gnss_automation_modules/tech_spec_digital_logsheet.md`*

**Deliverable 2.5: RINEX Quality Control Module** 🔄 **IN PROGRESS**
- `teqc` as primary QC backend (gfzrnx not yet acquired)
- Wrapper exists in `packages/pogf-geodetic-suite/`; Trimble conversion step documented
- Trimble NetR9 filename pattern identified; `drive-archaeologist` profiles need updating
- *Spec: `docs/project_documentation/gnss_automation_modules/tech_spec_rinex_qc.md`*

**Deliverable 2.2: Automated IGS Product Downloader** 🔄 **IN PROGRESS**
- Partial implementation in `packages/pogf-geodetic-suite/`
- Needs: correct IGS20 naming, CDDIS/IGN/BKG fallback chain
- *Spec: `docs/project_documentation/gnss_automation_modules/tech_spec_igs_downloader.md`*

**Deliverable 1.2: Unified Data Ingestion Pipeline** 🔄 **IN PROGRESS (~30%)**
- Architecture defined; Celery tasks are stubs
- Phase 1B-i: consolidation of `src/ingestion/` → `services/ingestion-pipeline/` complete (PR #32)
- Pending: teqc integration, Trimble→RINEX conversion step, scanner→pipeline handoff
- *Spec: `docs/project_documentation/pogf_infrastructure/tech_spec_ingestion_pipeline.md`*

**Deliverable 2.1: drive-archaeologist Integration** 🔄 **IN PROGRESS (~60%)**
- Phase 1 scanner works; archive support partial
- Pending: Trimble raw file classification (`.T01`, `.T02`, `.T04`, `.DAT`, `.TGD`),
  ingestion-pipeline handoff
- Location: `tools/drive-archaeologist/`
- *Ref: `docs/project_documentation/gnss_automation_modules/ref_drive_archaeologist.md`*

---

### Tier 3: Core Data Processing

> Primary scientific processing engine. Depends on robust data ingestion from Tier 2.

**Deliverable 1.3: Automated Bernese Processing Workflow** 🔬 **RESEARCH COMPLETE — IMPLEMENTATION STARTING**

Research milestones completed (2026-02-26/27):
- Bernese 5.4 **installed and verified** on T420 — EXAMPLE campaign BPE ran 47 steps, solutions
  match reference at ≤0.09 mm
- Non-interactive BPE API confirmed: `startBPE.pm` Perl module (`$BPE/startBPE.pm`)
- Full BPE phase map documented (47 steps, quality gates, output files)
- PHIVOLCS-specific INP settings extracted from work instruction via RAG (GPSEST ×3,
  HELMR1, MAUPRP, ADDNEQ2, CODSPP)
- Post-BPE velocity pipeline fully mapped (`filter-fncrd.bat` → `plot_v2.py` →
  `vel_line_v8.m` → outlier review → final velocity)
- Bernese orchestration explainer written for data processing staff
- **velocity-reviewer tool** built: web-based replacement for the Windows-only
  `outlier_input-site.py` GUI (location: `tools/velocity-reviewer/`)
- Pending: INP files from data processing staff → Jinja2 templates → `LinuxBPEBackend`
- Pending: R740 Bernese installation (same procedure as T420, no ISA mismatch)
- Pending: `offset_events` DB table (Migration 007)
- Pending: `plot_v2.py` parameterisation (interactive reference station prompt → CLI arg)

Architecture decisions:
- `BPEBackend` protocol: `LinuxBPEBackend` (R740) + `WindowsBPEBackend` (future)
- Two pipeline variants: Campaign GPS (single-pass BPE) vs. Continuous GPS (two-pass BPE)
- Pre-download IGS products via our downloader (skip/bypass BPE step 000 FTP_DWLD)
- Human-in-the-loop gate at outlier review; all other steps automated

- *Spec: `docs/project_documentation/pogf_infrastructure/tech_spec_bernese_workflow.md`*

---

### Tier 4: Analysis, Presentation & Automation

> Consume, analyse, and present processed data.

**Deliverable 2.4: Geodetic Post-Processing & Modeling Suite** ⏳ **PENDING**
- Port legacy MATLAB/Python scripts from `analysis/` into `packages/pogf-geodetic-suite/`
- Covers: time series analysis, dislocation modeling, bootstrapping, visualization
- velocity-reviewer (`tools/velocity-reviewer/`) is the first component in this space
- *Spec: `docs/project_documentation/gnss_automation_modules/tech_spec_timeseries_suite.md`*

**Deliverable 1.4: Public Data Portal and API** ⏳ **PENDING**
- React/FastAPI web application; open access to processed historical geodetic data
- Cross-links to `vadase-rt-monitor` for real-time views
- *Spec: `docs/project_documentation/pogf_infrastructure/tech_spec_portal_api.md`*

**Deliverable 3.2: Automated Processing Documentation** ⏳ **PENDING**
- Auto-generate CLI help, config references from source; integrate into MkDocs build
- *Spec: `docs/project_documentation/documentation_portal/tech_spec_autodocs.md`*

---

## 6. VADASE Real-Time Monitor

`services/vadase-rt-monitor/` (~80% complete) is developed on a parallel track independent
of the Bernese pipeline. Key remaining work:

- Fix one-way latch bug in `domain/processor.py:130` (`manual_integration_active` never resets)
- `TCPAdapter`: implement NTRIP client handshake for Leica GR50
- Add Trimble sentence parser stubs (currently dead code — GR50 is Leica, not Trimble)
- PR #1 remediation (paused, lower priority than Phase 1B)

---

## 7. Key Principles

- **Iterative development:** Modules within a tier can be developed in parallel once their dependencies are met.
- **Test-driven:** Critical for porting legacy scientific code — correctness must be verified.
- **Open source first:** Avoid vendor lock-in; foster future collaboration.
- **Human-in-the-loop:** Orchestration automates mechanics; scientific judgment stays with staff.
- **Documentation-as-code:** Every architectural decision recorded in ADRs; every session logged.
