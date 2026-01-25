# Technical Specification: Geodetic Post-Processing & Modeling Suite

**Version:** 2.0 (Revised)

**Date:** 2026-01-25

## 1. Introduction

### 1.1. Purpose

This document provides the technical specifications for the **Geodetic Post-Processing & Modeling Suite**. This project aims to create a comprehensive, open-source Python-based library and set of tools to unify and replace the various MATLAB, Python, and C scripts currently used for **post-processed, non-real-time** geodetic research. This includes scripts for RINEX conversion, time series analysis, deformation modeling, and bootstrapping, as found in the `/analysis/` directory. **Real-time VADASE processing and monitoring are handled by the separate `vadase-rt-monitor` project.**

### 1.2. Scope

This specification covers the suite's architecture as a unified Python library and a set of command-line tools. It details the required modules for data preparation, analysis, modeling, and visualization, with the goal of porting and integrating the logic from existing scripts (e.g., `vel_line*.m`, `geodetic2enu*.py`, `bootstrap*.py`, `disloc.c`). **It explicitly excludes real-time or near real-time NMEA/VADASE stream processing, which falls under the purview of `vadase-rt-monitor`.**

## 2. System Architecture

The suite is architected as a modular, multi-purpose package:

1.  **A Unified Python Library:** A set of sub-packages with a clear API encapsulating all core post-processing functions. This library will be the primary deliverable, providing a stable, testable, and reusable foundation.
2.  **Command-Line Tools:** A set of scripts that use the library to provide easy access to common workflows, directly replacing the functionality of the current standalone scripts.

## 3. Core Modules & Features

### 3.1. Module: Data Conversion & Preparation

- **Goal:** Replace scripts in `analysis/01`, `analysis/04`, and `analysis/10`.
- **Functionality:**
    - **RINEX Conversion Wrapper:** Provide a Python interface to external binaries like `teqc` and `runpkr00` (as seen in `campaign_v6.py`), handling file I/O and configuration.
    - **Coordinate System Conversion:** Implement functions for `geodetic2enu` transformations, porting the logic from `geodetic2enu_v2.py` and its dependencies (`pymap3d`, `pygeodesy`).
    - **RINEX Data Checking:** Port the logic from `RINEX2data_checker.py` for preliminary data validation.

### 3.2. Module: Time Series Analysis & Modeling

- **Goal:** Port and enhance the functionality of the `vel_line_v*.m` scripts from `analysis/02`.
- **Functionality:**
    - **Data Ingestion:** Read time series data from various formats and from the POGF database.
    - **Offset Modeling:** Replicate the logic for handling offsets from the `offsets` file, accounting for `EQ`, `CE`, `UK`, `VE` types.
    - **Velocity Estimation:** Implement a robust least-squares regression to calculate station velocities and standard errors for each data segment, as seen in the MATLAB script.
    - **Outlier Detection:** Implement the IQR-based outlier detection (`rmoutliers`) from the MATLAB script.
    - **Periodic Signal Modeling:** Add support for fitting and removing annual/semi-annual signals.
- **Note:** This module focuses on the analysis of post-processed GNSS time series. Real-time or near real-time VADASE time series processing, as seen in `analysis/07 Sample time series from NMEA/`, is handled by the `vadase-rt-monitor` project.

### 3.3. Module: Dislocation Modeling & Inversion

- **Goal:** Port the C and MATLAB dislocation modeling codes from `analysis/03` and `analysis/08`.
- **Functionality:**
    - **Forward Modeling:** Create a Python wrapper around (or port the logic from) the `disloc.c` code to calculate surface displacement from a given fault geometry.
    - **Greens Function Generation:** Port the logic from `makeG_2d.m` and its variants to create the Green's functions needed for inversions.
    - **Velocity Projection:** Port the `velproj.m` logic for projecting velocities.

### 3.4. Module: Bootstrapping & Uncertainty Analysis

- **Goal:** Re-implement the bootstrapping workflows from `analysis/08`.
- **Functionality:**
    - Implement the bootstrapping algorithm from `bootstrap_v2.py`.
    - Integrate it with the dislocation modeling module to perform uncertainty analysis on fault parameters.

### 3.5. Module: Visualization

- **Goal:** Unify plotting capabilities across all modules.
- **Functionality:**
    - **Time Series Plots:** Generate high-quality, multi-panel plots (E, N, U) based on the `vel_line` scripts, including offset markers, velocity annotations, and outlier highlighting.
    - **Dislocation Model Plots:** Re-implement the plotting capabilities of `displot.m`.
    - **Velocity Field Maps:** Create functions to generate quiver plots of velocity fields, similar to the goals of the GMT scripts in `analysis/06`.

## 4. Technology Stack

- **Language:** Python 3.11+
- **Core Scientific Libraries:** Pandas, NumPy, SciPy.
- **Plotting Library:** Matplotlib (primary), with optional support for Plotly.
- **Coordinate Conversion:** `pymap3d`, `pygeodesy`.
- **C/Fortran Integration (for legacy code):** `ctypes` or `f2py` may be used as an interim step if direct porting of `disloc.c` or `baseline.for` is too complex initially.
- **CLI Framework:** `click`.

## 5. Integration

The unified library will serve as the backend for all scientific analysis. It will be used by:
- The **Public Data Portal** for generating visualizations.
- An **Automated Processing Pipeline** to generate standard data products after a new Bernese run.
- **Jupyter Notebooks** for interactive research and exploration by scientists.
- The **CLI tools** for manual and scripted analysis.