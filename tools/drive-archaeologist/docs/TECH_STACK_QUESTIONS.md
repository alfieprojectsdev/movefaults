# Tech Stack Questions - Awaiting Decision

**Date Created:** 2025-11-01
**Status:** Pending Review by Alfie
**Context:** Root instance (claude-config) reviewed the proposed tech stack in `Smart USB data ingestion system.md`

---

## 🎯 Overall Assessment

**Tech Stack Score: 9/10** ⭐⭐⭐⭐⭐

Your choices are excellent. Just a few clarifications needed to finalize the dependency list.

---

## ❓ Questions Requiring Decisions

### 1. File Type Detection: `python-magic` vs `filetype`

**Current Choice:** `python-magic>=0.4.27`

**Problem:** Requires `libmagic` system dependency (C library)
- Linux: `sudo apt install libmagic1`
- Mac: `brew install libmagic`
- Windows: Painful installation process

**Alternative:** `filetype>=1.2.0` (Pure Python, no C dependencies)

**Comparison:**

| Feature | python-magic | filetype |
|---------|--------------|----------|
| **Accuracy** | 95%+ (uses libmagic database) | 90% (pattern matching) |
| **Installation** | Requires apt/brew | `uv add filetype` (done) |
| **Windows Support** | ⚠️ Difficult | ✅ Easy |
| **RINEX Detection** | ✅ Excellent | ✅ Good (text-based, easy pattern) |
| **Binary Formats** | ✅ Excellent | ⚠️ Less accurate for obscure formats |

**Question for Alfie:**
- **Do you need libmagic's accuracy for obscure binary formats?**
- **Or is 90% accuracy with easier installation acceptable?**
- **Will your users (geodesists at PHIVOLCS) struggle with system dependencies?**

**Recommendation:** Start with `filetype`, add `python-magic` as optional dependency if accuracy issues arise.

**Code Impact:**
```python
# Current approach (python-magic)
import magic
mime = magic.from_file('ALGO0010.22O')  # Requires libmagic

# Alternative (filetype)
import filetype
kind = filetype.guess('ALGO0010.22O')
if kind is None:
    # Fallback to extension-based detection for text files
    pass
```

---

### 2. Platform Support: Windows Users?

**Current Status:** Doc mentions Linux/Mac/Windows support

**Questions:**
- **Will PHIVOLCS staff run this on Windows machines?**
- **Or primarily Linux VMs / Ubuntu workstations?**
- **If Windows: Do they have admin rights to install system dependencies?**

**Why This Matters:**

| Dependency | Windows Complexity |
|------------|-------------------|
| `filetype` | ✅ Easy (pure Python) |
| `python-magic` | ⚠️ Requires manual DLL installation |
| `pytesseract` (OCR) | ❌ Complex (requires Tesseract executable) |
| `opencv-python` (OCR) | ⚠️ Large download (~100MB) |

**Recommendation:**
- **If Windows users exist:** Stick to pure Python dependencies
- **If Linux-only:** Can use heavier deps without worry

---

### 3. Archive File Handling: Priority Level?

**Question:** How common are archived files (`.7z`, `.rar`, `.zip`, `.tar.gz`) on your GNSS hard drives?

**Scenarios:**

**A) Very Common (>30% of drives have archives):**
```toml
# Make archive handling core dependency
dependencies = [
    # ... existing
    "py7zr>=0.20.0",   # Pure Python 7z
    "rarfile>=4.0",    # RAR support
]
```

**B) Occasional (<30% of drives):**
```toml
# Keep as optional dependency (current approach is good)
[project.optional-dependencies]
archive = [
    "py7zr>=0.20.0",
    "rarfile>=4.0",
]
```

**C) Rare (<10% of drives):**
```toml
# Don't support initially - users can extract manually
# Add later if needed
```

**Follow-up Questions:**
- Do field teams archive data before handing over drives?
- Are archives used for compression or just organization?
- What formats are most common? (`.zip` is stdlib, no dependency needed)

---

### 4. OCR Support: Scanned PDFs Common?

**Current Status:** OCR dependencies are optional (good!)

