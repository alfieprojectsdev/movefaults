import asyncio
import typer
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from src.strategies.playback import RealTimeStrategy, FastImportStrategy
from src.adapters.inputs.directory import DirectoryAdapter
from src.adapters.outputs.null import NullOutputPort
from src.domain.processor import IngestionCore

app = typer.Typer()

# ---------------------------------------------------------------------------
# Console banner (ANSI — zero extra deps)
# ---------------------------------------------------------------------------

_RED   = "\033[1;31m"
_RESET = "\033[0m"
_BOLD  = "\033[1m"
_SEP   = f"{_RED}{'━' * 62}{_RESET}"


def _print_event_banner(
    station: str,
    detection_time: datetime,
    peak_velocity: float,
    peak_displacement: float,
    duration: float,
) -> None:
    time_str = detection_time.strftime("%Y-%m-%d %H:%M:%S UTC")
    print()
    print(_SEP)
    print(
        f"{_RED}{_BOLD}  ⚠  SEISMIC EVENT DETECTED{_RESET}"
        f"                       [{_BOLD}{station}{_RESET}]"
    )
    print(_SEP)
    print(f"  Detection   {time_str}")
    print(
        f"  Peak vel  {_BOLD}{peak_velocity:>8.1f} mm/s{_RESET}"
        f"   │   Peak disp  {_BOLD}{peak_displacement:>7.1f} mm{_RESET}"
        f"   │   Duration  {duration:.0f} s"
    )
    print(_SEP)
    print()


class _DemoEventPort:
    """Wraps an OutputPort to fire the console banner on write_event_detection."""

    def __init__(self, wrapped):
        self._wrapped = wrapped

    async def connect(self):
        await self._wrapped.connect()

    async def close(self):
        await self._wrapped.close()

    async def write_velocity(self, *a, **k):
        await self._wrapped.write_velocity(*a, **k)

    async def write_displacement(self, *a, **k):
        await self._wrapped.write_displacement(*a, **k)

    async def write_event_detection(
        self, station, detection_time, peak_velocity, peak_displacement, duration
    ):
        await self._wrapped.write_event_detection(
            station, detection_time, peak_velocity, peak_displacement, duration
        )
        _print_event_banner(station, detection_time, peak_velocity, peak_displacement, duration)


class _CompositeWriter:
    """Fan-out to multiple OutputPort instances (e.g. DB + LivePlotter)."""

    def __init__(self, writers):
        self.writers = writers

    async def connect(self):
        for w in self.writers:
            await w.connect()

    async def close(self):
        for w in self.writers:
            await w.close()

    async def write_velocity(self, *a, **k):
        for w in self.writers:
            await w.write_velocity(*a, **k)

    async def write_displacement(self, *a, **k):
        for w in self.writers:
            await w.write_displacement(*a, **k)

    async def write_event_detection(self, *a, **k):
        for w in self.writers:
            await w.write_event_detection(*a, **k)


async def run_async(
    path: Path,
    mode: str,
    base_date: Optional[date],
    station_id: str,
    threshold: float,
    dry_run: bool,
    plot: bool,
    pattern: str,
    force_integration: bool,
    decay_factor: float,
    window_size: int,
):
    strategy = RealTimeStrategy(base_date=base_date) if mode == "replay" else FastImportStrategy()

    if path.is_file():
        adapter = DirectoryAdapter(directory=path.parent, strategy=strategy, pattern=path.name)
    else:
        adapter = DirectoryAdapter(directory=path, strategy=strategy, pattern=pattern)

    # TimescaleDBAdapter imported lazily: asyncpg never loads on --dry-run.
    if dry_run:
        primary = NullOutputPort()
    else:
        from src.adapters.outputs.timescaledb import TimescaleDBAdapter
        primary = TimescaleDBAdapter()

    writers = [primary]

    if plot:
        try:
            from src.visualization.live_plot import LivePlotter
            writers.append(LivePlotter(window_size=window_size))
        except ImportError:
            typer.echo("matplotlib not installed — skipping live plot.")

    base_port = writers[0] if len(writers) == 1 else _CompositeWriter(writers)
    # Always wrap in _DemoEventPort: replay_events.py is a demo/analysis tool.
    output_port = _DemoEventPort(base_port)

    queue = asyncio.Queue(maxsize=1000)
    stop_event = asyncio.Event()

    core = IngestionCore(
        station_id=station_id,
        output_port=output_port,
        threshold_mm_s=threshold,
        force_integration=force_integration,
        decay_factor=decay_factor,
    )

    typer.echo(f"Starting {mode.upper()} replay: {path}")

    producer_task = asyncio.create_task(adapter.start(queue, stop_event))
    consumer_task = asyncio.create_task(core.consume(queue, stop_event))

    try:
        await producer_task
        await consumer_task
        typer.echo("Replay complete.")
    except KeyboardInterrupt:
        typer.echo("Stopping...")
        stop_event.set()
        await asyncio.gather(producer_task, consumer_task, return_exceptions=True)


@app.command()
def main(
    file_path: Path = typer.Option(..., "--file", "-f", help="Path to NMEA file or directory"),
    mode: str = typer.Option("import", "--mode", "-m", help="'import' (fast) or 'replay' (1 Hz)"),
    base_date: Optional[str] = typer.Option(None, "--base-date", "-d", help="Base date YYYY-MM-DD"),
    station_id: str = typer.Option("TEST", "--station", "-s", help="Station ID"),
    threshold: float = typer.Option(15.0, "--threshold", help="Event threshold mm/s"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Discard DB writes (no asyncpg import)"),
    plot: bool = typer.Option(False, "--plot", help="Live matplotlib ENU plot"),
    pattern: str = typer.Option("*.rtl", "--pattern", "-p", help="File glob inside directory"),
    force_integration: bool = typer.Option(False, "--force-integration", help="Force MANUAL mode"),
    decay: float = typer.Option(1.0, "--decay", help="Leaky integrator decay factor"),
    window_size: int = typer.Option(600, "--window-size", "-w", help="Plot window size (samples)"),
):
    if not file_path.exists():
        typer.echo(f"Error: {file_path} not found.")
        raise typer.Exit(code=1)

    parsed_date = None
    if base_date:
        try:
            parsed_date = date.fromisoformat(base_date)
        except ValueError:
            typer.echo("Error: Invalid date format. Use YYYY-MM-DD.")
            raise typer.Exit(code=1)

    asyncio.run(
        run_async(
            file_path, mode, parsed_date, station_id, threshold,
            dry_run, plot, pattern, force_integration, decay, window_size,
        )
    )


if __name__ == "__main__":
    app()
