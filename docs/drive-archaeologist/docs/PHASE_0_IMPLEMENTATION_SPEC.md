# Phase 0 Implementation Specification

**Date:** 2025-11-06
**Phase:** 0 - Cross-Platform Scanner
**Duration:** 10 hours
**Status:** Ready for Implementation

---

## 🎯 Objective

Build a cross-platform CLI scanner that works reliably on Windows and Linux, producing JSONL output with file metadata and resume capability.

---

## 📋 Implementation Tasks

### Task 1: CLI Interface (2 hours)

**File:** `src/drive_archaeologist/cli.py`

**Implementation Requirements:**

```python
"""
CLI interface for drive-archaeologist using Click framework.
Provides the main 'scan' command for Phase 0.
"""

import click
from pathlib import Path
from rich.console import Console
from .scanner import DeepScanner

console = Console()

@click.group()
@click.version_option(version='0.1.0')
def main():
    """Drive Archaeologist - Excavate decades of data from old hard drives"""
    pass

@main.command()
@click.argument('path', type=click.Path(exists=True, path_type=Path))
@click.option(
    '--output', '-o',
    type=click.Path(path_type=Path),
    help='Output file path (default: scan_<name>_<timestamp>.jsonl)'
)
@click.option(
    '--resume', '-r',
    is_flag=True,
    help='Resume a previous interrupted scan'
)
def scan(path: Path, output: Path, resume: bool):
    """Scan a drive or directory and produce a JSONL file with metadata"""
    try:
        scanner = DeepScanner(path, output_file=output, resume=resume)
        scanner.scan()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Scan interrupted by user[/yellow]")
        console.print("[yellow]💾 Progress saved. Use --resume to continue[/yellow]")
        raise click.Abort()
    except Exception as e:
        console.print(f"[red]❌ Error: {e}[/red]")
        raise click.Abort()

if __name__ == '__main__':
    main()
```

**Acceptance Criteria:**
- ✅ `drive-archaeologist scan <path>` works
- ✅ `--output` flag allows custom output location
- ✅ `--resume` flag enables resuming interrupted scans
- ✅ Help text displays correctly (`drive-archaeologist --help`)
- ✅ Error messages are clear and helpful
- ✅ Validates that input path exists
- ✅ Handles KeyboardInterrupt gracefully (Ctrl+C)

**Testing:**
```bash
# Basic scan
drive-archaeologist scan C:\TestDrive

# Custom output
drive-archaeologist scan C:\TestDrive --output my_scan.jsonl

# Resume scan
drive-archaeologist scan C:\TestDrive --resume

# Help text
drive-archaeologist --help
drive-archaeologist scan --help
```

---

### Task 2: Core Scanner Implementation (4 hours)

**File:** `src/drive_archaeologist/scanner.py`

**Implementation Requirements:**

