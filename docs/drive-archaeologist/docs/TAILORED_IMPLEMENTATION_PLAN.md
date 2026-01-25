# Tailored Implementation Plan - Drive Archaeologist

**Date:** 2025-11-06
**Status:** Customized based on user requirements
**Customization:** Windows-first, archive support, OCR priority, profile system

---

## 🎯 Your Specific Requirements

Based on your answers, here's what I'm optimizing for:

| Requirement | Priority | Impact on Plan |
|-------------|----------|----------------|
| **Windows Support** | CRITICAL | Phase 0 must work on Windows |
| **Archive Files (.7z, .rar)** | HIGH | Move to Phase 2 (not deferred) |
| **OCR (scanned PDFs + images)** | HIGH | Move to Phase 3-4 (not Phase 5) |
| **Large Drives (>1TB)** | MEDIUM | Performance testing essential |
| **Profile System** | CRITICAL | Core architecture in Phase 1 |

---

## 🏗️ Architectural Decisions

### Profile System Design

**Core Concept:** Modular domain classifiers with CLI toggle

```bash
# Scan everything (all domains)
drive-archaeologist scan /media/DRIVE

# GNSS-only mode
drive-archaeologist scan /media/DRIVE --profile gnss

# Personal media mode
drive-archaeologist scan /media/DRIVE --profile media

# Multiple profiles
drive-archaeologist scan /media/DRIVE --profile gnss,media

# Exclude specific profiles
drive-archaeologist scan /media/DRIVE --exclude-profile personal
```

**Implementation Strategy:**
- Phase 0: No profiles (scan all files)
- Phase 1: Implement profile system with domain classifiers
- Phase 2+: All features respect profile selections

---

## 📋 Revised Phases

### Phase 0: Cross-Platform Scanner (Week 1) - 10 hours
**Goal:** Working CLI that scans drives on Windows AND Linux

#### Windows-Specific Requirements
- ✅ Use `pathlib.Path` (cross-platform paths)
- ✅ Use `pathvalidate.sanitize_filename()` (handles Windows reserved names: CON, PRN, etc.)
- ✅ Test on Windows file systems (NTFS, FAT32, exFAT)
- ✅ Handle long paths (Windows 260-char limit)
- ✅ Support both forward and backslashes

#### Deliverables
1. **CLI Interface** (`cli.py`)
   - `drive-archaeologist scan <path>` command
   - `--output` flag for custom output location
   - `--format` flag (jsonl, csv)
   - Progress bar (cross-platform with `rich`)

2. **Cross-Platform Scanner** (`scanner.py`)
   - Recursive filesystem traversal
   - Metadata extraction (path, size, timestamps, extension)
   - JSONL streaming output (crash-safe)
   - Progress logging
   - Error handling (permission errors, special files)
   - **Windows-specific**: Handle junction points, system files

3. **Basic Report**
   - File count by extension
   - Total size by extension
   - Directory depth analysis
   - Timestamp range

#### Testing Strategy
- ✅ Test on Windows 10/11
- ✅ Test on Linux (Ubuntu)
- ✅ Test with spaces in paths
- ✅ Test with unicode filenames
- ✅ Test on NTFS, FAT32, exFAT
- ✅ Test with >1TB drive (performance)

#### Dependencies
```toml
dependencies = [
    "click>=8.1.0",           # CLI framework
    "rich>=13.0.0",           # Progress bars, pretty output (cross-platform)
    "tqdm>=4.66.0",           # Fallback progress bars
    "pathvalidate>=3.0.0",    # Filename sanitization (Windows safe)
]
```

#### Success Criteria
- ✅ Scans 10,000 files in < 5 minutes (Windows & Linux)
- ✅ Handles Windows reserved filenames (CON.dat → CON_.dat)
- ✅ Works with long paths (>260 chars on Windows)
- ✅ Resume works after interruption
- ✅ No crashes on permission errors

#### Estimated Effort
- **Implementation:** 6 hours
- **Windows testing:** 2 hours
- **Documentation:** 2 hours
- **Total:** 10 hours

---

### Phase 1: Profile System + Classification (Week 2) - 18 hours
**Goal:** Modular domain classification with `--profile` parameter

#### Profile System Architecture

