# Drive Archaeologist - Phase Roadmap

**Visual guide to implementation phases**

---

## 🗺️ The Journey: From Empty Repo to Production Tool

```
┌─────────────────────────────────────────────────────────────────────┐
│                         YOUR CURRENT POSITION                        │
│  📍 Repository scaffolded, dependencies defined, ready to build     │
└─────────────────────────────────────────────────────────────────────┘

                                    ↓

┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 0: Minimal Viable Scanner (Week 1) ⭐⭐⭐ START HERE         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  🎯 Goal: Scan drive → Get file list with metadata                  │
│                                                                       │
│  📥 Input:  /media/OLD_DRIVE                                         │
│  📤 Output: scan_OLD_DRIVE_20250106.jsonl                           │
│            + progress logs                                           │
│                                                                       │
│  ✅ Features:                                                        │
│     • Recursive directory scanning                                   │
│     • File metadata extraction (size, dates, path)                   │
│     • Progress tracking with resume capability                       │
│     • Error handling (skip unreadable files)                         │
│     • JSONL streaming output (crash-safe)                            │
│                                                                       │
│  🛠️ New Code:                                                        │
│     • cli.py: `drive-archaeologist scan <path>` command             │
│     • scanner.py: DeepScanner class with checkpoint logic           │
│                                                                       │
│  📊 Success Metrics:                                                 │
│     • 10,000 files in < 5 min                                        │
│     • Resume works after interrupt                                   │
│     • Valid JSONL output                                             │
│                                                                       │
│  🚀 Effort: 8 hours                                                  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘

                                    ↓

┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 1: File Classification (Week 2) ⭐⭐⭐ HIGH VALUE            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  🎯 Goal: Identify what types of files you have                     │
│                                                                       │
│  📥 Input:  Same scan command, enhanced detection                    │
│  📤 Output: scan_*.jsonl with "domain" and "file_type" fields       │
│                                                                       │
│  ✅ Features:                                                        │
│     • GNSS format detection (RINEX, Trimble, Leica, Bernese)        │
│     • Media detection (photos, videos, audio)                        │
│     • Document detection (PDF, Office docs)                          │
│     • Code detection (Python, shell, MATLAB)                         │
│     • Pattern-based classification with confidence scores            │
│                                                                       │
│  🛠️ New Code:                                                        │
│     • classifier.py: UniversalClassifier system                      │
│     • domains/gnss/patterns.py: GNSS-specific patterns               │
│     • domains/common/patterns.py: General file patterns              │
│                                                                       │
│  📊 Success Metrics:                                                 │
│     • 95%+ accuracy on GNSS files                                    │
│     • 90%+ accuracy on general files                                 │
│     • < 10% overhead on scan time                                    │
│                                                                       │
│  🚀 Effort: 16 hours                                                 │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘

                                    ↓

┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 2: Structure Analysis (Week 3-4) ⭐⭐ CORE VALUE             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  🎯 Goal: Understand organization and recommend improvements         │
│                                                                       │
│  📥 Input:  scan_*.jsonl from Phase 0/1                             │
│  📤 Output: recommendations_*.csv (source → destination mappings)    │
│                                                                       │
│  ✅ Features:                                                        │
│     • Directory tree analysis                                        │
│     • Detect existing organizational patterns                        │
│     • Recommend DATAPOOL structure for GNSS files                    │
│     • Duplicate file detection (MD5 hashing)                         │
│     • Space savings analysis                                         │
│                                                                       │
│  🛠️ New Code:                                                        │
│     • analyzer.py: StructureAnalyzer class                           │
│     • recommendations.py: RecommendationEngine                       │
│     • cli.py: `drive-archaeologist analyze` command                 │
│                                                                       │
│  📊 Success Metrics:                                                 │
│     • Identifies 90%+ GNSS files for reorganization                  │
│     • 100% duplicate detection accuracy                              │
│     • Clear actionable recommendations                               │
│                                                                       │
│  🚀 Effort: 16 hours                                                 │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘

                                    ↓

┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Migration Scripts (Week 5) ⭐⭐ USABILITY                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  🎯 Goal: Generate safe, executable reorganization scripts           │
│                                                                       │
│  📥 Input:  recommendations_*.csv from Phase 2                       │
│  📤 Output: reorganize.sh (or .ps1) + undo.sh                       │
│                                                                       │
│  ✅ Features:                                                        │
│     • Generate bash/PowerShell migration scripts                     │
│     • Dry-run mode (preview changes)                                 │
│     • Safety checks (no overwrites)                                  │
│     • MD5 verification (optional)                                    │
│     • Rollback script generation                                     │
│                                                                       │
│  🛠️ New Code:                                                        │
│     • migration.py: MigrationScriptGenerator class                   │
│     • cli.py: `drive-archaeologist migrate` command                 │
│                                                                       │
│  📊 Success Metrics:                                                 │
│     • Scripts work on first try                                      │
│     • Zero data loss in testing                                      │
│     • Rollback restores original state                               │
│                                                                       │
│  🚀 Effort: 17 hours                                                 │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘

                  ═══════════════════════════════
                     🎉 PHASE 3 = USABLE TOOL
                     Total: ~57 hours (5 weeks)
                  ═══════════════════════════════

                                    ↓
                           (Evaluate before proceeding)
                                    ↓

┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 4: USB Auto-Detection (Week 6-7) ⭐ NICE TO HAVE             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  🎯 Goal: Automate scanning workflow                                │
│                                                                       │
│  ✅ Features:                                                        │
│     • USB drive mount detection                                      │
│     • Auto-trigger scan on insertion                                 │
│     • Desktop notifications                                          │
│     • HTML reports with charts                                       │
│     • Advanced duplicate detection (all files)                       │
│     • Archive file inspection                                        │
│                                                                       │
│  🛠️ New Code:                                                        │
│     • usb_monitor.py: USB detection with watchdog                    │
│     • report_generator.py: HTML report templates                     │
│     • cli.py: `drive-archaeologist watch` command                   │
│                                                                       │
│  🚀 Effort: 21 hours                                                 │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘

                                    ↓

┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 5: OCR & Text Extraction (Week 8-9) ⚠️ DEFER                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  🎯 Goal: Extract text from scanned documents                        │
│                                                                       │
│  ✅ Features:                                                        │
│     • PDF OCR for scanned logsheets                                  │
│     • Image text extraction                                          │
│     • Full-text search capability                                    │
│     • Skip OCR for native digital PDFs                               │
│                                                                       │
│  🛠️ New Code:                                                        │
│     • extractors/ocr.py: OCR engine with Tesseract                   │
│     • cli.py: `drive-archaeologist ocr` command                     │
│                                                                       │
│  ⚠️ Complexity:                                                      │
│     • Requires Tesseract installation (system dependency)            │
│     • Slow operation (OCR is time-consuming)                         │
│     • Complex error handling (quality detection)                     │
│                                                                       │
│  🚀 Effort: 24 hours                                                 │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘

                                    ↓

┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 6: Web UI & Cloud (Week 10+) ⚠️ FUTURE                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  🎯 Goal: Optional web interface and cloud features                 │
│                                                                       │
│  ✅ Features:                                                        │
│     • Web-based UI for browsing results                              │
│     • Cloud storage integration                                      │
│     • Remote drive scanning (SSH)                                    │
│     • Advanced analytics dashboards                                  │
│                                                                       │
│  🚀 Effort: TBD (based on Phase 1-5 feedback)                       │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🎯 Recommended Path

### CORE VALUE TRACK (Phases 0-3)
```
Week 1: Phase 0 → Working scanner
Week 2: Phase 1 → File classification
Week 3-4: Phase 2 → Structure analysis
Week 5: Phase 3 → Migration scripts

