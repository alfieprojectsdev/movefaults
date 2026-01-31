import asyncio
import typer
from pathlib import Path
from datetime import date
from typing import Optional

from src.strategies.playback import RealTimeStrategy, FastImportStrategy
from src.adapters.inputs.directory import DirectoryAdapter
from src.domain.processor import IngestionCore
from src.database.writer import DatabaseWriter

app = typer.Typer()

@app.command()
def main(
    file_path: Path = typer.Option(..., "--file", "-f", help="Path to NMEA file or directory"),
    mode: str = typer.Option("import", "--mode", "-m", help="Mode: 'import' or 'replay'"),
    base_date: Optional[str] = typer.Option(None, "--base-date", "-d", help="Base date (YYYY-MM-DD)"),
    station_id: str = typer.Option("TEST", "--station", "-s", help="Station ID to assign"),
    threshold: float = typer.Option(15.0, "--threshold", help="Event detection threshold (mm/s)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip database writes"),
    plot: bool = typer.Option(False, "--plot", help="Enable live plotting"),
    pattern: str = typer.Option("*.rtl", "--pattern", "-p", help="File pattern to match in directory (e.g. *.rtl)")
):
    if not file_path.exists():
        typer.echo(f"Error: {file_path} not found.")
        raise typer.Exit(code=1)

    parsed_date = None
    if base_date:
        try:
            parsed_date = date.fromisoformat(base_date)
        except ValueError:
            typer.echo("Error: Invalid date.")
            raise typer.Exit(code=1)

            typer.echo("Error: Invalid date.")
            raise typer.Exit(code=1)

    asyncio.run(run_async(file_path, mode, parsed_date, station_id, threshold, dry_run, plot, pattern))

# --- MOCK / COMPOSITE WRITER ---
# (Keeping concise for this rewrite, but reusing logic)
class MockDbWriter:
    async def connect(self): typer.echo("MOCK DB: Connected.")
    async def close(self): typer.echo("MOCK DB: Closed.")
    async def write_velocity(self, s, d): typer.echo(f"MOCK: VEL {d['timestamp']} vH={d.get('vH_magnitude',0):.4f}")
    async def write_displacement(self, s, d): typer.echo(f"MOCK: DSP {d['timestamp']}")
    async def write_event_detection(self, s, t, pv, pd, dur): typer.echo("MOCK: EVENT")

class CompositeWriter:
    def __init__(self, writers): self.writers = writers
    async def connect(self): 
        for w in self.writers: await w.connect()
    async def close(self): 
        for w in self.writers: await w.close()
    async def write_velocity(self, *a, **k): 
        for w in self.writers: await w.write_velocity(*a, **k)
    async def write_displacement(self, *a, **k): 
        for w in self.writers: await w.write_displacement(*a, **k)
    async def write_event_detection(self, *a, **k): 
        for w in self.writers: await w.write_event_detection(*a, **k)

async def run_async(path: Path, mode: str, base_date: Optional[date], station_id: str, threshold: float, dry_run: bool, plot: bool, pattern: str):
    # 1. Select Strategy
    if mode == "replay":
        strategy = RealTimeStrategy(base_date=base_date)
    else:
        strategy = FastImportStrategy()

    # 2. Configure Input Adapter
    # Handle single file vs directory
    if path.is_file():
        # Adapter handles single file if pattern matches name, or we explicitly use parent/name
        adapter = DirectoryAdapter(directory=path.parent, strategy=strategy, pattern=path.name)
    else:
        adapter = DirectoryAdapter(directory=path, strategy=strategy, pattern=pattern)

    # 3. Configure Output Adapter
    writers = []
    if dry_run: writers.append(MockDbWriter())
    else: writers.append(DatabaseWriter())
    
    if plot:
        try:
            from src.visualization.live_plot import LivePlotter
            writers.append(LivePlotter())
        except ImportError:
            typer.echo("Matplotlib missing.")

    output_port = CompositeWriter(writers)

    # 4. Wiring (The Hexagon)
    queue = asyncio.Queue(maxsize=1000)
    stop_event = asyncio.Event()

    core = IngestionCore(
        station_id=station_id, 
        output_port=output_port, 
        threshold_mm_s=threshold
    )

    typer.echo(f"System Start: {mode.upper()} mode on {path}")
    
    # Run Producer and Consumer concurrently
    producer_task = asyncio.create_task(adapter.start(queue, stop_event))
    consumer_task = asyncio.create_task(core.consume(queue, stop_event))

    try:
        # Wait for producer to finish (it yields None when done)
        await producer_task
        # Wait for consumer to empty queue and see None
        await consumer_task
        typer.echo("System Finished Normally.")
    except KeyboardInterrupt:
        typer.echo("Stopping...")
        stop_event.set()
        await asyncio.gather(producer_task, consumer_task, return_exceptions=True)

if __name__ == "__main__":
    app()
