# VADASE Real-Time Monitor

Real-time GNSS displacement monitoring for earthquake detection, as an open
replacement for the visualisation in Leica SpiderQC.

## Overview

The service ingests NMEA VADASE (Variometric Approach for Displacement Analysis
Stand-alone Engine) streams from CORS receivers. For each station it:

- parses `$GNLVM` (velocity) and `$GNLDM` (displacement) sentences, with checksum validation
- decides, epoch by epoch, whether to trust the receiver's own displacement or integrate velocity itself (`ReceiverMode`)
- detects events when horizontal velocity exceeds a per-station threshold (`threshold_mm_s`, 15.0 mm/s for every configured station)
- writes velocity, displacement and event summaries to TimescaleDB, with Grafana dashboards on top

**Two station counts, both real.** PHIVOLCS operates a CORS network of about 35
stations. `config/stations.yml` configures **4** of them (PBIS, BOST, BTU2,
PAPI), on LAN addresses that only resolve inside one building. Check the file
rather than this sentence; the configured count is the one that changes.

## Layout

```
src/
  parsers/nmea_parser.py        LVM/LDM parsing, XOR checksum (NMEAChecksumError)
  domain/processor.py           IngestionCore: ReceiverMode state machine, leaky integrator, event detection
  ports/                        InputPort, OutputPort protocols
  adapters/inputs/              TCPAdapter (NTRIP, reconnect with jittered backoff), DirectoryAdapter (files)
  adapters/outputs/             TimescaleDBAdapter, LoggingOutputPort (dry run), NullOutputPort, CompositeOutputPort
  strategies/playback.py        FastImportStrategy, RealTimeStrategy (replay at 1 Hz or faster)
  visualization/live_plot.py    matplotlib live ENU plot for replays
scripts/                        run_ingestor.py, replay_events.py, stress_test_parallel.py,
                                mock_ntrip_caster.py, threshold_evidence.py
config/                         stations.yml, stations_local_test.yml, logging.yml, thresholds.yml (empty)
grafana/                        dashboards and provisioning, mounted by the repo-root docker-compose.yml
notebooks/                      event_validation.ipynb, poster_reproduction.ipynb
```

The database schema is not here: it is migrations `010`–`012` in the repo-root
`migrations/` tree. See [docs/DATABASE_SCHEMA.md](docs/DATABASE_SCHEMA.md).

## Quick start

Everything runs from the monorepo; this service has no `pyproject.toml` of its own.

```bash
# from the repository root
uv sync --all-extras                 # structlog, asyncpg, typer etc. come from the extras
docker compose up -d db grafana      # TimescaleDB on 5433, Grafana on 127.0.0.1:3000
uv run alembic upgrade head          # creates the vadase_* tables (run from the root)
```

### Run the ingestor

```bash
cd services/vadase-rt-monitor
PYTHONPATH=. uv run python scripts/run_ingestor.py                 # config/stations.yml
PYTHONPATH=. uv run python scripts/run_ingestor.py --dry-run       # log writes, no database
```

`PYTHONPATH=.` makes the bare `src.` imports resolve. There is deliberately no
`vadase-ingestor` console script: the wheel maps only `src/` directories, so a
`scripts.` target could never import.

### Replay a recorded event, no database needed

```bash
./run_demo.sh                        # BOST, 2023-12-02 Mw 7.6, at 8x speed
```

`run_demo.sh` needs the BOST capture at `data/NMEA_BOST LDM_20231202_140000/`,
which is not in the repository. Replay any capture by hand:

```bash
PYTHONPATH=. uv run python scripts/replay_events.py \
  --file "data/NMEA_DGOS_10102025/NMEA_DGOS LDM_20251010_040000.rtl" \
  --mode replay --base-date 2025-10-10 --plot --dry-run
```

- `--mode replay` streams at 1 Hz; `--mode import` (the default) goes as fast as possible.
- `--force-integration` starts in MANUAL mode (integrate velocity) instead of RECEIVER.
- `--speed` multiplies replay speed (`--speed 8` is 8x real time).
- `--decay` sets the leaky-integrator factor (default 1.0, no leak).
- `--dry-run` discards database writes; event banners still print.

### Parallel stress test

```bash
PYTHONPATH=. uv run python scripts/stress_test_parallel.py \
  --data-dir "data/NMEA_DGOS_10102025" --count 6 --mode replay --plot
```

`--plot` draws the first simulated station (SIM_01) only.

### Mock NTRIP caster

```bash
# terminal 1
PYTHONPATH=. uv run python scripts/mock_ntrip_caster.py \
  --file "data/NMEA_DGOS_10102025/NMEA_DGOS LDM_20251010_040000.rtl" --port 2101
# terminal 2
PYTHONPATH=. uv run python scripts/run_ingestor.py --config config/stations_local_test.yml --dry-run
```

### Tests and lint

```bash
# from the repository root
uv run pytest services/vadase-rt-monitor/tests      # 51 tests, 2026-10-14
ruff check services/vadase-rt-monitor
```

### Grafana

`http://127.0.0.1:3000`. The admin password is `GRAFANA_PASSWORD` from the
environment, defaulting to `admin`; set it before exposing the port.

## Configuration

`config/stations.yml`, one entry per station:

- `id`, `name`, `latitude`, `longitude`, `elevation`, `fault_segment`
- `host`, `port`, and for an NTRIP caster `mountpoint`, `user`, `password`
- `threshold_mm_s`: the event threshold for that station
- `filter: {enabled, decay}`: when enabled, the leaky integrator uses `decay`
  (0.99 in the shipped config); when absent or disabled, 1.0 (pure integration)

`config/thresholds.yml` is **empty** (0 bytes). The threshold lives in
`stations.yml`.

## Evidence for the threshold

- [`vadase_detection_validation.md`](../../docs/project_documentation/vadase_detection_validation.md):
  the 2026-06-08 Mw 7.8 Sarangani event across ten sites, measured 2026-09-22.
- [`vadase_threshold_evidence.md`](../../docs/project_documentation/vadase_threshold_evidence.md):
  five captures (BOST and PBIS December 2023, DGOS October 2025 and January 2026,
  and a non-seismic TUA2 spike), measured 2026-10-06. Every figure is
  reproduced by `scripts/threshold_evidence.py`.

None of the captures are in the repository: they are PHIVOLCS field data,
and `*.rtl` and `data/` are git-ignored. Keep them under `data/` in a working
clone. (Two DGOS sets were committed from 2026-01-31 until #277 removed them;
they remain in history.)

## Known defects outside the Python package

- `Dockerfile` copies a `pyproject.toml` this directory does not have and runs
  `vadase-ingestor`, which does not exist. It cannot build as written.
- `docker-compose.yml` in this directory is not a compose file (its content is
  its own filename). Use the repo-root `docker-compose.yml`.

## Documentation

[docs/INDEX.md](docs/INDEX.md) lists the rest. `CLAUDE.md` at the repo root has
the architecture notes that span files (receiver mode, import paths, the `src`
namespace package).

## License

MIT, copyright PHIVOLCS/DOST: see the repo-root [`LICENSE`](../../LICENSE) and
[`NOTICE`](../../NOTICE). GNSS observation data is not covered by that licence.

## Citation

> Bacolcol, T., et al. (2025). Real-time measurement of GNSS motions using VADASE: Application to recent earthquakes in the Philippines. GEOCON 2025.

## Acknowledgments

- DOST-PHIVOLCS MOVE Faults Project
- NAMRIA Philippine Active Geodetic Network (PAGeNet)
- Leica Geosystems for VADASE algorithm specifications
