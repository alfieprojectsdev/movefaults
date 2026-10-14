# VADASE Real-Time Monitor: Developer Onboarding

Welcome! This guide will help you understand the VADASE Real-Time Monitor codebase. We're assuming you have experience with Python for data analysis (pandas, numpy, matplotlib) but may be new to network programming and real-time systems.

## What This System Does

The VADASE Real-Time Monitor is an earthquake detection system that:

1. **Connects** to GNSS (GPS) stations across the Philippines (PHIVOLCS operates ~35; `config/stations.yml` configures 4)
2. **Receives** real-time position data in NMEA format
3. **Processes** velocity and displacement measurements
4. **Detects** earthquakes when ground motion exceeds thresholds
5. **Stores** data in a time-series database for analysis

Think of it as a seismograph network that automatically alerts when earthquakes happen, but using GPS data instead of traditional seismometers.

## Key Concepts You'll Need

### NMEA Data Format
GNSS receivers send data in NMEA sentences - text strings like:
```
$GNLVM,113805.50,030215,0.0011,0.0021,0.0015,...*47
```
This contains timestamp, velocity components (East/North/Up), and quality metrics.

### CORS Stations
Continuously Operating Reference Stations - permanent GPS receivers that provide real-time positioning data. Each station has:
- Geographic coordinates
- Network connection details (IP address, port)
- Detection thresholds

### VADASE Algorithm
Variometric Approach for Displacement Analysis - converts GPS carrier phase measurements into precise displacement estimates.

## Core Source Files

### Data Parsing: `src/parsers/nmea_parser.py`

**What it does:** Converts raw NMEA text into structured Python dictionaries.

**Key functions:**
- `parse_lvm()` - Parses velocity sentences ($GNLVM)
- `parse_ldm()` - Parses displacement sentences ($GNLDM)
- `validate_nmea_checksum()` - Ensures data integrity

**Why it's important:** This is your data ingestion layer. Raw network data comes in as text strings, and this file turns them into usable numbers.

```python
# Example: What parse_lvm() returns
{
    'timestamp': datetime(2015, 2, 3, 11, 38, 5, 500000, tzinfo=timezone.utc),
    'vE': 0.0011,  # East velocity in m/s
    'vN': 0.0021,  # North velocity in m/s
    'vU': 0.0015,  # Up velocity in m/s
    'n_sats': 8    # Number of satellites used
}
```

### Core Processing: `src/domain/processor.py`

**What it does:** The brain of the system. Processes parsed data and makes decisions about earthquake detection.

**Key components:**
- **Event Detection:** Compares velocity against thresholds to detect earthquakes
- **Receiver mode (`ReceiverMode`):** Decides whether to use the receiver's displacement or integrate velocity itself
- **Leaky Integrator:** Converts velocity to displacement when needed

**Why receiver mode exists:**
In quiet time, Leica receivers normally echo velocity values in the displacement fields; they send a real integrated displacement only once their own threshold is crossed. That is expected behaviour, not a fault, but it means the displacement field is useless most of the time. The processor compares the two:
- `velocity == displacement` for 5 epochs → MANUAL mode (integrate velocity ourselves)
- displacement different from velocity while velocity is low, for 3 epochs → MANUAL with integration frozen (treated as scintillation)
- displacement different and velocity above the threshold, for 30 epochs → back to RECEIVER mode

`DOMAIN_LOGIC.md` has the full table.

```python
# Core processing loop
async def process_sentence(self, sentence: str):
    if sentence.startswith('$GNLVM'):  # Velocity data
        await self.handle_velocity(sentence)
    elif sentence.startswith('$GNLDM'):  # Displacement data
        await self.handle_displacement(sentence)
```

### Network Connections: `src/adapters/inputs/tcp.py`

**What it does:** Manages TCP connections to GPS stations.

**Key concepts:**
- **NTRIP Protocol:** Standard for accessing real-time GNSS data over internet
- **Async I/O:** Uses asyncio for handling multiple concurrent connections
- **Reconnection Logic:** Automatically reconnects if network fails

**Network Programming for Data Scientists:**
This is probably new territory! The adapter handles:
- Opening TCP sockets to remote servers
- Authentication (username/password for NTRIP)
- Reading streaming text data line-by-line
- Feeding data into an asyncio.Queue for processing

```python
# Simplified connection logic
self.reader, self.writer = await asyncio.open_connection(host, port)
if self.mountpoint:
    await self._perform_handshake()  # NTRIP authentication
```

### Data Storage: `src/adapters/outputs/timescaledb.py`

**What it does:** `TimescaleDBAdapter` saves processed data to TimescaleDB (PostgreSQL with time-series extensions). It implements the `OutputPort` protocol; sibling implementations in the same package: `NullOutputPort` (tests), `LoggingOutputPort` (dry-run), `CompositeOutputPort` (fan-out to several sinks).

