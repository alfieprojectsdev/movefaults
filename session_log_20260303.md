# Session Log: INP Diff, Primary Source Verification, velocity-reviewer Complete (2026-03-03)

## Overview

Full working session. Resumed from 2026-03-02 context compaction. Three main threads:
(1) complete the Bernese 5.2→5.4 INP file comparison; (2) primary source verification of
the full post-BPE velocity pipeline; (3) complete the `velocity-reviewer` tool with the
missing PLOT file stripping step.

---

## 1. INP File Diff — PHIVOLCS 5.2 vs EXAMPLE 5.4

Compared five INP files received 2026-03-02 (`temp/INP-files/R2S_GEN/`) against the
installed EXAMPLE 5.4 files (`$U/OPT/R2S_GEN/`): ADDNEQ2, MAUPRP, RNXGRA, RXOBV3, CODSPP.

### Key structural differences (5.2 → 5.4)

| Aspect | 5.2 | 5.4 |
|--------|-----|-----|
| ENVIRONMENT block | 5 hardcoded Windows paths | `ENVIRONMENT 1 "" "${}"` (BPE injects) |
| Path variables | `${X}/GEN` | `${MODEL}`, `${CONFIG}` |
| File extension | `CONST.` (dot suffix) | `CONST.BSW`, `.SAT` |
| Session naming | `$YSS+0` (2-digit year) | `$YYYSS+0` (4-digit year) |
| SAMPLTOL | absent | `0.5` (new in 5.4) |
| IONEXCF | file path | disabled (= 0) |

### Parameters that actually differ (Jinja2 targets)

Only 3 parameters need overriding from 5.4 defaults:

| Parameter | PHIVOLCS value | EXAMPLE 5.4 default | Reason |
|-----------|---------------|---------------------|--------|
| RNXGRA MINOBS | 100 (campaign) / 200 (continuous) | 200 | campaign GPS sessions are shorter |
| RNXGRA MAXBAD | 70 (campaign) / 10 (continuous) | 10 | campaign more lenient |
| ADDNEQ2 MAXPAR | 4000 | 1000 | PHIVOLCS network is larger (~45 stations + IGS refs) |

All path variables (V_ATLINF, V_BLQINF, V_CRDINF, V_RNXDIR, etc.) are handled by PCF
server variable injection at runtime — no Jinja2 templating needed for them.

### Conclusion

Option A (minimal Jinja2) confirmed: only the 3 parameters above need overrides in the
templates. Two template variants needed: one for Campaign GPS, one for Continuous GPS
(RNXGRA threshold difference). Everything else inherits from 5.4 defaults.

---

## 2. Orchestration Explainer Gap Analysis

Reviewed `docs/work_instructions_review.md` for automation gaps. Confirmed the
`docs/bernese_orchestration_explainer.md` is missing:

1. **Raw receiver → RINEX conversion pipeline** (runpkr00 + teqc) — entirely absent
2. **8 campaign file generation order** — not enumerated
3. **Post-BPE pipeline scripts** — filter-fncrd.bat, plot_v2.py, vel_line_v8.m not named
4. **Reference station dependency** (S01R) — not mentioned
5. **BLQ file external dependency** — not mentioned

Explainer update deferred to a dedicated documentation session (not in scope for this
implementation session).

---

## 3. Velocity Pipeline Primary Source Verification

Queried Gemini + NotebookLM against the PHIVOLCS work instruction document, then confirmed
against actual production scripts identified via staff interview.

### Script locations (confirmed by processing staff)

| Work instruction name | Actual file |
|-----------------------|-------------|
| `plot_v2.py` | `analysis/02 Time Series/RUNX_v2.py` |
| `filter-fncrd.bat` | `analysis/02 Time Series/00_CRD_NAMRIA.bat`, `00_CRD_NP.bat`, `00_CRD_PIVS.bat` |
| `vel_line_v8.m` | `analysis/02 Time Series/modified scripts/vel_line_v8_newvelduetooffset_v4.m` |
| `offsets` | `analysis/offsets` (production file with 73 entries) |

### Findings from direct source reading

**RUNX_v2.py (= plot_v2.py):**
- PLOT file format confirmed at line 137:
  `'{:.4f}  {:>13}  {:>13}  {:>13}\n'.format(date, coorde, coordn, coordu)`
- Decimal year: `year + int(DOY)/365.25` (confirmed from line 129)
- Interactive prompt at line ~80: `input('\t Input reference station: ')` — must be
  parameterised before headless use

**00_CRD_*.bat (= filter-fncrd.bat):**
- Uses `findstr /V` to EXCLUDE ~200 global IGS stations; keeps whatever's left
  (local PHIVOLCS + regional refs not in the exclusion list)
- Three variants (NAMRIA, NP, PIVS) differ in which regional stations are included
- Python replacement should use WHITELIST approach (local ∪ regional_refs) — simpler and
  less fragile than copying a 200-station exclusion list

