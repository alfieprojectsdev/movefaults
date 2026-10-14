# Data Ingestion System

The ingestion system is designed for the ~35 stations PHIVOLCS operates (4 are configured in `config/stations.yml` today). No latency figure has been measured. It leverages Python's `asyncio` for high-concurrency network I/O.

## Asynchronous Pipeline

For each station configured in `stations.yml`, the system spawns an asynchronous pipeline consisting of a **Producer** and a **Consumer**.

### 1. The Producer (Input Adapter)
Responsible for reading raw strings from the source.
- **`TCPAdapter`** (`src/adapters/inputs/tcp.py`): connects to a TCP server or, with a `mountpoint`, performs an NTRIP handshake. Reconnects with exponential backoff and full jitter, so many stations do not reconnect in lockstep after a shared caster outage. A handshake failure that retrying cannot fix (bad credentials, wrong mountpoint) raises `FatalConfigError`, and that station stops instead of hammering the shared caster account.
- **`DirectoryAdapter`** (`src/adapters/inputs/directory.py`): reads historical `.rtl` or `.nmea` files for replay.

Both implement `InputPort` (`src/ports/inputs.py`).

### 2. The Buffer
An `asyncio.Queue` (bounded at 100 lines per station in `run_ingestor.py`) sits between the Producer and the Core. This decoupling ensures that if the database is temporarily slow, the TCP sockets don't block and lose data packets.

### 3. The Consumer (IngestionCore)
Pulls sentences from the queue and executes the domain logic (parsing, integration, detection).

## Operational Modes

### Real-Time Streaming
In production, the system connects directly to the PHIVOLCS CORS network via TCP. It handles automatic reconnection logic if a station goes offline.

### Event Replay (Playback)
For research and validation, the system can "replay" historical data files as if they were live streams. This is controlled by the `src/strategies/playback.py` module.

- **FastImportStrategy**: Imports data as fast as the CPU allows. Useful for backfilling the database.
- **RealTimeStrategy**: Uses `asyncio.sleep` to reproduce the gaps between the file's timestamps, divided by `speed` (1.0 by default; `run_demo.sh` uses 8). This allows researchers to watch the "earthquake wave" arrive on the Grafana dashboard in real-time.

```python
# RealTimeStrategy Logic
delta = (current_epoch - previous_epoch).total_seconds()
if 0 < delta < 60:
    await asyncio.sleep(delta / self.speed)   # speed > 1 replays faster than real time
```

## Scaling
Each station is two asyncio tasks (adapter and core) on one event loop, sharing one output adapter, rather than a thread per station. Database writes are batched (see `DATABASE_SCHEMA.md`). `scripts/stress_test_parallel.py` simulates several stations from recorded files; no measured ceiling is recorded.
