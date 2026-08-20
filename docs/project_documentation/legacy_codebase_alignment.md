# Legacy Codebase Alignment Analysis

**Date:** 2026-02-03
**Scope:** Directory `/home/finch/repos/movefaults_clean/analysis/`

## Executive Summary
This document records the analysis of the legacy `analysis/` directory and maps its contents to the phased implementation plan outlined in the [Project Roadmap](./roadmap.md). The `analysis/` directory serves as the primary source of scientific algorithms and logic that must be ported to the new unified architecture. Use this guide when implementing **Tier 2** and **Tier 4** deliverables.

## 1. Mappings by Roadmap Tier

### **Tier 2: Data Acquisition & Ingestion**
*Foundational logic for raw data handling and quality control.*

| Legacy Directory | Roadmap Deliverable | Description & Action |
| :--- | :--- | :--- |
| **`10 RINEX Checker/`** | [Deliverable 2.5: RINEX QC Module](./roadmap.md#tier-2-data-acquisition--ingestion-parallel-development---build-on-tier-1) | Contains `RINEX2data_checker.py`. **Action:** Use as the prototype for the `gfzrnx` wrapper logic. |
| **`01 RINEX conversion/`** | [Deliverable 1.2: Ingestion Pipeline](./roadmap.md#tier-2-data-acquisition--ingestion-parallel-development---build-on-tier-1) | Contains `campaign_v6.py`, `leica2rinex.bat`. **Action:** Extract logic for converting raw receiver formats (e.g., Leica) to RINEX to support raw data ingestion. |

### **Tier 4: Analysis, Presentation & Automation**
*Scientific core logic to be refactored into the unified Python library.*

These directories map directly to **[Deliverable 2.4: Geodetic Post-Processing & Modeling Suite](./roadmap.md#tier-4-analysis-presentation--automation-build-on-tier-3)**.

| Legacy Directory | Domain Area | Description |
| :--- | :--- | :--- |
| **`02 Time Series/`** | Time Series Analysis | Core logic for analyzing station position changes over time. |
| **`03 Yu 2D Interseismic Dislocation/`** | Modeling | Specific 2D dislocation modeling algorithms (Yu model). |
| **`04 Displacement/`** | Displacement | Basic displacement calculation logic. |
| **`05 Single Frequency/`** | Processing | specialized/legacy single-frequency processing logic. |
| **`06 Ku-en Dislocation Model/`** | Modeling | Implementation of the Ku-en dislocation model. |
| **`08 Bootstrapping/`** | Statistics | Statistical validation and error estimation methods. |
| **`09 Kinematic/`** | Kinematic | Logic for processing kinematic (moving) GNSS data. |

### **Service Layer / Experimental**

| Legacy Directory | Related System | Description |
| :--- | :--- | :--- |
| **`07 Sample time series from NMEA/`** | `vadase-rt-monitor` | appears to contain sample input/output for real-time NMEA streams. **Action:** Use as test data/reference for the Real-Time Monitor service. |

## 2. Implementation Strategy

1.  **Extract & Adapt (Tier 2):** When building the Ingestion Pipeline and QC Module, audit the scripts in `01` and `10` first. Do not copy-paste; refactor into clean, testable Python 3 functions within the new `packages/` structure.
2.  **Refactor & Unify (Tier 4):** The bulk of the work lies in mapping `02`-`09` to the new `Geodetic Post-Processing & Modeling Suite`. This will require significant refactoring to create a cohesive API, moving away from loose scripts to a structured object-oriented or functional library.
