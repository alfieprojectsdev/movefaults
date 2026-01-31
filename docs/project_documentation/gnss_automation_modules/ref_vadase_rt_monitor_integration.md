# Reference: VADASE Real-Time Monitor (Integration Points)

**Deliverable originally related to:** Aspects of Time Series Analysis & Visualization.

**Addressed by:** Existing project `/home/finch/repos/movefaults/docs/vadase-rt-monitor/`

## Purpose

The `vadase-rt-monitor` project provides a dedicated, open-source real-time GNSS displacement monitoring system. This system specifically addresses the ingestion and processing of **NMEA-based VADASE data streams for rapid evaluation and display** of real-time velocity and displacement monitoring, earthquake detection, and visualization. This type of data is distinct from the proprietary raw GNSS data intended for precise Bernese post-processing.

The presence of MATLAB scripts like `vel_line_v6_ldm.m` and `vel_line_v6_lvm.m` in `analysis/07 Sample time series from NMEA/` confirms that real-time or near real-time VADASE data analysis has been a part of past workflows. The `vadase-rt-monitor` project consolidates and modernizes this specific real-time domain.

## VADASE Real-Time Monitor Overview

The `vadase-rt-monitor` project (located at `/home/finch/repos/movefaults/docs/vadase-rt-monitor/`) is designed for:

-   Ingesting **NMEA-based LDM (Displacement) and LVM (Velocity) data streams**, primarily for rapid evaluation and display.
-   Real-time velocity and displacement monitoring.
-   Automatic earthquake detection based on configurable thresholds.
-   Time-series visualization via Grafana dashboards.
-   Event cataloging and alerting.

### Key Components

-   **Parser:** Handles full LDM/LVM NMEA sentence parsing.
-   **Stream Handler:** Manages asynchronous TCP connections for concurrent stations.
-   **Database:** Uses TimescaleDB for optimized time-series storage.
-   **Detection:** Implements configurable threshold-based event detection.
-   **Visualization:** Grafana dashboards for real-time data display.

## Integration and Delineation

To avoid duplication of effort and ensure a clear separation of concerns, the MOVE Faults project will leverage `vadase-rt-monitor` for all real-time VADASE processing and monitoring.

-   **Geodetic Post-Processing & Modeling Suite (Deliverable 2.4):** This suite will explicitly *exclude* the processing and analysis of real-time or near real-time VADASE NMEA streams. Its focus will remain on post-processed, daily or high-rate data products (e.g., from Bernese solutions) for long-term time series analysis, deformation modeling, and historical data visualization.
-   **Public Data Portal and API (Deliverable 1.4):** This portal will provide access to processed, historical geodetic data. It will **not** provide its own real-time data visualizations but will offer direct links to the relevant `vadase-rt-monitor` Grafana dashboards for users seeking live information.
-   **Data Flow:** The `vadase-rt-monitor` project will manage its own data ingestion and database (likely its TimescaleDB instance) for real-time data. Data outputs from `vadase-rt-monitor` that are deemed "finalized" (e.g., confirmed event detections, daily averages that could be part of a historical archive) may be integrated into the Centralized Geodetic Database (Deliverable 1.1) in the future, if deemed necessary. This integration point will require a separate, future specification.
