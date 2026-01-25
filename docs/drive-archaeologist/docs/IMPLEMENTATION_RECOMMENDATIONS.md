# Drive Archaeologist - Implementation Recommendations

**Date:** 2025-11-06
**Status:** Awaiting Approval
**Objective:** Excavate decades of data from old hard drives

---

## Executive Summary

Based on analysis of the project documentation, this plan provides a phased implementation strategy building from the simplest usable iteration to the full-featured system envisioned in the docs. Each phase delivers immediate value while building toward the complete vision.

**Key Principles:**
- ✅ Start with immediate usability (working tool in Phase 0)
- ✅ Minimize external dependencies initially
- ✅ Add complexity only when proven necessary
- ✅ Support both GNSS-specific and general-purpose file archaeology
- ✅ Design for slow, unreliable drives (resume capability, progress tracking)
- ✅ ADHD-friendly (visual feedback, no babysitting required)

---

## Tech Stack Decisions (Required Before Phase 0)

### Decision 1: File Type Detection
**Recommendation:** Start with `filetype` (pure Python), defer `python-magic`

**Rationale:**
- Zero system dependencies (cross-platform friendly)
- 90% accuracy sufficient for initial implementation
- RINEX files are text-based (easy pattern matching)
- Can add `python-magic` as optional dependency in Phase 3 if accuracy issues arise

**Action:** Remove `python-magic>=0.4.27` from core dependencies, move to optional

---

### Decision 2: Archive Handling
**Recommendation:** Phase 2 feature (optional dependency)

**Rationale:**
- Phase 0-1 focuses on direct file access
- `.zip` support via stdlib (no dependency)
- `.7z`, `.rar` support via optional dependencies when needed
- Users can manually extract archives for Phase 0-1

**Action:** Keep archive dependencies optional (current approach is correct)

---

### Decision 3: OCR Support
**Recommendation:** Phase 4 feature (optional dependency)

**Rationale:**
- Complex system dependencies (Tesseract)
- Not required for core scanning/classification functionality
- Valuable for scanned logsheets but deferred until core features proven

**Action:** Keep OCR optional (current approach is correct)

---

### Decision 4: USB Hot-Plug Detection
**Recommendation:** Phase 3 feature, add `watchdog` as optional dependency

**Rationale:**
- Not needed for initial manual scanning workflow
- Adds complexity to first-time user experience
- Valuable for production use but not MVP

**Action:** Add to optional dependencies: `[project.optional-dependencies] usb = ["watchdog>=3.0.0"]`

---

### Decision 5: Additional Dependencies

**ADD to core dependencies:**
- `pathvalidate>=3.0.0` - Filename sanitization (prevents edge case bugs)
- `filetype>=1.2.0` - Pure Python file detection (replaces python-magic)

**REMOVE from core dependencies:**
- `python-magic>=0.4.27` - Move to optional

---

## Phase 0: Minimal Viable Scanner (Week 1)
**Goal:** Working CLI tool that can scan a drive and produce a report

### Deliverables
1. **CLI Interface** (`src/drive_archaeologist/cli.py`)
   - `drive-archaeologist scan <path>` command
   - `--output` flag for custom output location
   - `--format` flag (jsonl, csv)
   - Progress bar with file count

2. **Basic Scanner** (`src/drive_archaeologist/scanner.py`)
   - Recursive filesystem traversal
   - Metadata extraction (path, size, timestamps, extension)
   - JSONL output (streaming, crash-safe)
   - Progress logging to separate log file
   - Error handling (skip unreadable files, continue scanning)

3. **Simple Report**
   - File count by extension
   - Total size by extension
   - Directory depth analysis
   - Timestamp range (oldest/newest files)

### Features
- ✅ Scan any directory or drive
- ✅ Stream results to disk (memory-efficient for large drives)
- ✅ Resume capability (checkpoint every 1000 files)
- ✅ Real-time progress updates
- ✅ Handles errors gracefully

