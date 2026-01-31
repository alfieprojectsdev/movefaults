# Gemini Session Handover: MOVE Faults Monorepo Project

**Date:** 2026-01-26

## 1. Overall Project Goal

The primary objective of this project is to establish the **Philippine Open Geodesy Framework (POGF)**. This involves consolidating multiple disparate codebases and workflows into a single, unified, and maintainable **monorepo**. The end goal is a cohesive system for ingesting, processing, analyzing, and distributing geodetic data.

## 2. Final Project & Repository Structure

After analysis and migration, the project is now a monorepo located at `/home/finch/repos/movefaults_clean/`.

The agreed-upon structure is:
```
/movefaults_clean/
├── docs/                # Unified documentation portal source
├── packages/            # For shared Python libraries (e.g., geodetic suite)
│   └── CORS-dashboard/  # Legacy project (forensically analyzed)
├── services/            # For deployable, long-running services
│   └── vadase-rt-monitor/
└── tools/               # For command-line developer/operator tools
    └── drive-archaeologist/
```

- **Git History:** The Git history was completely reset to fix an issue where large data files were accidentally committed, making the repository size unmanageable. A new, comprehensive `.gitignore` is in place to prevent this from recurring.

## 3. Summary of Architectural Decisions & Deliverables

The following deliverables and architectural decisions were established. The full technical specifications and ADRs can be found in the `docs/project_documentation/` directory.

### POGF Infrastructure (Deliverable Group 1)
- **Centralized Database:** Use **PostgreSQL** with **PostGIS** (for spatial data) and **TimescaleDB** (for time-series data).
- **Data Ingestion Pipeline:** A Python service using **Celery** for asynchronous task management to pull data from various sources into the database.
- **Automated Bernese Workflow:** A Python/Celery orchestrator that wraps the command-line **Bernese Processing Engine (BPE)**, using Jinja2 templates to generate configuration files.
- **Public Data Portal:** A decoupled web application using a **React** frontend and a **Python/FastAPI** backend. This portal is for serving **processed, historical data** and will link out to other systems for real-time views.

### GNSS Automation Modules (Deliverable Group 2)
- **USB/Drive Ingestion:** Use the existing **`drive-archaeologist`** project. The plan includes specializing it with custom "profiles" to identify and classify "site condition" files (e.g., photos, scanned logs) from legacy drives.
- **Real-Time Monitoring:** All real-time monitoring, especially of NMEA/VADASE data streams, is handled by the existing **`vadase-rt-monitor`** project. The two projects will link to each other but have separate scopes.
- **IGS Product Downloader:** A standalone Python CLI tool for resiliently downloading IGS products.
- **Digital Field Operations System:** A **Progressive Web App (PWA)** with offline capabilities to replace paper log sheets.
- **Post-Processing & Modeling Suite:** A unified Python library to consolidate, port, and replace the numerous scripts in the original `analysis/` directory. This suite will handle time series analysis, dislocation modeling, bootstrapping, and data conversion.
- **RINEX QC Module:** A Python wrapper around the powerful open-source `gfzrnx` binary.

### Documentation (Deliverable Group 3)
- **Documentation Portal:** A static site built with **MkDocs** and the **Material for MkDocs** theme, following a "Docs as Code" philosophy.
- **Automated Documentation:** A set of Python scripts to automatically generate reference material (e.g., CLI help text, configuration glossaries) during the documentation build process.

## 4. Glossary Refinement: The Nuance of "Campaign"

A key term requiring clarification is "campaign," which has distinct meanings within the project domain:

-   **Campaign GPS (Observation Method):** This refers to the periodic, temporary deployment of portable GNSS receivers at specific monitoring points for a limited duration (e.g., hours to days). This method is primarily used for measuring **interseismic motion** – the slow, long-term deformation occurring between earthquakes.

-   **Continuous GPS (cGPS) (Observation Method):** This refers to permanently installed GNSS receivers that collect data continuously. Within cGPS, there's a critical distinction:
    -   **Proprietary Raw Data (e.g., Trimble, Leica formats):** High-rate, raw observations intended for precise, post-processing via conversion to RINEX and subsequent Bernese processing.
    -   **VADASE Real-Time Monitoring Data (NMEA formats):** Data (since ~2019, selected Leica models) primarily for rapid evaluation and display, providing near-real-time velocity/displacement. This is distinct from raw data for precise Bernese processing and is handled by `vadase-rt-monitor`.

-   **Bernese Processing Campaign (Software Context):** This is a technical term specific to the Bernese GNSS Software. It defines a software execution run on a specific set of observation data (which could originate from either Campaign GPS or Continuous GPS observation methods) over a defined time window, using a particular processing strategy.

The project's goal is to automate the entire workflow, supporting data from both Campaign GPS and cGPS observation methods, and organizing these into Bernese processing campaigns.

## 5. Legacy Project Insights

### CORS-Dashboard (Legacy Project at `packages/CORS-dashboard/`)
-   **Historical Context:** This project predates the establishment of VADASE sites. It was primarily designed to display data from traditional cGPS stations, which produce proprietary raw data needing RINEX conversion for precise processing.
-   **Overview:** A discontinued React (v15.x) / Material-UI web application using Express.js as a backend, and GraphQL for data fetching. It featured extensive mapping (`Leaflet`, `Mapbox GL`) and data visualization (`D3`).
-   **Key Discovery:** The project contained a detailed **`LogSheetForm`** component, providing concrete UI/UX patterns and data entry fields for a digital logsheet.
-   **Relevance to Current Deliverables:**
    -   **Public Data Portal (1.4):** Provides direct UI/UX inspiration for maps, data visualization, and overall dashboard layout. Its use of GraphQL is a valuable pattern for potential API evolution.
    -   **Digital Field Operations System (2.3):** The `LogSheetForm` component is a significant precursor, offering actionable insights for designing the field data entry forms and workflow.
-   **Action:** This project serves as a rich source of design patterns and feature ideas. Its specific `LogSheetForm` component is particularly relevant for the `Digital Field Operations System`.
    *Full details: `docs/project_documentation/legacy_review/CORS-dashboard_review.md`*

## 5. Current Status & Next Steps

1.  **Migration Complete:** The `drive-archaeologist` and `vadase-rt-monitor` projects have been successfully moved into the `movefaults_clean` monorepo.
2.  **Configuration Unified:** A single, root-level `pyproject.toml` has been created to manage dependencies for the entire workspace.
3.  **Repository Cleaned:** The Git history has been reset, and a robust `.gitignore` is in place to ensure the repository has a manageable size.

**Your immediate next action is to publish the repository to GitHub.**

-   **Action:** `cd /home/finch/repos/movefaults_clean` and run the `git remote add ...` and `git push ...` commands as previously instructed.

**After that, you can:**
-   Safely delete the old `/home/finch/repos/movefaults` directory.
-   Exit this session.
-   Start a new Gemini CLI session from `/home/finch/repos/movefaults_clean` and provide this document as context.