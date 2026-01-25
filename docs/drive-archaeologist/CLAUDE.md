# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**drive-archaeologist** is a Python CLI tool for excavating and organizing decades of legacy GNSS (GPS) data from old hard drives. Designed for PHIVOLCS (Philippine Institute of Volcanology and Seismology) to process messy historical data archives.

**Status:** Early development (v0.1.0) - project structure established, implementation pending
**Target Users:** Geodesists, geophysicists, data scientists working with legacy GNSS archives
**Python Version:** 3.11+

### Core Problem Being Solved

PHIVOLCS has decades of GNSS data scattered across old hard drives with inconsistent organization:
- Files in random directories with no clear structure
- Mixed file types (RINEX, Trimble DAT, Leica MDB, PDFs, GMT scripts)
- Duplicate files across drives
- Missing metadata and documentation
- No standardized naming conventions

This tool scans drives, identifies file types, recommends reorganization, and generates migration scripts.

## Project Structure

```
drive-archaeologist/
├── src/drive_archaeologist/       # Main package
│   ├── cli.py                     # Click-based CLI entry point
│   ├── scanner.py                 # Filesystem scanning & metadata extraction
│   ├── classifier.py              # File type detection (RINEX, GNSS formats)
│   ├── archive_handler.py         # Archive extraction (ZIP, 7z, RAR)
│   ├── __init__.py
│   └── __main__.py
├── tests/                         # Pytest test suite
├── docs/                          # Design documents
│   ├── Smart USB data ingestion system.md    # Full architecture spec
│   └── TECH_STACK_QUESTIONS.md               # Open dependency decisions
├── scripts/                       # Helper scripts
├── main.py                        # Simple entry point for development
└── pyproject.toml                 # Project metadata and dependencies
```

**Key Files:**
- **`src/drive_archaeologist/cli.py`** - Command-line interface (Click framework)
- **`src/drive_archaeologist/scanner.py`** - Core scanning logic, file walking, metadata extraction
- **`src/drive_archaeologist/classifier.py`** - Pattern matching for GNSS file types
- **`docs/Smart USB data ingestion system.md`** - Complete architecture document with phased implementation plan

## Development Commands

### Installation

```bash
# Install in development mode with all dev dependencies
pip install -e ".[dev]"

# Install with optional OCR support (requires Tesseract)
pip install -e ".[ocr]"

# Using uv (faster, recommended)
uv pip install -e ".[dev]"
```

**System Dependencies:**
- `libmagic1` (for python-magic file detection): `sudo apt install libmagic1`
- `tesseract-ocr` (optional, for OCR features): `sudo apt install tesseract-ocr`

### Running the Tool

```bash
# Via installed command
drive-archaeologist --help
drive-arch --help  # Short alias

# During development
python main.py
python -m drive_archaeologist
```

### Testing

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=drive_archaeologist --cov-report=html

# Run specific test file
pytest tests/test_scanner.py

# Run tests matching pattern
pytest -k "test_rinex"
```

### Linting & Type Checking

```bash
# Lint with Ruff (fast, Rust-based)
ruff check .
ruff check --fix .  # Auto-fix issues

# Format code
ruff format .

