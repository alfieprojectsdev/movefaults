# Drive Archaeologist

Excavate decades of data from old hard drives.

Automatically scans, classifies, and organizes legacy GNSS data, field notes, and mixed personal/work files scattered across dusty hard drives.

## Features

### Phase 0 (Current)
- Cross-platform CLI scanner (Windows + Linux)
- JSONL output with file metadata
- Resume capability for interrupted scans
- Progress tracking
- Error handling (skip unreadable files)

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