**vel_line_v8_newvelduetooffset_v4.m:**
- **Does NOT read OUTLIERS.txt** — has its own `rmoutliers("quartiles", ThresholdFactor=3)`
- OUTLIERS.txt must be applied to PLOT files DIRECTLY before MATLAB runs
- Data flow: metres → cm conversion (`*100`); regression slope `model(2,1)*10` → mm/yr
- Writes `Velocity_rover(regress)_10` (velocities), `outliers` (auto-detected), JPG plots

**analysis/offsets (production file):**
- Format confirmed: `SITE decimal_year TYPE` (space-delimited, no header)
- 73 entries covering EQ, CE, VE, UK events from 2014–2025
- `reader.py read_offsets()` confirmed correct

### CRITICAL discovery: vel_line_v8.m ignores OUTLIERS.txt

The original `outlier_input-site.py` workflow writes OUTLIERS.txt, but `vel_line_v8.m`
never reads it — it does its own IQR detection internally. The velocity-reviewer's
OUTLIERS.txt is an intermediate artefact that must be **applied to PLOT files** before
MATLAB runs. This was missing from the implementation plan.

---

## 4. velocity-reviewer — PLOT File Stripping

Added the missing piece to complete the tool.

### `write_cleaned_plots()` in `reader.py`

For each site with a non-empty selection:
1. Backs up `SITE` → `SITE.bak` on first export (creates if not exists)
2. On re-export, always reads from `SITE.bak` (restores semantics) — idempotent
3. Strips rows whose `round(float(col0), 4)` is in the selected timestamp set
4. Writes cleaned data back to `SITE`

Precision note: `round(..., 4)` aligns with the 4-decimal-place format written by
`RUNX_v2.py` (`{:.4f}`), guarding against IEEE 754 float drift in the JSON round-trip.

### `POST /api/export` updated

Now calls both `write_outliers_txt()` and `write_cleaned_plots()` and returns
`rows_removed` alongside `total_outliers` and `path`. Toast in `index.html` updated
to confirm "X rows stripped from PLOT files".

### Smoke test

Full round-trip test with synthetic Bernese PLOT format data (20 epochs, 1 injected
outlier): correct strip on first export; correct backup creation; correct restore-then-
strip on re-export with different selection. All assertions passed.

Commit: `bd743bb` — `feat(velocity-reviewer): strip PLOT files on export via write_cleaned_plots()`

---

## 5. Memory Updates

`memory/velocity_pipeline.md` comprehensively updated with:
- Confirmed teqc commands (Trimble: `-tr d`, Leica: `-lei mdb`) from §4.2.3/§4.2.4
- PLOT file format from `RUNX_v2.py:137`
- offsets file format from production file
- vel_line_v8 confirmed does NOT read OUTLIERS.txt
- 00_CRD_*.bat exclusion logic + three-variant mapping
- 8 campaign file generation order
- SAVEDISK directory structure
- BLQ web service (http://holt.oso.chalmers.se/loading/, FES2004, no tabs)
- IGS reference station list (S01R + 12 others)
- Two-pass BPE for continuous GPS

---

## 6. Pending Actions (carried forward)

| Action | Notes |
|--------|-------|
| Update logsheet API + frontend (Option B) | `LogSheetIn` @model_validator + LogSheetForm.tsx rebuild |
| Update orchestration explainer gaps | Add §: RINEX conversion, 8 campaign files, post-BPE scripts, BLQ dependency |
| Update orchestration explainer processing times | First run: 2–4 hrs; subsequent: 30–60 min |
| Build Jinja2 INP templates | From completed diff; 3 parameters + 2 variants (campaign/continuous) |
| Install Bernese on R740 | Same procedure as T420; no ISA mismatch |
| Parameterise `plot_v2.py` | `--reference-station` CLI arg |
| drive-archaeologist Trimble profiles | `.T01`, `.T02`, `.T04`, `.DAT`, `.TGD` |
| Write field ops PWA user guide | One-pager + quick guide |
| VADASE latch bug fix | `domain/processor.py:130` |

---

## Files Created / Modified This Session

| File | Change |
|------|--------|
| `tools/velocity-reviewer/src/velocity_reviewer/reader.py` | `write_cleaned_plots()` added |
| `tools/velocity-reviewer/src/velocity_reviewer/app.py` | Import + `POST /api/export` updated |
| `tools/velocity-reviewer/src/velocity_reviewer/static/index.html` | Toast updated |
| `memory/velocity_pipeline.md` | Comprehensive update (teqc, PLOT format, offsets, vel_line_v8, 00_CRD_*.bat, BLQ, SAVEDISK) |
| `docs/project_documentation/deliverables_tracker.md` | Date, status updates, recently completed, near-term items |
| `docs/project_documentation/roadmap.md` | Date, 1.3 research milestones, 2.4 status → in progress |
| `session_log_20260303.md` | This file |
