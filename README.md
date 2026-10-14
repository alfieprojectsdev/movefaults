# Philippine Open Geodesy Framework (POGF) Monorepo

The Philippine Open Geodesy Framework (POGF) is a unified platform for the ingestion, processing, analysis, and distribution of geodetic data from the PHIVOLCS GNSS network. This monorepo consolidates disparate manual workflows into a cohesive, maintainable system.

## 🏗️ Project Structure

The project is organized as a monorepo containing shared packages, specialized services, and utility tools:

```text
movefaults_clean/
├── packages/
│   ├── pogf-geodetic-suite/     # Core logic: transforms, RINEX QC, IGS downloader
│   └── CORS-dashboard/          # Legacy React/GraphQL dashboard (reference only)
├── services/
│   ├── vadase-rt-monitor/       # Real-time NMEA displacement monitoring
│   ├── ingestion-pipeline/      # Automated RINEX ingestion (Celery-based)
│   ├── bernese-workflow/        # Bernese GNSS Software (BPE) orchestrator
│   └── field-ops/               # Digital field logsheet PWA (FastAPI + React)
├── tools/
│   ├── drive-archaeologist/     # CLI for excavating legacy GNSS data
│   └── velocity-reviewer/       # Web UI for interactive time series outlier review
├── scripts/                     # The production path today: staging, PCF derivation, BPE drivers, QC
├── analysis/                    # Legacy research scripts (being ported) + epb_discriminator research
├── config/bernese/              # Captured Bernese panels and PCFs, ocean-loading requests
└── docs/                        # Roadmap, runbooks, decision records; start with docs/SETTLED.md
```

### What actually runs in production

Bernese processing in production runs through **`scripts/`** (shell and Perl
drivers around BSW 5.4 on the gps3 server), not through `services/bernese-workflow`.
The service invokes BSW for real and is tested, but no production month has
run through it yet; moving production onto it is the current direction. Nothing
writes solutions into the database yet, and the ingestion pipeline is not in
the production loop. `CLAUDE.md` ("How components connect") has the detail.

## 🛠️ Technical Implementation Details

### 🗄️ Database Architecture
- **Engine:** PostgreSQL 16+ with **PostGIS** (geospatial) and **TimescaleDB** (time-series) extensions.
- **Schema Isolation:**
  - `public`: Core geodetic metadata (`stations`, `rinex_files`, `timeseries_data`).
  - `field_ops`: Logsheets, equipment inventory, and staff records.
- **Migrations:** Managed via **Alembic**, ensuring versioned schema evolution across all environments.

### 📥 Unified Ingestion Pipeline (`services/ingestion-pipeline`)
- **Stack:** Python, Celery, Redis.
- **Workflow:**
  1. **Standardization:** Handles multiple compression formats (`.gz`, `.zip`, `.Z`) and Hatanaka decompression (`.crx`, `.??d` → `.rnx`, `.??o`) using `crx2rnx`.
  2. **Validation:** Multi-stage check including a fast header scan (RINEX version detection) and deep quality control via `teqc`.
  3. **Metadata Extraction:** Parses fixed-width RINEX headers to extract station codes, sampling intervals, receiver/antenna types, and observation windows.
  4. **Persistence:** Idempotent loading into PostgreSQL with SHA-256-based deduplication.
- **Status:** about 30%; not in the production loop.

### 📡 VADASE Real-Time Monitor (`services/vadase-rt-monitor`)
- **Architecture:** Hexagonal (Ports & Adapters) for high testability and source/output flexibility.
- **Core Logic:**
  - Consumes NMEA 0183 streams (via TCP or File).
  - Parsers for `$GNLVM` (Velocity) and `$GNLDM` (Displacement) sentences.
  - **Receiver mode:** A `ReceiverMode` state machine decides, in both directions, whether to trust the receiver's own displacement or integrate velocity itself, because quiet-time receivers echo velocity in the displacement field.
  - **Leaky integrator:** `disp = disp * decay_factor + vel * dt`, a high-pass filter against drift. `decay_factor` defaults to 1.0 (no leak), so the leak is opt-in per station.
  - **Event Detection:** Real-time thresholding on horizontal velocity magnitude (mm/s) to trigger seismic event alerts.

