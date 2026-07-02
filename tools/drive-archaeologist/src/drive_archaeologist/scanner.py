"""
Core scanner implementation with resume capability and progress tracking.
Streams results to JSONL format for memory efficiency.
Includes support for scanning inside archives.

Hardened against corrupt filesystems (DA-002): capacity-sanity gate for
bogus directory-entry sizes, mojibake filename detection, symlink
non-traversal, itemized skip reporting, exclude globs, archive recursion
depth cap, and an output clobber guard. Also provides a stats-only mode
backing the `survey` CLI (DA-003).
"""

import fnmatch
import json
import os
import shutil
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .archive_handler import ArchiveHandler
from .classifier import Classifier
from .utils.checkpoint import CheckpointManager
from .utils.paths import is_suspect_name, sanitize_for_json, should_skip_path

console = Console()

# Categories that make a drive ineligible for wiping (DA-003 verdict)
GNSS_CATEGORIES = {"GNSS Data", "GNSS Raw (Trimble)"}

CORRUPT_CATEGORY = "Corrupt Direntry"
SYMLINK_CATEGORY = "Symlink"

# Cap on how many skipped/excluded roots are itemized (memory bound)
_MAX_ITEMIZED = 200


class ScanStats:
    """Aggregate counters accumulated during a scan (drives the survey verdict)."""

    def __init__(self):
        self.total_bytes = 0  # sane files only — corrupt claims excluded
        self.claimed_bytes = 0  # every direntry's claimed size, lies included
        self.categories: Counter[str] = Counter()
        self.extensions: Counter[str] = Counter()
        self.gnss_files = 0
        self.corrupt_entries = 0
        self.symlinks = 0
        self.hardlink_dups = 0
        self.archives_seen = 0
        self.archives_extracted = 0
        self.archives_depth_capped = 0
        self.excluded_count = 0
        self.skipped_roots: list[str] = []
        self.excluded_roots: list[str] = []
        self.metadata_inconsistent = False