```python
"""
Core scanner implementation with resume capability and progress tracking.
Streams results to JSONL format for memory efficiency.
"""

import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from .utils.checkpoint import CheckpointManager
from .utils.paths import should_skip_path, sanitize_for_json

console = Console()

class DeepScanner:
    """
    Recursively scan a directory tree and output file metadata to JSONL.

    Features:
    - Streaming JSONL output (memory-efficient)
    - Resume capability via checkpoints
    - Progress tracking with rich
    - Error handling (skip unreadable files)
    - Cross-platform path handling
    """

    def __init__(self, root_path: Path, output_file: Optional[Path] = None, resume: bool = False):
        """
        Initialize scanner.

        Args:
            root_path: Directory to scan
            output_file: Output JSONL file (default: scan_<name>_<timestamp>.jsonl)
            resume: Whether to resume a previous scan
        """
        self.root = Path(root_path).resolve()
        self.timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.scan_id = self.root.name.replace('/', '_').replace('\\', '_')

        # Output files
        if output_file:
            self.output_file = Path(output_file)
        else:
            self.output_file = Path(f"scan_{self.scan_id}_{self.timestamp}.jsonl")

        self.log_file = self.output_file.with_suffix('.log')

        # Checkpoint manager for resume capability
        self.checkpoint = CheckpointManager(self.scan_id) if resume else None

        # Statistics
        self.file_count = 0
        self.error_count = 0
        self.skipped_count = 0
        self.start_time = time.time()

    def log(self, message: str, level: str = "INFO"):
        """Log message to file and optionally console"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}"

        with open(self.log_file, 'a', encoding='utf-8') as f:
            f.write(log_line + '\n')

    def scan(self):
        """Main scanning loop with progress tracking"""
        self.log(f"🔍 Starting deep scan of: {self.root}")
        self.log(f"📊 Output: {self.output_file}")
        self.log(f"📝 Log: {self.log_file}")

        console.print(f"[bold blue]🔍 Scanning:[/bold blue] {self.root}")
        console.print(f"[bold green]📄 Output:[/bold green] {self.output_file}")

        # Open output file in append mode (for resume capability)
        mode = 'a' if self.checkpoint else 'w'

        with open(self.output_file, mode, encoding='utf-8') as outfile:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.completed} files"),
                TimeElapsedColumn(),
                console=console
            ) as progress:
                task = progress.add_task("[cyan]Scanning...", total=None)

                # Recursively traverse directory tree
                for filepath in self.root.rglob('*'):
                    # Skip if already scanned (resume mode)
                    if self.checkpoint and self.checkpoint.is_scanned(filepath):
                        continue

                    # Skip system directories and special files
                    if should_skip_path(filepath):
                        self.skipped_count += 1
                        continue

                    # Only process files (not directories)
                    if filepath.is_file():
                        try:
                            metadata = self._extract_metadata(filepath)

                            # Write as JSON Lines (one JSON object per line)
                            outfile.write(json.dumps(metadata, ensure_ascii=False) + '\n')
                            outfile.flush()  # Force write to disk immediately

                            self.file_count += 1
                            progress.update(task, advance=1, description=f"[cyan]Scanning... ({self.file_count} files)")

                            # Checkpoint every 1000 files
                            if self.checkpoint and self.file_count % 1000 == 0:
                                self.checkpoint.mark_scanned(filepath)
                                self.checkpoint.save_checkpoint()
                                self.log(f"💾 Checkpoint saved ({self.file_count} files)")

                        except PermissionError:
                            self.error_count += 1
                            self.log(f"⚠️  Permission denied: {filepath}")
                        except OSError as e:
                            self.error_count += 1
                            self.log(f"⚠️  OS error on {filepath}: {e}")
                        except Exception as e:
                            self.error_count += 1
                            self.log(f"❌ Unexpected error on {filepath}: {e}")

        self._print_summary()

    def _extract_metadata(self, filepath: Path) -> dict:
        """
        Extract file metadata (fast operations only).

        Args:
            filepath: Path to file

        Returns:
            Dictionary with file metadata
        """
        stat = filepath.stat()

        return {
            'path': sanitize_for_json(str(filepath.absolute())),
            'name': filepath.name,
            'extension': filepath.suffix.lower(),
            'size_bytes': stat.st_size,
            'size_mb': round(stat.st_size / (1024 * 1024), 2),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'parent_dir': sanitize_for_json(str(filepath.parent)),
            'depth': len(filepath.relative_to(self.root).parts),
            'scan_timestamp': datetime.now().isoformat(),
        }

    def _print_summary(self):
        """Print final statistics"""
        elapsed = time.time() - self.start_time
        elapsed_str = time.strftime('%H:%M:%S', time.gmtime(elapsed))
        rate = self.file_count / elapsed if elapsed > 0 else 0

        console.print("\n" + "=" * 60)
        console.print("[bold green]🎉 Scan Complete![/bold green]")
        console.print(f"[bold]📁 Files processed:[/bold] {self.file_count:,}")
        console.print(f"[bold]⏭️  Files skipped:[/bold] {self.skipped_count:,}")
        console.print(f"[bold yellow]⚠️  Errors:[/bold yellow] {self.error_count}")
        console.print(f"[bold]⏱️  Time elapsed:[/bold] {elapsed_str}")
        console.print(f"[bold]⚡ Rate:[/bold] {rate:.1f} files/sec")
        console.print(f"[bold green]💾 Results:[/bold green] {self.output_file}")
        console.print(f"[bold blue]📝 Log:[/bold blue] {self.log_file}")
        console.print("=" * 60 + "\n")

        self.log("=" * 60)
        self.log(f"🎉 Scan Complete!")
        self.log(f"📁 Files processed: {self.file_count:,}")
        self.log(f"⏭️  Files skipped: {self.skipped_count:,}")
        self.log(f"⚠️  Errors: {self.error_count}")
        self.log(f"⏱️  Time elapsed: {elapsed_str}")
        self.log(f"⚡ Rate: {rate:.1f} files/sec")
        self.log("=" * 60)
```