### 🗺️ Digital Field Operations (`services/field-ops`)
- **Stack:** FastAPI (Backend), React/Vite (Frontend PWA).
- **Offline-First:** Uses **IndexedDB** for local storage and **Service Workers** for background synchronization.
- **Idempotency:** Client-side UUID generation (`client_uuid`) ensures that logsheet submissions are idempotent even during flaky network conditions.
- **Equipment Tracking:** equipment records keyed by QR code, with a lookup API. The PWA has no QR scanner yet.
- **Deploy safety:** `/health` answers 503 when the database schema is behind the deployed migrations, so the host refuses the deploy instead of serving errors.

### 📈 Bernese Workflow Orchestrator (`services/bernese-workflow`)
- **Target:** Bernese GNSS Software v5.4 (Linux/Windows).
- **Orchestration:** Python wrapper for the **Bernese Processing Engine (BPE)**.
- **Templating:** Uses **Jinja2** to dynamically generate `.INP` (Input) and `.PCF` (Process Control) files based on PHIVOLCS-specific processing strategies.
- **Automation:** Interfaces with `startBPE.pm` for non-interactive execution of multi-step processing campaigns; `month_driver.run_days` runs a range of days with day-level resume.
- **Status:** about 60%. Not yet the path production runs take (see above).

### 🔍 Velocity Reviewer (`tools/velocity-reviewer`)
- **Stack:** FastAPI, Uvicorn, Plotly.
- **Logic:** Browser-based replacement for legacy Matplotlib GUIs. Features interactive ENU (East-North-Up) time series plots with:
  - **Automated Outlier Detection:** Based on Interquartile Range (IQR).
  - **Point-and-Click Selection:** Human-in-the-loop outlier marking.
  - **PLOT File Stripping:** Direct export of cleaned data files for subsequent velocity estimation.

## 🚀 Getting Started

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (highly recommended for dependency management)
- Docker and Docker Compose (for database and services)

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/alfieprojectsdev/movefaults.git
   cd movefaults
   ```

2. **Sync dependencies:**
   ```bash
   uv sync --all-extras     # every service's dependencies; plain `uv sync` is not enough to run all tests
   ```

3. **Environment Setup:**
   Copy the example environment files and adjust as necessary:
   ```bash
   cp tiger-cloud-pogf-db-credentials.env.example .env
   ```

4. **Start Infrastructure:**
   ```bash
   docker compose up -d     # TimescaleDB on 5433, Redis on 6380
   ```

5. **Run the tests:**
   ```bash
   uv run pytest                                   # eight Python suites
   cd services/field-ops/frontend && npm test      # field-ops frontend (vitest), not collected by pytest
   ```

## 🗺️ Roadmap

The project is currently in a phased implementation:

*   **Tier 1 (Foundational):** Geodetic Database ✅ (nothing writes solutions into it yet); Documentation Portal ⏳ (not started).
*   **Tier 2 (Ingestion):** Field Ops ✅ (deployed); RINEX QC ✅ in practice (teqc first, gfzrnx fallback); IGS Downloader 🔄; Ingestion Pipeline 🔄 (about 30%); drive-archaeologist 🔄 (about 60%).
*   **Tier 3 (Processing):** Bernese Workflow 🔄 (the service is built and tested; production still runs through `scripts/`).
*   **Tier 4 (Analysis):** Post-Processing Suite 🔄 (velocities verified against PHIVOLCS' MATLAB output; bootstrapping not ported); Public Data Portal and auto-docs ⏳ (not started).

For a detailed breakdown, see [roadmap.md](./docs/project_documentation/roadmap.md).

## 📄 License

MIT — see [`LICENSE`](LICENSE).

**Copyright is held by PHIVOLCS/DOST**, not by an individual: this work was
produced on institute hardware, in the course of employment, in service of
PHIVOLCS research mandates.

The licence covers the *software and documentation* in this repository. It does
**not** cover GNSS observation data (the file server is the system of record,
release is governed by agency policy, and PAGENET is NAMRIA's under a separate
MOU), nor the third-party tools this code invokes — Bernese, teqc, gfzrnx and
RNXCMP each carry their own terms. [`NOTICE`](NOTICE) states the full scope.

## ✍️ Citing this work

See [`CITATION.cff`](CITATION.cff), or use GitHub's **Cite this repository**
button. Authorship and copyright are separate: the copyright holder is
PHIVOLCS/DOST, the author credited for citation is below.

## ✍️ Authors

- **Alfie Pelicano** — *Lead Developer*, PHIVOLCS-DOST — [alfieprojects.dev@gmail.com](mailto:alfieprojects.dev@gmail.com)
