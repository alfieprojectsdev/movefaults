# ADR-008 (Revised): Unifying the Geodetic Post-Processing Workflow in Python

**Date:** 2026-01-25

**Status:** Proposed

## Context

The discovery of the `/analysis/` directory reveals that the project's post-processing needs are far greater than just time series plotting. The current workflow is a heterogeneous collection of MATLAB scripts (`vel_line*.m`), C-code (`disloc.c`), FORTRAN (`.for`), Python utility scripts (`geodetic2enu_v2.py`), and various shell scripts. This fragmentation creates significant challenges:
1.  **Multiple Proprietary Dependencies:** The reliance on MATLAB is a major cost and integration barrier.
2.  **Language Silos:** The mix of C, FORTRAN, MATLAB, and Python makes the full workflow difficult to run, maintain, and understand for any single developer.
3.  **No Central Integration:** The scripts are standalone and require manual data passing, which is inefficient and error-prone.

We need a unified, open-source solution that consolidates this logic into a single, cohesive, and maintainable framework.

## Decision

We will create a **unified Geodetic Post-Processing & Modeling Suite in Python**. The strategy is to systematically port, wrap, or re-implement the functionality of the existing scripts from the `/analysis/` directory into a single, installable Python library. The core technology choices are:

1.  **Primary Language & Ecosystem: Python**
    - **Reasoning:** This is the only viable choice for unifying the project. Python has mature, best-in-class libraries for scientific computing (NumPy, SciPy, Pandas), plotting (Matplotlib), and can effectively interface with or replace the logic from the other languages. This creates a single, consistent technology stack.

2.  **Core Libraries: NumPy, Pandas, SciPy, Matplotlib**
    - **Reasoning:** This suite of libraries directly replaces the core functionality provided by MATLAB. Pandas is ideal for time series data, SciPy provides the statistical and optimization functions for modeling, and Matplotlib is the standard for publication-quality plotting.

3.  **Strategy for Legacy Code (C/FORTRAN): Wrap then Port**
    - **Reasoning:** Directly porting complex, legacy scientific code like `disloc.c` can be risky and time-consuming. A two-stage approach is preferred:
        1.  **Wrap:** Initially, use Python's built-in `ctypes` or `f2py` to create a Python wrapper around the existing, compiled C/FORTRAN code. This provides immediate functionality and a clear API boundary.
        2.  **Port:** Over time, the internal logic of the wrapped code can be re-implemented in pure Python, with the new implementation being validated against the original. This mitigates risk and makes the transition manageable.

## Alternatives Considered

### 1. Maintain the Polyglot System (Status Quo)

- **Pros:** No initial development effort.
- **Cons:** This is not a tenable solution. It fails to address any of the core problems of cost, maintainability, and integration. It makes true automation impossible.

### 2. A "System of Systems" Wrapper

- **Description:** Write a high-level Python script that simply calls out to all the other executables (`matlab`, `gmt`, compiled C code) using `subprocess`.
- **Pros:** Might seem faster to implement initially than a full port.
- **Cons:** This is a "duct tape" solution. It is extremely brittle, slow (due to process-spawning overhead), and still requires all the underlying dependencies (MATLAB licenses, etc.) to be installed. It does not solve the core problem, it only hides it behind a thin layer of Python.

## Consequences

### Positive

- **Unified & Maintainable Codebase:** All post-processing logic will live in a single, version-controlled, and tested Python library.
- **Eliminates Proprietary Dependencies:** The systematic porting will completely remove the dependency on MATLAB, reducing costs and improving accessibility.
- **Seamless Integration:** As a standard Python package, the new suite will integrate directly with the POGF Database, the automated Bernese workflow, and any future data products or services.
- **Accelerates Research:** By providing a stable, easy-to-use, and open-source library, the suite will empower scientists to perform analysis more efficiently and repeatably.

### Negative

- **Significant Porting Effort:** This is a major undertaking. The logic in the various MATLAB, C, and FORTRAN scripts must be carefully studied, understood, and correctly ported to Python. This requires significant domain expertise and development time.
- **Validation is Critical:** Throughout the porting process, rigorous testing and validation will be required to ensure that the new Python implementations produce scientifically equivalent results to the original scripts. This is a non-trivial validation effort.
- **Initial Complexity of Wrapping:** While safer, wrapping legacy C/FORTRAN code requires specific expertise in tools like `ctypes` and `f2py`.