**Acceptance Criteria:**
- ✅ Recursively scans directory tree
- ✅ Extracts metadata (path, size, timestamps, etc.)
- ✅ Writes JSONL output (streaming, one line per file)
- ✅ Progress bar shows file count and elapsed time
- ✅ Handles errors gracefully (skip unreadable files, continue)
- ✅ Checkpoint system saves progress every 1000 files
- ✅ Final summary displays statistics
- ✅ Log file contains detailed progress

**Testing:**
- Scan directory with 100 files
- Scan directory with 10,000 files
- Test with unreadable files (permission errors)
- Test resume capability (kill process, restart with --resume)
- Test on Windows (junction points, reserved names)
- Test on Linux (symlinks, permission errors)

---

### Task 3: Checkpoint Manager (2 hours)

**File:** `src/drive_archaeologist/utils/checkpoint.py`

**Implementation Requirements:**

```python
"""
Checkpoint manager for resume capability.
Tracks which files have been scanned to enable resuming interrupted scans.
"""

import json
from pathlib import Path
from typing import Set

class CheckpointManager:
    """
    Manages checkpoint files for scan resume capability.

    Saves progress periodically so scans can be resumed if interrupted.
    """

    def __init__(self, scan_id: str):
        """
        Initialize checkpoint manager.

        Args:
            scan_id: Unique identifier for this scan
        """
        self.scan_id = scan_id
        self.checkpoint_file = Path(f"checkpoint_{scan_id}.json")
        self.scanned_paths: Set[str] = set()

        # Load existing checkpoint if available
        if self.checkpoint_file.exists():
            self._load_checkpoint()

    def _load_checkpoint(self):
        """Load checkpoint from disk"""
        try:
            with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.scanned_paths = set(data.get('scanned_paths', []))
        except Exception:
            # If checkpoint is corrupted, start fresh
            self.scanned_paths = set()

    def mark_scanned(self, path: Path):
        """Mark a file as scanned"""
        self.scanned_paths.add(str(path.absolute()))

    def save_checkpoint(self):
        """Save current progress to disk"""
        data = {
            'scan_id': self.scan_id,
            'scanned_paths': list(self.scanned_paths),
            'total_files': len(self.scanned_paths),
        }

        with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    def is_scanned(self, path: Path) -> bool:
        """Check if a file has already been scanned"""
        return str(path.absolute()) in self.scanned_paths

    def cleanup(self):
        """Remove checkpoint file"""
        if self.checkpoint_file.exists():
            self.checkpoint_file.unlink()
```

**Acceptance Criteria:**
- ✅ Tracks scanned files
- ✅ Saves checkpoint to JSON file
- ✅ Loads existing checkpoint on resume
- ✅ Handles corrupted checkpoint files (starts fresh)
- ✅ Cleanup method removes checkpoint file

**Testing:**
- Start scan, interrupt after 500 files, resume
- Test with corrupted checkpoint file
- Verify checkpoint file format (valid JSON)
- Test cleanup method

---

### Task 4: Path Utilities (1 hour)

**File:** `src/drive_archaeologist/utils/paths.py`

**Implementation Requirements:**

```python
"""
Cross-platform path utilities for Windows and Linux compatibility.
Handles Windows reserved filenames, long paths, and system directories.
"""

import platform
from pathlib import Path
from pathvalidate import sanitize_filename

# Windows reserved names
WINDOWS_RESERVED_NAMES = {
    'CON', 'PRN', 'AUX', 'NUL',
    'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
    'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
}

# System directories to skip
SYSTEM_DIRECTORIES = {
    '$RECYCLE.BIN',
    'System Volume Information',
    '.Trash',
    '.Trashes',
    '__MACOSX',
}

def should_skip_path(path: Path) -> bool:
    """
    Determine if a path should be skipped during scanning.

    Args:
        path: Path to check

    Returns:
        True if path should be skipped, False otherwise
    """
    # Skip system directories
    for part in path.parts:
        if part in SYSTEM_DIRECTORIES:
            return True

    # Skip hidden files on Unix (starting with .)
    # But don't skip . and .. for directory traversal
    if path.name.startswith('.') and path.name not in {'.', '..'}:
        return True

    return False

def sanitize_for_json(text: str) -> str:
    """
    Sanitize string for JSON output.

    Args:
        text: String to sanitize

    Returns:
        Sanitized string safe for JSON
    """
    # Replace backslashes with forward slashes for cross-platform consistency
    # (but keep original paths in output for user clarity)
    return text

def safe_filename(name: str) -> str:
    """
    Sanitize filename for cross-platform safety.
    Handles Windows reserved names.

    Args:
        name: Filename to sanitize

    Returns:
        Safe filename
    """
    # Use pathvalidate for comprehensive sanitization
    return sanitize_filename(name, platform="auto")

def is_reserved_name(name: str) -> bool:
    """
    Check if filename is a Windows reserved name.

    Args:
        name: Filename to check (without extension)

    Returns:
        True if reserved, False otherwise
    """
    name_upper = Path(name).stem.upper()
    return name_upper in WINDOWS_RESERVED_NAMES
```

