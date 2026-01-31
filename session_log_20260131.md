# Session Log: Offline File Ingestion Implementation (2026-01-31)

## Overview
Successfully implemented the Offline File Ingestion feature for VADASE RT Monitor. This allows historical NMEA data to be imported or replayed as a simulated stream, enabling offline analysis and detector testing.

## Key Accomplishments

### 1. Architectural Refactoring
Decoupled data sources from the processing logic to support pluggable inputs.

*   **New Package**: `services/vadase-rt-monitor/src/sources/`
    *   `base.py`: Defined `DataSource` abstract protocol.
    *   `file.py`: Implemented `FileSource` for reading `.nmea`/`.rtl` files.
        *   **Import Mode**: Yields lines as fast as possible.
        *   **Replay Mode**: Simulates real-time delays based on timestamps.
        *   **Date Handling**: Logic to handle NMEA time rollovers (23:59 -> 00:00).
    *   `tcp.py`: Encapsulated original TCP stream logic into `TcpSource`.
*   **Processor**: `services/vadase-rt-monitor/src/stream/processor.py`
    *   Replaced `VADASEStreamHandler` with `IngestionProcessor`.
    *   Accepts any `DataSource` instance.
    *   Handles event detection logic (thresholding).

### 2. CLI Tools & Scripts
*   **Replay Script**: `services/vadase-rt-monitor/scripts/replay_events.py`
    *   New CLI tool for offline operations.
    *   **Flags**:
        *   `--file`: Path to input NMEA file.
        *   `--mode`: `import` or `replay`.
        *   `--dry-run`: Uses `MockDbWriter` to print SQL actions to stdout instead of DB.
        *   `--plot`: Enables live Matplotlib visualization.
*   **Ingestor Update**: `services/vadase-rt-monitor/scripts/run_ingestor.py`
    *   Updated to use the new `TcpSource` and `IngestionProcessor` architecture.

### 3. Visualization
*   **Live Plotter**: `services/vadase-rt-monitor/src/visualization/live_plot.py`
    *   Implemented `LivePlotter` class using `matplotlib`.
    *   Visualizes Velocity vs. Displacement in real-time during replay.

### 4. Database Integration
*   **Writer Update**: `services/vadase-rt-monitor/src/database/writer.py`
    *   Updated signatures to accept `station_id`.
    *   Added `close()` method for connection cleanup.
*   **Mocking**: Implemented verbose `MockDbWriter` in `replay_events.py` for verification without Postgres.

### 5. Verification & Findings
*   **Unit Tests**:
    *   `tests/test_file_source.py`: Verified file reading and date parsing.
    *   `tests/test_nmea_parser.py`: Confirmed parser accuracy.
*   **Data Analysis**:
    *   Analyzed provided files in `services/vadase-rt-monitor/data/`.
    *   **Finding**: Files `080000.rtl` through `210000.rtl` contain **identical values** for Velocity (`$GNLVM`) and Displacement (`$GNLDM`) sentences. This was confirmed by inspection, explaining why plots looked identical.

## Changed Files
*   `services/vadase-rt-monitor/src/sources/base.py` (New)
*   `services/vadase-rt-monitor/src/sources/file.py` (New)
*   `services/vadase-rt-monitor/src/sources/tcp.py` (New)
*   `services/vadase-rt-monitor/src/stream/processor.py` (New Refactor)
*   `services/vadase-rt-monitor/src/database/writer.py` (Updated)
*   `services/vadase-rt-monitor/src/visualization/live_plot.py` (New)
*   `services/vadase-rt-monitor/scripts/replay_events.py` (New)
*   `services/vadase-rt-monitor/scripts/run_ingestor.py` (Updated)
*   `services/vadase-rt-monitor/pyproject.toml` (Added `aiofiles`, `typer`, `matplotlib`)

## Hexagonal Architecture Refactor
Moved system to a strict Ports & Adapters architecture.

*   **Ports**: `src/ports/inputs.py`, `src/ports/outputs.py`
*   **Adapters**:
    *   `src/adapters/inputs/directory.py`: Replaces `FileSource`. Handles file rotation.
    *   `src/adapters/inputs/tcp.py`: Replaces `TcpSource`.
*   **Strategies**: `src/strategies/playback.py`.
*   **Domain**: `src/domain/processor.py` (IngestionCore) now consumes from `asyncio.Queue`.
*   **Wiring**: `replay_events.py` updated to assemble the graph.

## NTRIP Client Implementation
Upgraded TCP Adapter (`src/adapters/inputs/tcp.py`) to a robust NTRIP v1.0 Client.

*   **Handshake**: Sends `GET /<mountpoint>` with Basic Authentication headers.
*   **Validation**: parses HTTP status codes (`ICY 200 OK`).
*   **Resilience**: Implemented 10-second Watchdog timer to detect stalls and auto-reconnect.
*   **Production Ready**: Updated `run_ingestor.py` to use new config fields (`mountpoint`, `user`, `password`).

## Smart Integration (Data Repair)
Implemented logic in `IngestionCore` to handle receivers misconfigured in "Velocity Only" mode (where `$GNLDM` duplicates `$GNLVM`).

*   **Detection**: Automatically detects if `abs(Velocity - Displacement) < 1e-9` for 5 consecutive samples.
*   **Correction**: Switches to **Manual Integration** mode, calculating cumulative displacement locally (`disp += vel * dt`).
*   **Behavior**:
    *   **Velocity**: Appears as White Noise (zero-centered).
    *   **Displacement**: Appears as a Random Walk (Red Noise).
    *   **Note**: Without a High-Pass Filter, the integrated displacement effectively drifts over time. This is **expected behavior** and not a bug.
