# ADR-009: Technology Choice for RINEX Quality Control (QC) Module

**Date:** 2026-01-25

**Status:** Proposed

## Context

Processing low-quality GNSS data is a waste of computational resources and can lead to incorrect scientific results. It is essential to perform a quality control (QC) check on raw RINEX files as soon as they are ingested, before they enter the main processing chain. This requires a tool that can parse RINEX files and calculate a standard set of QC metrics (e.g., multipath, cycle slips, data gaps, SNR).

## Decision

We will **not** build the core RINEX QC analysis logic from scratch in Python. Instead, our architectural decision is to **develop a Python wrapper around the `gfzrnx` command-line tool**.

1.  **Core Technology: `gfzrnx`**
    - **Reasoning:** `gfzrnx` is a modern, comprehensive, and high-performance open-source (LGPLv3) RINEX toolkit developed by the GFZ German Research Centre for Geosciences. It is written in Rust, which makes it exceptionally fast at parsing and processing large RINEX files. It already implements a wide array of sophisticated QC checks that are considered standard in the geodetic community. Attempting to replicate this functionality in Python would be a massive, time-consuming, and redundant effort. It is far more efficient to leverage this existing, high-quality, specialized tool.

2.  **Implementation Strategy: Python Wrapper**
    - **Reasoning:** To integrate the power of `gfzrnx` into our Python-based ecosystem, we will create a wrapper. This Python module will use the `subprocess` library to execute the `gfzrnx` binary. The wrapper's responsibility will be to provide a clean, Pythonic API that handles the details of:
      - Constructing the correct `gfzrnx` command-line arguments for a given task.
      - Executing the subprocess.
      - Parsing the machine-readable output from `gfzrnx` (specifically its JSON output) into convenient Python data structures (e.g., dictionaries, dataclasses).

This "wrapper" approach provides the best of both worlds: the raw performance and proven algorithms of a compiled Rust application, combined with the ease of use and seamless integration of a native Python library.

## Alternatives Considered

### 1. Re-implementing the QC Logic in Pure Python

- **Pros:** Would result in a "pure Python" solution with no external binary dependencies, which simplifies deployment.
- **Cons:** This is a terrible use of development resources. The underlying algorithms for calculating metrics like cycle slips and multipath are complex and require significant domain expertise. Furthermore, a pure Python implementation would be orders of magnitude slower than the highly optimized Rust code in `gfzrnx`.

### 2. Using an Older Tool like `TEQC`

- **Pros:** `TEQC` from UNAVCO is a well-known, classic tool for RINEX QC.
- **Cons:** `TEQC` is legacy software. It has not been actively developed for many years, has limited support for modern RINEX 3/4 formats, and its output formats are less convenient for machine parsing compared to the JSON output from `gfzrnx`. `gfzrnx` is the modern, actively maintained successor in this space.

### 3. Using Shell Scripts to Call `gfzrnx` Directly

- **Pros:** Very simple for one-off manual checks.
- **Cons:** This does not create a reusable, importable library. It makes integration with our Python-based Ingestion Pipeline difficult and brittle. Error handling and parsing the JSON output are much more robustly handled in Python than in a shell script.

## Consequences

### Positive

- **Drastic Reduction in Development Time:** We are leveraging an existing, feature-complete application, saving potentially months of development work.
- **Exceptional Performance:** For the CPU-intensive task of parsing and analyzing RINEX files, we get the performance of a compiled Rust application, which is a huge advantage.
- **Authoritative and Correct:** We are using a tool from a trusted, authoritative source in the geodesy community (GFZ), which gives us confidence in the correctness of the generated metrics.

### Negative

- **External Binary Dependency:** The most significant consequence is that our system now has a dependency on the `gfzrnx` binary. This binary is not a Python package and must be installed separately on any system or container that runs the QC module. This dependency must be explicitly managed in our deployment scripts and Dockerfiles.
- **Wrapper Maintenance:** The Python wrapper is coupled to the command-line interface of `gfzrnx`. If future versions of `gfzrnx` change their command-line arguments or JSON output format, our wrapper will need to be updated. This is a manageable, but important, maintenance responsibility.
- **Two-Part Debugging:** If an issue occurs, we will need to determine if the bug is in our Python wrapper or in the underlying `gfzrnx` tool itself.
