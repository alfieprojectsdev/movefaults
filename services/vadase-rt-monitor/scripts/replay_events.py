import asyncio
import typer
from pathlib import Path
from datetime import date
from typing import Optional
from src.sources.file import FileSource
from src.stream.processor import IngestionProcessor
from src.database.writer import DatabaseWriter

app = typer.Typer()

@app.command()
def main(
    file_path: Path = typer.Option(..., "--file", "-f", help="Path to NMEA file"),
    mode: str = typer.Option("import", "--mode", "-m", help="Mode: 'import' or 'replay'"),
    base_date: Optional[str] = typer.Option(None, "--base-date", "-d", help="Base date (YYYY-MM-DD)"),
    station_id: str = typer.Option("TEST", "--station", "-s", help="Station ID to assign"),
    threshold: float = typer.Option(15.0, "--threshold", help="Event detection threshold (mm/s)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Skip database writes"),
    plot: bool = typer.Option(False, "--plot", help="Enable live plotting (requires matplotlib)")
):
    """
    Ingest or replay NMEA data from a file.
    """
    if not file_path.exists():
        typer.echo(f"Error: File {file_path} not found.")
        raise typer.Exit(code=1)

    parsed_date = None
    if base_date:
        try:
            parsed_date = date.fromisoformat(base_date)
        except ValueError:
            typer.echo("Error: Invalid date format. Use YYYY-MM-DD.")
            raise typer.Exit(code=1)

    asyncio.run(run_async(file_path, mode, parsed_date, station_id, threshold, dry_run, plot))

class MockDbWriter:
    async def connect(self):
        typer.echo("MOCK DB: Connected.")

    async def close(self):
        typer.echo("MOCK DB: Closed.")

    async def write_velocity(self, station_id, data):
        typer.echo(f"MOCK DB: INSERT velocity station={station_id} time={data['timestamp']} vH={data.get('vH_magnitude', 0):.4f}")

    async def write_displacement(self, station_id, data):
        typer.echo(f"MOCK DB: INSERT displacement station={station_id} time={data['timestamp']} dH={data.get('dH_magnitude', 0):.4f}")

    async def write_event_detection(self, station, detection_time, peak_velocity, peak_displacement, duration):
        typer.echo(f"MOCK DB: EVENT DETECTED station={station} time={detection_time} peak_v={peak_velocity} duration={duration}")

class CompositeWriter:
    """Writes to both DB/Mock and Plotter"""
    def __init__(self, writers):
        self.writers = writers
    
    async def connect(self):
        for w in self.writers: await w.connect()
    
    async def close(self):
        for w in self.writers: await w.close()

    async def write_velocity(self, *args, **kwargs):
        for w in self.writers: await w.write_velocity(*args, **kwargs)

    async def write_displacement(self, *args, **kwargs):
        for w in self.writers: await w.write_displacement(*args, **kwargs)

    async def write_event_detection(self, *args, **kwargs):
        for w in self.writers: await w.write_event_detection(*args, **kwargs)

async def run_async(file_path: Path, mode: str, base_date: Optional[date], station_id: str, threshold: float, dry_run: bool, plot: bool):
    # Initialize components
    source = FileSource(file_path, mode=mode, base_date=base_date)
    
    writers = []
    
    if dry_run:
        typer.echo("Dry-run mode: Database writes disabled.")
        writers.append(MockDbWriter())
    else:
        db_writer = DatabaseWriter()
        writers.append(db_writer)
        
    if plot:
        try:
            from src.visualization.live_plot import LivePlotter
            typer.echo("Live Plotting: Enabled.")
            writers.append(LivePlotter())
        except ImportError:
            typer.echo("Error: Matplotlib not installed. Cannot plot.")
            if not dry_run: return # Exit if expecting plot but failed? Or continue?
            # actually better to just warn
    
    composite_writer = CompositeWriter(writers)
    
    # Connect all writers
    try:
        await composite_writer.connect()
    except Exception as e:
        typer.echo(f"Warning: Could not connect to writers: {e}")
        raise

    processor = IngestionProcessor(
        source=source,
        station_id=station_id,
        db_writer=composite_writer,
        threshold_mm_s=threshold
    )

    typer.echo(f"Starting {mode} from {file_path} for station {station_id}...")
    
    try:
        await processor.run()
        typer.echo("Processing complete.")
    except KeyboardInterrupt:
        typer.echo("Stopped by user.")
    except Exception as e:
        typer.echo(f"Error during processing: {e}")
    finally:
        await composite_writer.close()

if __name__ == "__main__":
    app()
