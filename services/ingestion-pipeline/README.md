# ingestion-pipeline

Celery-based RINEX ingestion: find observation files, decompress and validate
them, and record them in the central database. Status as of 2026-10-14: about
30%, 7 modules, 36 tests. **It is not in the production loop.** Production
staging is done by `scripts/` (`CLAUDE.md`, "What actually runs today").

## How it works

```
scanner.py      walk a tree, SHA-256 each RINEX observation file, skip files
                ingestion_logs already records, queue the rest
    │
pipeline.py     trigger_ingest(): a Celery chain of three tasks
    ▼
tasks.py
  standardize_format   unpack .gz/.zip/.Z and Hatanaka (.crx/.??d, needs crx2rnx on PATH)
  validate_rinex       RINEX header check (required) + QC through
                       pogf_geodetic_suite RinexQC: teqc, gfzrnx fallback (optional;
                       a missing or hung tool gives null QC metrics, not a failure)
  load_to_postgres     public.rinex_files row from the header; ingestion_logs updated.
                       Fails if the station code is not in public.stations
```

`tools/drive-archaeologist` can feed it: `drive-arch scan --ingest` dispatches
classified GNSS files here.

Tables: `ingestion_logs` (root migration 006, QC columns in 013) and
`rinex_files`, through the shared models in the repo-root `src/db/`.

## Running it

From the repository root:

```bash
uv sync --all-extras
docker compose up -d db redis                     # Postgres on 5433, Redis on 6380
uv run alembic upgrade head
uv run celery -A ingestion_pipeline.celery worker --loglevel=info
```

Settings come from the environment: `DATABASE_URL`, and `REDIS_HOST`,
`REDIS_PORT` (default 6380) and `REDIS_PASSWORD`.

## Tests

```bash
uv run pytest services/ingestion-pipeline/tests
```

One test skips when neither `teqc` nor `gfzrnx` is on `PATH`, because without
a QC tool it cannot tell a valid file from an unvalidated one.

## Not done

- the Trimble raw → RINEX conversion step;
- running on real data at scale;
- any connection to the Bernese stage.
