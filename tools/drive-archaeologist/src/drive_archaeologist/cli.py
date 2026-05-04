"""
CLI interface for drive-archaeologist using Click framework.
Provides the main 'scan' command for Phase 0.
"""

from pathlib import Path

import click
from rich.console import Console

from .scanner import DeepScanner

console = Console()


@click.group()
@click.version_option(version="0.1.0")
def main():
    """Drive Archaeologist - Excavate decades of data from old hard drives"""
    pass


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output file path (default: scan_<name>_<timestamp>.jsonl)",
)
@click.option("--resume", "-r", is_flag=True, help="Resume a previous interrupted scan")
@click.option(
    "--ingest", is_flag=True, help="Dispatch classified GNSS files to the ingestion pipeline"
)
@click.option(
    "--dry-run", is_flag=True, help="Log what would be dispatched without sending to Celery"
)
def scan(path: Path, output: Path | None, resume: bool, ingest: bool, dry_run: bool):
    """Scan a drive or directory and produce a JSONL file with metadata"""
    on_classified = None
    if ingest or dry_run:
        from .ingestion_dispatch import make_dispatch_callback

        on_classified = make_dispatch_callback(dry_run=dry_run)

    try:
        scanner = DeepScanner(path, output_file=output, resume=resume, on_classified=on_classified)
        scanner.scan()
    except KeyboardInterrupt:
        console.print("\n[yellow]Warning: Scan interrupted by user[/yellow]")
        console.print("[yellow]Progress saved. Use --resume to continue[/yellow]")
        raise click.Abort() from None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from None


if __name__ == "__main__":
    main()
