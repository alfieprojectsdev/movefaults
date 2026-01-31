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
@click.option("--trigger-ingestion", "-t", is_flag=True, help="Trigger RINEX ingestion for GNSS data files found")
def scan(path: Path, output: Path, resume: bool, trigger_ingestion: bool):
    """Scan a drive or directory and produce a JSONL file with metadata"""
    try:
        scanner = DeepScanner(path, output_file=output, resume=resume, trigger_ingestion=trigger_ingestion)
        scanner.scan()
    except KeyboardInterrupt:
        console.print("\n[yellow]Warning: Scan interrupted by user[/yellow]")
        console.print("[yellow]Progress saved. Use --resume to continue[/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort()


if __name__ == "__main__":
    main()
