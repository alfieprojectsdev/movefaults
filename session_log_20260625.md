# Session Log — 2026-06-25

**Context:** NAMRIA Bernese training, Day 4. PAGENET campaign (2026/0840) on the T420.
Modules 11 (float) + 12 (ambiguity resolution) — the heart of high-precision GNSS. Plus a hardline
ops-tooling detour (separate repo) and the deploy script secrets extraction.

---

## 1. Module 11 (float) + 12 (ambiguity resolution) — DONE after 3 fixes

Full pipeline 301→499 completed: **`OK: 1, Error: 0`, 50:59.** Three failures, three fixes:

### Fail 1 — PID 322 (float screening): troposphere overflow
`### sr trpvec1 ... Zenith delay: ****** M` on stations **PIMO/PTAG**. Root cause: **PIMO–PTAG 12 km
baseline** — too short, tropo nearly identical → differential zenith delay **unobservable** → diverged
to -4.9 m → overflow → GPSEST abort. Amplified by loose `SIGREL=5.00 m` + scintillation-thinned data.
- This baseline was already the network anomaly in MAUPRP (#12: MAXL3 0, MIN.SLIP 0, #MA 0).
- **Fix:** dropped **PTAG** (NOT PIMO). PIMO is an **IGS fiducial** (DOMES 22003M001) — ties PAGENET to ITRF,
  must keep. PTAG was malformed: **blank DOMES**, **RINEX2 source** (`ptag0840.26O` vs PIMO's RINEX3
  `PIMO00PHL_R_`), **naming collision** (`PTAG` vs `PTAG 22006M005`, coords differ ~3 m same file).
  PTAG obs stashed to `OBS/.excluded/` (recoverable). PTAG is a CORS hub (3 baselines) but partners
  (PSJN, PTLC) don't orphan; PIMO re-paired to **PMRV** (longer, observable baseline). Datum survives:
  9 IGS anchors remain (CUSV DAEJ DARW GUAM HKSL JOG2 NTUS PIMO TWTF).

### Fail 2 — PID 341 (ADDNEQ2): dimension too small
`*** SR neqckdim: DIMENSION TOO SMALL. Requested: 1001, Maximum: 1000.` Off by ONE.
- **ROOM-WIDE issue** — confirmed other trainees hit "dimension too small" too. The AIUB/PHIVOLCS panels
  ship `MAXPAR=1000`, but the full ~71-station PAGENET network needs 1001 (3 coords + tropo + stacked
  params/station). Everyone processing all stations hits it at ADDNEQ2.
- **Fix:** bumped `MAXPAR` 1000→**5000** in **all 5 ADDNEQ2 panels** (PGN_GEN, PGN_FIN, PGN_WK, PGN_MO,
  PGN_RED) — not just the one that failed, so Modules 13/15/16 won't re-hit it. Spinbox max is 20000;
  production ~270 stations (R740) may need more.

### Success — full AR ladder, mm solution
71 stations, 301→499, ambiguity-fixed.

## 2. Ambiguity fixing rates (the headline numbers) — `OUT/AMB_20260840.SUM`

Per-strategy (stratified wavelength ladder):
| Stage | λ | GPS | GAL | GLO |
|---|---|---|---|---|
| **WL** (code wide-lane) | ~86 cm | **88.6%** | 92.5% | — |
| **NL** (code narrow-lane) | ~10.7 cm | 61.3% | 70.4% | — |
| **L5** (phase WL, <200km) | | 70.9% | 70.8% | 38.6% |
| **L3** (phase NL, <200km) | | 59.5% | — | 30.5% |

Network totals: **GPS ~71%, GAL ~73%, GLO ~31%.** Resolved RMS 1.5–10 mm (mm-level payoff).

### Interpretation
- **WL ~90% = textbook** — 86 cm wavelength crushes noise, confident integer fix. Ladder foundation solid.
- **GPS/GAL ~71-73%, below ~80% mid-latitude benchmark = SCINTILLATION** — equatorial ionosphere drags
  narrow-lane/L3 fixing down. Predicted; physics of PAGENET's location, not a processing fault.
- **GLO ~31% is NORMAL, not a problem** — GLONASS FDMA (per-satellite frequencies) → inter-frequency
  biases break clean DD integer structure. GLONASS fixes poorly everywhere, mid-latitude included.
  Do NOT read as data/scintillation issue.

## 3. Watch-script bug (fix for next time)
Watch reported "ERRORED" on a successful run: `grep -qi ERROR` matched the literal **"Error: 0"** in the
status line. Must match `Error: [1-9]` or check the "OK:/Error:" counts numerically, not substring "ERROR".

## State at end of session (Day 4)
- **Done:** Modules 11 (float) + 12 (ambiguity resolution). Pipeline through PID 499, mm-level fixed solution.
- **Next:** **Module 13** (final fixed solution → `STA/FIN_20260840.CRD` = final coords). PCF rows 501-512
  + vars (`V_FIN=FIN`, `V_CLUFIN=A`) NOT yet appended. Then Module 14 (HELMCHK/COMPARF, 10mm gate).
  MAXPAR already bumped in PGN_FIN → Module 13 ADDNEQ2 won't re-hit the wall.
- Campaign intact: 71 stations (PTAG excluded, in `OBS/.excluded/`); PIMO(IGS) kept, re-paired to PMRV.

## Non-Bernese work this session (see hardline repo + deploy script)
- **hardline** — new public repo github.com/alfieprojectsdev/hardline (zero-config direct-cable connector;
  MIT; noreply commit identity, no PII). Motivation: MIS-managed WiFi keeps breaking R740 workflows.
- **deploy_r740.sh** — added `--direct` mode (uses hardline), extracted secrets to gitignored
  `deploy_r740.secrets`. ⚠️ OAuth token in it needs rotation (sat in plaintext).