class DeepScanner:
    """
    Recursively scan a directory tree, including archives, and output file metadata to JSONL.
    """

    def __init__(
        self,
        root_path: Path,
        output_file: Path | None = None,
        resume: bool = False,
        on_classified: Callable[[dict], None] | None = None,
        *,
        include_hidden: bool = False,
        excludes: list[str] | None = None,
        max_archive_depth: int = 3,
        force: bool = False,
        stats_only: bool = False,
        fs_capacity_bytes: int | None = None,
    ):
        self.root = Path(root_path).resolve()
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.scan_id = self.root.name.replace("/", "_").replace("\\", "_")
        self.on_classified = on_classified
        self.include_hidden = include_hidden
        self.excludes = list(excludes) if excludes else []
        self.max_archive_depth = max_archive_depth
        self.force = force
        self.stats_only = stats_only

        if stats_only:
            self.output_file = None
            self.log_file = None
            self.checkpoint = None
        else:
            if output_file:
                self.output_file = Path(output_file)
            else:
                self.output_file = Path(f"scan_{self.scan_id}_{self.timestamp}.jsonl")
            self.log_file = self.output_file.with_suffix(".log")
            self.checkpoint = (
                CheckpointManager(self.scan_id, checkpoint_dir=self.output_file.parent)
                if resume
                else None
            )

        self.classifier = Classifier()
        self.archive_handler = ArchiveHandler()
        self.stats = ScanStats()
        self._seen_inodes: set[tuple[int, int]] = set()

        if fs_capacity_bytes is not None:
            self._fs_capacity: int | None = fs_capacity_bytes
        else:
            try:
                self._fs_capacity = shutil.disk_usage(str(self.root)).total
            except OSError:
                self._fs_capacity = None

        self.file_count = 0
        self.error_count = 0
        self.skipped_count = 0
        self.start_time = time.time()
        self.progress: Progress | None = None
        self.task = None

    def log(self, message: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"[{timestamp}] [{level}] {sanitize_for_json(message)}"
        if self.log_file is None:
            if level in ("WARNING", "ERROR"):
                console.print(f"[yellow]{log_line}[/yellow]")
            return
        try:
            # errors="replace": corrupt filesystems produce undecodable path
            # bytes; a log write must never kill the scan
            with open(self.log_file, "a", encoding="utf-8", errors="replace") as f:
                f.write(log_line + "\n")
        except Exception:
            # Errors during logging shouldn't crash the scan
            console.print(f"[red]Error writing to log file: {log_line}[/red]")

    def scan(self):
        """Main scanning loop with progress tracking"""
        if (
            self.output_file is not None
            and self.output_file.exists()
            and not self.checkpoint
            and not self.force
        ):
            raise FileExistsError(
                f"Output file exists: {self.output_file} — re-running would overwrite the "
                "previous scan. Use --resume to continue it or --force to overwrite."
            )

        self.log(f"Starting deep scan of: {self.root}")
        console.print(f"[bold blue]Scanning:[/bold blue] {self.root}")
        if self.output_file is not None:
            self.log(f"Output: {self.output_file}")
            console.print(f"[bold green]Output:[/bold green] {self.output_file}")

        mode = "a" if self.checkpoint else "w"
        outfile = (
            open(self.output_file, mode, encoding="utf-8", errors="replace")
            if self.output_file is not None
            else None
        )
        try:
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
        finally:
            if outfile is not None:
                outfile.close()

        if self.checkpoint:
            self.checkpoint.save_checkpoint()
            self.log("Final checkpoint saved")

        self._print_summary()

    def _is_excluded(self, path: Path) -> bool:
        if not self.excludes:
            return False
        try:
            rel = str(path.relative_to(self.root))
        except ValueError:
            # Inside an archive temp dir — exclude globs are root-relative only
            rel = path.name
        return any(
            fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat) for pat in self.excludes
        )

    def _record_itemized(self, bucket: list[str], path: Path):
        if len(bucket) < _MAX_ITEMIZED:
            bucket.append(sanitize_for_json(str(path)))

    def _scan_directory(
        self, dir_path: Path, outfile, archive_path: Path | None = None, archive_depth: int = 0
    ):
        """Recursively scan a directory."""
        try:
            entries = list(dir_path.iterdir())
        except OSError as e:
            self.error_count += 1
            self.log(f"Error listing {dir_path}: {e}")
            return

        for filepath in entries:
            if self.checkpoint and self.checkpoint.is_scanned(filepath):
                continue

            if self._is_excluded(filepath):
                self.stats.excluded_count += 1
                self._record_itemized(self.stats.excluded_roots, filepath)
                continue

            if should_skip_path(filepath, include_hidden=self.include_hidden):
                self.skipped_count += 1
                self._record_itemized(self.stats.skipped_roots, filepath)
                continue

            try:
                # Symlink gate (DA-002 #8): record, never traverse — a link to
                # /home would otherwise walk the HOST filesystem into the catalog
                if filepath.is_symlink():
                    self._record_symlink(filepath, outfile, archive_path)
                    continue
                if filepath.is_file():
                    self._process_file(filepath, outfile, archive_path, archive_depth)
                elif filepath.is_dir():
                    self._scan_directory(filepath, outfile, archive_path, archive_depth)
            except (PermissionError, OSError) as e:
                self.error_count += 1
                self.log(f"Error accessing {filepath}: {e}")

    def _record_symlink(self, filepath: Path, outfile, archive_path: Path | None):
        self.stats.symlinks += 1
        try:
            target = os.readlink(filepath)
        except OSError:
            target = None
        metadata = {
            "path": sanitize_for_json(str(filepath.absolute())),
            "name": sanitize_for_json(filepath.name),
            "extension": filepath.suffix.lower(),
            "category": SYMLINK_CATEGORY,
            "size_bytes": 0,
            "size_mb": 0.0,
            "symlink_target": sanitize_for_json(target) if target else None,
            "parent_dir": sanitize_for_json(str(filepath.parent)),
            "scan_timestamp": datetime.now().isoformat(),
            "in_archive": bool(archive_path),
            "archive_path": sanitize_for_json(str(archive_path)) if archive_path else None,
        }
        self.stats.categories[SYMLINK_CATEGORY] += 1
        if outfile is not None:
            outfile.write(json.dumps(metadata, ensure_ascii=False) + "\n")
        if self.checkpoint:
            self.checkpoint.mark_scanned(filepath)

    def _process_file(
        self, filepath: Path, outfile, archive_path: Path | None = None, archive_depth: int = 0
    ):
        """Process a single file, handling archives recursively."""
        try:
            metadata = self._extract_metadata(filepath, archive_path)
            corrupt = metadata["category"] == CORRUPT_CATEGORY
            hardlink_dup = bool(metadata.get("hardlink_dup"))

            if outfile is not None:
                outfile.write(json.dumps(metadata, ensure_ascii=False) + "\n")
                outfile.flush()
            self.file_count += 1

            category = metadata["category"] or "Unclassified"
            self.stats.categories[category] += 1
            self.stats.extensions[metadata["extension"] or "(none)"] += 1
            size = metadata["size_bytes"] or 0
            self.stats.claimed_bytes += size
            if corrupt:
                self.stats.corrupt_entries += 1
            else:
                self.stats.total_bytes += size
            if category in GNSS_CATEGORIES:
                self.stats.gnss_files += 1
            if (
                self._fs_capacity
                and self.stats.claimed_bytes > self._fs_capacity
                and not self.stats.metadata_inconsistent
            ):
                self.stats.metadata_inconsistent = True
                self.log(
                    "Sum of claimed file sizes exceeds filesystem capacity — "
                    "directory metadata is inconsistent (probable corruption)",
                    level="WARNING",
                )

            if self.progress and self.task is not None:
                self.progress.update(
                    self.task, advance=1, description=f"[cyan]Scanning... ({self.file_count} files)"
                )

            if self.on_classified is not None and not corrupt:
                try:
                    self.on_classified(metadata)
                except Exception as e:
                    self.error_count += 1
                    self.log(f"on_classified callback error for {filepath}: {e}", level="ERROR")

            # Never open a corrupt direntry; never re-extract a cross-linked one
            if self.archive_handler.is_archive(filepath) and not corrupt and not hardlink_dup:
                self.stats.archives_seen += 1
                if archive_depth >= self.max_archive_depth:
                    self.stats.archives_depth_capped += 1
                    self.log(
                        f"Archive depth cap ({self.max_archive_depth}) reached, not extracting: {filepath}",
                        level="WARNING",
                    )
                else:
                    self.log(f"Found archive: {filepath}. Extracting...")
                    temp_dir = self.archive_handler.extract(filepath)
                    if temp_dir:
                        self.stats.archives_extracted += 1
                        self.log(f"Successfully extracted to: {temp_dir}")
                        self._scan_directory(
                            temp_dir,
                            outfile,
                            archive_path=filepath,
                            archive_depth=archive_depth + 1,
                        )
                        shutil.rmtree(temp_dir, ignore_errors=True)
                        self.log(f"Cleaned up temporary directory: {temp_dir}")
                    else:
                        self.log(f"Failed to extract archive: {filepath}", level="WARNING")

            if self.checkpoint:
                self.checkpoint.mark_scanned(filepath)
                if self.file_count % 1000 == 0:
                    self.checkpoint.save_checkpoint()
                    self.log(f"Checkpoint saved ({self.file_count} files)")

        except Exception as e:
            self.error_count += 1
            self.log(f"Unexpected error processing {filepath}: {e}")

    def _extract_metadata(self, filepath: Path, archive_path: Path | None = None) -> dict:
        """Extract file metadata."""
        suspect = is_suspect_name(filepath.name)
        try:
            stat = filepath.stat()
            size: int | None = stat.st_size
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
            created = datetime.fromtimestamp(stat.st_ctime).isoformat()
            inode_key = (stat.st_dev, stat.st_ino) if stat.st_ino else None
        except OSError:
            # Corrupt entries may not even stat
            suspect = True
            size = None
            modified = None
            created = None
            inode_key = None

        corrupt_reason = None
        if suspect:
            corrupt_reason = "undecodable_name"
        elif self._fs_capacity is not None and size is not None and size > self._fs_capacity:
            # A single direntry claiming more bytes than the filesystem can
            # hold is a corrupt FAT chain (DA-002 #1) — never read it
            corrupt_reason = "oversize_direntry"

        if corrupt_reason:
            category: str | None = CORRUPT_CATEGORY
        else:
            category = self.classifier.classify(filepath)

        hardlink_dup = False
        if inode_key is not None and corrupt_reason is None:
            if inode_key in self._seen_inodes:
                hardlink_dup = True
                self.stats.hardlink_dups += 1
            else:
                self._seen_inodes.add(inode_key)

        data = {
            "path": sanitize_for_json(str(filepath.absolute())),
            "name": sanitize_for_json(filepath.name),
            "extension": filepath.suffix.lower(),
            "category": category,
            "size_bytes": size,
            "size_mb": round(size / (1024 * 1024), 2) if size is not None else None,
            "modified": modified,
            "created": created,
            "parent_dir": sanitize_for_json(str(filepath.parent)),
            "depth": len(filepath.relative_to(self.root).parts) if not archive_path else None,
            "scan_timestamp": datetime.now().isoformat(),
            "in_archive": bool(archive_path),
            "archive_path": sanitize_for_json(str(archive_path)) if archive_path else None,
        }
        if corrupt_reason:
            data["corrupt_reason"] = corrupt_reason
        if hardlink_dup:
            data["hardlink_dup"] = True
        return data

    def survey_verdict(self) -> tuple[str, list[str]]:
        """One-line wipe/keep verdict + disclosure warnings (DA-003)."""
        warnings = []
        if self.stats.metadata_inconsistent or self.stats.corrupt_entries:
            warnings.append(
                f"filesystem metadata inconsistent — {self.stats.corrupt_entries} corrupt "
                "direntries; sizes are not trustworthy"
            )
        if self.skipped_count and not self.include_hidden:
            roots = ", ".join(self.stats.skipped_roots[:5])
            warnings.append(
                f"{self.skipped_count} hidden/system entries were NOT surveyed "
                f"(first roots: {roots}) — re-run with --include-hidden for full coverage"
            )
        if self.stats.symlinks:
            warnings.append(f"{self.stats.symlinks} symlinks recorded but not followed")
        if self.stats.archives_seen and not self.stats.archives_extracted:
            warnings.append(
                f"{self.stats.archives_seen} archives present but not opened — "
                "GNSS files inside archives would not be counted"
            )
        if self.error_count:
            warnings.append(f"{self.error_count} entries could not be read")

        if self.stats.gnss_files:
            verdict = (
                f"{self.stats.gnss_files} GNSS-classified files — DO NOT wipe; "
                "run a full scan and excavate first"
            )
        elif self.stats.metadata_inconsistent:
            verdict = "corrupt filesystem — verdict unreliable, inspect manually before wiping"
        else:
            verdict = "no GNSS payload detected — safe-to-wipe candidate (human confirms)"
        return verdict, warnings

    def _print_summary(self):
        """Print final statistics"""
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime("%H:%M:%S", time.gmtime(elapsed))
        rate = self.file_count / elapsed if elapsed > 0 else 0

        console.print("\n" + "=" * 60)
        console.print("[bold green]Scan Complete![/bold green]")
        console.print(f"[bold]Files processed:[/bold] {self.file_count:,}")
        console.print(f"[bold]Total size:[/bold] {self.stats.total_bytes / (1024**2):,.1f} MB")
        console.print(f"[bold]Files skipped (hidden/system):[/bold] {self.skipped_count:,}")
        if self.stats.skipped_roots:
            console.print(
                f"[dim]  skipped roots (first {min(len(self.stats.skipped_roots), 10)}): "
                + ", ".join(self.stats.skipped_roots[:10])
                + "[/dim]"
            )
        if self.stats.excluded_count:
            console.print(f"[bold]Excluded by pattern:[/bold] {self.stats.excluded_count:,}")
        if self.stats.symlinks:
            console.print(
                f"[bold]Symlinks (recorded, not followed):[/bold] {self.stats.symlinks:,}"
            )
        if self.stats.corrupt_entries:
            console.print(
                f"[bold red]Corrupt direntries:[/bold red] {self.stats.corrupt_entries:,}"
            )
        if self.stats.hardlink_dups:
            console.print(
                f"[bold]Hardlink/cross-link duplicates:[/bold] {self.stats.hardlink_dups:,}"
            )
        if self.stats.archives_depth_capped:
            console.print(
                f"[bold yellow]Archives past depth cap (not opened):[/bold yellow] "
                f"{self.stats.archives_depth_capped:,}"
            )
        if self.stats.metadata_inconsistent:
            console.print(
                "[bold red]⚠ filesystem metadata inconsistent with capacity — "
                "probable corruption[/bold red]"
            )
        console.print(f"[bold yellow]Errors:[/bold yellow] {self.error_count}")
        console.print(f"[bold]Time elapsed:[/bold] {elapsed_str}")
        console.print(f"[bold]Rate:[/bold] {rate:.1f} files/sec")
        if self.output_file is not None:
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