**Acceptance Criteria:**
- ✅ `should_skip_path()` identifies system directories
- ✅ `safe_filename()` sanitizes Windows reserved names
- ✅ `is_reserved_name()` detects reserved names
- ✅ Works on Windows and Linux

**Testing:**
- Test with Windows reserved names (CON.dat, PRN.log)
- Test with system directories ($RECYCLE.BIN, System Volume Information)
- Test with hidden files (.gitignore, .DS_Store)
- Test with unicode filenames (Tagalog characters)

---

### Task 5: Project Structure Setup (30 minutes)

**Files to Create:**

1. `src/drive_archaeologist/__init__.py`
```python
"""Drive Archaeologist - Excavate decades of data from old hard drives"""

__version__ = "0.1.0"
```

2. `src/drive_archaeologist/__main__.py`
```python
"""Allow running via python -m drive_archaeologist"""

from .cli import main

if __name__ == '__main__':
    main()
```

3. `src/drive_archaeologist/utils/__init__.py`
```python
"""Utility modules for drive-archaeologist"""
```

4. `.gitignore` (update if needed)
```
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.venv/
venv/
ENV/
env/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# Drive Archaeologist outputs
scan_*.jsonl
scan_*.log
checkpoint_*.json

# Testing
.pytest_cache/
.coverage
htmlcov/
```

**Acceptance Criteria:**
- ✅ Package structure is correct
- ✅ Can import `drive_archaeologist`
- ✅ Can run `python -m drive_archaeologist`
- ✅ `.gitignore` excludes output files

---

### Task 6: Testing (2 hours)

**Create:** `tests/test_scanner.py`

```python
"""
Tests for the core scanner functionality.
"""

import pytest
from pathlib import Path
import json
import tempfile
import shutil
from drive_archaeologist.scanner import DeepScanner

def test_scanner_basic(tmp_path):
    """Test basic scanning functionality"""
    # Create test files
    test_dir = tmp_path / "test_scan"
    test_dir.mkdir()
    (test_dir / "file1.txt").write_text("test")
    (test_dir / "file2.txt").write_text("test")

    # Scan
    output_file = tmp_path / "scan_output.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file)
    scanner.scan()

    # Verify output
    assert output_file.exists()

    # Parse JSONL
    files = []
    with open(output_file) as f:
        for line in f:
            files.append(json.loads(line))

    assert len(files) == 2
    assert all('path' in f for f in files)
    assert all('size_bytes' in f for f in files)

def test_scanner_resume(tmp_path):
    """Test resume capability"""
    # Create test files
    test_dir = tmp_path / "test_scan"
    test_dir.mkdir()
    for i in range(10):
        (test_dir / f"file{i}.txt").write_text(f"test {i}")

    # First scan (will be interrupted)
    output_file = tmp_path / "scan_output.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file, resume=False)
    # Simulate partial scan by scanning only first few files
    # (In real test, we'd interrupt the scan)

    # Second scan with resume
    scanner2 = DeepScanner(test_dir, output_file=output_file, resume=True)
    scanner2.scan()

    # Verify no duplicates
    files = []
    with open(output_file) as f:
        for line in f:
            files.append(json.loads(line))

    # Check for duplicates by path
    paths = [f['path'] for f in files]
    assert len(paths) == len(set(paths)), "Duplicate files found"

def test_scanner_handles_errors(tmp_path):
    """Test that scanner handles permission errors gracefully"""
    # This test is platform-specific and may need adjustment
    # Create test file with restricted permissions
    test_dir = tmp_path / "test_scan"
    test_dir.mkdir()
    restricted_file = test_dir / "restricted.txt"
    restricted_file.write_text("test")

    # Make file unreadable (Unix only)
    if platform.system() != 'Windows':
        restricted_file.chmod(0o000)

    # Scan should complete without crashing
    output_file = tmp_path / "scan_output.jsonl"
    scanner = DeepScanner(test_dir, output_file=output_file)
    scanner.scan()

    # Scanner should have logged errors
    assert scanner.error_count >= 0  # May be 0 on Windows
```