```python
# src/drive_archaeologist/core/profiles.py

class ProfileManager:
    """Manages domain-specific classification profiles"""

    def __init__(self):
        self.profiles = {
            'gnss': GNSSProfile(),
            'media': MediaProfile(),
            'documents': DocumentProfile(),
            'code': CodeProfile(),
            'personal': PersonalProfile(),
        }

    def get_active_profiles(self, include=None, exclude=None):
        """Returns active profiles based on CLI flags"""
        if include:
            return {k: v for k, v in self.profiles.items() if k in include}
        elif exclude:
            return {k: v for k, v in self.profiles.items() if k not in exclude}
        else:
            return self.profiles  # All profiles
```

#### Deliverables

1. **Profile Manager** (`core/profiles.py`)
   - Profile registration system
   - CLI parameter handling (`--profile`, `--exclude-profile`)
   - Profile activation/deactivation logic

2. **GNSS Profile** (`domains/gnss/profile.py`)
   - RINEX observation files (`.??O`, `.rnx`, RINEX3)
   - RINEX navigation files (`.??N`)
   - Trimble formats (`.dat`, `.T01`, `.T02`)
   - Leica formats (`.m00`, `.m01`, `.m[0-9]{2}`)
   - Bernese outputs (`.STA`, `.OUT`, `.PRT`, `.SUM`)
   - Site logs (pattern: `*site*log*.pdf`, `*SITE*LOG*.PDF`)
   - Trimble raw binary (`.T0[0-2]`, `.DAT`)

3. **Media Profile** (`domains/media/profile.py`)
   - Images: JPEG, PNG, TIFF, RAW formats (CR2, NEF, ARW)
   - Video: MP4, AVI, MOV, MKV, WEBM
   - Audio: MP3, FLAC, WAV, AAC, OGG
   - EXIF metadata extraction (Pillow)

4. **Documents Profile** (`domains/documents/profile.py`)
   - PDF files (native and scanned)
   - Office: DOCX, XLSX, PPTX
   - Legacy Office: DOC, XLS, PPT
   - Text: TXT, MD, RTF
   - CSV, TSV data files

5. **Code Profile** (`domains/code/profile.py`)
   - Python: `.py`, `.pyx`, `.ipynb`
   - Shell: `.sh`, `.bash`, `.zsh`
   - MATLAB: `.m`, `.mat`
   - R: `.r`, `.R`, `.rmd`
   - Web: `.js`, `.html`, `.css`
   - Config: `.json`, `.yaml`, `.toml`, `.ini`

6. **Personal Profile** (`domains/personal/profile.py`)
   - Financial patterns: `*budget*`, `*loan*`, `*mortgage*`, `*tax*`
   - Private photos: EXIF privacy detection
   - Journals, diaries: common naming patterns
   - **Purpose:** Allow exclusion of sensitive data

7. **Enhanced CLI**
   ```bash
   drive-archaeologist scan /media/DRIVE --profile gnss
   drive-archaeologist scan /media/DRIVE --profile gnss,media
   drive-archaeologist scan /media/DRIVE --exclude-profile personal
   ```

#### Testing Strategy
- Create test fixtures for each profile
- Test GNSS filename variations (short/long names, different epochs)
- Test profile combinations (`--profile gnss,media`)
- Test profile exclusion (`--exclude-profile personal`)
- Validate classification confidence thresholds

#### Dependencies
```toml
dependencies = [
    # ... existing from Phase 0 ...
    "filetype>=1.2.0",        # Pure Python MIME detection
    "pillow>=10.0.0",         # Image metadata (EXIF)
]
```

#### Success Criteria
- ✅ Profile system works with all combinations
- ✅ 95%+ accuracy on GNSS files
- ✅ 90%+ accuracy on media/documents
- ✅ < 15% overhead on scan time
- ✅ Clear profile documentation

#### Estimated Effort
- **Profile architecture:** 4 hours
- **GNSS profile implementation:** 4 hours
- **Other profiles:** 6 hours
- **Testing:** 3 hours
- **Documentation:** 1 hour
- **Total:** 18 hours

---

### Phase 2: Archive Support + Structure Analysis (Week 3-4) - 20 hours
**Goal:** Extract/analyze archives + recommend organization

#### Archive Handling (NEW - moved from Phase 4)

Since archives are **common** on your drives, we need robust support early.

#### Deliverables

1. **Archive Inspector** (`archive_handler.py`)
   - Detect archive files (`.zip`, `.7z`, `.rar`, `.tar.gz`, `.tar.bz2`)
   - List contents without extraction (metadata only)
   - Estimate extraction size
   - Detect nested archives
   - Option to scan inside archives (recursive)

