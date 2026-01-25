"""
Core scanner implementation with resume capability and progress tracking.
Streams results to JSONL format for memory efficiency.
Includes support for scanning inside archives.
"""

import json
import time
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .archive_handler import ArchiveHandler
from .classifier import Classifier
from .utils.checkpoint import CheckpointManager
from .utils.paths import sanitize_for_json, should_skip_path

console = Console()


class DeepScanner:
    """
    Recursively scan a directory tree, including archives, and output file metadata to JSONL.
    """

    def __init__(self, root_path: Path, output_file: Optional[Path] = None, resume: bool = False):
        self.root = Path(root_path).resolve()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.scan_id = self.root.name.replace("/", "_").replace("\\", "_")

        if output_file:
            self.output_file = Path(output_file)
        else:
            self.output_file = Path(f"scan_{self.scan_id}_{self.timestamp}.jsonl")

        self.log_file = self.output_file.with_suffix(".log")
        self.checkpoint = CheckpointManager(self.scan_id) if resume else None
        self.classifier = Classifier()
        self.archive_handler = ArchiveHandler()

        self.file_count = 0
        self.error_count = 0
        self.skipped_count = 0
        self.start_time = time.time()
        self.progress: Optional[Progress] = None
        self.task = None

    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] {message}"
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
        except Exception:
            # Errors during logging shouldn't crash the scan
            console.print(f"[red]Error writing to log file: {log_line}[/red]")

    def scan(self):
        """Main scanning loop with progress tracking"""
        self.log(f"Starting deep scan of: {self.root}")
        self.log(f"Output: {self.output_file}")
        console.print(f"[bold blue]Scanning:[/bold blue] {self.root}")
        console.print(f"[bold green]Output:[/bold green] {self.output_file}")

        mode = "a" if self.checkpoint else "w"
        with open(self.output_file, mode, encoding="utf-8") as outfile:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.completed} files"),
                TimeElapsedColumn(),
                console=console,
            ) as progress:
                self.progress = progress
                self.task = self.progress.add_task("[cyan]Scanning...", total=None)
                self._scan_directory(self.root, outfile)

        self._print_summary()

    def _scan_directory(self, dir_path: Path, outfile, archive_path: Optional[Path] = None):
        """Recursively scan a directory."""
        for filepath in dir_path.iterdir():
            if self.checkpoint and self.checkpoint.is_scanned(filepath):
                continue

            if should_skip_path(filepath):
                self.skipped_count += 1
                continue

            try:
                if filepath.is_file():
                    self._process_file(filepath, outfile, archive_path)
                elif filepath.is_dir():
                    self._scan_directory(filepath, outfile, archive_path)
            except (PermissionError, OSError) as e:
                self.error_count += 1
                self.log(f"Error accessing {filepath}: {e}")

    def _process_file(self, filepath: Path, outfile, archive_path: Optional[Path] = None):
        """Process a single file, handling archives recursively."""
        try:
            metadata = self._extract_metadata(filepath, archive_path)
            outfile.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            outfile.flush()
            self.file_count += 1

            if self.progress and self.task is not None:
                self.progress.update(self.task, advance=1, description=f"[cyan]Scanning... ({self.file_count} files)")

            if self.archive_handler.is_archive(filepath):
                self.log(f"Found archive: {filepath}. Extracting...")
                temp_dir = self.archive_handler.extract(filepath)
                if temp_dir:
                    self.log(f"Successfully extracted to: {temp_dir}")
                    self._scan_directory(temp_dir, outfile, archive_path=filepath)
                    shutil.rmtree(temp_dir, ignore_errors=True)
                    self.log(f"Cleaned up temporary directory: {temp_dir}")
                else:
                    self.log(f"Failed to extract archive: {filepath}", level="WARNING")

            if self.checkpoint and self.file_count % 1000 == 0:
                self.checkpoint.mark_scanned(filepath)
                self.checkpoint.save_checkpoint()
                self.log(f"Checkpoint saved ({self.file_count} files)")

        except Exception as e:
            self.error_count += 1
            self.log(f"Unexpected error processing {filepath}: {e}")

    def _extract_metadata(self, filepath: Path, archive_path: Optional[Path] = None) -> dict:
        """Extract file metadata."""
        stat = filepath.stat()
        category = self.classifier.classify(filepath)

        data = {
            "path": sanitize_for_json(str(filepath.absolute())),
            "name": filepath.name,
            "extension": filepath.suffix.lower(),
            "category": category,
            "size_bytes": stat.st_size,
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
            "parent_dir": sanitize_for_json(str(filepath.parent)),
            "depth": len(filepath.relative_to(self.root).parts) if not archive_path else None,
            "scan_timestamp": datetime.now().isoformat(),
            "in_archive": bool(archive_path),
            "archive_path": sanitize_for_json(str(archive_path)) if archive_path else None,
        }
        return data

    def _print_summary(self):
        """Print final statistics"""
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        rate = self.file_count / elapsed if elapsed > 0 else 0

        console.print("\n" + "=" * 60)
        console.print("[bold green]Scan Complete![/bold green]")
        console.print(f"[bold]Files processed:[/bold] {self.file_count:,}")
        console.print(f"[bold]Files skipped:[/bold] {self.skipped_count:,}")
        console.print(f"[bold yellow]Errors:[/bold yellow] {self.error_count}")
        console.print(f"[bold]Time elapsed:[/bold] {elapsed_str}")
        console.print(f"[bold]Rate:[/bold] {rate:.1f} files/sec")
        console.print(f"[bold green]Results:[/bold green] {self.output_file}")
        console.print(f"[bold blue]Log:[/bold blue] {self.log_file}")
        console.print("=" * 60 + "\n")
        self.log("=" * 60)
        self.log("Scan Complete!")
        self.log(f"Files processed: {self.file_count:,}")
        self.log(f"Files skipped: {self.skipped_count:,}")
        self.log(f"Errors: {self.error_count}")
        self.log(f"Time elapsed: {elapsed_str}")
        self.log(f"Rate: {rate:.1f} files/sec")
        self.log("=" * 60)