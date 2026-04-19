# Database Schema

The monitor uses **TimescaleDB** (a PostgreSQL extension for time-series) to store high-frequency 1Hz GNSS data. The persistence logic is implemented in `src/database/writer.py`.

## Core Tables

### 1. `vadase_velocity`
Stores instantaneous velocity components for every epoch.
- `time` (TIMESTAMPTZ): The GNSS epoch timestamp.
- `station` (TEXT): Unique ID of the CORS station.
- `vE`, `vN`, `vU` (DOUBLE): Velocity components in meters per second.
- `quality` (DOUBLE): 3D component quality ($m/s$).

### 2. `vadase_displacement`
Stores integrated displacement components.
- `time` (TIMESTAMPTZ): The GNSS epoch timestamp.
- `station` (TEXT): Unique ID.
- `dE`, `dN`, `dU` (DOUBLE): Displacement in meters.
- `quality` (DOUBLE): 3D quality ($m$).

### 3. `event_detections`
Stores metadata for detected earthquake events.
- `detection_time` (TIMESTAMPTZ): When the velocity first exceeded the threshold.
- `station` (TEXT): Reporting station.
- `peak_velocity_horizontal` (DOUBLE): Max $vH$ during the event ($mm/s$).
- `peak_displacement_horizontal` (DOUBLE): Max $dH$ during the event ($mm$).
- `duration_seconds` (DOUBLE): Length of the seismic event.

## Performance Optimizations

### Hypertables
Both `vadase_velocity` and `vadase_displacement` are configured as **Hypertables**, partitioned by the `time` column. This allows for:
- Efficient data retention policies (e.g., dropping raw 1Hz data after 30 days).
- Parallelized query execution over large time ranges.

### Batch Writing
To minimize database round-trips and I/O wait, the `DatabaseWriter` implements a buffering mechanism:
1.  Measurements are appended to an in-memory list.
2.  A background task flushes the buffer every `flush_interval` (nominally 1 second) or when `batch_size` (nominally 100) is reached.
3.  Writes use `executemany` for efficient bulk insertion.

```python
async def _flush_velocity(self):
    async with self._lock:
        batch = self._velocity_buffer
        self._velocity_buffer = []
    # Bulk insert using asyncpg
    await conn.executemany('INSERT INTO ...', batch)
```

## Indexes
- **Primary**: `(time, station)` is indexed to ensure fast lookups for dashboarding and to prevent duplicate entries from overlapping data streams (`ON CONFLICT DO NOTHING`).
