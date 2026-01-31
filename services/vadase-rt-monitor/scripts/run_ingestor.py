import asyncio
import yaml
import structlog
from src.adapters.inputs.tcp import TCPAdapter
from src.domain.processor import IngestionCore
from src.database.writer import DatabaseWriter
from src.ports.outputs import OutputPort

logger = structlog.get_logger()

# We need a concrete OutputPort that wraps DatabaseWriter to satisfy the protocol
# Or rely on DatabaseWriter duck-typing checking out (it generally does).
# Let's assume duck-typing works or explicitly verify/wrap if needed.
# Since DatabaseWriter matches OutputPort signature, we can use it directly.

async def main():
    """
    Main entry point for the VADASE RT-Monitor ingestor service.
    Refactored for Hexagonal Architecture (NTRIP -> Queue -> Core).
    """
    try:
        with open('config/stations.yml', 'r') as f:
            config = yaml.safe_load(f)
            stations = config.get('stations', [])
    except FileNotFoundError:
        print("Config file config/stations.yml not found.")
        return

    if not stations:
        print("No stations defined in config/stations.yml")
        return

    # Initialize shared database writer (or one per station? Usually one shared pool)
    # The existing writer seems designed to be shared or singleton-like connection-wise
    db_writer = DatabaseWriter()
    await db_writer.connect() # Ensure pool is up

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

        core = IngestionCore(
            station_id=station_id,
            output_port=db_writer,
            threshold_mm_s=s.get('threshold_mm_s', 15.0)
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

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
