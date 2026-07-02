# Session Log — 2026-06-26

**Context:** NAMRIA Bernese training, final day. PAGENET campaign — completing the full BPE
pipeline (Modules 13-16) and starting the 7-day weekly combined solution. Plus tooling
(headless driver, resume automation), a Linux setup primer for another trainer, and a
GFZRNX licensing determination.

---

## 1. Module 13/14 — verified PASS (from 2026-06-25 run)
`FIN_20260840.CRD` produced. **HELMCHK: RMS 8.64 mm, 6 fiducials accepted, 0 rejected** —
under the 10 mm datum-tie gate. PIMO (IGS anchor, DOMES 22003M001) max 3D residual 26 mm,
accepted despite equatorial scintillation. The final mm coordinates exist.

## 2. PCF upgraded to full Module 16 (`$U/PCF/PAGENET.PCF`)
Eldar's reference PCFs in `~/Downloads/eldar/PCFs/`. Upgraded the working PCF from Module 14
(stops at 514) to full Module 16 by adding:
- **Module 15** (NEQ stacking): `530 ADD_WK` (PGN_WK), `531 ADD_MON` (PGN_MO)
- **Module 16** (save/cleanup): `901 R2S_SUM`, `902 R2S_SAV`, `903 R2S_DEL`, `991 BPE_CLN`, `999 DUMMY`
- 7 vars: V_WK, V_MO, V_RESULT, V_SAV, V_SAVOBS, V_RED, V_DEL.

**Diverged from Eldar's file on purpose:** dropped dangling `WAIT=522` (PID 522 never defined —
instructor typo, would hang BPE); kept `ORBGEN WAIT=101 111` (POLUPD makes the pole ORBGEN needs)
over Eldar's looser `001 111`; kept `V_HOIFIL=HOI_$YYYSS+0` over Eldar's `$HOI_` (stray leading `$`);
moved 513/514 to PGN_FIN directly, retiring the SOB_FIN symlink crutch.

## 3. The 7-day weekly needs a daily batch (the real Module 15 deliverable)
ADD_WK combines **7 daily FIN normal equations**. Only 084 was processed → need 085-090 too.
Data inventory: `$D/PGN` holds the full week, but in **two naming schemes**:
- PAGENET CORS = RINEX2 short-names (`pzam0810.26d`, DOY in name, year in `.26d` ext)
- IGS fiducials = RINEX3 long-names (`CUSV00THA_R_20260840000_...`)
Processable week = where both exist = **084-090** (~54 stations/day, uniform). Products
(orbit/clk) all pre-staged in `$D/COD0OPSFIN` — no download.

## 4. Headless driver (Simon's lesson = the orchestrator contract)
Simon Fuller (Position++) demoed driving BPE menu-free via the stock `rnx2snx_pcs.pl` — which
**hardcodes** `PCF_FILE`/`BPE_CAMPAIGN`. Created `$U/SCRIPT/pagenet_pcs.pl` = the stock script
parameterized: takes `yyyy ssss [pcf]`, defaults PCF=PAGENET, tags STATUS/SYSOUT to the PCF.
This is exactly the contract the Python bernese-workflow orchestrator must speak
(subprocess → Perl startBPE → parse ERROR_STATUS). Also built **`PAGENET_DLY.PCF`** — the full
PCF truncated at 514 (drops 530/531/901-999) so each daily run stops before the weekly/cleanup.

## 5. Daily processing run — 084/085/086 DONE, 087-090 remaining
~2h/day on T420 (the `502 GPSCLU_P` final clustered GPSEST solve dominates — single big cluster
from `V_CLUFIN=A` auto-clustering). Two failures, both fixed:

