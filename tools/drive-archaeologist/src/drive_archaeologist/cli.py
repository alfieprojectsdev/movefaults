"""
CLI interface for drive-archaeologist using Click framework.
Provides the 'scan' command (full JSONL catalog) and the 'survey'
command (fast wipe/keep triage, DA-003).
"""

from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

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
@click.option("--force", is_flag=True, help="Overwrite an existing output file (otherwise refused)")
@click.option(
    "--include-hidden",
    is_flag=True,
    help="Also scan hidden (dot-prefixed) and system entries ($RECYCLE.BIN, .Trash*, ...)",
)
@click.option(
    "--exclude",
    "-x",
    "excludes",
    multiple=True,
    help="Glob (relative to scan root, or bare name) to skip; repeatable",
)
@click.option(
    "--max-archive-depth",
    type=int,
    default=3,
    show_default=True,
    help="How many levels of nested archives to extract (0 = never extract)",
)
@click.option(
    "--ingest", is_flag=True, help="Dispatch classified GNSS files to the ingestion pipeline"
)
@click.option(
    "--dry-run", is_flag=True, help="Log what would be dispatched without sending to Celery"
)
def scan(
    path: Path,
    output: Path | None,
    resume: bool,
    force: bool,
    include_hidden: bool,
    excludes: tuple[str, ...],
    max_archive_depth: int,
    ingest: bool,
    dry_run: bool,
):
    """Scan a drive or directory and produce a JSONL file with metadata"""
    on_classified = None
    if ingest or dry_run:
        from .ingestion_dispatch import make_dispatch_callback

        on_classified = make_dispatch_callback(dry_run=dry_run)

    try:
        scanner = DeepScanner(
            path,
            output_file=output,
            resume=resume,
            on_classified=on_classified,
            include_hidden=include_hidden,
            excludes=list(excludes),
            max_archive_depth=max_archive_depth,
            force=force,
        )
        scanner.scan()
    except KeyboardInterrupt:
        console.print("\n[yellow]Warning: Scan interrupted by user[/yellow]")
        console.print("[yellow]Progress saved. Use --resume to continue[/yellow]")
        raise click.Abort() from None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from None


@main.command()
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--include-hidden/--no-include-hidden",
    default=True,
    show_default=True,
    help="Survey hidden/system entries too (a stick whose content sits in .Trash-1000 "
    "would otherwise read as empty)",
)
@click.option(
    "--exclude",
    "-x",
    "excludes",
    multiple=True,
    help="Glob (relative to survey root, or bare name) to skip; repeatable",
)
@click.option(
    "--extract-archives",
    is_flag=True,
    help="Also look inside archives (slower; extracts to $TMPDIR)",
)
@click.option("--top", type=int, default=12, show_default=True, help="Rows in the category table")
def survey(
    path: Path,
    include_hidden: bool,
    excludes: tuple[str, ...],
    extract_archives: bool,
    top: int,
):
    """Fast triage: what's on this drive, and is it safe to wipe?

    Walks once with the same classifier as `scan` but writes NO catalog,
    computes NO hashes, and (by default) opens NO archives. Prints a
    category/extension breakdown and a wipe/keep verdict with explicit
    disclosure of anything the walk did not cover.
    """
    try:
        scanner = DeepScanner(
            path,
            stats_only=True,
            include_hidden=include_hidden,
            excludes=list(excludes),
            max_archive_depth=1 if extract_archives else 0,
        )
        scanner.scan()
    except KeyboardInterrupt:
        console.print("\n[yellow]Survey interrupted[/yellow]")
        raise click.Abort() from None
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise click.Abort() from None

    stats = scanner.stats
    table = Table(title=f"Survey: {path}")
    table.add_column("Category", style="cyan")
    table.add_column("Files", justify="right")
    table.add_column("Top extensions", style="dim")
    for category, count in stats.categories.most_common(top):
        exts = [
            e
            for e, _ in stats.extensions.most_common()
            if scanner.classifier.classify_by_ext(e) == category
        ][:4]
        table.add_row(category, f"{count:,}", " ".join(exts))
    console.print(table)
    console.print(
        f"[bold]Total:[/bold] {scanner.file_count:,} files, {stats.total_bytes / (1024**3):.2f} GiB"
    )

    verdict, warnings = scanner.survey_verdict()
    for w in warnings:
        console.print(f"[yellow]⚠ {w}[/yellow]")
    color = "red" if stats.gnss_files or stats.metadata_inconsistent else "green"
    console.print(f"[bold {color}]Verdict: {verdict}[/bold {color}]")


@main.command()
def tui():
    """Launch the interactive TUI (drive picker + survey).

    Requires the optional TUI dependencies:
    uv sync --extra drive-archaeologist-tui
    """
    try:
        from .tui.app import run_tui
    except ModuleNotFoundError as e:
        if e.name and e.name.startswith("textual"):
            console.print(
                "[red]Textual is not installed — install the TUI extra first:[/red]\n"
                "  uv sync --extra drive-archaeologist-tui"
            )
            raise click.Abort() from None
        raise
    run_tui()


if __name__ == "__main__":
    main()