Result: Complete, usable tool for drive archaeology
```

### ENHANCEMENT TRACK (Phase 4+)
```
Evaluate after Phase 3:
• Is manual scanning acceptable? → Skip Phase 4
• Are scanned PDFs common? → Prioritize Phase 5
• Need remote access? → Consider Phase 6

Result: Add features based on real usage patterns
```

---

## 📊 Feature Comparison by Phase

| Feature | Phase 0 | Phase 1 | Phase 2 | Phase 3 | Phase 4 | Phase 5 |
|---------|---------|---------|---------|---------|---------|---------|
| **Scan drives** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **File metadata** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Resume scanning** | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Classify GNSS files** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Classify media/docs** | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Structure analysis** | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Duplicate detection** | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Recommendations** | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| **Migration scripts** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **Dry-run/rollback** | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| **USB auto-scan** | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| **HTML reports** | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| **Archive inspection** | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ |
| **OCR text extraction** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| **Full-text search** | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

---

## 💰 Value vs. Effort Analysis

```
High Value, Low Effort (DO FIRST)
┌─────────────────────────┐
│  Phase 0: Scanner       │  ← Start here
│  Phase 1: Classification│
└─────────────────────────┘

High Value, Medium Effort (DO NEXT)
┌─────────────────────────┐
│  Phase 2: Analysis      │
│  Phase 3: Migration     │
└─────────────────────────┘

Medium Value, High Effort (EVALUATE)
┌─────────────────────────┐
│  Phase 4: USB Auto      │  ← Test Phase 0-3 first
└─────────────────────────┘