### Fail A — PID 222 RXOBV3 on station PLG2 (086)
`### SR RXOSTA: RINEX station name not listed in station info file` — PLG2 absent from `PGN.STA`,
hard-aborts RXOBV3 (the #1 PHIVOLCS pain, loud form). PLG2 is **intermittent** — present only
DOY 086 + 088 of 7 → that's why 084/085 passed. Fix: stashed PLG2 from DATAPOOL (`.excluded_plg2/`)
and campaign RAW — reversible, gives a consistent 7-day network for the weekly. 088 pre-immunized.

### Non-fail — PID 322 PTAG troposphere (085 passed)
084 failed here on the PIMO-PTAG 12km baseline (unobservable differential troposphere → overflow).
085 passed the *same* baseline clean → **PTAG is data-dependent per day, NOT structurally broken**.
PTAG is a legit NAMRIA PAGENET CORS; PIMO outweighs it only as the IGS fiducial when they conflict.
No blanket exclusion — handle reactively if a specific day trips 322.

## 6. Halt at 15:25 (training ended 16:00) — clean boundary
Killed chain + driver + BPE + orphan menu wrappers by explicit PID. 084/085/086 intact,
087 discarded (killed at RNXGRA, no partial output, no locks). Resume = `~/run_pagenet_week.sh`.

## 7. Resume automation (`~/run_pagenet_week.sh`)
Self-contained, shellcheck-clean, **idempotent** (skips days whose FIN NQ exists), **self-detaching**
(`--detach` → setsid/nohup, survives logout), single-instance lock, halt-on-error with station-hint
diagnostics. One command at home: `~/run_pagenet_week.sh --detach` → finishes 087-090 unattended.
Resume notes: `~/RESUME_pagenet_week.md`. Then Phase B (fix PGN_WK panel `\`→`/`, anchor 090) +
Phase C (ADD_WK weekly combine).

## 8. Bernese-on-Linux primer for Simon (`docs/bernese_linux_setup_primer.md`)
Simon (decade+ Bernese instructor, Perl-on-Windows, Linux by accumulation) asked how we got BPE
native on Linux. Wrote a peer-level **delta sheet** — not a primer: only the 2024-25 toolchain
breakages (gfortran ≥10 arg-mismatch, x86-64-v3 ISA note objcopy strip, Ubuntu PPA trap forcing
conda-forge gfortran, Qt4.8.7 static build on g++-13+, X11 soname symlinks), with unix-tooling
asides glossed for an occasional-Linux reader. No Bernese/Perl 101, no PII.

## 9. GFZRNX vs teqc — decision + licensing
Decision: **teqc stays primary** for GPS-only RINEX-2 work; **gfzrnx migration trigger = first
RINEX 3/4 file teqc can't process, NOT multi-GNSS desire**. teqc is unmaintained (UNAVCO 2019),
RINEX-2-era; the mixed-version PAGENET data (IGS=RINEX3) means the version-migration is when-not-if.
License: scientific (free) covers current manual desktop processing; the **planned year-end
automated server pipeline** = "recurring process chain" → needs commercial campus license even for
a public agency. Drafted GFZ inquiry (`~/Downloads/gfzrnx_license_inquiry_GFZ.md`) + internal cover
note for Project Lead Dr. Bacolcol + GGRDD section head (`~/Downloads/gfzrnx_internal_cover_note.md`).

## 10. R740 deployment-readiness evaluation (`docs/project_documentation/bernese_orchestrator_r740_readiness.md`)
Consolidated the week's empirical findings into a prioritized orchestrator-hardening plan for
BRN-001. **Verdict: engine proven (full RNX2SNX ran headless on real data), robustness layer is the
gap.** Every failure fixed BY HAND this week = a thing the orchestrator must do AUTOMATICALLY before
unattended R740 trust. P0 (per-session station validator, MAXPAR sizing, GEN/SESSIONS, PCF
parameterization), P1 (CODSPP-QC + tropo-retry + sanitizer + resumable scheduler), P2 (clustering perf
+ Module 15/16 scope). Sharpest insight: the **R740 multi-core win is inverted** — untuned, R740 runs
the same single-core 502 GPSCLU_P solve on a bigger network = worse than T420; the 24-core payoff is
entirely clustering + USER.CPU tuning (a config task, not free hardware). Memory gaps #12-14 added.

## Commits (branch docs/bernese-training-notes, pushed to origin)
- `f65da8d` — session logs (06-25, 06-26), Linux setup primer, resume scripts (run_pagenet_week.sh,
  pagenet_pcs.pl, RESUME note), runbook typo fix.
- `cf1cf2a` — R740 orchestrator deployment-readiness evaluation.
- Excluded deliberately: untracked presentation/legacy pile; gitignored `deploy_r740.secrets` (verified).

## State at end of session
- **Done:** Modules 11-14 (084); daily FIN solutions for 084, 085, 086; full training-week consolidation
  + R740 readiness plan committed.
- **Next (at home):** `~/run_pagenet_week.sh --detach` → 087-090, then Phase B (fix PGN_WK panel) +
  Phase C (ADD_WK weekly combine).
- PLG2 stashed (088 immune); PTAG handled reactively; campaign intact.
- **Pending (user, async):** send GFZ license inquiry + internal cover note (fill brackets); rotate the
  OAuth token in `deploy_r740.secrets`.
