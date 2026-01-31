# VADASE Real-Time Monitor

Open-source real-time GNSS displacement monitoring system for earthquake detection, replacing proprietary Leica SpiderQC visualization.

## Overview

This system ingests NMEA-based VADASE (Variometric Approach for Displacement Analysis Stand-alone Engine) data streams from PHIVOLCS's network of 35 CORS stations and provides:

- Real-time velocity and displacement monitoring
- Automatic earthquake detection based on configurable thresholds
- Time-series visualization via Grafana dashboards
- Event cataloging and alerting

## Key Features

- **Parser**: Full LDM (Displacement) and LVM (Velocity) NMEA sentence parsing with checksum validation
- **Stream Handler**: Async TCP connections supporting 35+ concurrent stations
- **Database**: TimescaleDB for optimized time-series storage
- **Detection**: Configurable threshold-based event detection with quality filtering
- **Visualization**: Grafana dashboards replicating conference poster layouts

## Quick Start

### Prerequisites

- Python 3.11+
- [UV](https://github.com/astral-sh/uv) package manager
- Docker & Docker Compose
- PostgreSQL/TimescaleDB

### Installation
```bash
# Install UV (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone repository
git clone https://github.com/YOUR_USERNAME/vadase-rt-monitor.git
cd vadase-rt-monitor

# Install dependencies (creates virtual environment automatically)
uv sync --all-extras

# Copy environment template
cp .env.example .env
# Edit .env with your database credentials and station configurations
```

### Setup Database
```bash
# Start TimescaleDB via Docker
docker-compose up -d timescaledb

# Initialize schema
uv run python -c "
import asyncio
from scripts.init_database import init_db
asyncio.run(init_db())
"
```

### Run Ingestion
```bash
# Using the registered script command
uv run vadase-ingestor

# Or directly
uv run python scripts/run_ingestor.py
```

### Development
```bash
# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=src --cov-report=html

# Format code
uv run black src/ tests/ scripts/

# Lint code
uv run ruff check src/ tests/ scripts/

# Type check
uv run mypy src/
```

### Access Grafana
```
http://localhost:3000
Username: admin
Password: admin
```

## Testing & Verification
### 1. Offline Event Replay
Replay historical earthquake log files (`.rtl`, `.nmea`) to verify parser logic and visualization.
```bash
# Replay a specific earthquake file with live plotting and forced manual integration
uv run python scripts/replay_events.py \
  --file "data/NMEA_DGOS_10102025/NMEA_DGOS LDM_20251010_040000.rtl" \
  --mode replay \
  --base-date 2025-10-10 \
  --plot \
  --force-integration \
  --dry-run
```
*   `--mode replay`: Simulates real-time 1Hz streaming.
*   `--force-integration`: Overrides receiver's displacement data with locally calculated values (fixes "Velocity Only" issues).
*   `--dry-run`: Skips writing to Postgres (outputs to stdout logs).

### 2. Parallel Stress Test
Simulate multi-station load by running concurrent ingestion pipelines.
```bash
# Run 6 simulated stations in parallel from the data directory
uv run python scripts/stress_test_parallel.py \
  --data-dir "data/NMEA_DGOS_10102025" \
  --count 6 \
  --mode replay \
  --force-integration \
  --plot
```
*   `--plot`: Enables live plotting for the **first** station (SIM_01) only.

### 3. Mock NTRIP Integration
Test the full TCP/NTRIP stack using a mock server.

**Terminal 1 (Server):**
```bash
uv run python scripts/mock_ntrip_caster.py \
  --file "data/NMEA_DGOS_10102025/NMEA_DGOS LDM_20251010_040000.rtl" \
  --port 2101
```

**Terminal 2 (Client):**
```bash
# Create a local test config pointing to localhost
uv run python scripts/run_ingestor.py \
  --config config/stations_local_test.yml \
  --dry-run
```

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed system design.

## Validation

The parser has been validated against known earthquake events:
- 2022 Mw 7.0 Northwest Luzon earthquake
- 2023 Mw 7.4 Surigao del Sur earthquake
- 2023 Mw 6.8 Sarangani earthquake

See [docs/VALIDATION_GUIDE.md](docs/VALIDATION_GUIDE.md) for reproduction steps.

## Configuration

Station metadata, detection thresholds, and logging are configured via YAML files in `config/`:

- `stations.yml` - Station IDs, coordinates, TCP connection details
- `thresholds.yml` - Velocity thresholds per fault segment
- `logging.yml` - Log levels and output destinations

## Contributing

This is an internal PHIVOLCS project. For questions or contributions, contact the Geodesy Section.

## License

[Specify license - likely GPL-3.0 or MIT for open-source]

## Citation

If you use this system in research, please cite:

> Bacolcol, T., et al. (2025). Real-time measurement of GNSS motions using VADASE: Application to recent earthquakes in the Philippines. GEOCON 2025.

## Acknowledgments

- DOST-PHIVOLCS MOVE Faults Project
- NAMRIA Philippine Active Geodetic Network (PAGeNet)
- Leica Geosystems for VADASE algorithm specifications