Low Value, High Effort (DEFER)
┌─────────────────────────┐
│  Phase 5: OCR           │  ← Only if proven necessary
│  Phase 6: Web UI        │
└─────────────────────────┘
```

---

## 🛣️ Decision Points

### After Phase 0
**Question:** Does the scanner work as expected?
- ✅ YES → Proceed to Phase 1
- ❌ NO → Debug performance/compatibility issues

### After Phase 1
**Question:** Is classification accurate enough?
- ✅ YES → Proceed to Phase 2
- ❌ NO → Improve pattern matching, add more formats

### After Phase 2
**Question:** Are recommendations useful?
- ✅ YES → Proceed to Phase 3
- ❌ NO → Refine structure detection algorithms

### After Phase 3
**Question:** Is manual scanning workflow acceptable?
- ✅ YES → Ship it! 🎉 (Skip Phase 4+)
- ❌ NO → Evaluate Phase 4 (USB auto-detection)

### After Phase 4 (if implemented)
**Question:** Do you have many scanned PDFs?
- ✅ YES → Consider Phase 5 (OCR)
- ❌ NO → Phase 5 not needed

---

## 📈 Cumulative Progress

```
Phase 0:  [████░░░░░░] 20% → Working scanner
Phase 1:  [██████░░░░] 40% → + Classification
Phase 2:  [████████░░] 70% → + Analysis
Phase 3:  [██████████] 100% → + Migration = COMPLETE TOOL
Phase 4:  [██████████] + Automation (bonus)
Phase 5:  [██████████] + OCR (bonus)
```

---

## 🎁 What You Get After Each Phase

### Phase 0: "I Can See What's There"
```bash
$ drive-archaeologist scan /media/OLD_DRIVE
✅ Scanned 15,247 files in 3m 42s
📄 Output: scan_OLD_DRIVE_20250106.jsonl
```

### Phase 1: "I Know What Types of Files I Have"
```bash
$ drive-archaeologist scan /media/OLD_DRIVE
✅ Scanned 15,247 files
📊 GNSS files: 1,247 (RINEX, Trimble, Bernese)
📸 Media files: 8,492 (photos, videos)
📄 Documents: 3,103 (PDF, Office)
💻 Code: 892 (Python, MATLAB, shell)
❓ Unknown: 1,513
```

### Phase 2: "I Know How to Organize It"
```bash
$ drive-archaeologist analyze scan_OLD_DRIVE.jsonl
📊 Structure Analysis Complete
🔧 Recommendations:
   • Move 1,247 GNSS files to DATAPOOL/{SITE}/{YEAR}/
   • Remove 342 duplicate photos (saving 2.3 GB)
   • Organize media by decade: 2000s, 2010s, 2020s
📄 Output: recommendations_OLD_DRIVE.csv
```

### Phase 3: "I Can Safely Reorganize It"
```bash
$ drive-archaeologist migrate recommendations.csv --dry-run
🔍 DRY RUN: Preview of changes
   → Would move 1,247 GNSS files
   → Would organize 8,492 media files
   → Would remove 342 duplicates
   → Would save 2.3 GB of space

$ drive-archaeologist migrate recommendations.csv --execute
✅ Migration complete!
📄 Undo script: undo_migration.sh
```

---

## 🚦 Go/No-Go Criteria

### Before Starting Phase 0
- [ ] Tech stack decisions approved
- [ ] Dependencies updated in pyproject.toml
- [ ] Test environment ready (test drive available)

### Before Starting Phase 1
- [ ] Phase 0 scanner works reliably
- [ ] JSONL output format validated
- [ ] Performance acceptable on test data

### Before Starting Phase 2
- [ ] Classification accuracy meets targets (90%+)
- [ ] All target file formats detected correctly
- [ ] No performance regressions

### Before Starting Phase 3
- [ ] Structure analysis produces useful recommendations
- [ ] Duplicate detection is accurate
- [ ] Reports are clear and actionable

### Before Starting Phase 4
- [ ] Phases 0-3 tested with real PHIVOLCS drives
- [ ] User feedback collected
- [ ] USB auto-detection is actually needed

---

## 🎬 Next Steps

### Immediate (Today)
1. Review `QUICK_DECISION_GUIDE.md`
2. Choose Option A, B, or C
3. Answer any clarifying questions
4. Approve Phase 0 implementation

### Week 1
- Implement Phase 0
- Test with real drive
- Generate first JSONL report

### Week 2+
- Iterate based on feedback
- Proceed to Phase 1 if Phase 0 successful
- Adjust plan as needed

---

**Remember:** Each phase delivers standalone value. You can stop after any phase and have a useful tool!

**Ready to start?** See `QUICK_DECISION_GUIDE.md` for next steps.
