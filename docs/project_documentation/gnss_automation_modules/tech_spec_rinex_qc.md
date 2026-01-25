# Technical Specification: RINEX Quality Control (QC) Module

**Version:** 1.0

**Date:** 2026-01-25

## 1. Introduction

### 1.1. Purpose

This document outlines the technical specifications for the RINEX Quality Control (QC) Module. The purpose of this module is to provide a standardized, automated way to assess the quality of raw RINEX files before they are archived and processed.

### 1.2. Scope

This specification covers the module's architecture as a Python wrapper around an external tool. It details the required QC metrics, the types of reports it will generate, and its integration into the broader POGF ecosystem.

## 2. System Architecture

The architecture of this module is that of a **wrapper**. Instead of re-implementing complex QC algorithms from scratch, the module will leverage a powerful, existing open-source tool. The module will provide a clean Python API that hides the complexity of calling this external tool.

- **Core Engine:** The `gfzrnx` command-line tool, developed by GFZ, will be used as the core engine for all RINEX file parsing and metric calculation.
- **Python Wrapper:** A Python library will be developed that:
  - Provides a simple, high-level API (e.g., `qc_module.run_qc(file_path)`).
  - Constructs the appropriate `gfzrnx` command-line arguments.
  - Executes `gfzrnx` as a subprocess.
  - Parses the output (JSON, text) into Python objects (dictionaries, dataclasses).
- **CLI:** The wrapper library will also include a simple command-line interface for manual or scripted use.

## 3. Core Features

### 3.1. Data Input

The module will accept paths to RINEX files in version 2, 3, and 4 formats, as supported by `gfzrnx`.

### 3.2. QC Metrics

The module will expose the key QC metrics provided by `gfzrnx`, including:
- **Completeness:** Percentage of expected observations present.
- **Data Gaps:** Number and duration of gaps in the data.
- **Cycle Slips:** Number of detected cycle slips (`L1`, `L2`, etc.).
- **Multipath:** Multipath estimates for code observations (`MP1`, `MP2`, etc.).
- **Signal-to-Noise Ratio (SNR):** SNR values for key signals.
- **Skyplot:** Azimuth and elevation of observed satellites.

### 3.3. Report Generation

The `run_qc()` function will be able to produce several types of output for a given RINEX file:

1.  **JSON Report:** A machine-readable `.json` file containing all calculated metrics in a structured format. This is the primary output for integration with other services.
2.  **Graphical Report (PNG):** A multi-panel plot showing key metrics visually. This will include skyplots, SNR over time, and multipath over time.
3.  **Text Summary:** A human-readable `.txt` summary of the most important QC findings.

### 3.4. Integration

- **Ingestion Pipeline:** This is the primary intended use case. The Unified Data Ingestion Pipeline will call this QC module after a new RINEX file is downloaded and validated. If the QC report indicates poor quality (based on configurable thresholds), the file can be flagged in the database or moved to a quarantine area.
- **Manual Use:** Analysts can use the provided CLI to quickly assess the quality of any RINEX file.

## 4. Technology Stack

- **Language:** Python 3.11+
- **Core Engine:** `gfzrnx` (external binary dependency).
  - **Justification:** A feature-rich, high-performance, and actively maintained open-source tool from a reputable source (GFZ). Re-implementing its capabilities would be an enormous and redundant effort.
- **Wrapper Implementation:** Python's built-in `subprocess` module.
  - **Justification:** Sufficient for executing the external command and capturing its output.
- **Plotting:** Matplotlib.
  - **Justification:** To generate the graphical PDF reports from the data provided by `gfzrnx`.
- **CLI Framework:** `click`.

## 5. Command-Line Interface

- **`rinex-qc --file <path/to/rinex.rnx> --output-dir <path>`**
  - Runs a full QC analysis and generates all three report types (JSON, PNG, TXT) in the specified output directory.

- **`rinex-qc --file <path> --json-only`**
  - A streamlined mode that only produces the machine-readable JSON output. This is ideal for use within scripts or other automated workflows where only the raw data is needed.

## 6. Deployment Note

Any environment that uses this module (e.g., the Docker container for the Ingestion Pipeline workers) **must** have the `gfzrnx` binary installed and available in its `PATH`. The installation of this dependency must be part of the deployment and provisioning scripts.
