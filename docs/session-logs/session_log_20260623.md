# Session Log — 2026-06-23

**Context:** NAMRIA Bernese training, Day 2. First hands-on with the PAGENET campaign on the T420
(only Linux machine in the room). Rescued a broken campaign, speed-ran Modules 5 & 6 PCF, discovered
orchestrator gaps. (Continuation: Module 6 full run + Module 7 happened 2026-06-24 — see that log.)

---

## 1. PAGENET campaign rescue (Module 4 carry-over)

User finished Module 4 manually via the GUI but the BPE wouldn't run — errors pointed at `INTRO`.
Root causes found + fixed:

- **Active campaign = `INTRO`** (Bernese tutorial default, nonexistent) instead of PAGENET. The RUNBPE
  panel had `PCF_FILE=PAGENET.PCF` but `ACTIVE_CAMPAIGN=${P}/INTRO`. Errors: "BPE-Protocol Directory
  .../INTRO/BPE/ does not exist". Fix: register PAGENET in campaign list + select as active.
- **Campaign dir half-built** — `$P/PAGENET` had only `STA/`. Missing all other required subdirs.
  Created `ATM BPE GRD OBS ORB ORX OUT RAW SOL` (+ `GEN/`).
- **No session table** — created `GEN/SESSIONS.SES` (copied EXAMPLE's `???0` daily template).
- **`chmod +x RUNBPE.sh`?** No — red herring. It's already +x and BPE uses `RUNBPE.pm` (Perl) anyway.

Lesson: the canonical Bernese way (menu *Campaign → Create New Campaign*) builds all of this; the
hand-mkdir bypass is exactly what bit the user. → fed into orchestrator gap #2.

---

## 2. Module 5 & 6 PCF speed-run

All Module 5/6 **variables were already present** in PAGENET.PCF (NUTMOD/SUBMOD/MEANPL/STOCH/SATCRX/
RNXDIR/RNXSEL/CLU) — only the script **rows** were missing. Added (column-aligned, verified no dup PIDs):
```
011 RNX_COP  099 DUMMY                                    (Mod 6 insert)
101 POLUPD 111 ORBMRG 112 ORBGEN 113 SATCLK 199 DUMMY     (Mod 5)
201 RNXGRA 211 RNXSMTAP 212 RNXSMT_P 221 RXOBV3AP 222 RXOBV3_P  (Mod 6)
```
First partial BPE run (001–005 only, before rows added) finished in 2s (`23-Jun 15:18`).
Confirmed prereqs staged: COD0OPSFIN orbit/ERP/clock products, RINEX in `$D/PGN`, session 2026/0840.

- **ORBMRG.INP "missing"** — false alarm. ORBMRG runs on defaults (its panel is CCPREORB.INP). PGN_GEN complete.

---

## 3. SAT_2026.CRX + AIUB endpoint change

Module 5 §5.6.1 needs `SAT_$Y+0.CRX` = `SAT_2026.CRX` ("instructor provides"). Was missing.
- AIUB moved BSWUSER downloads to **S3-style object storage**. `BSWUSER54/GEN/` paths now 404 (NoSuchKey).
- SAT problem files served only from the 5.2 path:
  `https://www.aiub.unibe.ch/download/BSWUSER52/GEN/SAT_YYYY.CRX` (version-shared file; BSW5.2 header but
  5.4-compatible). No dir listing (object storage) — must request exact keys.
- Fetched + placed in `$CONFIG` = `$C/GLOBAL/CONFIG/SAT_2026.CRX` (where Bernese loads it, NOT campaign GEN).

---

## 4. Orchestrator R740 gaps discovered (→ memory `bernese_orchestrator_r740_gaps.md`)

While reconciling the manual PAGENET workflow against `services/bernese-workflow`, found 7 gaps the
orchestrator must fix before R740 production (BRN-001). Top ones:
1. **BRN-006 validator runs at wrong time** — checks campaign `RAW/` pre-BPE, but RINEX arrives via
   RNX_COP (PID 011) *inside* BPE → empty RAW → vacuous pass (same class as the `.RXO` bug).
2. **prepare_campaign() omits `GEN/` + SESSIONS.SES** — `_SUBDIRS` has no GEN; exactly what broke the
   manual run (§1).
3. **PCF + driver hardcoded to RNX2SNX** (`rnx2snx_pcs.pl`, CPU_FILE "PCF") — can't run PAGENET.
4. Template is AIUB-stock flavor (R2S_GEN, `_H` variants), not PHIVOLCS PAGENET (PGN_GEN, `_P`).
5. Module-5 model vars missing from template/PCFContext.
6. GEN config files (SAT_*.CRX, nutation/pole) not staged or pre-flight-checked.
7. IGS-001 product naming (COD0OPSFIN_*) to verify.

---

## 5. Course-notes read-through + runbooks started

Read Modules 5–8 PDFs (`/home/finch/Downloads/eldar/CourseNotes/`). Classified execution vs theory.
Started runbook `docs/project_documentation/bernese_monitoring_cheatsheet.md` (files to watch during a
run) and the Modules 7/8 runbook (later extended to 7–17 on 06-24).

Key framing established: course is **GUI menu work, identical on Linux and Windows** — the only diff is
path style (`C:\Bernese\...` vs `/home/finch/...`), and Bernese fills those from `${X}`/`${D}`. Alfie is
the only Linux trainee; not disadvantaged.

---

## State at end of 06-23
- PAGENET.PCF complete through Module 6 (rows ≤222); campaign tree + session table built; SAT_2026.CRX placed.
- Ready to run Module 6 end-to-end (happened next morning, 06-24: OK, 20m00s).
- Memory written: `bernese_orchestrator_r740_gaps.md`, indexed in MEMORY.md.