2. **Archive CLI Options**
   ```bash
   # Scan archives (list contents, don't extract)
   drive-archaeologist scan /media/DRIVE --scan-archives

   # Extract and scan archives (slower, comprehensive)
   drive-archaeologist scan /media/DRIVE --extract-archives

   # Ignore archives (fastest)
   drive-archaeologist scan /media/DRIVE  # default: list only, don't scan inside
   ```

3. **Structure Analyzer** (`analyzer.py`)
   - Directory tree analysis
   - Pattern detection (DATAPOOL, RAW, organized vs. chaos)
   - Cluster detection (files grouped by type/date/site)
   - Canonical structure recognition

4. **GNSS-Specific Structure Patterns**
   - Detect DATAPOOL: `{SITE}/{YEAR}/{DOY}/`
   - Detect RAW: `RAW/{YEAR}/{DOY}/`
   - Extract site codes from RINEX filenames
   - Detect incomplete date ranges (missing DOY)

5. **Recommendations Engine** (`recommendations.py`)
   - Suggest optimal folder structure per profile
   - Identify misplaced files
   - Detect duplicates (MD5 for files <100MB, size+name for larger)
   - Flag potential issues (orphaned data, missing files)

6. **Enhanced Reports**
   - Current structure summary
   - Recommended structure (DATAPOOL for GNSS)
   - File movement plan (source → destination)
   - Duplicate files report
   - Space savings potential (duplicates + compression)
   - Archive contents summary

#### Testing Strategy
- Test with `.zip` (stdlib), `.7z`, `.rar`, `.tar.gz`
- Test nested archives
- Test password-protected archives (detect, skip gracefully)
- Test corrupted archives (error handling)
- Validate structure detection on messy drives

#### Dependencies
```toml
dependencies = [
    # ... existing ...
    "pandas>=2.0.0",          # Data analysis
]

[project.optional-dependencies]
archive = [
    "py7zr>=0.20.0",          # Pure Python 7z support
    "rarfile>=4.0",           # RAR support (requires unrar binary)
]
```

#### Success Criteria
- ✅ Detects all common archive formats
- ✅ Lists archive contents without extraction
- ✅ Optional deep scan (extract + analyze)
- ✅ Identifies 90%+ GNSS files for DATAPOOL
- ✅ 100% duplicate detection accuracy (within size threshold)
- ✅ Analysis completes in reasonable time (<10 min for 100k files)

#### Estimated Effort
- **Archive handler:** 6 hours
- **Structure analyzer:** 6 hours
- **Recommendations engine:** 5 hours
- **Testing:** 2 hours
- **Documentation:** 1 hour
- **Total:** 20 hours

---

### Phase 3: Migration Scripts + Basic OCR (Week 5-6) - 24 hours
**Goal:** Safe reorganization + text extraction from scanned logsheets

#### Migration Scripts (from original Phase 3)

1. **Migration Planner** (`migration.py`)
   - Generate bash (Linux) and PowerShell (Windows) scripts
   - Dry-run mode (default: true)
   - Safety checks (no overwrites, MD5 verification)
   - Rollback script generation (undo.sh / undo.ps1)

2. **Cross-Platform Script Generation**
   ```bash
   # Linux
   drive-archaeologist migrate scan_results.jsonl --target-dir ~/DATAPOOL --dry-run
   # Generates: reorganize.sh + undo.sh

   # Windows
   drive-archaeologist migrate scan_results.jsonl --target-dir "C:\DATAPOOL" --dry-run
   # Generates: reorganize.ps1 + undo.ps1
   ```

3. **Script Features**
   - Create necessary directories (cross-platform)
   - Move files with safety checks (`mv -n` on Linux, `Move-Item -ErrorAction Stop` on Windows)
   - Log all operations
   - Verify file integrity post-move (optional MD5 check)
   - Handle long paths on Windows (\\?\ prefix)

#### Basic OCR (NEW - moved from Phase 5)

Since you have **many scanned PDFs + images of logsheets**, OCR is important.

4. **OCR Engine** (`extractors/ocr.py`)
   - PDF OCR for scanned logsheets
   - Image OCR for photographed paper logs
   - Detect digital vs. scanned PDFs (skip OCR for native PDFs)
   - Configurable OCR languages (English + Filipino?)
   - Quality detection (warn on low-quality scans)

5. **OCR CLI**
   ```bash
   # OCR scanned PDFs found in scan
   drive-archaeologist ocr scan_results.jsonl --profile gnss

   # OCR specific file types
   drive-archaeologist ocr scan_results.jsonl --file-types pdf,jpg,png

   # OCR with language specification
   drive-archaeologist ocr scan_results.jsonl --lang eng+fil
   ```