**Key operations:**
- `write_velocity()` - Stores velocity measurements
- `write_displacement()` - Stores displacement measurements
- `write_event_detection()` - Records detected earthquakes

**Database Schema:**
- Separate tables for velocity and displacement data
- Hypertables for efficient time-series queries
- Indexes on station_id and timestamp

### Interfaces: `src/ports/`

**What it does:** Defines the contracts between components.

**Hexagonal Architecture:**
- `InputPort` - Interface for data sources (TCP, files, directories)
- `OutputPort` - Interface for data sinks (database, files, APIs)

**Why this matters:** The core processor doesn't know if data comes from network or files. This makes testing and extension easy.

## Data Flow Through the System

```
GPS Station → TCP Connection → NMEA Parser → Processor → Database
     ↓             ↓             ↓           ↓           ↓
  Raw data     Raw text     Structured   Smart      Time-series
              strings       dicts       processing   storage
```

1. **Network Layer** (`tcp.py`): Receives streaming NMEA sentences
2. **Parsing Layer** (`nmea_parser.py`): Converts text to structured data
3. **Processing Layer** (`processor.py`): Applies algorithms and detects events
4. **Storage Layer** (`adapters/outputs/timescaledb.py`): Saves results to database

## Configuration Files

### `config/stations.yml`
Defines the configured stations (4 today: PBIS, BOST, BTU2, PAPI):
```yaml
stations:
  - id: PBIS
    name: Bislig City, Surigao del Sur
    latitude: 8.1956
    longitude: 126.3919
    elevation: 15.0
    host: <LAN address>
    port: 5017
    threshold_mm_s: 15.0  # Earthquake detection threshold
    fault_segment: Philippine Fault - Surigao Segment
    filter:
      enabled: true
      decay: 0.99         # leaky-integrator factor; 1.0 when disabled
```

### `config/thresholds.yml`
Empty (0 bytes). The threshold is per station, in `stations.yml`.

## Development and Testing Scripts

### `scripts/run_ingestor.py`
Main entry point. Loads station config and starts processing for all stations.

### `scripts/replay_events.py`
**Perfect for learning!** Replays historical earthquake data from files:
- Tests parser accuracy
- Validates detection algorithms
- No network required

### `scripts/mock_ntrip_caster.py`
Fake GPS server for testing network code without real stations.

### `scripts/threshold_evidence.py`
Measures the alarm threshold against real captures; produces the figures in the repo-root `docs/project_documentation/vadase_threshold_evidence.md`.

Parser tests are in `tests/test_nmea_parser.py`, not in `scripts/`.

## Key Algorithms to Understand

### 1. Horizontal Velocity Magnitude
```python
def compute_horizontal_magnitude(vE, vN):
    return math.sqrt(vE**2 + vN**2)
```
Combines East/North components into total ground motion speed.

### 2. Leaky Integration
```python
# Convert velocity to displacement over time
displacement = (previous_displacement * decay) + (velocity * time_delta)
```
Accumulates displacement from velocity measurements, with decay to prevent drift.

### 3. Event Detection
```python
if horizontal_velocity_mm_s > threshold_mm_s:
    # Earthquake detected!
    record_event(start_time, peak_velocity, duration)
```

## Getting Started

1. **Read the code in this order:**
   - `nmea_parser.py` (data structures)
   - `processor.py` (algorithms)
   - `tcp.py` (networking)
   - `run_ingestor.py` (system assembly)

2. **Replay a recorded event** (from this directory; no database needed):
   ```bash
   PYTHONPATH=. uv run python scripts/replay_events.py \
     --file "data/NMEA_DGOS_10102025/NMEA_DGOS LDM_20251010_040000.rtl" \
     --mode replay --base-date 2025-10-10 --dry-run
   ```

3. **Run the tests** (from the repo root):
   ```bash
   uv run pytest services/vadase-rt-monitor/tests
   ```

4. **Explore data** (from this directory):
   ```bash
   PYTHONPATH=. uv run python -c "
   from src.parsers.nmea_parser import parse_lvm
   result = parse_lvm('$GNLVM,113805.50,030215,0.001,0.002,0.003,*47')
   print(result)
   "
   ```

## Common Patterns You'll See

- **Async/Await:** All I/O operations are asynchronous for handling multiple stations
- **Queues:** Data flows between components via `asyncio.Queue`
- **Protocols:** Type hints define interfaces between components
- **Structured Logging:** Uses `structlog` for detailed, searchable logs
- **YAML Config:** Human-readable configuration files

## Testing Strategy

- **Unit Tests:** Test individual functions (parsing, algorithms)
- **Integration Tests:** Test component interactions
- **Offline Replay:** Test with historical data
- **Mock Servers:** Test network code without real connections

## Next Steps

1. Run the replay script with some sample data
2. Modify a threshold and see how detection changes
3. Add logging to understand the data flow
4. Try connecting to a test station (if available)

Remember: This system processes real-time data from actual earthquakes. Your changes could affect earthquake monitoring operations, so test thoroughly!
