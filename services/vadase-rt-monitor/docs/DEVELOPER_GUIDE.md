# Developer & Researcher Guide

This guide explains how to extend the VADASE Real-Time Monitor and use the included toolset for geodetic research.

## 1. Extending the System

The Hexagonal Architecture makes it easy to add new functionality without modifying the core ingestion logic.

### Adding a New Output Adapter
If you want to send data to a new destination (e.g., a real-time Kafka stream or a different database), follow these steps:
1.  **Define the Interface**: Ensure your new class implements the `OutputPort` protocol found in `src/ports/outputs.py`.
2.  **Implement the Logic**: Create a new file in `src/adapters/outputs/` (e.g., `kafka_adapter.py`).
3.  **Update the Runner**: Instantiate your new adapter in `scripts/run_ingestor.py`.

### Implementing a Custom Detection Heuristic
The current earthquake detection is based on a simple horizontal velocity threshold. To implement a more advanced algorithm (e.g., STA/LTA or Machine Learning based):
1.  Modify `src/domain/processor.py`.
2.  Update the `check_event_threshold` method or add a new method to the `IngestionCore` class.
3.  Use the `peak_velocity` and `peak_displacement` state variables to track the event progress.

## 2. Research Tools (`scripts/`)

For graduate students, the scripts in the `scripts/` directory are the most valuable for data analysis.

### `replay_events.py`: Offline Analysis
Use this to analyze historical earthquake logs.
- **Why**: It allows you to tune thresholds and integration decay factors without needing real-time data.
- **Key Flag**: `--plot` uses Matplotlib to show live charts of the velocity and displacement, which is great for visual verification of wave arrivals.

### `mock_ntrip_caster.py`: Network Simulation
Simulates an NTRIP (Networked Transport of RTCM via Internet Protocol) stream.
- **Why**: Allows you to test the system's network resilience and TCP reconnection logic on your local machine.

### `stress_test_parallel.py`: Scalability Testing
Launches multiple concurrent ingestion cores.
- **Why**: If you are adding more CORS stations to the network, use this to determine the CPU and Memory ceiling of your server.

## 3. Jupyter Notebooks (`notebooks/`)

The repository includes two template notebooks for high-level research:
- `event_validation.ipynb`: Compare the monitor's detected peaks against official seismic catalogs (e.g., USGS or PHIVOLCS records).
- `poster_reproduction.ipynb`: Replicates the time-series charts used in the GEOCON 2025 conference poster.

## 4. Coding Standards
- **Type Hinting**: All new code should use Python type hints to ensure compatibility with `mypy`.
- **Async Safety**: Since the system is highly concurrent, avoid blocking calls (like `time.sleep()`) in the core; always use `await asyncio.sleep()`.
- **Logging**: Use the `self.logger` (powered by `structlog`) to emit structured JSON logs. This allows for easy log analysis using ELK stack or Grafana Loki.
