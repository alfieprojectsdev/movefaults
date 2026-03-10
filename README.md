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
├── analysis/                    # Legacy research scripts (to be ported)
└── docs/                        # Project roadmap, tech specs, and ADRs
```

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
  4. **Persistence:** Idempotent loading into PostgreSQL with MD5-based deduplication.

### 📡 VADASE Real-Time Monitor (`services/vadase-rt-monitor`)
- **Architecture:** Hexagonal (Ports & Adapters) for high testability and source/output flexibility.
- **Core Logic:**
  - Consumes NMEA 0183 streams (via TCP or File).
  - Parsers for `$GNLVM` (Velocity) and `$GNLDM` (Displacement) sentences.
  - **Smart Integration:** A "Leaky Integrator" (High-pass filter) that compensates for "Velocity-as-Displacement" artifacts found in some receiver firmwares.
  - **Event Detection:** Real-time thresholding on horizontal velocity magnitude (mm/s) to trigger seismic event alerts.

### 🗺️ Digital Field Operations (`services/field-ops`)
- **Stack:** FastAPI (Backend), React/Vite (Frontend PWA).
- **Offline-First:** Uses **IndexedDB** for local storage and **Service Workers** for background synchronization.
- **Idempotency:** Client-side UUID generation (`client_uuid`) ensures that logsheet submissions are idempotent even during flaky network conditions.
- **Equipment Tracking:** QR-code based inventory system to link physical hardware to geodetic site visits.

### 📈 Bernese Workflow Orchestrator (`services/bernese-workflow`)
- **Target:** Bernese GNSS Software v5.4 (Linux/Windows).
- **Orchestration:** Python wrapper for the **Bernese Processing Engine (BPE)**.
- **Templating:** Uses **Jinja2** to dynamically generate `.INP` (Input) and `.PCF` (Process Control) files based on PHIVOLCS-specific processing strategies.
- **Automation:** Interfaces with `startBPE.pm` for non-interactive execution of multi-step processing campaigns.

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
   git clone https://github.com/alfiepelicano/move-faults-monorepo.git
   cd move-faults-monorepo
   ```

2. **Sync dependencies:**
   Using `uv` (fastest):
   ```bash
   uv sync
   ```

3. **Environment Setup:**
   Copy the example environment files and adjust as necessary:
   ```bash
   cp tiger-cloud-pogf-db-credentials.env.example .env
   ```

4. **Start Infrastructure:**
   ```bash
   docker-compose up -d
   ```

## 🗺️ Roadmap

The project is currently in a phased implementation:

*   **Tier 1 (Foundational):** Geodetic Database and Documentation Portal. ✅
*   **Tier 2 (Ingestion):** Field Ops, RINEX QC, and IGS Downloader. 🔄
*   **Tier 3 (Processing):** Automated Bernese Workflow. 🔄 (Research Complete)
*   **Tier 4 (Analysis):** Post-Processing Suite and Public Data Portal. 🔄

For a detailed breakdown, see [roadmap.md](./docs/project_documentation/roadmap.md).

## 📄 License

This project is licensed under the MIT License - see the `LICENSE` file for details (or `pyproject.toml`).

## ✍️ Authors

- **Alfie Pelicano** - *Lead Developer* - [alfieprojects.dev@gmail.com](mailto:alfieprojects.dev@gmail.com)
