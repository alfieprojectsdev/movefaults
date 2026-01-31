# Project Roadmap: Phased Implementation Based on Dependency Hierarchies

**Date:** 2026-01-26

## 1. Introduction

This document outlines the proposed roadmap for the Philippine Open Geodesy Framework (POGF) monorepo project, structured around a phased implementation based on technical dependencies. This approach ensures that foundational components are in place before dependent systems are developed, minimizing rework and maximizing efficiency.

## 2. Domain Terminology: The Nuance of "Campaign"

A key term requiring clarification is "campaign," which has distinct meanings within the project domain. Understanding these distinctions is crucial for the architectural design:

*   **Campaign GPS (Observation Method):** Refers to the periodic, temporary deployment of portable GNSS receivers at specific monitoring points for a limited duration (e.g., hours to days). Primarily used for measuring **interseismic motion** (slow, long-term deformation).
*   **Continuous GPS (cGPS) (Observation Method):** Refers to permanently installed GNSS receivers collecting data continuously.
    *   *Proprietary Raw Data:* High-rate observations for precise post-processing (Bernese).
    *   *VADASE Real-Time Data:* NMEA streams for rapid velocity/displacement evaluation (handled by `vadase-rt-monitor`).
*   **Bernese Processing Campaign (Software Context):** A technical term specific to the Bernese GNSS Software. It defines a software execution run on a set of observation data (from either Campaign GPS or cGPS methods) over a defined time window.

**Goal:** The project automates the workflow for *both* observation methods, organizing them into efficient *Bernese processing campaigns*.

## 3. Overall Project Goal

The primary objective of this project is to establish the POGF by consolidating multiple disparate codebases and workflows into a single, unified, and maintainable monorepo. The end goal is a cohesive system for ingesting, processing, analyzing, and distributing geodetic data.

## 4. Final Project & Repository Structure

The project operates as a monorepo located at `/home/finch/repos/movefaults_clean/` (or its eventual `main` branch root). The structure is:
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

## 5. Phased Implementation Roadmap

The project deliverables are organized into four sequential tiers, representing a logical flow from foundational setup to advanced analysis and presentation.

---

### **Tier 1: Foundational Infrastructure (High Priority - Start First)**

This tier focuses on establishing the absolute core components that all other systems will rely upon. Development in this tier should be initiated first.

*   **Deliverable 1.1: Centralized Geodetic Database**
    *   **Description:** Design and implement a PostgreSQL database with PostGIS and TimescaleDB as the single source of truth for all geodetic data.
    *   **Dependencies:** None (foundational).
    *   *Documentation: `docs/project_documentation/pogf_infrastructure/tech_spec_database.md`, `docs/project_documentation/pogf_infrastructure/adr_database_choice.md`*

*   **Deliverable 3.1: Centralized Documentation Portal**
    *   **Description:** Implement a "Docs as Code" portal using MkDocs, GitHub Actions, and GitHub Pages. This will house all project documentation, including this roadmap.
    *   **Dependencies:** None (foundational for knowledge management).
    *   *Documentation: `docs/project_documentation/documentation_portal/tech_spec_docs_portal.md`, `docs/project_documentation/documentation_portal/adr_docs_portal_choice.md`*

---

### **Tier 2: Data Acquisition & Ingestion (Parallel Development - Build on Tier 1)**

Once the database foundation is laid, the next priority is to build robust pipelines to get data into it. Components within this tier can often be developed in parallel once Tier 1 is underway.

*   **Deliverable 2.5: RINEX Quality Control (QC) Module**
    *   **Description:** A Python wrapper around the `gfzrnx` binary to perform automated quality checks on RINEX files.
    *   **Dependencies:** Basic Python environment.
    *   **Feeds into:** Unified Data Ingestion Pipeline (1.2).
    *   *Documentation: `docs/project_documentation/gnss_automation_modules/tech_spec_rinex_qc.md`, `docs/project_documentation/gnss_automation_modules/adr_rinex_qc_choice.md`*

*   **Deliverable 2.2: Automated IGS Product Downloader**
    *   **Description:** A resilient Python CLI tool for automatically downloading IGS products (orbits, clocks, etc.).
    *   **Dependencies:** Basic Python environment.
    *   **Feeds into:** Automated Bernese Processing Workflow (1.3).
    *   *Documentation: `docs/project_documentation/gnss_automation_modules/tech_spec_igs_downloader.md`, `docs/project_documentation/gnss_automation_modules/adr_igs_downloader_choice.md`*

*   **Deliverable 1.2: Unified Data Ingestion Pipeline**
    *   **Description:** A scalable Python/Celery service to automatically retrieve, validate, and standardize RINEX data from various sources into the Centralized Geodetic Database.
    *   **Dependencies:** Centralized Geodetic Database (1.1), RINEX QC Module (2.5).
    *   *Documentation: `docs/project_documentation/pogf_infrastructure/tech_spec_ingestion_pipeline.md`, `docs/project_documentation/pogf_infrastructure/adr_ingestion_pipeline_choice.md`*

