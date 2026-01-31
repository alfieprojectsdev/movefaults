### 1\. Architectural Refactor Plan

**Goal:** Decouple data acquisition from data processing.

- **Current State:** `Async TCP Client` 
	$$
	→
	$$
	 `Parser` 
	$$
	→
	$$
	 `TimescaleDB`
- **Target State:** `Source Interface` (TCP vs. File) 
	$$
	→
	$$
	 `Parser` 
	$$
	→
	$$
	 `Ingestor` 
	$$
	→
	$$
	 `TimescaleDB`

**Instructions for the Agent:**

- **Create a `DataSource` Protocol:** Define an abstract base class or protocol with an `__aiter__` (async iterator) method that yields raw NMEA lines.
- **Refactor `TcpStreamHandler`:** Make it implement `DataSource`.
- **Create `FileSource`:** A new class implementing `DataSource` that reads line-by-line from a local file (or directory of files).
	- *Requirement:* It must handle standard file I/O asynchronously (using `aiofiles` is recommended to avoid blocking the event loop during large file reads).

### 2\. The "Dual Mode" Strategy

You likely need two different ways to handle offline files. The agent needs to distinguish between them:

#### Mode A: "Bulk Import" (For Visualization & Analysis)

- **Purpose:** Rapidly loading a 2-hour earthquake event log to view in Grafana immediately.
- **Constraint:** Speed. Don't `sleep()` between lines.
- **Timestamp Handling:** This is critical. The agent **must not** use `NOW()` for database insertion. It must parse the GNSS time from the NMEA sentence (usually in UTC) and use *that* as the primary key for TimescaleDB.
	- *Note:* Standard NMEA sentences often contain time but not the date. The `FileSource` must allow the user to specify a "Start Date" argument, or the agent must implement logic to handle day rollovers if the file spans midnight.

#### Mode B: "Real-Time Replay" (For Testing Detection)

- **Purpose:** Simulating the event to test if your `thresholds.yml` triggers the correct alerts.
- **Constraint:** Timing. The system should inject delays to match the sampling rate (e.g., 1Hz or 10Hz).
- **Logic:** `await asyncio.sleep(diff)` between timestamps to simulate the actual event cadence.

### 3\. Agent Prompt / Spec

You can copy-paste this block directly to your coding agent (Aider/Goose):

> **Task: Implement Offline File Ingestion for VADASE Monitor**
> 
> **Context:** We need to analyze historical NMEA logs from large earthquakes locally without connecting to the live TCP stream.
> 
> **Requirements:**
> 
> 1. **Refactor Ingestion:** Abstract the input source. Create a `DataSource` interface. Move the existing TCP logic into `TcpSource`.
> 2. **New Module:** Create `src/sources/file_source.py`.
> 	- Input: File path (string).
> 	- Logic: Read file line-by-line.
> 3. **CLI Update:** Add a new command to `scripts/run_ingestor.py` (or a new script `scripts/replay_event.py`) using `typer` or `argparse`.
> 	- `uv run vadase-replay --file ./data/surigao_2023.nmea --mode import`
> 4. **Date Handling:** NMEA time often lacks the date. Add a CLI flag `--base-date "2023-12-02"` to resolve the timestamps correctly before inserting into TimescaleDB.
> 5. **Performance:** For `--mode import`, use `asyncpg`'s `copy_records_to_table` or batch inserts (batch size ~1000) rather than single-row inserts to handle large event files quickly.
> 6. **Idempotency:** Ensure that re-importing the same file doesn't crash the ingestor (handle `UniqueViolation` in Postgres gracefully or use `ON CONFLICT DO NOTHING`).

### 4\. TimescaleDB & Grafana Considerations

For the visualization to work effectively offline, the agent needs to ensure the Grafana queries are robust.

- **Grafana Dashboard:** The standard "Last 5 minutes" view won't show imported historical data.
- **Agent Task:** Ask the agent to generate a "Historical Analysis" dashboard JSON (or a variant of the main one) where the default time range is set to the file's timestamp extent, or ensure the current dashboard uses `$__timeFilter` correctly so you can manually select "December 2, 2023" to see the Surigao event.