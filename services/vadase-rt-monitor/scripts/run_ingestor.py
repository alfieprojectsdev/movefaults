import asyncio
import os
import re
import yaml
import structlog
import typer
from dotenv import load_dotenv
from src.adapters.inputs.tcp import TCPAdapter
from src.domain.processor import IngestionCore
from src.database.writer import DatabaseWriter
from src.ports.outputs import OutputPort

logger = structlog.get_logger()
app = typer.Typer()

class MockDbWriter(OutputPort):
    async def connect(self):
        logger.info("MOCK DB: Connected.")

    async def close(self):
        logger.info("MOCK DB: Closed.")

    async def write_velocity(self, station_id, data):
        logger.info("MOCK: VEL", time=data['timestamp'], vH=data.get('vH_magnitude'))

    async def write_displacement(self, station_id, data):
        logger.info("MOCK: DSP", time=data['timestamp'], dH=data.get('dH_magnitude'))

    async def write_event_detection(self, station, detection_time, peak_velocity, peak_displacement, duration):
        logger.warning(f"MOCK: EVENT DETECTED: {detection_time} PeakV={peak_velocity}")

def expand_env_vars(content: str) -> str:
    """
    Replaces ${VAR_NAME} with environment variable values.
    If variable is not set, it keeps the placeholder.
    """
    pattern = re.compile(r'\$\{([^}]+)\}')
    return pattern.sub(lambda m: os.getenv(m.group(1), m.group(0)), content)

async def run_service(config_path: str, dry_run: bool):
    """
    Main entry point for the VADASE RT-Monitor ingestor service.
    Refactored for Hexagonal Architecture (NTRIP -> Queue -> Core).
    """
    try:
        with open(config_path, 'r') as f:
            content = f.read()
            expanded_content = expand_env_vars(content)
            config = yaml.safe_load(expanded_content)
            stations = config.get('stations', [])
    except FileNotFoundError:
        print(f"Config file {config_path} not found.")
        return
    
    if not stations:
        print(f"No stations defined in {config_path}")
        return

    # Initialize Output Port
    if dry_run:
        db_writer = MockDbWriter()
    else:
        db_writer = DatabaseWriter()
    
    await db_writer.connect()

    tasks = []
    stop_events = []

    print(f"Starting ingestor for {len(stations)} stations (Dry Run: {dry_run})...")

    tasks = []
    stop_events = []

    print(f"Starting ingestor for {len(stations)} stations...")

    for s in stations:
        station_id = s['id']
        
        # 1. Setup Hexagon Components
        adapter = TCPAdapter(
            host=s['host'],
            port=s['port'],
            station_id=station_id,
            mountpoint=s.get('mountpoint'), # Optional NTRIP fields
            user=s.get('user'),
            password=s.get('password')
        )

        # Extract Filter Config
        filter_cfg = s.get('filter', {})
        decay = filter_cfg.get('decay', 0.99) if filter_cfg.get('enabled', False) else 1.0

        core = IngestionCore(
            station_id=station_id,
            output_port=db_writer,
            threshold_mm_s=s.get('threshold_mm_s', 15.0),
            decay_factor=decay
        )

        # 2. Wiring
        queue = asyncio.Queue(maxsize=100)
        stop_event = asyncio.Event()
        stop_events.append(stop_event)

        # 3. Launch Tasks
        # Producer (NTRIP -> Queue)
        tasks.append(asyncio.create_task(adapter.start(queue, stop_event)))
        
        # Consumer (Queue -> Processing -> DB)
        tasks.append(asyncio.create_task(core.consume(queue, stop_event)))

    try:
        # Run everything
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        print("Shutting down...")
        for se in stop_events:
            se.set()
        # Allow cleanup time
        await asyncio.sleep(1)
        await db_writer.close()

@app.command()
def main(
    config: str = typer.Option("config/stations.yml", "--config", "-c", help="Path to station config file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Use Mock DB instead of Postgres")
):
    load_dotenv()
    try:
        asyncio.run(run_service(config, dry_run))
    except KeyboardInterrupt:
        pass

if __name__ == '__main__':
    app()