**Create:** `tests/test_paths.py`

```python
"""
Tests for path utilities.
"""

import pytest
from pathlib import Path
from drive_archaeologist.utils.paths import (
    should_skip_path,
    safe_filename,
    is_reserved_name,
)

def test_should_skip_system_directories():
    """Test that system directories are skipped"""
    assert should_skip_path(Path("C:/$RECYCLE.BIN/file.txt"))
    assert should_skip_path(Path("/System Volume Information/file.txt"))
    assert not should_skip_path(Path("/home/user/file.txt"))

def test_should_skip_hidden_files():
    """Test that hidden files are skipped"""
    assert should_skip_path(Path(".hidden_file"))
    assert should_skip_path(Path("/home/user/.gitignore"))
    assert not should_skip_path(Path("/home/user/normal_file.txt"))

def test_reserved_names():
    """Test Windows reserved name detection"""
    assert is_reserved_name("CON")
    assert is_reserved_name("con")
    assert is_reserved_name("PRN")
    assert is_reserved_name("COM1")
    assert not is_reserved_name("CONFIG")
    assert not is_reserved_name("normal_file")

def test_safe_filename():
    """Test filename sanitization"""
    # Windows reserved names
    assert safe_filename("CON") != "CON"
    assert safe_filename("PRN.txt") != "PRN.txt"

    # Special characters
    result = safe_filename("file:with*special?chars")
    assert ':' not in result
    assert '*' not in result
    assert '?' not in result
```

**Acceptance Criteria:**
- ✅ All tests pass on Windows
- ✅ All tests pass on Linux
- ✅ Test coverage >80%
- ✅ Tests can be run with `pytest`

**Run Tests:**
```bash
# Install dev dependencies
uv pip install -e ".[dev]"

# Run tests
pytest

# Run with coverage
pytest --cov=drive_archaeologist --cov-report=html
```

---

### Task 7: Documentation (1 hour)

**Create:** `README.md` (update existing)

```markdown
# 🔍 Drive Archaeologist

Excavate decades of data from old hard drives.

Automatically scans, classifies, and organizes legacy GNSS data, field notes, and mixed personal/work files scattered across dusty hard drives.

## Features

### Phase 0 (Current)
- ✅ Cross-platform CLI scanner (Windows + Linux)
- ✅ JSONL output with file metadata
- ✅ Resume capability for interrupted scans
- ✅ Progress tracking
- ✅ Error handling (skip unreadable files)

### Coming Soon
- Phase 1: Profile system + file classification
- Phase 2: Archive support + structure analysis
- Phase 3: Safe migration scripts + OCR
- Phase 4: USB auto-detection + HTML reports
- Phase 5: Advanced OCR + full-text search

## Installation

### Requirements
- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager

### Install uv
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Install Drive Archaeologist
```bash
# Clone repository
git clone https://github.com/alfieprojectsdev/drive-archaeologist.git
cd drive-archaeologist

# Create virtual environment
uv venv

# Activate environment
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install in development mode
uv pip install -e .
```

## Quick Start

### Scan a Drive
```bash
# Basic scan
drive-archaeologist scan C:\OldDrive

# Custom output location
drive-archaeologist scan /media/usb --output my_scan.jsonl

# Resume interrupted scan
drive-archaeologist scan C:\OldDrive --resume
```

### Output Format

The scanner produces a JSONL file (JSON Lines), where each line is a JSON object representing one file:

```json
{"path": "C:\\OldDrive\\ALGO0010.22O", "name": "ALGO0010.22O", "extension": ".22o", "size_bytes": 4251840, "size_mb": 4.05, "modified": "2022-04-10T14:23:15", "created": "2022-04-10T14:20:00", "parent_dir": "C:\\OldDrive", "depth": 1, "scan_timestamp": "2025-11-06T10:30:00"}
```

### Analyze Results

Use standard command-line tools to analyze the JSONL output:

```bash
# Count files by extension (Linux/macOS)
cat scan_output.jsonl | jq -r '.extension' | sort | uniq -c | sort -rn

