# Implementation Plan - Deliverable 1.2: Unified Data Ingestion Pipeline

## Goal
Build a robust, idempotent, and scalable service to ingest proprietary raw GNSS data (RINEX) into the Centralized Geodetic Database.

## Architecture Pattern: Pipe & Filter (with Idempotency)
Unlike real-time streams, file ingestion is discrete. We will use a **Pipe & Filter** pattern implemented via **Celery Chains**.

### Key Concepts
1.  **Filters (Steps):** Discrete processing units (Validate, Standardize, Load).
2.  **Pipe (Transport):** Celery passing results from one task to the next.
3.  **Idempotency:** A check at the entry gate (and potentially at each step) to ensure the same file (same content hash) is not processed redundantly.

## Proposed Changes

### 1. New Service Directory: `services/ingestion-pipeline`
Structure:
```
services/ingestion-pipeline/
├── src/
│   ├── filters/           # The Processing Steps
│   │   ├── validator.py
│   │   ├── standardizer.py
│   │   └── loader.py
│   ├── triggers/          # The Sources
│   │   ├── watcher.py     # Local FS
│   │   └── poller.py      # FTP/S3
│   ├── core/
│   │   ├── celery_app.py  # Celery Config
│   │   └── idempotency.py # Hash checking logic
│   └── models.py          # Job tracking DB models
├── tests/
├── config.toml
└── pyproject.toml
```

### 2. The Pipeline (Celery Chain)
The workflow for a single file will be defined as:
```python
chain(
    calculate_hash.s(file_path) |
    check_idempotency.s() |
    validate_rinex.s() |
    standardize_rinex.s() |
    load_to_db.s()
)
```

#### Step details:
1.  **`calculate_hash`**: Computes SHA-256 of the raw file.
2.  **`check_idempotency`**: Queries DB/Redis. If hash exists and state is `COMPLETED`, abort. If `FAILED`, allow retry.
3.  **`validate_rinex`**:
    *   Syntactic check: Does it look like RINEX?
    *   Quality check: Run `gfzrnx -chk` (wrapper around external binary).
    *   **On Failure**: Tag job as `INVALID`, move file to `/quarantine`.
4.  **`standardize_rinex`**:
    *   **Decompression**: If `.yyd` (Hatanaka), run `rnx2crx` to get `.yyo`.
    *   **Renaming**: Parse header to get `StationID`, `Year`, `DOY`. Rename to `SSSSDDDO.YYo` standard.
5.  **`load_to_db`**:
    *   Insert/Update `stations` table (metadata).
    *   Insert `rinex_files` record (path, hash, metadata).
    *   **On Success**: Move file to `/archive/Year/DOY/`.

### 3. Data Models (Postgres)
We need a table to track the ingestion status of every file to support idempotency and observability.

```sql
CREATE TABLE ingestion_jobs (
    id UUID PRIMARY KEY,
    file_hash VARCHAR(64) UNIQUE NOT NULL,
    original_filename VARCHAR,
    status VARCHAR (PENDING, PROCESSING, COMPLETED, FAILED, INVALID),
    error_message TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

## User Review Required
> [!IMPORTANT]
> **External Dependencies**: This pipeline relies on `gfzrnx` (RINEX manipulation) and `rnx2crx` (Hatanaka decompression). These binaries must be installed in the environment.
>
> **Idempotency Scope**: Should we look at *current* filename or purely *content hash*?
> *Recommendation*: Pure content hash. A file renamed locally is still the same data.

## Verification Plan
1.  **Unit Tests**: Mock the binary calls (`gfzrnx`) to test the Python logic of each filter.
2.  **Idempotency Test**:
    *   Ingest `file_A.rnx`. Assert success.
    *   Ingest `file_A_copy.rnx` (same content). Assert "Skipped/Duplicate".
3.  **Integration Test**:
    *   Place a valid RINEX file in the watch folder.
    *   Verify it moves to `/archive` and appears in the `rinex_files` DB table.
