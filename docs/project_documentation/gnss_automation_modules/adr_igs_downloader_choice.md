# ADR-006: Architecture for Automated IGS Product Downloader

**Date:** 2026-01-25

**Status:** Proposed

## Context

High-precision GNSS processing with the Bernese software requires a multitude of external data products from the IGS and other data centers (e.g., precise orbits, clock corrections, Earth rotation parameters). These products are hosted on public FTP and HTTP servers, which can sometimes be unreliable. The process of manually downloading the correct products for a given processing run is tedious and a common source of failure.

We need an automated tool that is resilient to network failures and can be trusted to maintain a local, up-to-date repository of these required products.

## Decision

We will build a standalone Python command-line tool. This tool will be designed to be run on a schedule (e.g., via `cron`) to download products. The key architectural decisions are:

1.  **Architecture: Standalone Command-Line Tool**
    - **Reasoning:** A simple, self-contained CLI tool is the most effective design. It adheres to the UNIX philosophy of "do one thing and do it well." It is easy to install, test, debug, and integrate with any standard scheduling system (`cron`, Windows Task Scheduler, etc.). It is not a long-running service or daemon, which simplifies its design and reduces overhead.

2.  **Core Technology: Python with the `requests` library**
    - **Reasoning:** Python is the project's primary language. The `requests` library is the de facto standard for making HTTP/FTP requests in Python. It elegantly handles sessions, connection pooling, and error conditions, which is essential for interacting with potentially unreliable remote servers. This is a much more robust and maintainable approach than using lower-level libraries.

3.  **Configuration Method: External TOML file**
    - **Reasoning:** The list of IGS products, their various official and mirror URLs, and the rules for constructing filenames are complex and subject to change. Hard-coding this information would be brittle. Storing it in a human-readable TOML configuration file makes the tool flexible and easy for operators to update without modifying the Python source code.

4.  **Decoupling from Processing Workflow**
    - **Reasoning:** The downloader's sole responsibility is to populate a local data store. The Bernese processing workflow will then consume products from this reliable local store. This decoupling is a critical design choice. It makes the entire system more resilient; the processing workflow can still run even if the external IGS servers are temporarily unavailable. It also allows products to be pre-downloaded independently of processing.

## Alternatives Considered

### 1. Using `wget` or `curl` in a Shell Script

- **Pros:** `wget` and `curl` are powerful, mature tools with built-in support for retries and mirror handling. This approach would have no Python dependency.
- **Cons:** While possible, implementing the more complex logic required by this tool would be difficult in a shell script. This includes dynamically generating URLs based on dates (e.g., GPS week and day), validating checksums, and the highly structured fallback logic (try primary 3 times, then try mirror 1, etc.). A Python script provides a much more maintainable and readable solution for this level of complexity.

### 2. Tightly Integrating Downloading into the Bernese Workflow

- **Pros:** Conceptually simple; the workflow just gets what it needs when it needs it.
- **Cons:** This creates a brittle, tightly coupled system. If an IGS server is down when a processing job starts, the entire job fails. By creating a separate downloader that populates a local repository, the processing workflow becomes insulated from the unreliability of external network resources.

### 3. Using a Generic Off-the-Shelf Download Manager

- **Pros:** Might provide a GUI and other user-friendly features.
- **Cons:** Not suited for this task. Generic downloaders cannot handle the specialized logic of constructing IGS filenames and URLs based on specific dates, GPS weeks, and product types (e.g., `codg<week><dow>.sp3.Z`). This custom logic is a core requirement.

## Consequences

### Positive

- **Robustness and Resilience:** The combination of retry logic, mirror fallback, and checksum validation will make the product acquisition process highly reliable.
- **Modularity:** Decoupling the downloader from the processing workflow improves the resilience and modularity of the entire system.
- **Maintainability:** The use of Python and a TOML configuration file makes the tool easy to understand, maintain, and extend.
- **Simplicity:** The standalone CLI tool design is simple and has a very low operational overhead.

### Negative

- **Requires Scheduling:** The tool is not a daemon; an external scheduler like `cron` must be configured to run it periodically. This is a standard operational task but is an explicit step that must be taken.
- **Local Storage Requirement:** The tool requires disk space to maintain the local repository of downloaded products. The storage requirements will grow over time.