*   **Deliverable 2.1: Integration of `drive-archaeologist`**
    *   **Description:** Configure and potentially specialize the existing `drive-archaeologist` tool to scan USB drives for GNSS data and "site condition" files, feeding its structured metadata output into the Unified Data Ingestion Pipeline.
    *   **Dependencies:** Unified Data Ingestion Pipeline (1.2), Centralized Geodetic Database (1.1).
    *   *Documentation: `docs/project_documentation/gnss_automation_modules/ref_drive_archaeologist.md`*

*   **Deliverable 2.3: Digital Field Operations System**
    *   **Description:** A PWA (Progressive Web App) to replace paper-based field log sheets, providing offline data entry and synchronization.
    *   **Legacy Insight:** Will directly leverage the `LogSheetForm` component and logic discovered in the legacy `CORS-dashboard` project (`packages/CORS-dashboard/`).
    *   **Dependencies:** Centralized Geodetic Database (1.1 - for station metadata sync). Can largely be developed in parallel.
    *   **Informs:** Public Data Portal (1.4 - for log sheet viewing).
    *   *Documentation: `docs/project_documentation/gnss_automation_modules/tech_spec_digital_logsheet.md`, `docs/project_documentation/gnss_automation_modules/adr_digital_logsheet_choice.md`*

---

### **Tier 3: Core Data Processing (Build on Tier 2)**

This tier implements the primary scientific processing engine, relying on the robust data ingestion established in Tier 2.

*   **Deliverable 1.3: Automated Bernese Processing Workflow**
    *   **Description:** A Python/Celery orchestrator to automate the Bernese GNSS Software (BPE) execution, from input preparation to results loading.
    *   **Dependencies:** Centralized Geodetic Database (1.1), Unified Data Ingestion Pipeline (1.2), Automated IGS Product Downloader (2.2).
    *   **Feeds into:** Geodetic Post-Processing & Modeling Suite (2.4), Public Data Portal (1.4).
    *   *Documentation: `docs/project_documentation/pogf_infrastructure/tech_spec_bernese_workflow.md`, `docs/project_documentation/pogf_infrastructure/adr_bernese_workflow_choice.md`*

---

### **Tier 4: Analysis, Presentation & Automation (Build on Tier 3)**

This final tier focuses on consuming, analyzing, and presenting the processed data, and ensuring continuous documentation updates.

*   **Deliverable 2.4: Geodetic Post-Processing & Modeling Suite**
    *   **Description:** A unified Python library to port, wrap, and replace legacy MATLAB/C/Python scripts from the `analysis/` directory. Covers time series analysis, dislocation modeling, bootstrapping, and visualization for *non-real-time* data.
    *   **Dependencies:** Automated Bernese Processing Workflow (1.3 - for processed time series), Centralized Geodetic Database (1.1).
    *   **Feeds into:** Public Data Portal (1.4).
    *   *Documentation: `docs/project_documentation/gnss_automation_modules/tech_spec_timeseries_suite.md`, `docs/project_documentation/gnss_automation_modules/adr_timeseries_suite_choice.md`*

*   **Deliverable 1.4: Public Data Portal and API**
    *   **Description:** A React/FastAPI web application providing intuitive, open access to **processed, historical** geodetic data from the Centralized Geodetic Database, linking to `vadase-rt-monitor` for real-time views.
    *   **Legacy Insight:** Will adopt UI/UX patterns for mapping and data visualization from the legacy `CORS-dashboard` project.
    *   **Dependencies:** Centralized Geodetic Database (1.1), Automated Bernese Processing Workflow (1.3), Geodetic Post-Processing & Modeling Suite (2.4), `vadase-rt-monitor` (for cross-linking).
    *   *Documentation: `docs/project_documentation/pogf_infrastructure/tech_spec_portal_api.md`, `docs/project_documentation/pogf_infrastructure/adr_portal_api_choice.md`*

*   **Deliverable 3.2: Automated Processing Documentation**
    *   **Description:** Scripts to automatically generate reference documentation (CLI help, config references) from source code and configuration files, integrated into the documentation portal's build process.
    *   **Dependencies:** Centralized Documentation Portal (3.1), existence of tools to document (e.g., 2.2, 2.4, 2.5).
    *   *Documentation: `docs/project_documentation/documentation_portal/tech_spec_autodocs.md`, `docs/project_documentation/documentation_portal/adr_autodocs_choice.md`*

---

## 6. Key Considerations and Principles

*   **Iterative Development:** While dependencies suggest a sequence, internal modules within a tier can often be developed iteratively.
*   **Test-Driven Development:** Crucial for porting legacy scientific code and ensuring correctness.
*   **Open Source First:** Prioritize open-source tools and libraries to avoid vendor lock-in and foster collaboration.
*   **Documentation:** Continuous update of the Centralized Documentation Portal (3.1) is paramount throughout all phases.
*   **Legacy Insight:** Leverage the forensic analysis of `CORS-dashboard` and other legacy materials for UI/UX inspiration and technical patterns.

This roadmap provides a high-level plan for implementing the MOVE Faults monorepo project. Regular review and adaptation will be essential as development progresses.