### Testing Strategy
- Test on small directory (< 100 files)
- Test on medium directory (1,000-10,000 files)
- Verify resume capability (kill process mid-scan, restart)
- Verify output format (valid JSONL, parseable)

### Success Criteria
- ✅ Can scan 10,000 files in < 5 minutes
- ✅ Produces valid JSONL output
- ✅ Resume works after interruption
- ✅ No memory growth during long scans

### Dependencies
- `click` (CLI framework)
- `rich` (progress bars, pretty output)
- `tqdm` (progress tracking)

### Estimated Effort
- **Implementation:** 4-6 hours
- **Testing:** 2 hours
- **Documentation:** 1 hour
- **Total:** ~8 hours

---

## Phase 1: File Classification (Week 2)
**Goal:** Identify file types beyond extensions

### Deliverables
1. **Classifier System** (`src/drive_archaeologist/classifier.py`)
   - Pattern-based classification (regex matching)
   - Extension-based fallback
   - Domain-specific classifiers (GNSS, Media, Documents, Code)
   - Confidence scoring

2. **GNSS Patterns** (`src/drive_archaeologist/domains/gnss/patterns.py`)
   - RINEX observation files (`.??O`, `.rnx`, RINEX3 naming)
   - RINEX navigation files (`.??N`)
   - Trimble formats (`.dat`, `.T01`, `.T02`)
   - Leica formats (`.m00`, `.m01`, etc.)
   - Bernese outputs (`.STA`, `.OUT`, `.PRT`, `.SUM`)
   - Site logs (pattern: `*site*log*.pdf`)

3. **General Patterns** (`src/drive_archaeologist/domains/common/patterns.py`)
   - Media: images (JPEG, PNG, RAW), video (MP4, AVI), audio (MP3, FLAC)
   - Documents: PDF, DOCX, XLSX, PPT
   - Code: Python, Shell, MATLAB, R
   - Archives: ZIP, TAR.GZ, 7Z, RAR

4. **Enhanced Report**
   - File count by classified type
   - Domain breakdown (GNSS, Media, Documents, etc.)
   - Unclassified files report

### Features
- ✅ Automatic file type detection
- ✅ GNSS-specific format recognition
- ✅ Extensible pattern system
- ✅ Confidence scoring for ambiguous files