# Type checking with mypy
mypy src/drive_archaeologist
```

## Architecture

### Phased Implementation Strategy

**Phase 1: Foundation (Week 1-2)**
- Scan drives recursively
- Extract file metadata (size, modified date, MD5 hash)
- Classify files by type (RINEX, GNSS formats, PDFs, images)
- Output CSV report

**Phase 2: Structure Recognition (Week 3-4)**
- Analyze directory organization patterns
- Detect canonical structures (e.g., `DATAPOOL/SITE/YYYY/`)
- Recommend optimal reorganization
- Generate comparison reports

**Phase 3: Migration Scripts (Week 5-6)**
- Generate safe, reversible bash scripts
- Dry-run mode by default
- Preserve timestamps and prevent overwrites
- Create undo scripts

**Phase 4: USB Hot-Drop (Week 7-8)**
- Auto-trigger on USB mount using watchdog
- Desktop notifications
- Automated report generation

### Key Design Principles

1. **Non-Destructive**: Never modify original files without explicit confirmation
2. **Resume Capability**: Long-running scans must be resumable
3. **Progress Tracking**: Real-time feedback for multi-hour operations
4. **Dry-Run First**: Generate preview scripts, execute only on confirmation
5. **ADHD-Optimized**: Chunked processing, visual progress, external logs

### File Type Detection Patterns

**RINEX (Receiver Independent Exchange Format):**
- Observation: `ALGO0010.22O` (4-char site + 3-digit DOY + 1-char session + 2-digit year + O)
- Navigation: `ALGO0010.22N`
- RINEX 3: `ALGO00CAN_R_20220010000_01D_30S_MO.crx`

**Proprietary GNSS Formats:**
- Trimble: `*.dat`
- Leica: `*.m00`, `*.m01`, etc.
- Bernese: `*.STA`, `*.OUT`, `*.PRT`

**Documentation:**
- Logsheets: `*logsheet*.pdf`, `*log*.pdf`
- Site photos: `SITE*.jpg`, `MONUMENT*.png`
- GMT scripts: `*.gmt`, `*.sh`

## Open Technical Decisions

**See `docs/TECH_STACK_QUESTIONS.md` for detailed analysis of pending decisions:**

1. **File Type Detection Library**
   - `python-magic` (95% accuracy, requires libmagic) vs
   - `filetype` (90% accuracy, pure Python, no system deps)
   - **Status:** Awaiting user decision based on deployment environment

2. **Platform Support**
   - Primary: Linux (Ubuntu/Debian)
   - Windows support TBD (affects dependency choices)

3. **Archive Handling**
   - Priority level for ZIP/7z/RAR support
   - Whether archives are common in legacy drives

4. **OCR Support**
   - For scanned PDFs (requires Tesseract)
   - Currently optional dependency

5. **USB Hot-Plug Detection**
   - `watchdog>=3.0.0` dependency needed (mentioned in spec, not in pyproject.toml)
   - Phase 4 feature

## Dependencies

**Core Runtime:**
- `click>=8.1.0` - CLI framework
- `rich>=13.0.0` - Beautiful terminal output (progress bars, tables)
- `pandas>=2.0.0` - Data analysis and CSV generation
- `pillow>=10.0.0` - Image metadata extraction
- `pypdf>=3.0.0` - PDF text extraction
- `python-magic>=0.4.27` - File type detection (requires libmagic)
- `tqdm>=4.66.0` - Progress bars

**Development:**
- `pytest>=7.4.0` - Testing framework
- `pytest-cov>=4.1.0` - Coverage reporting
- `ruff>=0.1.0` - Fast linter and formatter
- `mypy>=1.5.0` - Static type checking
- `ipython>=8.12.0` - Interactive Python shell

**Optional:**
- `pytesseract>=0.3.10` + `opencv-python>=4.8.0` - OCR for scanned PDFs

## Common Patterns

### File Scanning with Progress Tracking

```python
from pathlib import Path
from tqdm import tqdm
import hashlib

def scan_with_progress(root_path):
    """Scan with progress bar for long-running operations"""
    files = list(Path(root_path).rglob('*'))

    for filepath in tqdm(files, desc="Scanning", unit="files"):
        if filepath.is_file():
            # Process file
            metadata = extract_metadata(filepath)
            yield metadata
```

### Resume Capability Pattern

```python
import json
from pathlib import Path

class ProgressTracker:
    def __init__(self, scan_id):
        self.progress_file = Path(f"scan_progress_{scan_id}.json")
        self.scanned_paths = set()

        if self.progress_file.exists():
            with open(self.progress_file) as f:
                self.scanned_paths = set(json.load(f))

    def is_scanned(self, path):
        return str(path) in self.scanned_paths

    def mark_scanned(self, path):
        self.scanned_paths.add(str(path))

    def save_checkpoint(self):
        """Save every N files to enable resume"""
        with open(self.progress_file, 'w') as f:
            json.dump(list(self.scanned_paths), f)
