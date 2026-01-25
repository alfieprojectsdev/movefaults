# Phase 0 Implementation - Kickoff Document

**Date:** 2025-11-06
**Status:** APPROVED - Ready to Start
**Duration:** 10 hours (~1.5 weeks)

---

## ✅ User Confirmations Received

All decisions confirmed. Ready to proceed with implementation.

### 1. Profile System Architecture ✅
**Confirmed:** `--profile gnss` design approved
- No changes needed
- Implementation in Phase 1 as planned

### 2. Development Priority ✅
**Confirmed:** Windows-first development
- Primary staff computers: Windows
- Production deployment: Linux servers
- Goal: Flexibility for both environments with minimal reconfiguration

### 3. OCR Language Support ✅
**Confirmed:** English + Filipino (Tagalog)
- **Critical requirement:** Handwritten notes support
- Tesseract language packs: `eng + fil`
- Image preprocessing for handwriting recognition

### 4. Archive Handling Behavior ✅
**Confirmed:** Option C - User must explicitly enable
- Default: List archive files (no deep scan)
- Deep scan: `--scan-archives` flag required
- Rationale: Performance and user control

### 5. Testing Infrastructure ✅
**Confirmed:** Test drives available
- Small test folders (development testing)
- Medium drives (~100GB) (integration testing)
- Large drives (>1TB) (performance testing)

---

## 📦 Package Manager: uv

**IMPORTANT:** Use `uv` instead of `pip` for all package management.

Reference: `docs/Smart USB data ingestion system.md`

### Installation Commands

```bash
# Install uv (if not installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment
uv venv

# Activate environment (Windows)
.venv\Scripts\activate

# Activate environment (Linux)
source .venv/bin/activate

# Install project in development mode
uv pip install -e .

# Install with optional dependencies
uv pip install -e ".[dev]"
uv pip install -e ".[archive]"
uv pip install -e ".[ocr]"
```

### Why uv?
- ⚡ Fast (Rust-based, 10-100x faster than pip)
- 🔒 Reliable (deterministic resolution)
- 🎯 Correct (proper dependency resolution)
- 📦 Modern (pip-compatible interface)

---

## 🎯 Phase 0 Goals

### Primary Objective
Build a cross-platform CLI scanner that works reliably on Windows and Linux.

### Deliverables

1. **CLI Interface** (`src/drive_archaeologist/cli.py`)
   - `drive-archaeologist scan <path>` command
   - Progress bars with `rich` library
   - Clean, professional output
   - Cross-platform path handling

2. **Core Scanner** (`src/drive_archaeologist/scanner.py`)
   - Recursive filesystem traversal
   - Metadata extraction (path, size, timestamps, extension)
   - JSONL streaming output (crash-safe)
   - Resume capability (checkpoint system)
   - Error handling (permissions, special files)
   - Windows-specific: junction points, long paths, reserved names

3. **Basic Statistics Report**
   - File count by extension
   - Total size by extension
   - Directory depth analysis
   - Oldest/newest file timestamps
   - Scan duration and performance stats

---

## 🔧 Phase 0 Technical Specifications

### Dependencies (Phase 0)

```toml
# Core dependencies for Phase 0
dependencies = [
    "click>=8.1.0",           # CLI framework
    "rich>=13.0.0",           # Beautiful terminal output (cross-platform)
    "pathvalidate>=3.0.0",    # Filename sanitization (Windows reserved names)
]
```

### File Structure

```
src/drive_archaeologist/
├── __init__.py
├── __main__.py              # Entry point for python -m
├── cli.py                   # Click CLI commands
├── scanner.py               # DeepScanner class
├── utils/
│   ├── __init__.py
│   ├── paths.py            # Cross-platform path utilities
│   ├── progress.py         # Progress tracking
│   └── checkpoint.py       # Resume capability
└── core/
    ├── __init__.py
    └── config.py           # Configuration management
```