6. **Text Extraction Output**
   - Extracted text saved to `.txt` files alongside originals
   - Metadata includes OCR confidence score
   - Searchable index (SQLite database)

#### Testing Strategy
- Test migration scripts on Windows & Linux
- Test with long paths (Windows)
- Test with special characters in filenames
- Test rollback scripts (undo migration)
- Test OCR on scanned PDFs (various qualities)
- Test OCR on photos of logsheets
- Validate text extraction accuracy

#### Dependencies
```toml
[project.optional-dependencies]
ocr = [
    "pytesseract>=0.3.10",    # OCR for scanned PDFs/images
    "opencv-python>=4.8.0",   # Image preprocessing
    "pypdf>=3.0.0",           # PDF text extraction (native PDFs)
]
```

**System Requirements:**
- Tesseract OCR engine: `choco install tesseract` (Windows) or `apt install tesseract-ocr` (Linux)

#### Success Criteria
- ✅ Migration scripts work on Windows & Linux
- ✅ Dry-run accurately previews changes
- ✅ Migration completes successfully
- ✅ Rollback restores original state
- ✅ Zero data loss in stress testing
- ✅ OCR accuracy >80% on clear scans
- ✅ OCR correctly skips native digital PDFs

#### Estimated Effort
- **Migration planner (cross-platform):** 8 hours
- **OCR engine:** 10 hours
- **Testing:** 4 hours
- **Documentation:** 2 hours
- **Total:** 24 hours

---

### Phase 4: USB Auto-Detection + Advanced Reports (Week 7-8) - 22 hours
**Goal:** Automated workflow + rich HTML reports

#### Deliverables

1. **USB Monitor** (`usb_monitor.py`)
   - Cross-platform USB mount detection (Windows & Linux)
   - Auto-trigger scan on mount
   - Desktop notifications (Windows + Linux)
   - Background service mode

2. **HTML Report Generator** (`report_generator.py`)
   - Interactive HTML reports with charts
   - Timeline visualization (files by year)
   - Duplicate files grouped by hash
   - Storage optimization recommendations
   - Profile-specific reports (GNSS report vs. Media report)

3. **Advanced Duplicate Detection**
   - MD5 hashing for all files (not just <100MB)
   - Perceptual hashing for images (detect similar images)
   - Video duplicate detection (frame sampling)

4. **Archive Deep Scan**
   - Extract archives to temp directory
   - Scan contents
   - Clean up temp files
   - Include in reports

#### Testing Strategy
- Test USB detection on Windows & Linux
- Test with various drive formats (FAT32, NTFS, exFAT)
- Validate HTML reports in browsers (Chrome, Firefox, Edge)
- Test duplicate detection at scale (100k+ files)

#### Dependencies
```toml
[project.optional-dependencies]
usb = [
    "watchdog>=3.0.0",        # USB monitoring
]
reports = [
    "plotly>=5.0.0",          # Interactive charts
    "jinja2>=3.0.0",          # HTML templates
]
```

#### Success Criteria
- ✅ USB detection works reliably (90%+ success rate)
- ✅ HTML reports render correctly
- ✅ Duplicate detection performance acceptable (<30s for 100k files)
- ✅ Archive deep scan completes without errors

#### Estimated Effort
- **USB monitoring (cross-platform):** 8 hours
- **HTML reports:** 8 hours
- **Advanced duplicate detection:** 4 hours
- **Testing:** 2 hours
- **Total:** 22 hours

---

### Phase 5: Advanced OCR + Search (Week 9-10) - 20 hours
**Goal:** Full-text search across extracted documents

#### Deliverables

1. **Advanced OCR Features**
   - Batch OCR processing (parallel)
   - Image preprocessing (deskew, denoise, contrast adjustment)
   - Multi-column detection (complex layouts)
   - Table extraction from scanned documents

2. **Search Engine** (`search_engine.py`)
   - Full-text search in OCR'd documents
   - Search EXIF metadata
   - Keyword indexing (SQLite FTS5)
   - Boolean search operators (AND, OR, NOT)
   - Search results ranking

3. **Search CLI**
   ```bash
   # Search across all extracted text
   drive-archaeologist search "station TSKB" --index scan_results.db

   # Search specific profiles
   drive-archaeologist search "earthquake" --profile gnss --index scan_results.db

   # Search with filters
   drive-archaeologist search "2022" --file-type rinex_obs --index scan_results.db
   ```

