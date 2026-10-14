# Quick Decision Guide - Drive Archaeologist

> **PLANNING DOCUMENT, November 2025, written before the tool existed.** Kept
> for the reasoning; it does not describe the code. For what the tool does now,
> see `../README.md` and `../CLAUDE.md`.

**Date:** 2025-11-06
**Purpose:** Fast reference for key decisions before starting implementation

---

## 🎯 What You Need to Decide RIGHT NOW

### 1. Tech Stack Choices (5 minutes)

#### ✅ RECOMMENDED: Accept These Defaults
- **File Detection**: Use `filetype` (pure Python) instead of `python-magic`
- **Archive Support**: Phase 2 (deferred)
- **OCR Support**: Phase 5 (deferred)
- **USB Auto-Detection**: Phase 4 (deferred)
- **Add Dependencies**: `filetype`, `pathvalidate`

**If you agree with all defaults above, you're ready to start Phase 0 immediately.**

---

### 2. Implementation Phases (10 minutes to review)

| Phase | What You Get | Time | Start When? |
|-------|-------------|------|-------------|
| **Phase 0** | Working CLI scanner with JSONL output | 8 hrs | **NOW** |
| **Phase 1** | File classification (RINEX, Trimble, etc.) | 16 hrs | After Phase 0 |
| **Phase 2** | Structure analysis & recommendations | 16 hrs | After Phase 1 |
| **Phase 3** | Migration script generation | 17 hrs | After Phase 2 |
| **Phase 4** | USB auto-detection, HTML reports | 21 hrs | **OPTIONAL** |
| **Phase 5** | OCR for scanned PDFs | 24 hrs | **DEFER** |
| **Phase 6** | Web UI, cloud integration | TBD | **FUTURE** |

**Recommended:** Start with Phases 0-3 (~57 hours total), then evaluate Phase 4+ based on real usage.

---

## 🚀 Three Ways to Proceed

### Option A: "Just Start Building" (Fastest)
**If you trust the recommendations and want to start immediately:**

```bash
# Accept all defaults, start Phase 0 implementation
/plan-implementation "Implement Phase 0 (Minimal Viable Scanner) from IMPLEMENTATION_RECOMMENDATIONS.md"
```

**Time to first working version:** 8 hours

---

### Option B: "I Have Questions" (Recommended)
**If you need clarification before starting:**

Answer these 5 questions:
1. **Platform**: Do you need Windows support in Phase 0? (Yes/No)
2. **Archives**: Are `.7z`/`.rar` files common on your drives? (Common/Rare/Never)
3. **OCR**: Do you have scanned PDFs that need text extraction? (Many/Some/None)
4. **Scale**: What's a typical drive size? (< 100 GB / 100-500 GB / > 1 TB)
5. **Use Case**: Primary use case? (GNSS-only / Mixed Personal+Work / Other)

Then I'll adjust the recommendations and start implementation.

---

### Option C: "I Want to Modify the Plan" (Slowest)
**If you disagree with the phased approach or tech choices:**

Tell me what you want to change:
- Different tech stack choices?
- Different phase priorities?
- Additional features in Phase 0?
- Remove certain features entirely?

I'll revise the recommendations before starting.

---

## 📋 What's Already Done

✅ Repository structure created
✅ `pyproject.toml` configured (needs dependency updates)
✅ Documentation analyzed
✅ Tech stack evaluated
✅ Implementation plan drafted

**What's NOT done yet:**
❌ Actual code implementation (files are scaffolded but empty)
❌ Tests
❌ Documentation

---

## ⚡ Fastest Path to Working Tool

**Total time: ~8 hours of implementation**

1. **Phase 0 Only** → Working scanner that you can use immediately
   - Scan any drive
   - Get JSONL output with file metadata
   - Resume capability if interrupted
   - Basic statistics report

2. **Why start with Phase 0?**
   - Immediate usability (working tool in 1 day)
   - Validates core assumptions (performance, usability)
   - Real data to inform Phase 1+ design
   - Early feedback from actual use

3. **What can you do with Phase 0?**
   ```bash
   # Scan a drive
   drive-archaeologist scan /media/OLD_DRIVE

   # Get output
   # → scan_OLD_DRIVE_20250106.jsonl (all file metadata)
   # → scan_OLD_DRIVE_20250106.log (progress log)

   # Analyze with standard tools
   cat scan_*.jsonl | jq -r '.extension' | sort | uniq -c | sort -rn
   ```

---

## 🎬 Ready to Start?

### If you choose **Option A** (Just Start):
```
Reply: "Proceed with Phase 0 using recommended defaults"
```

### If you choose **Option B** (Answer Questions):
```
Reply with your answers to the 5 questions above
```

### If you choose **Option C** (Modify Plan):
```
Reply with what you want changed in the plan
```

---

## 📊 Expected Outcomes by Phase

### After Phase 0 (Week 1)
- ✅ You can scan your first drive
- ✅ Get structured data about what's on it
- ✅ Basic statistics (file count, size, extensions)
- 🎯 **Value**: Know what you're dealing with

### After Phase 1 (Week 2)
- ✅ Files are classified (RINEX, Trimble, photos, etc.)
- ✅ GNSS-specific format detection
- ✅ Domain breakdown (GNSS vs. Media vs. Documents)
- 🎯 **Value**: Understand what types of files you have

### After Phase 2 (Week 4)
- ✅ Structure analysis (is there organization?)
- ✅ Recommendations for reorganization
- ✅ Duplicate file detection
- 🎯 **Value**: Know how to reorganize the chaos

### After Phase 3 (Week 5)
- ✅ Executable migration scripts
- ✅ Dry-run preview
- ✅ Safe file moving with rollback
- 🎯 **Value**: Actually reorganize your drives safely

---

## 🔄 Feedback Loop

**After each phase:**
1. Test with real drives
2. Gather feedback (what works, what doesn't)
3. Adjust next phase based on learnings
4. Decide: continue to next phase or iterate?

**This approach minimizes wasted effort on features you might not need.**

---

## 💡 Key Insights from Docs Analysis

### What Makes This Tool Unique
1. **ADHD-Friendly**: Set it and forget it, come back to results
2. **Resume Capability**: Handles slow, unreliable drives
3. **No Data Loss**: Dry-run first, verify before moving
4. **Mixed Data Support**: GNSS + personal files on same drive
5. **Incremental Value**: Each phase adds immediate usability

### What Makes This Plan Solid
- ✅ Minimizes dependencies in early phases
- ✅ Each phase delivers standalone value
- ✅ Defers complex features until core is proven
- ✅ Supports real-world messy data (not just GNSS)
- ✅ Cross-platform from the start

---

## ❓ Common Questions

**Q: Why not start with all features at once?**
A: Risk reduction. Build core first, validate it works, then add complexity.

**Q: Can I skip Phase 1 and go straight to Phase 2?**
A: No, Phase 2 depends on classification from Phase 1.

**Q: What if I need OCR immediately?**
A: We can re-prioritize, but it's complex. Better to validate Phase 0-1 first.

**Q: Will this work on Windows?**
A: Yes, designed for cross-platform from Phase 0 (using `pathlib`, `pathvalidate`).

**Q: What about my 20-year-old drive with corrupted files?**
A: Phase 0 handles this (graceful error handling, skip unreadable files).

---

**BOTTOM LINE:**
- Phases 0-3 = Core usable tool (5 weeks)
- Phase 4+ = Nice-to-have features (evaluate later)
- Start with Phase 0 to get immediate value (1 week)

**Your move!** Choose Option A, B, or C above.