### Windows-Specific Requirements

#### 1. Path Handling
- Use `pathlib.Path` exclusively (cross-platform)
- Handle both forward slashes (`/`) and backslashes (`\`)
- Support UNC paths (`\\server\share\`)
- Support long paths (>260 chars) with `\\?\` prefix

#### 2. Reserved Filenames
Windows reserved names that need sanitization:
- `CON`, `PRN`, `AUX`, `NUL`
- `COM1` through `COM9`
- `LPT1` through `LPT9`

Use `pathvalidate.sanitize_filename()` to handle these.

#### 3. File System Features
- Handle junction points (Windows symlinks)
- Skip system files (`System Volume Information`, `$RECYCLE.BIN`)
- Handle permission errors gracefully (Administrator files)

#### 4. Performance
- Test on NTFS (primary Windows file system)
- Test on FAT32 (older USB drives, 4GB file limit)
- Test on exFAT (modern USB drives, no file size limit)

---

## 📊 Output Format Specification

### JSONL Output (JSON Lines)

Each line is a valid JSON object representing one file:

```json
{"path": "C:\\Users\\User\\Documents\\ALGO0010.22O", "name": "ALGO0010.22O", "extension": ".22o", "size_bytes": 4251840, "size_mb": 4.05, "modified": "2022-04-10T14:23:15", "created": "2022-04-10T14:20:00", "parent_dir": "C:\\Users\\User\\Documents", "depth": 3, "scan_timestamp": "2025-11-06T10:30:00"}
```

**Fields:**
- `path`: Absolute path (Windows or Linux format)
- `name`: Filename only
- `extension`: File extension (lowercase, with dot)
- `size_bytes`: File size in bytes
- `size_mb`: File size in MB (rounded to 2 decimals)
- `modified`: Last modified timestamp (ISO 8601)
- `created`: Creation timestamp (ISO 8601)
- `parent_dir`: Parent directory path
- `depth`: Directory depth from scan root
- `scan_timestamp`: When this file was scanned (ISO 8601)

### Log File Format

```
[2025-11-06 10:30:00] 🔍 Starting deep scan of: C:\Users\User\OldDrive
[2025-11-06 10:30:00] 📊 Output: scan_OldDrive_20251106_103000.jsonl
[2025-11-06 10:30:00] 📝 Log: scan_OldDrive_20251106_103000.log
[2025-11-06 10:30:10] ✅ Processed 100 files (10.0 files/sec)
[2025-11-06 10:30:20] ✅ Processed 200 files (10.5 files/sec)
[2025-11-06 10:30:30] 💾 Checkpoint saved (1000 files)
[2025-11-06 10:35:00] 🎉 Scan Complete!
[2025-11-06 10:35:00] 📁 Files processed: 4,523
[2025-11-06 10:35:00] ⚠️  Errors: 3
[2025-11-06 10:35:00] ⏱️  Time elapsed: 00:05:00
```

---

## 🧪 Testing Strategy

### Unit Tests
- Path sanitization (Windows reserved names)
- Extension extraction
- Size calculation
- Timestamp formatting
- Cross-platform path handling

### Integration Tests
- Scan small directory (<100 files)
- Scan medium directory (1,000-10,000 files)
- Resume capability (kill process, restart)
- Error handling (unreadable files, permission errors)

### Platform-Specific Tests

#### Windows Tests
- [ ] Test on Windows 10
- [ ] Test on Windows 11
- [ ] Test with paths >260 characters
- [ ] Test with reserved filenames (`CON.dat`, `PRN.log`)
- [ ] Test with unicode filenames (Tagalog characters: `ñ`, `Ñ`)
- [ ] Test on NTFS file system
- [ ] Test on FAT32 file system (external USB)
- [ ] Test on exFAT file system (large USB)
- [ ] Test with spaces in paths
- [ ] Test with junction points
- [ ] Test permission errors (system files)
- [ ] Test drive letters (`C:\`, `D:\`, `E:\`)
- [ ] Test UNC paths (`\\server\share\`)

#### Linux Tests
- [ ] Test on Ubuntu/Debian
- [ ] Test with symlinks
- [ ] Test with permission errors
- [ ] Test on ext4 file system
- [ ] Test on mounted NTFS drive

### Performance Tests
- [ ] Scan 10,000 files in < 5 minutes
- [ ] Scan 100,000 files in < 45 minutes
- [ ] Memory usage < 100MB for 10,000 files
- [ ] Resume works reliably (tested 5 times)
- [ ] No memory leaks during long scans

---

## 📈 Success Metrics

### Functional Requirements
- ✅ Scans any directory or drive
- ✅ Outputs valid JSONL format
- ✅ Handles errors gracefully (no crashes)
- ✅ Resume works after interruption
- ✅ Works on Windows and Linux

### Performance Requirements
- ✅ 10,000 files in < 5 minutes
- ✅ Memory usage < 100MB (streaming mode)
- ✅ Progress updates every 100 files
- ✅ Checkpoint every 1,000 files

### Quality Requirements
- ✅ Zero crashes on test drives
- ✅ Handles permission errors
- ✅ Handles special characters in filenames
- ✅ Handles long paths (Windows)
- ✅ Clear error messages

---

## 🛠️ Implementation Tasks

### Task 1: CLI Interface (2 hours)
**File:** `src/drive_archaeologist/cli.py`

**Requirements:**
- Use `click` framework
- Implement `scan` command
- Add `--output` flag (custom output location)
- Add `--resume` flag (continue previous scan)
- Validate input path exists
- Display help text

**Example:**
```bash
drive-archaeologist scan C:\OldDrive
drive-archaeologist scan C:\OldDrive --output custom_scan.jsonl
drive-archaeologist scan C:\OldDrive --resume
```

---

### Task 2: Core Scanner (4 hours)
**File:** `src/drive_archaeologist/scanner.py`

**Requirements:**
- Recursive directory traversal (`pathlib.Path.rglob()`)
- File metadata extraction (`stat()`)
- JSONL streaming output (write each file immediately)
- Progress tracking (log every 100 files)
- Error handling (try/except, log errors, continue)

**Class Structure:**
```python
class DeepScanner:
    def __init__(self, root_path, output_file=None, resume=False):
        """Initialize scanner with root path"""

    def scan(self):
        """Main scanning loop with progress tracking"""

    def _extract_metadata(self, filepath):
        """Extract file metadata (fast operations only)"""

    def _should_skip(self, filepath):
        """Determine if file should be skipped (system files, etc.)"""

    def _print_summary(self):
        """Final statistics"""
```

---

### Task 3: Checkpoint System (2 hours)
**File:** `src/drive_archaeologist/utils/checkpoint.py`

**Requirements:**
- Save progress every 1,000 files
- Resume from last checkpoint
- Track scanned paths to avoid duplicates
- JSON checkpoint file format

**Class Structure:**
```python
class CheckpointManager:
    def __init__(self, scan_id):
        """Initialize checkpoint manager"""

    def mark_scanned(self, path):
        """Mark file as scanned"""

    def save_checkpoint(self):
        """Save current progress to disk"""

    def is_scanned(self, path):
        """Check if file already scanned"""
```

---

### Task 4: Path Utilities (1 hour)
**File:** `src/drive_archaeologist/utils/paths.py`

**Requirements:**
- Sanitize filenames (Windows reserved names)
- Normalize paths (forward slashes)
- Handle long paths (Windows \\?\ prefix)
- Detect system directories (skip $RECYCLE.BIN, etc.)

**Functions:**
```python
def sanitize_filename(name: str) -> str:
    """Sanitize filename for cross-platform safety"""

def normalize_path(path: Path) -> str:
    """Normalize path to consistent format"""

def is_system_directory(path: Path) -> bool:
    """Check if directory is a system directory"""

def handle_long_path(path: Path) -> Path:
    """Handle Windows long paths (>260 chars)"""
```

---

### Task 5: Progress Display (1 hour)
**File:** `src/drive_archaeologist/utils/progress.py`

**Requirements:**
- Real-time progress bar (using `rich`)
- File count and rate display
- Elapsed time display
- ETA calculation (estimated time remaining)

**Class Structure:**
```python
class ProgressTracker:
    def __init__(self):
        """Initialize progress tracker"""

    def update(self, file_count: int, elapsed: float):
        """Update progress display"""

    def complete(self):
        """Mark scan as complete"""
```

---

## 📚 Documentation Requirements

### User Documentation
- [ ] Installation guide (using `uv`)
- [ ] Quick start guide
- [ ] CLI reference
- [ ] Output format specification
- [ ] Troubleshooting guide

### Developer Documentation
- [ ] Code architecture overview
- [ ] Contributing guide
- [ ] Testing guide
- [ ] Windows-specific notes

---

## 🚀 Execution Plan

### Step 1: Update pyproject.toml (15 min)
- Add Phase 0 dependencies
- Verify CLI entry points
- Update documentation links

### Step 2: Implement Core (6 hours)
- Task 1: CLI Interface (2 hours)
- Task 2: Core Scanner (4 hours)

### Step 3: Add Utilities (4 hours)
- Task 3: Checkpoint System (2 hours)
- Task 4: Path Utilities (1 hour)
- Task 5: Progress Display (1 hour)

### Step 4: Testing (2 hours)
- Unit tests (30 min)
- Integration tests (30 min)
- Windows testing (1 hour)

### Step 5: Documentation (1 hour)
- Installation guide
- Quick start guide
- CLI reference

**Total: 10 hours**

---

## 🎯 Definition of Done

Phase 0 is complete when:

- ✅ CLI command works: `drive-archaeologist scan <path>`
- ✅ Scans any directory and produces valid JSONL output
- ✅ Resume capability works (tested)
- ✅ Works on Windows 10/11 (tested)
- ✅ Works on Linux (tested)
- ✅ Handles errors gracefully (no crashes)
- ✅ Performance meets targets (10k files in <5 min)
- ✅ Unit tests pass
- ✅ Integration tests pass
- ✅ Documentation complete (installation + quick start)
- ✅ Code committed and pushed to branch

---

## 📝 Notes for Implementation

### Windows Development Notes
1. **Test with real drives**: USB drives, external HDDs, network shares
2. **Test with edge cases**: Long paths, reserved names, special characters
3. **Test performance**: Large drives (>1TB) with many files

### Linux Compatibility
1. **Path separators**: Code should work with both `/` and `\`
2. **Symlinks**: Handle gracefully (don't follow infinite loops)
3. **Permissions**: Skip files that can't be read (don't crash)

### Performance Optimization
1. **Streaming output**: Write each file immediately (don't buffer in memory)
2. **Generator-based traversal**: Use `rglob()` generator (don't load all paths)
3. **Checkpoint system**: Save progress periodically (enable resume)

---

## 🔄 Next Steps After Phase 0

Once Phase 0 is complete and tested:

1. **User feedback**: Test with real PHIVOLCS drives
2. **Performance validation**: Measure actual scan times
3. **Bug fixes**: Address any issues found
4. **Phase 1 kickoff**: Implement profile system + classification

---

## ✅ Ready to Start

All confirmations received. All decisions documented. Ready to execute `/plan-implementation`.

**Package Manager:** uv (Rust-based, fast)
**Development Platform:** Windows-first
**Testing Infrastructure:** Available (small, medium, large drives)
**Profile System:** Approved (implementation in Phase 1)
**OCR Languages:** English + Filipino (Tagalog) + handwriting support
**Archive Handling:** User must enable with `--scan-archives` flag

**Let's build this!** 🚀