#### Testing Strategy
- Test search accuracy on OCR'd documents
- Test search performance (< 1s for 10k documents)
- Validate ranking algorithm

#### Dependencies
```toml
[project.optional-dependencies]
search = [
    "whoosh>=2.7.4",          # Pure Python full-text search
]
```

#### Success Criteria
- ✅ Search results accurate and relevant
- ✅ Search completes in <1s for 10k documents
- ✅ Boolean operators work correctly

#### Estimated Effort
- **Advanced OCR:** 10 hours
- **Search engine:** 8 hours
- **Testing:** 2 hours
- **Total:** 20 hours

---

### Phase 6: Web UI + Cloud Features (Week 11+) - TBD
**Goal:** Optional web interface and cloud integration

(Defer until Phases 0-5 complete and evaluated)

---

## 📊 Updated Timeline

| Phase | Duration | Cumulative | Deliverables |
|-------|----------|-----------|--------------|
| **Phase 0** | 10 hrs (1.5 weeks) | 10 hrs | Cross-platform scanner |
| **Phase 1** | 18 hrs (2 weeks) | 28 hrs | Profile system + classification |
| **Phase 2** | 20 hrs (2.5 weeks) | 48 hrs | Archives + structure analysis |
| **Phase 3** | 24 hrs (3 weeks) | 72 hrs | Migration + basic OCR |
| **Phase 4** | 22 hrs (2.5 weeks) | 94 hrs | USB auto + HTML reports |
| **Phase 5** | 20 hrs (2.5 weeks) | 114 hrs | Advanced OCR + search |
| **Phase 6** | TBD | TBD | Web UI (evaluate later) |

**Total for Phases 0-5:** ~114 hours (~14 weeks)

---

## 🔧 Updated Dependencies

### Core Dependencies (Phase 0-1)
```toml
dependencies = [
    "click>=8.1.0",           # CLI framework
    "rich>=13.0.0",           # Beautiful terminal output
    "tqdm>=4.66.0",           # Progress bars
    "pathvalidate>=3.0.0",    # Filename sanitization (Windows safe)
    "filetype>=1.2.0",        # Pure Python file detection
    "pillow>=10.0.0",         # Image metadata (EXIF)
    "pandas>=2.0.0",          # Data analysis (Phase 2)
]
```

### Optional Dependencies
```toml
[project.optional-dependencies]
# Archive support (Phase 2)
archive = [
    "py7zr>=0.20.0",          # 7z support
    "rarfile>=4.0",           # RAR support
]

# OCR support (Phase 3)
ocr = [
    "pytesseract>=0.3.10",    # OCR engine
    "opencv-python>=4.8.0",   # Image preprocessing
    "pypdf>=3.0.0",           # PDF text extraction
]

# USB monitoring (Phase 4)
usb = [
    "watchdog>=3.0.0",        # File system monitoring
]

# HTML reports (Phase 4)
reports = [
    "plotly>=5.0.0",          # Interactive charts
    "jinja2>=3.0.0",          # HTML templates
]

# Full-text search (Phase 5)
search = [
    "whoosh>=2.7.4",          # Pure Python search engine
]

# Development
dev = [
    "pytest>=7.4.0",
    "pytest-cov>=4.1.0",
    "ruff>=0.1.0",
    "mypy>=1.5.0",
    "ipython>=8.12.0",
]
```

---

## 🎯 Profile System Examples

### Use Case 1: GNSS-Only Drive
```bash
# Scan only GNSS files
drive-archaeologist scan /media/PHIVOLCS_2022 --profile gnss

# Output focuses on RINEX, Trimble, Leica, Bernese files
# Ignores personal photos, documents, etc.
```

### Use Case 2: Mixed Personal+Work Drive
```bash
# Scan everything EXCEPT personal files
drive-archaeologist scan /media/OLD_SEAGATE --exclude-profile personal

# Analyzes GNSS + media + documents
# Skips files matching personal patterns (budget*, tax*, etc.)
```

### Use Case 3: Media Archive
```bash
# Scan only media files
drive-archaeologist scan /media/FAMILY_PHOTOS --profile media

# Focuses on photos, videos, audio
# Extracts EXIF metadata
# Detects duplicates
```

### Use Case 4: Code Repository Recovery
```bash
# Scan only code files
drive-archaeologist scan /media/OLD_LAPTOP --profile code

# Finds Python, shell, MATLAB files
# Detects orphaned git repos
```

---