### Testing Strategy
- Create test fixtures for each file type
- Test GNSS filename variations (short/long names, different epochs)
- Test misnamed files (e.g., `.txt` that's actually RINEX)
- Validate classification confidence thresholds

### Success Criteria
- ✅ 95%+ accuracy on GNSS files
- ✅ 90%+ accuracy on general files
- ✅ < 5% unclassified files in typical dataset
- ✅ Classification adds < 10% overhead to scan time

### Dependencies
- `filetype` (MIME type detection)

### Estimated Effort
- **Implementation:** 6-8 hours
- **Pattern development:** 4 hours
- **Testing:** 3 hours
- **Documentation:** 1 hour
- **Total:** ~16 hours

---

## Phase 2: Structure Analysis (Week 3-4)
**Goal:** Understand how files are organized and recommend improvements

### Deliverables
1. **Structure Analyzer** (`src/drive_archaeologist/analyzer.py`)
   - Directory tree analysis
   - Pattern detection (identify common organizational schemes)
   - Cluster detection (files grouped by type, date, site)
   - Canonical structure recognition (DATAPOOL pattern detection)

2. **GNSS Structure Patterns**
   - Detect DATAPOOL-style organization: `{SITE}/{YEAR}/{DOY}/`
   - Detect RAW data organization: `RAW/{YEAR}/{DOY}/`
   - Detect mixed/chaotic organization
   - Extract site codes from RINEX filenames

3. **Recommendations Engine** (`src/drive_archaeologist/recommendations.py`)
   - Suggest optimal folder structure
   - Identify misplaced files
   - Detect duplicate files (by hash)
   - Flag potential issues (missing files, orphaned data)

4. **Enhanced Analysis Report**
   - Current structure summary
   - Recommended structure
   - File movement plan (source → destination)
   - Duplicate files report
   - Space savings potential

### Features
- ✅ Detects existing organizational patterns
- ✅ Recommends DATAPOOL structure for GNSS files
- ✅ Year/date-based organization for media files
- ✅ Duplicate detection (MD5 hashing for small files)
- ✅ Preview reorganization without making changes

### Testing Strategy
- Test with messy directory structure
- Test with partially organized structure
- Test with already-organized structure (should recommend minimal changes)
- Validate duplicate detection accuracy

### Success Criteria
- ✅ Identifies 90%+ of GNSS files for DATAPOOL reorganization
- ✅ Detects duplicate files with 100% accuracy
- ✅ Recommendations are actionable (clear source→destination mappings)
- ✅ Analysis completes in reasonable time (< 10 min for 100k files)

### Dependencies
- `pandas` (data analysis)

### Estimated Effort
- **Implementation:** 8-10 hours
- **Testing:** 4 hours
- **Documentation:** 2 hours
- **Total:** ~16 hours

---

## Phase 3: Migration Script Generation (Week 5)
**Goal:** Generate safe, executable reorganization scripts

### Deliverables
1. **Migration Planner** (`src/drive_archaeologist/migration.py`)
   - Generate bash/PowerShell scripts
   - Dry-run mode (preview changes)
   - Safety checks (no overwrites, MD5 verification)
   - Rollback script generation

2. **CLI Commands**
   - `drive-archaeologist migrate <scan_results.jsonl>`
   - `--target-dir` flag (destination root)
   - `--dry-run` flag (default: true)
   - `--verify` flag (MD5 check after move)
   - `--generate-undo` flag (create rollback script)

3. **Script Features**
   - Create necessary directories
   - Move files with safety checks (`mv -n` to prevent overwrites)
   - Log all operations
   - Verify file integrity post-move (optional MD5 check)
   - Generate undo script for rollback

4. **Enhanced Reports**
   - Preview of changes (file count, space usage)
   - Potential conflicts report
   - Success/failure log

### Features
- ✅ Dry-run by default (safe to test)
- ✅ Generates executable bash/PowerShell scripts
- ✅ MD5 verification for integrity
- ✅ Rollback capability
- ✅ Prevents data loss (no overwrites)

### Testing Strategy
- Test dry-run mode (no files moved)
- Test actual migration on test directory
- Test rollback script (undo migration)
- Test conflict detection (duplicate filenames)
- Test on Windows (PowerShell script) and Linux (bash)

### Success Criteria
- ✅ Dry-run accurately previews changes
- ✅ Migration completes successfully on test data
- ✅ Rollback restores original state
- ✅ Zero data loss in stress testing
- ✅ Handles edge cases (spaces in filenames, unicode characters)

### Dependencies
- `pathvalidate` (filename sanitization)

### Estimated Effort
- **Implementation:** 8-10 hours
- **Testing:** 5 hours
- **Documentation:** 2 hours
- **Total:** ~17 hours

---

## Phase 4: USB Auto-Detection & Advanced Features (Week 6-7)
**Goal:** Automated workflow and advanced file analysis

### Deliverables
1. **USB Monitor** (`src/drive_archaeologist/usb_monitor.py`)
   - Watch for USB drive mounts
   - Auto-trigger scan on mount
   - Desktop notifications
   - Background service mode

2. **Advanced File Analysis**
   - MD5 hashing for duplicate detection (all files)
   - PDF text extraction (metadata only, not full OCR)
   - Image metadata (EXIF data for photos)
   - Archive file inspection (list contents without extraction)

3. **Enhanced Reports**
   - Interactive HTML report with charts
   - Timeline visualization (files by year)
   - Duplicate files grouped by hash
   - Storage optimization recommendations

4. **CLI Commands**
   - `drive-archaeologist watch` (monitor USB mounts)
   - `drive-archaeologist analyze <scan_results.jsonl>` (deep analysis)
   - `drive-archaeologist report <scan_results.jsonl>` (generate HTML report)

### Features
- ✅ Automatic scanning on USB insertion
- ✅ Comprehensive duplicate detection
- ✅ Rich HTML reports with visualizations
- ✅ Archive file inspection
- ✅ Image metadata extraction

### Testing Strategy
- Test USB detection on multiple platforms
- Test with various drive formats (FAT32, NTFS, exFAT)
- Validate HTML report generation
- Test duplicate detection at scale (100k+ files)

### Success Criteria
- ✅ Detects USB mounts reliably (90%+ success rate)
- ✅ HTML reports render correctly in all major browsers
- ✅ Duplicate detection performance acceptable (< 30s for 100k files)
- ✅ Archive inspection doesn't extract files unnecessarily

### Dependencies
- `watchdog` (USB monitoring) - optional
- `pypdf` (PDF metadata)
- `pillow` (image EXIF)

### Estimated Effort
- **Implementation:** 10-12 hours
- **Testing:** 6 hours
- **Documentation:** 3 hours
- **Total:** ~21 hours

---

## Phase 5: OCR & Advanced Text Extraction (Week 8-9)
**Goal:** Extract text from scanned documents and images

### Deliverables
1. **OCR Engine** (`src/drive_archaeologist/extractors/ocr.py`)
   - PDF OCR for scanned logsheets
   - Image OCR for site photos with text
   - Configurable OCR languages
   - Quality detection (skip OCR for native digital PDFs)

2. **Text Search**
   - Search extracted text from PDFs
   - Search EXIF metadata
   - Keyword indexing
   - Full-text search capability

3. **CLI Commands**
   - `drive-archaeologist ocr <scan_results.jsonl>` (extract text)
   - `drive-archaeologist search <keyword>` (search extracted text)

### Features
- ✅ OCR for scanned PDFs
- ✅ Text extraction from images
- ✅ Searchable metadata database
- ✅ Skip unnecessary OCR (digital PDFs)

### Testing Strategy
- Test with scanned vs. digital PDFs
- Test OCR accuracy on sample documents
- Validate search results
- Performance testing (OCR is slow - ensure progress tracking)

### Success Criteria
- ✅ OCR accuracy > 85% on clear scans
- ✅ Skips unnecessary OCR (digital PDFs detected)
- ✅ Search results accurate and fast (< 1s for 10k files)
- ✅ Progress tracking for long OCR jobs

### Dependencies
- `pytesseract` (OCR) - optional
- `opencv-python` (image preprocessing) - optional

### Estimated Effort
- **Implementation:** 12-15 hours
- **Testing:** 6 hours
- **Documentation:** 3 hours
- **Total:** ~24 hours

---

## Phase 6: Web UI & Cloud Features (Week 10+)
**Goal:** Optional web interface and cloud storage integration

### Deliverables
1. **Web Interface** (optional)
   - Browse scan results
   - Interactive file browser
   - Visualization dashboards
   - Migration plan review

2. **Cloud Integration** (optional)
   - Export to cloud storage (Google Drive, Dropbox)
   - Remote scanning (scan drives over SSH)
   - Multi-drive comparison

3. **Advanced Analytics**
   - Storage trends over time
   - File type distribution charts
   - Duplicate analysis
   - Cost optimization (cloud storage)

### Features (Optional/Future)
- Web-based UI for browsing results
- Cloud storage integration
- Remote drive scanning
- Advanced analytics

### Dependencies
- `fastapi` (web framework) - optional
- `plotly` (interactive charts) - optional
- Cloud SDK libraries - optional

### Estimated Effort
- **TBD** - Based on user feedback from Phases 1-5

---

## Implementation Priority Matrix

| Phase | Complexity | Value | Dependencies | Recommended Priority |
|-------|-----------|-------|--------------|---------------------|
| Phase 0 | LOW | HIGH | None | ⭐⭐⭐ **START HERE** |
| Phase 1 | MEDIUM | HIGH | Phase 0 | ⭐⭐⭐ **IMMEDIATE NEXT** |
| Phase 2 | MEDIUM | HIGH | Phase 1 | ⭐⭐ **CORE VALUE** |
| Phase 3 | MEDIUM | MEDIUM | Phase 2 | ⭐⭐ **USABILITY** |
| Phase 4 | HIGH | MEDIUM | Phase 3 | ⭐ **NICE TO HAVE** |
| Phase 5 | HIGH | LOW | Phase 4 | ⚠️ **DEFER** |
| Phase 6 | VERY HIGH | LOW | Phase 5 | ⚠️ **FUTURE** |

---

## Risk Assessment & Mitigation

### Risk 1: Slow Drive Performance
**Impact:** HIGH - Scanning old drives may take hours/days
**Mitigation:**
- Streaming output (JSONL) - results saved incrementally
- Resume capability - checkpoint every 1000 files
- Skip large files option - configurable size threshold
- Progress logging - user can monitor without babysitting

### Risk 2: File System Errors
**Impact:** MEDIUM - Corrupted files, permission errors
**Mitigation:**
- Graceful error handling - skip unreadable files, continue
- Error logging - separate error log file
- Retry logic - configurable retry attempts
- Detailed error reports - help users identify problematic files

### Risk 3: Cross-Platform Compatibility
**Impact:** MEDIUM - Windows vs. Linux path differences
**Mitigation:**
- Use `pathlib` everywhere - cross-platform path handling
- Filename sanitization - `pathvalidate` for safety
- Test on multiple platforms - Windows, Linux, macOS
- Platform-specific script generation - bash vs. PowerShell

### Risk 4: Memory Usage on Large Drives
**Impact:** MEDIUM - Millions of files could exhaust memory
**Mitigation:**
- Streaming processing - JSONL format, one line per file
- No in-memory aggregation - use pandas for analysis after scan
- Generator-based traversal - avoid loading file lists
- Configurable chunk size - batch processing

### Risk 5: User Confusion on Mixed Data
**Impact:** LOW - Users unsure how to handle personal + work data
**Mitigation:**
- Clear domain separation - GNSS vs. Media vs. Documents
- Privacy warnings - flag potential financial documents
- Selective migration - users choose which domains to migrate
- Separate reports - GNSS report vs. Media report

---

## User Workflow Examples

### Workflow 1: First-Time GNSS Drive Scan
```bash
# Install
pip install drive-archaeologist

# Scan drive
drive-archaeologist scan /media/OLD_PHIVOLCS_DRIVE --output gnss_scan.jsonl

# Review results
drive-archaeologist report gnss_scan.jsonl

# Generate migration plan
drive-archaeologist migrate gnss_scan.jsonl --target-dir ~/DATAPOOL --dry-run

# Review preview, then execute
drive-archaeologist migrate gnss_scan.jsonl --target-dir ~/DATAPOOL --execute
```

### Workflow 2: Mixed Personal + Work Drive
```bash
# Scan entire drive
drive-archaeologist scan /media/OLD_SEAGATE --output mixed_scan.jsonl

# Review what was found
drive-archaeologist report mixed_scan.jsonl

# Migrate only GNSS data
drive-archaeologist migrate mixed_scan.jsonl \
  --filter gnss \
  --target-dir ~/work/DATAPOOL \
  --dry-run

# Migrate media separately
drive-archaeologist migrate mixed_scan.jsonl \
  --filter media \
  --target-dir ~/personal/photos \
  --dry-run
```

### Workflow 3: USB Auto-Scan
```bash
# Start USB monitor
drive-archaeologist watch --auto-scan --notify

# Insert USB drive
# (automatically scans and generates report)

# Review notification
# Open generated report: usb_scan_20250106_143052.html
```

---

## Documentation Requirements

### Phase 0 Documentation
- [ ] Installation guide (pip install)
- [ ] Quick start guide (scan your first drive)
- [ ] CLI reference (all commands and flags)
- [ ] Output format specification (JSONL schema)
- [ ] Troubleshooting common errors

### Phase 1+ Documentation
- [ ] File classification guide (supported formats)
- [ ] GNSS-specific patterns explained
- [ ] Custom pattern development guide
- [ ] Migration safety best practices
- [ ] Performance tuning guide

### Phase 4+ Documentation
- [ ] USB monitoring setup (systemd service, Windows service)
- [ ] OCR configuration guide
- [ ] Advanced analytics examples

---

## Testing Strategy

### Unit Tests
- File classification accuracy
- Pattern matching edge cases
- Path sanitization
- Error handling

### Integration Tests
- End-to-end scan workflow
- Migration script generation
- Resume capability
- Cross-platform compatibility

### Performance Tests
- Large directory scanning (100k+ files)
- Memory usage profiling
- Streaming output validation
- Duplicate detection at scale

### User Acceptance Tests
- Real PHIVOLCS drives
- Mixed personal/work drives
- Windows workstation deployment
- Field team usability feedback

---

## Success Metrics

### Phase 0 Success
- ✅ Can scan 10,000 files in < 5 minutes
- ✅ Zero crashes on test drives
- ✅ Resume works reliably
- ✅ Users understand output format

### Phase 1 Success
- ✅ 95%+ GNSS classification accuracy
- ✅ < 10% unclassified files
- ✅ Fast classification (< 10% overhead)

### Phase 2 Success
- ✅ Useful structure recommendations
- ✅ 100% accurate duplicate detection
- ✅ Clear actionable reports

### Phase 3 Success
- ✅ Migration scripts work on first try
- ✅ Zero data loss in testing
- ✅ Rollback restores original state

### Overall Project Success
- ✅ Deployed at PHIVOLCS successfully
- ✅ Saves users 80%+ time vs. manual organization
- ✅ Zero reported data loss incidents
- ✅ Positive feedback from field teams

---

## Next Steps for Approval

1. **Review Tech Stack Decisions** (Required)
   - Confirm `filetype` vs. `python-magic` choice
   - Confirm phased dependency approach
   - Approve additional dependencies (`pathvalidate`, `filetype`)

2. **Approve Phase Priorities**
   - Phase 0-1: Core value (immediate start)
   - Phase 2-3: High value (schedule after 0-1)
   - Phase 4+: Deferred (evaluate based on feedback)

3. **Resource Allocation**
   - Estimated 8 weeks for Phases 0-3
   - Estimated 4 weeks for Phases 4-5
   - Phase 6: TBD based on user feedback

4. **Success Criteria Agreement**
   - Performance benchmarks acceptable?
   - Classification accuracy targets realistic?
   - Testing strategy comprehensive?

---

## Questions for User

1. **Platform Priority**: Linux-first, or Windows compatibility required from Phase 0?
2. **Archive Handling**: How common are `.7z`, `.rar` archives on PHIVOLCS drives?
3. **OCR Need**: Are scanned PDFs common enough to justify Phase 5 complexity?
4. **Deployment Target**: Individual workstations, or shared server?
5. **Data Volume**: Typical drive size and file count? (helps calibrate performance targets)

---

## Appendix A: File Format Support

### GNSS Formats (Phase 1)

| Format | Extension | Detection Method | Confidence |
|--------|-----------|------------------|------------|
| RINEX v2 Obs | `.??O` | Filename pattern | 100% |
| RINEX v2 Nav | `.??N` | Filename pattern | 100% |
| RINEX v3 Obs | `.rnx`, `.crx` | Filename + header | 95% |
| Trimble DAT | `.dat` | Header signature | 80% |
| Trimble T0x | `.T01`, `.T02` | Extension | 90% |
| Leica MDB | `.m00`, `.m01` | Extension | 90% |
| Bernese STA | `.STA` | Extension + content | 95% |
| Bernese OUT | `.OUT`, `.PRT` | Extension | 85% |
| Site Logs | `*log*.pdf` | Filename pattern | 70% |

### General Formats (Phase 1)

| Category | Extensions | Detection Method |
|----------|-----------|------------------|
| Images | `.jpg`, `.png`, `.tif`, `.raw` | EXIF signature |
| Video | `.mp4`, `.avi`, `.mov` | File signature |
| Audio | `.mp3`, `.flac`, `.wav` | File signature |
| Documents | `.pdf`, `.docx`, `.xlsx` | MIME type |
| Code | `.py`, `.sh`, `.m`, `.r` | Extension |
| Archives | `.zip`, `.tar.gz`, `.7z` | File signature |

---

## Appendix B: Performance Benchmarks

### Target Performance (Phase 0-1)

| Scenario | Target Time | Notes |
|----------|------------|-------|
| 1,000 files | < 30 seconds | Small drive |
| 10,000 files | < 5 minutes | Medium drive |
| 100,000 files | < 45 minutes | Large drive |
| 1,000,000 files | < 8 hours | Massive archive |

### Memory Usage Targets

| File Count | Max Memory | Notes |
|-----------|-----------|-------|
| 10,000 | < 100 MB | Streaming mode |
| 100,000 | < 500 MB | Checkpoint mode |
| 1,000,000+ | < 2 GB | Generator-based |

---

## Appendix C: Example Output Formats

### JSONL Output (Phase 0)
```json
{"path": "/media/drive/DATAPOOL/ALGO/2022/ALGO0010.22O", "name": "ALGO0010.22O", "extension": ".22o", "size_bytes": 4251840, "size_mb": 4.05, "modified": "2022-04-10T14:23:15", "created": "2022-04-10T14:20:00", "parent_dir": "/media/drive/DATAPOOL/ALGO/2022", "depth": 4}
```

### Classification Output (Phase 1)
```json
{"path": "/media/drive/DATAPOOL/ALGO/2022/ALGO0010.22O", "name": "ALGO0010.22O", "extension": ".22o", "domain": "gnss", "file_type": "rinex_obs", "confidence": 1.0, "metadata": {"site": "ALGO", "year": 2022, "doy": 1}}
```

### Migration Plan (Phase 3)
```bash
#!/bin/bash
# Generated by drive-archaeologist on 2025-01-06 14:30:52
# Source: /media/OLD_DRIVE
# Target: /home/user/DATAPOOL
# Dry run: DRY_RUN=false ./migrate.sh

DRY_RUN=${DRY_RUN:-true}

# ALGO0010.22O: /media/OLD_DRIVE/misc/old_files/ALGO0010.22O → /home/user/DATAPOOL/ALGO/2022/001/ALGO0010.22O
if [ "$DRY_RUN" = true ]; then
  echo "WOULD MOVE: /media/OLD_DRIVE/misc/old_files/ALGO0010.22O → /home/user/DATAPOOL/ALGO/2022/001/ALGO0010.22O"
else
  mkdir -p "/home/user/DATAPOOL/ALGO/2022/001"
  mv -n "/media/OLD_DRIVE/misc/old_files/ALGO0010.22O" "/home/user/DATAPOOL/ALGO/2022/001/ALGO0010.22O"
  echo "MOVED: ALGO0010.22O"
fi
```

---

**End of Recommendations Document**

**Status:** Ready for Review
**Next Action:** User approval to proceed with Phase 0 implementation
**Contact:** Review and approve before executing `/plan-implementation`
