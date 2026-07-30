import asyncio
import typer
import random
import structlog
from pathlib import Path
from typing import List, Optional
from datetime import date

from src.strategies.playback import RealTimeStrategy, FastImportStrategy
from src.adapters.inputs.directory import DirectoryAdapter
from src.adapters.outputs.composite import CompositeOutputPort
from src.domain.processor import IngestionCore
from src.ports.outputs import OutputPort

app = typer.Typer()
logger = structlog.get_logger()

class StressTestWriter(OutputPort):
    async def connect(self): pass
    async def close(self): pass
    async def write_velocity(self, station_id, data): pass
    async def write_displacement(self, station_id, data): pass
    async def write_event_detection(self, station, t, pv, pd, dur):
        logger.warning("EVENT DETECTED", station=station, peak_v=pv)

async def run_station(file_path: Path, station_id: str, mode: str, base_date: Optional[date], force_integration: bool, enable_plot: bool):
    try:
        if mode == "replay":
            strategy = RealTimeStrategy(base_date=base_date)
        else:
            strategy = FastImportStrategy()

        adapter = DirectoryAdapter(directory=file_path.parent, strategy=strategy, pattern=file_path.name)

        writers = [StressTestWriter()]
        
        # Enable plotting ONLY for SIM_01 to respect single-thread GUI limitations
        # unless user really wants chaos (but we'll stick to 1 for stability)
        if enable_plot and station_id == "SIM_01":
            try:
                from src.visualization.live_plot import LivePlotter
                writers.append(LivePlotter())
                logger.info("plotting_enabled", station=station_id)
            except ImportError:
                logger.warning("matplotlib_missing")

        output_port = CompositeOutputPort(writers)
        
        queue = asyncio.Queue(maxsize=100)
        stop_event = asyncio.Event()

        core = IngestionCore(
            station_id=station_id,
            output_port=output_port,
            force_integration=force_integration
        )

        logger.info("station_starting", station=station_id, file=file_path.name)

        # Composition root owns the port lifecycle (consume() no longer does).
        await output_port.connect()
        try:
            producer = asyncio.create_task(adapter.start(queue, stop_event))
            consumer = asyncio.create_task(core.consume(queue, stop_event))
            await asyncio.gather(producer, consumer)
        finally:
            await output_port.close()
        logger.info("station_finished", station=station_id)

    except Exception as e:
        logger.error("station_error", station=station_id, error=str(e))

@app.command()
def main(
    data_dir: Path = typer.Option(..., "--data-dir", "-d", help="Directory containing .rtl files"),
    count: int = typer.Option(6, "--count", "-n", help="Number of files to run in parallel"),
    mode: str = typer.Option("import", "--mode", "-m", help="Mode: 'import' or 'replay'"),
    force_integration: bool = typer.Option(False, "--force-integration", help="Force manual integration"),
    plot: bool = typer.Option(False, "--plot", help="Enable plotting (for SIM_01 only)")
):
    """
    Runs a parallel stress test.
    """
    if not data_dir.exists():
        typer.echo(f"Error: {data_dir} not found.")
        raise typer.Exit(1)

    files = list(data_dir.glob("*.rtl"))
    if not files:
        typer.echo("No .rtl files found.")
        raise typer.Exit(1)
    
    selected_files = random.sample(files, min(count, len(files)))
    
    logger.info("starting_stress_test", station_count=len(selected_files), mode=mode, plot=plot)

    async def orchestrator():
        tasks = []
        for i, file_path in enumerate(selected_files):
            station_id = f"SIM_{i+1:02d}"
            parsed_date = date(2025, 10, 10) 
            tasks.append(run_station(file_path, station_id, mode, parsed_date, force_integration, plot))
        
        await asyncio.gather(*tasks)

    asyncio.run(orchestrator())

if __name__ == "__main__":
    app()
