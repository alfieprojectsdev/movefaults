import asyncio
import yaml
from src.sources.tcp import TcpSource
from src.stream.processor import IngestionProcessor
from src.database.writer import DatabaseWriter

async def main():
    """
    Main entry point for the VADASE RT-Monitor ingestor service
    """
    # Load station configurations
    with open('config/stations.yml', 'r') as f:
        config = yaml.safe_load(f)
        stations = config.get('stations', [])

    if not stations:
        print("No stations defined in config/stations.yml")
        return

    # Initialize database writer
    db_writer = DatabaseWriter()
    await db_writer.connect()

    # Create a task for each station handler
    tasks = []
    for s in stations:
        source = TcpSource(
            host=s['host'],
            port=s['port'],
            station_id=s['id']
        )
        
        processor = IngestionProcessor(
            source=source,
            station_id=s['id'],
            db_writer=db_writer,
            threshold_mm_s=s.get('threshold_mm_s', 15.0)
        )
        
        # Processor.run() handles connection and infinite loop
        tasks.append(processor.run())

    print(f"Starting ingestor for {len(stations)} stations...")
    await asyncio.gather(*tasks)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Ingestor stopped by user.")
