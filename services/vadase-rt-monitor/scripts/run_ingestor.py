import asyncio
import yaml
import structlog
import typer
from src.adapters.inputs.tcp import TCPAdapter
from src.adapters.outputs.null import NullOutputPort
from src.domain.processor import IngestionCore

logger = structlog.get_logger()
app = typer.Typer()


async def run_service(config_path: str, dry_run: bool):
    """
    Main entry point for the VADASE RT-Monitor ingestor service.
    Hexagonal Architecture: NTRIP -> Queue -> IngestionCore -> OutputPort.
    """
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            stations = config.get('stations', [])
    except FileNotFoundError:
        print(f"Config file {config_path} not found.")
        return

    if not stations:
        print(f"No stations defined in {config_path}")
        return

    # TimescaleDBAdapter is imported lazily so asyncpg is never loaded on --dry-run.
    if dry_run:
        db_writer = NullOutputPort()
    else:
        from src.adapters.outputs.timescaledb import TimescaleDBAdapter
        db_writer = TimescaleDBAdapter()

    await db_writer.connect()

    tasks = []
    stop_events = []

    print(f"Starting ingestor for {len(stations)} stations (dry_run={dry_run})...")

    for s in stations:
        station_id = s['id']

        adapter = TCPAdapter(
            host=s['host'],
            port=s['port'],
            station_id=station_id,
            mountpoint=s.get('mountpoint'),
            user=s.get('user'),
            password=s.get('password')
        )

        filter_cfg = s.get('filter', {})
        decay = filter_cfg.get('decay', 0.99) if filter_cfg.get('enabled', False) else 1.0

        core = IngestionCore(
            station_id=station_id,
            output_port=db_writer,
            threshold_mm_s=s.get('threshold_mm_s', 15.0),
            decay_factor=decay
        )

        queue = asyncio.Queue(maxsize=100)
        stop_event = asyncio.Event()
        stop_events.append(stop_event)

        tasks.append(asyncio.create_task(adapter.start(queue, stop_event)))
        tasks.append(asyncio.create_task(core.consume(queue, stop_event)))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass
    finally:
        print("Shutting down...")
        for se in stop_events:
            se.set()
        await asyncio.sleep(1)
        await db_writer.close()


@app.command()
def main(
    config: str = typer.Option("config/stations.yml", "--config", "-c", help="Path to station config file"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Discard all DB writes (no asyncpg import)")
):
    try:
        asyncio.run(run_service(config, dry_run))
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    app()