**Question:** Are scanned PDFs (logsheets, field notes) common on your drives?

**OCR Dependencies:**
```toml
ocr = [
    "pytesseract>=0.3.10",    # Requires Tesseract executable
    "opencv-python>=4.8.0",   # 100MB+ download
]
```

**System Requirements:**
- Linux: `sudo apt install tesseract-ocr`
- Mac: `brew install tesseract`
- Windows: Manual installer download

**Scenarios:**

**A) Scanned PDFs are common (>20% of drives):**
- Keep OCR optional, but document installation clearly
- Provide troubleshooting guide for Tesseract

**B) Rare (<10% of drives):**
- Keep OCR optional, minimal documentation
- Users who need it can install on-demand

**C) Never encountered:**
- Remove OCR dependencies entirely (save complexity)

**Follow-up:**
- Are field logsheets digitally created (native PDF) or scanned?
- Do you need OCR for searchability, or just file detection?

---

## 📋 Missing Dependencies (Add These)

### 1. `watchdog` - USB Hot-Plug Detection

**Status:** ❌ Mentioned in doc, missing from `pyproject.toml`

**Your doc includes:**
```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
```

**Fix:**
```toml
dependencies = [
    # ... existing
    "watchdog>=3.0.0",  # File system monitoring for USB hot-plug
]
```

**Decision Needed:** Is USB hot-plugging a Phase 1 feature or deferred?

---

### 2. `pathvalidate` - Filename Sanitization (Recommended)

**Problem:** GNSS filenames from old drives might have:
- Illegal Windows characters (`CON.dat`, `PRN.log`)
- Special characters that break paths
- Unicode issues

**Recommendation:**
```toml
dependencies = [
    # ... existing
    "pathvalidate>=3.0.0",  # Sanitize filenames for cross-platform safety
]
```

**Example Use:**
```python
from pathvalidate import sanitize_filename
safe_name = sanitize_filename("CON.dat")  # Becomes "CON_.dat" on Windows
```

**Decision:** Add this? (Low-risk, small library, prevents edge case bugs)

---

### 3. `structlog` - Structured Logging (Optional)

**Current:** Using stdlib `logging` module

**Upgrade Option:**
```toml
dependencies = [
    "structlog>=23.0.0",  # Structured logging (JSON output)
]
```

**Why Consider:**
- PHIVOLCS might want audit trails (who moved what file, when)
- Structured logs = easier to query/analyze
- JSON output = machine-readable

**Trade-off:**
- **Pro:** Better for compliance, debugging, long-term records
- **Con:** Adds complexity, stdlib logging is simpler

**Decision:** Is audit logging a requirement? Or nice-to-have?

---

## 🎯 Recommended Actions (Once Questions Answered)

### Short-term (Phase 1):
1. Decide on `python-magic` vs `filetype`
2. Add `watchdog>=3.0.0` to dependencies
3. Consider adding `pathvalidate>=3.0.0`
4. Keep OCR optional (current approach is good)

### Medium-term (Phase 2-3):
1. Test archive handling with real PHIVOLCS drives
2. Evaluate if `python-magic` accuracy issues arise
3. Add Windows installation guide if needed

### Long-term (Production):
1. Add `structlog` if audit requirements emerge
2. Create deployment guide for PHIVOLCS IT
3. Document system dependency installation per OS

---

## 📝 Notes for Future Review

**When Reviewing:**
- Check actual PHIVOLCS hard drives (what file types exist?)
- Ask field team about archive usage patterns
- Test installation on PHIVOLCS workstations (Windows vs Linux)
- Gather feedback on system dependency installation friction

**Decision Priority:**
1. 🔴 **HIGH:** `python-magic` vs `filetype` (affects Phase 1 development)
2. 🟡 **MEDIUM:** Archive handling priority (affects Phase 3 timeline)
3. 🟢 **LOW:** OCR support (can defer until real need identified)
4. 🟢 **LOW:** `structlog` vs stdlib logging (can refactor later)

---

**Next Steps:** Review when more pensive, then update `pyproject.toml` accordingly.

**Contact:** Root instance (claude-config) for clarifications