## 🚀 Updated Implementation Priority

### Critical Path (Phases 0-3) - 72 hours (~9 weeks)
**Must Have:**
- ✅ Cross-platform scanner (Windows + Linux)
- ✅ Profile system (`--profile` parameter)
- ✅ GNSS + Media + Document classification
- ✅ Archive support (common on your drives)
- ✅ Structure analysis + recommendations
- ✅ Safe migration scripts
- ✅ Basic OCR (many scanned docs)

**Result:** Complete, production-ready tool for your use case

---

### Enhancement Track (Phases 4-5) - 42 hours (~6 weeks)
**Should Have:**
- USB auto-detection (convenience)
- HTML reports (visualization)
- Advanced OCR (better accuracy)
- Full-text search (findability)

**Result:** Advanced features, evaluate based on Phase 0-3 usage

---

### Future Track (Phase 6) - TBD
**Nice to Have:**
- Web UI (if multi-user needed)
- Cloud integration (if remote access needed)

**Result:** Enterprise features, evaluate later

---

## 🧪 Windows-Specific Testing Checklist

### Phase 0 Testing
- [ ] Test on Windows 10
- [ ] Test on Windows 11
- [ ] Test on NTFS file system
- [ ] Test on FAT32 file system (external drives)
- [ ] Test on exFAT file system (large USB drives)
- [ ] Test with paths >260 characters
- [ ] Test with reserved filenames (CON.dat, PRN.log, etc.)
- [ ] Test with unicode filenames (Tagalog characters)
- [ ] Test with spaces in paths
- [ ] Test with junction points / symlinks
- [ ] Test permission errors (system files)
- [ ] Test drive letter paths (C:\, D:\, etc.)
- [ ] Test UNC paths (\\server\share\)

### Phase 3 Testing (Windows)
- [ ] PowerShell script generation works
- [ ] Migration scripts handle long paths
- [ ] Rollback scripts work correctly
- [ ] Test with Windows Defender running (file locks)
- [ ] Test with OneDrive-synced folders

---

## 💡 Key Architectural Decisions

### 1. Profile System is Core
**Decision:** Implement profiles in Phase 1, not later
**Rationale:** Your use case requires toggling between GNSS-only and mixed scans
**Impact:** All features (scanning, analysis, migration) respect profile selections

### 2. Archives are Common
**Decision:** Move archive support to Phase 2
**Rationale:** Archives are common on your drives (not optional)
**Impact:** Archive handling is core feature, not deferred

### 3. OCR is Important
**Decision:** Move OCR to Phase 3 (from Phase 5)
**Rationale:** Many scanned PDFs + images of logsheets
**Impact:** OCR is part of core tool, not optional add-on

### 4. Windows is Primary
**Decision:** Windows support from Phase 0
**Rationale:** You confirmed Windows support is needed
**Impact:** All features tested on Windows from day 1

### 5. Performance for Large Drives
**Decision:** Streaming, chunking, resume capability
**Rationale:** >1TB drives require efficient processing
**Impact:** Memory-efficient design from Phase 0

---

## 🎬 Next Steps

### Immediate (Today)
1. Review this tailored plan
2. Confirm profile system design matches your vision
3. Confirm phase priorities (archives in Phase 2, OCR in Phase 3)
4. Approve starting Phase 0 implementation

### Phase 0 (Week 1-2)
1. Implement cross-platform scanner
2. Test on Windows & Linux
3. Test with >1TB drive
4. Deliver working CLI tool

### Phase 1 (Week 2-3)
1. Implement profile system
2. Add GNSS classification
3. Add media/document classification
4. Test `--profile` parameter

### Phase 2+ (Week 4-8)
- Continue based on Phase 0-1 feedback
- Adjust priorities as needed

---

## ❓ Confirmation Questions

Before I start implementation, please confirm:

1. **Profile System:** Does the `--profile gnss` design match your vision?
2. **Windows Priority:** Should I develop/test on Windows first, or Linux first?
3. **OCR Languages:** English only, or English + Filipino (Tagalog)?
4. **Archive Handling:** Extract archives by default, or list-only by default?
5. **Testing Drives:** Do you have test drives available for each phase?

---

## 🎯 Ready to Start?

Once you confirm the above, I'll:

1. Update `pyproject.toml` with new dependencies
2. Execute `/plan-implementation` for Phase 0
3. Start building the cross-platform scanner
4. Deliver working Phase 0 in ~10 hours

**Your move!** Confirm the plan or ask any questions.