```

### File Classification Pattern

```python
import re

GNSS_PATTERNS = {
    'rinex_obs': r'^\w{4}\d{3}[0-9a-x]\.\d{2}[oO]$',
    'rinex_nav': r'^\w{4}\d{3}[0-9a-x]\.\d{2}[nN]$',
    'rinex3': r'^\w{9}_\w_\d{11}_\d{2}\w_\d{2}\w_\w{2}\.\w{3}$',
    'trimble_dat': r'^.+\.dat$',
    'leica_mdb': r'^.+\.m[0-9]{2}$',
}

def classify_file(filename):
    for filetype, pattern in GNSS_PATTERNS.items():
        if re.match(pattern, filename, re.IGNORECASE):
            return filetype
    return 'unknown'
```

## Testing Strategy

- **Unit tests:** Individual functions (file classification, metadata extraction)
- **Integration tests:** Full scan workflows with test fixtures
- **Test fixtures:** Small sample datasets mimicking legacy drive structures
- **Coverage target:** >80% for core modules

**Test Data Requirements:**
- Sample RINEX files (OBS, NAV)
- Malformed filenames
- Duplicate files with different paths
- Directory structures (canonical and chaotic)

## Domain Knowledge: GNSS Data

**RINEX Filename Convention:**
- **Site code:** 4 characters (e.g., `ALGO` = Algonquin)
- **DOY (Day of Year):** 3 digits (001-366)
- **Session:** 1 character (0-9, a-x for 24-hour + sub-hourly)
- **Year:** 2 digits (22 = 2022)
- **Type:** O (observation), N (navigation), M (meteorological)

**Example:** `ALGO0010.22O`
- ALGO = Algonquin Park station
- 001 = January 1st
- 0 = first session (00:00-23:59)
- 22 = year 2022
- O = observation data

**Canonical Directory Structure:**
```
DATAPOOL/
└── {SITE}/          # 4-char station code
    └── {YYYY}/      # Year
        └── {DOY}/   # Day of year
            ├── {SITE}{DOY}{S}.{YY}O  # Observation
            └── {SITE}{DOY}{S}.{YY}N  # Navigation
```

## Special Considerations

1. **Large Files:** GNSS data files can be 100MB-1GB+. Use chunked reading for MD5 hashing.
2. **Slow Drives:** USB 2.0 drives may take hours to scan. Always show progress.
3. **Duplicate Detection:** Use MD5 hashes, not just filenames (files renamed across drives).
4. **Timestamp Preservation:** Critical for data provenance—use `mv -n` or Python's shutil with metadata preservation.
5. **Case Sensitivity:** RINEX extensions can be uppercase or lowercase (.O vs .o).

## Future Enhancements (Post-MVP)

- **Fuzzy Matching:** Detect misspelled site codes (`ALG0` → `ALGO`)
- **Duplicate Detection:** Cross-drive duplicate identification
- **Time-Series Validation:** Flag missing days in RINEX sequences
- **Web UI:** Replace CLI with browser-based interface
- **Database Backend:** SQLite for queryable scan results

## References

- **Architecture Spec:** `docs/Smart USB data ingestion system.md` (complete phased implementation plan)
- **Tech Stack Questions:** `docs/TECH_STACK_QUESTIONS.md` (pending dependency decisions)
- **RINEX Format:** https://files.igs.org/pub/data/format/rinex304.pdf
- **Project Repository:** https://github.com/alfieprojectsdev/drive-archaeologist

## Notes for Claude Instances

- **Current state:** Project skeleton exists, implementation files are empty placeholders
- **Priority:** Implement Phase 1 (foundation scanning and classification)
- **User context:** Transitioning geodesist with ADHD-optimized workflow preferences (see global CLAUDE.md)
- **Testing:** Follow TDD approach—write tests before implementation
- **Documentation:** Keep `docs/Smart USB data ingestion system.md` as source of truth for architecture decisions