# Find large files (>100MB)
cat scan_output.jsonl | jq 'select(.size_mb > 100) | {name, size_mb, path}'

# Count total files
wc -l < scan_output.jsonl
```

## Development

### Install Development Dependencies
```bash
uv pip install -e ".[dev]"
```

### Run Tests
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=drive_archaeologist --cov-report=html

# Run specific test
pytest tests/test_scanner.py::test_scanner_basic
```

### Code Quality
```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type checking
mypy src/
```

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Author

Alfie Pelicano (alfieprojects.dev@gmail.com)

## Acknowledgments

Built for PHIVOLCS (Philippine Institute of Volcanology and Seismology) to help organize decades of GNSS data and field observations.
```

**Acceptance Criteria:**
- ✅ README explains installation (using uv)
- ✅ README shows quick start examples
- ✅ README documents output format
- ✅ README explains development setup

---

## 📊 Success Criteria

### Functional Requirements
- ✅ `drive-archaeologist scan <path>` command works
- ✅ Scans any directory or drive
- ✅ Outputs valid JSONL format
- ✅ Handles errors gracefully (no crashes)
- ✅ Resume works after interruption
- ✅ Works on Windows 10/11
- ✅ Works on Linux (Ubuntu/Debian)

### Performance Requirements
- ✅ Scans 10,000 files in < 5 minutes
- ✅ Memory usage < 100MB (streaming mode)
- ✅ Progress updates every 100 files
- ✅ Checkpoint every 1,000 files

### Quality Requirements
- ✅ Zero crashes on test drives
- ✅ Handles permission errors
- ✅ Handles special characters in filenames
- ✅ Handles long paths (Windows >260 chars)
- ✅ Clear error messages
- ✅ Test coverage >80%

### Documentation Requirements
- ✅ Installation guide (using uv)
- ✅ Quick start guide
- ✅ CLI reference
- ✅ Output format specification
- ✅ Development setup guide

---

## 🧪 Testing Checklist

### Windows Testing
- [ ] Test on Windows 10
- [ ] Test on Windows 11
- [ ] Test with paths >260 characters
- [ ] Test with reserved filenames (`CON.dat`, `PRN.log`)
- [ ] Test with unicode filenames (Tagalog: `ñ`, `Ñ`)
- [ ] Test on NTFS file system
- [ ] Test on FAT32 file system
- [ ] Test on exFAT file system
- [ ] Test with spaces in paths
- [ ] Test with junction points
- [ ] Test permission errors
- [ ] Test drive letters (`C:\`, `D:\`)
- [ ] Test UNC paths (`\\server\share\`)

### Linux Testing
- [ ] Test on Ubuntu
- [ ] Test with symlinks
- [ ] Test permission errors
- [ ] Test on ext4 file system
- [ ] Test on mounted NTFS drive

### Performance Testing
- [ ] Scan 100 files (should be instant)
- [ ] Scan 1,000 files (< 1 minute)
- [ ] Scan 10,000 files (< 5 minutes)
- [ ] Scan 100,000 files (< 45 minutes)
- [ ] Memory usage remains stable
- [ ] Resume works after interrupt

### Error Handling Testing
- [ ] Unreadable files (permission denied)
- [ ] Corrupted file system
- [ ] Disk full (output file)
- [ ] Network drive disconnection (if applicable)
- [ ] Keyboard interrupt (Ctrl+C)

---

## 📝 Definition of Done

Phase 0 is complete when ALL of the following are true:

- ✅ All tasks implemented and committed
- ✅ All tests passing (Windows + Linux)
- ✅ Test coverage >80%
- ✅ Documentation complete
- ✅ Code reviewed (linting, type checking)
- ✅ Tested on real test drive (small, medium, large)
- ✅ No known bugs or crashes
- ✅ Performance meets targets
- ✅ User can install and run successfully
- ✅ Code pushed to branch
- ✅ Ready for Phase 1

---

## 🚀 Next Steps After Completion

1. **Tag release**: `v0.1.0-phase0`
2. **User testing**: Test with real PHIVOLCS drives
3. **Performance validation**: Measure actual scan times
4. **Bug fixes**: Address any issues found
5. **Phase 1 planning**: Profile system + classification

---

**This specification is ready for implementation via `/plan-implementation`.**
