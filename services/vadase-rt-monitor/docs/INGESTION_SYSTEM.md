# Data Ingestion System

The ingestion system is designed to handle 35+ concurrent GNSS station streams with sub-second latency. It leverages Python's `asyncio` for high-concurrency network I/O.

## Asynchronous Pipeline

For each station configured in `stations.yml`, the system spawns an asynchronous pipeline consisting of a **Producer** and a **Consumer**.

### 1. The Producer (Input Adapter)
Responsible for reading raw strings from the source.
- **TCPSource**: Connects to an NTRIP caster or TCP server, reads lines ending in `\r\n`.
- **FileSource**: Reads historical `.rtl` or `.nmea` files.

### 2. The Buffer
A thread-safe `asyncio.Queue` sits between the Producer and the Core. This decoupling ensures that if the database is temporarily slow, the TCP sockets don't block and lose data packets.

### 3. The Consumer (IngestionCore)
Pulls sentences from the queue and executes the domain logic (parsing, integration, detection).

## Operational Modes

### Real-Time Streaming
In production, the system connects directly to the PHIVOLCS CORS network via TCP. It handles automatic reconnection logic if a station goes offline.

### Event Replay (Playback)
For research and validation, the system can "replay" historical data files as if they were live streams. This is controlled by the `src/strategies/playback.py` module.

- **FastImportStrategy**: Imports data as fast as the CPU allows. Useful for backfilling the database.
- **RealTimeStrategy**: Uses `asyncio.sleep` to simulate 1Hz delays based on the timestamps in the file. This allows researchers to watch the "earthquake wave" arrive on the Grafana dashboard in real-time.

```python
# RealTimeStrategy Logic
delta = (current_epoch - previous_epoch).total_seconds()
if 0 < delta < 60:
    await asyncio.sleep(delta)
```

## Scaling to 35+ Stations
Because the system is event-driven rather than thread-per-station, the overhead for adding new stations is minimal. The bottleneck is typically database I/O, which is mitigated by batch writing.
