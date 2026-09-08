# Session Log — 2026-06-24

**Context:** NAMRIA Bernese training, Day 3. Working PAGENET campaign (session 2026/0840) on the
T420, the only Linux machine in the room. Caught up Modules 5→7, read ahead 8→17, handled infra fires.

---

## 1. Processing progress — Modules 5, 6, 7 all RUN OK

| Module | Result |
|---|---|
| 5 (POLUPD/ORBMRG/ORBGEN/SATCLK) | PCF vars pre-present; rows added | 
| 6 (RNXGRA/RNXSMT/RXOBV3) | first full run **OK, 20m00s** |
| 7 (CODSPP/CODXTR) | **OK, 8m38s** — clock-sync confirmed (`CLOCK OFFSETS STORED IN CODE+PHASE`), worst station PAPI 4.54% bad (<10%), none dropped |

PCF now has rows 001→299. Verified column-correct, no dup PIDs each time.

---

## 2. Docs/artifacts created this session

- **`docs/project_documentation/bernese_modules_7_8_runbook.md`** — full runbook **Modules 7–17**
  (retitled from 7–8). Per module: paste-ready PCF rows (column-aligned), new vars, new OPT dirs,
  key panel settings, verify outputs. Verdict table: all 9–17 are EXECUTION except **Module 8 (theory)**;
  **17 is one-time setup** (campaign files, already done — PGN.* exist).
- Earlier docs still live: `bernese_monitoring_cheatsheet.md`, `bernese_dependencies.md`.

### Cross-cutting gotchas captured in runbook
- Modules 11–16 need **new OPT dirs** (PGN_EDT/AMB/L53/QIF/L12/FIN, SOB_FIN, PGN_RED, PGN_WK/MO) — a run
  dies instantly at a PID if its OPT dir is missing. One-liner check included.
- Course **tables vs screenshots disagree** on some OPT dir names (PGN_* vs SOB_*) — trust the dir that exists.
- Module 16 **deletes** (V_DEL=Y, R2S_DEL, BPE_CLN) — confirm SAVEDISK before real run.

---

## 3. Infra fires handled

- **SAT_2026.CRX missing** (Module 5 blocker) → placed in `$CONFIG` (`$C/GLOBAL/CONFIG`). AIUB moved
  downloads to S3-style object storage; BSWUSER54/GEN 404s, served only from **BSWUSER52/GEN/SAT_YYYY.CRX**.
  Documented in [[bernese-orchestrator-r740-gaps]].
- **ORBMRG.INP "missing"** — false alarm; ORBMRG runs on defaults (panel is CCPREORB.INP). PGN_GEN complete.
- **Disk 100% full** (/home, 0 avail) → user ran `~/scripts/lean_machine.sh` (clears uv/npm/browser/
  playwright/docker/pip caches + AdsBot build artifacts; touches NO Bernese/GPSDATA — safe). Freed to 85%/21GB.
  Root cause: instructor's 7GB multi-day RINEX archive in `$D/PGN`; only 0840 (~766MB) needed.
- External drive: symlinked `PGN_All` + `Pagenet_Bernese_Files` from `/run/media/finch/Backup Plus/...`
  into `~/Downloads/eldar/`. Full RINEX archive lives on backup drive.

---

## 4. RINEX format + gzip handling (instructor flagged)

- Instructor confirmed this Bernese setup handles **gzip poorly** — yesterday's run likely worked only
  because RINEX was pre-decompressed. The flaky layer is **gzip**, NOT Hatanaka (CRX2RNX is integrated/fine).
- `.crx.gz` = two layers: strip gzip (`gunzip`), leave `.crx` (Hatanaka) for Bernese's CRX2RNX.
- THIS run (RINEX3 `.crx.gz`): RNX_COP **succeeded** auto-decompressing — gzip issue did NOT recur.
- RNXGRA logged many **`Error decoding observation record header line` ('  ' instead of '> ')** — RINEX3
  epoch-record format errors; records SKIPPED (data loss) but non-fatal. Worst: `PVIG00XYZ` (bogus XYZ
  country code). This is why the whole room's "201 looks stuck" — RNXGRA is just slow (9.5 min/72 files
  sequential) + noisy. Flag to instructor: conversion/data-quality issue in shared RINEX3 set.

---

## 5. Operational lessons

- **Closing the terminal that launched the menu KILLS the BPE** (SIGHUP to child processes). Happened mid-222.
  Recovery: `BPE → Reset CPU File → USER.CPU` (mandatory — clears stale locks), then re-run from the nearest
  **AP master** (never a `_P` slave — BPE crashes if you start on a slave). Restarted at 221 → clean, 8m38s.
- T420 `maxjobs=2` makes RXOBV3/CODSPP parallel steps grind 2-at-a-time. R740's 24 cores → 12× faster here.
- Launcher `~/.local/bin/bernese-menu` (symlinked from `~/scripts/`); `MENU.INP` lives in `$U/PAN`, not `$XQ`.

---

## 6. Repo / git work

- **PR #37 closed** as superseded (BRN-005/006 landed on main via parallel commits + c002a88 fixes + ANA-001).
- Added **`Bash(gh pr:*)`** to `.claude/settings.local.json` (the space-form `gh pr *` rule didn't match).
- **Bernese-config versioning strategy** recommended (scoped to movefaults repo): add a versioned
  user-env provisioning layer to `services/bernese-workflow` — `templates/pcf/`, `opt/` (gold-standard
  panels as static files), `reference/` (PGN.*) + a `provision_user_env(user_dir, host_profile)` that syncs
  to `$U`. Rule: edit in repo (PR-reviewed) → deploy to `$U`; never edit panels in EDITPCF on production.
  Closes orchestrator gaps #4/#5. NOT yet built — offered to scaffold + extract T420 `$U` config as baseline.

---

## 7. CODSPP coordinate-estimation experiments (post-Module-7, exploratory)

Re-ran CODSPP from PID 231 three ways to see how the "Estimate Coordinates" option changes output.
Pure learning — output is throwaway, no downstream impact (`.CRD` apriori feeds forward either way).

| Mode (CODSPP 2) | CODSPP 1.3 output | Result |
|---|---|---|
| **STATIC** (default) | `APR_$(CLUSTER)` `.CRD` | 1 coord/station/day. Output CRD shifted ~**dm** from apriori (CUSV Y −0.24 m). RMS unit wt ~0.7–1.0 m. |
| **KINEMATIC** | `APR_$(CLUSTER)` `.KIN` | 1 coord/station/**epoch** → `.KIN` series, ~2880 rows/sta @30s, `K` flag. "Output kinematic coordinates" field populates (was `---`). |
| NONE (not run) | — | would fix to apriori, estimate clock only; CRD = input. |

### Per-station kinematic scatter (std of ECEF X/Y/Z, mm) — 58 stations
Computed from all 8 `.KIN` clusters. Noise floor: **X ~0.3–0.7 m, Y ~0.5–0.9 m, Z ~0.2–0.4 m** = code SPP kinematic.
- **Y > X > Z everywhere** — ECEF axes (NOT ENU). PH ~120–125°E → ECEF Y ≈ E-W horizontal carries most noise. Needs ENU rotation to read as horiz/vert.
- Best PDIP (340/468/196), worst real PZAM (676/1228/443). **PURD = bad: 307 epochs, sdY 2.4 m** (RINEX gaps / skipped-record errors) → screening will drop.
- Nepoch 2880 = full day @30s; short ones (PCB2 2160, CUSV 2719, PURD 307) = data gaps.

### Coseismic relevance (discussed)
- Kinematic GPS = the method for coseismic: **static** daily Δposition = permanent offset (→ `offsets` file / `offset_events` table, applied before velocity regression); **kinematic high-rate** = dynamic displacement waveform ("GPS seismometer", doesn't saturate near-field like inertial sensors, measures static step directly).
- This run's code+30s → noise floor ~0.5–1 m → only sees >~1 m jumps (M7.5+ near-field). The std table = a **detection-threshold map** (each sta's sd = min resolvable coseismic jump in code mode). Real EQ detection needs **carrier phase (cm) @ 1 Hz** — exactly VADASE's tier.
- VADASE (real-time, single-sta variometric, drifts) vs Bernese kinematic PPP (post-processed, precise, authoritative) = complementary, same physics.

## 8. Instructor-provided scripts — eval + BSW_DWLD patch

Instructor demoed 4 scripts in `~/GPSUSER/SCRIPT/` (`ADD_MON ADD_WK P3_IGSRX BSW_DWLD`), proposed adding
after Module 7. **Eval: they are NOT a block — opposite ends of the workflow:**

| Script | Function | True PID (ref PHIVOL_REL.PCF) | Belongs |
|---|---|---|---|
| BSW_DWLD | DL AIUB config + CODE products + SAT_YYYY.CRX | ~00x (before 011) | **FRONT** |
| P3_IGSRX | DL IGS global RINEX (S3→GA archive) | ~00x | FRONT |
| ADD_WK | stack daily NEQ → weekly ADDNEQ2 (Sat only) | **530** (waits 514) | **END / Mod 15** |
| ADD_MON | stack daily NEQ → monthly ADDNEQ2 (month-end) | **531** (waits 514) | END / Mod 15 |

- ADD_WK/ADD_MON **cannot run after M7** — need daily `.NQ0` that only exists after Mod 8–14 (PID 514). Instructor's "after M7 not M15" is backwards for these two. Defer to when PCF has Mod 8–15.
- DL scripts after M7 = too late (Mod 5/6 already consumed orbits/RINEX). Correct home = front, before RNX_COP.

### Cross-platform perl-error pattern (why trainees crash, we don't — and vice versa)
- **P3_IGSRX**: works on our Linux (all https modules present), **breaks on Windows** trainees — base Strawberry/ActivePerl lacks `LWP::Protocol::https`+`IO::Socket::SSL`+`Net::SSLeay` → `getstore` on https GA archive fails. Also bare `die` line 52 if V_RNXDIR missing. Hardcoded IGS list ends in `"ABCD"` placeholder. Low value for us (we stage RINEX manually; list ≠ PAGENET CORS).
- **BSW_DWLD**: **mirror image — works on Windows, dies on our Linux.** 2 hardcoded Windows paths:
  `C:/Bernese/DATAPOOL/BSW54` (line 93/94) + `C:/Bernese/DATAPOOL/COD0OPSFIN` (line 129/130) →
  `chdir ... or die` crash at line 94.
- **ADD_MON landmine (future):** line 39 uses smartmatch `$mm ~~ [4,6,9,11]` — **removed in perl ≥5.42**,
  our perl already chokes on the feature pragma. Will throw `Unsupported use of ~~` when Mod 15 added. Fix: replace with `grep`.

### BSW_DWLD patch APPLIED (this session)
- Backup: `~/GPSUSER/SCRIPT/BSW_DWLD.orig`
- Edits: line 93 `$ionLocalDir = "$ENV{D}/BSW54"`; line 129 `$prodLocalDir = "$ENV{D}/COD0OPSFIN"`.
- `perl -c` OK. Both target dirs exist, curl + perl deps present.
- **Var audit:** all 21 `V_*` present in PAGENET.PCF; ~30 `DIR_/EXT_/PTH_` resolve from panel defaults
  (dead reads — download lists only actually use 7: `$yyyy $yyyyddd V_SATINF V_PCV V_REFINF V_PCVINF V_ORB`).
- **Value:** highest of the 4 — automates the manual SAT_2026.CRX + CODE-product staging that bit us 06-23.
  Idempotent (`needsDownload` HEAD size-check). Worth keeping as a front PID for PHIVOLCS production.

### ⚠️ R740 FLAG (BRN-001 install)
The same 2 hardcoded `C:/Bernese/DATAPOOL/...` paths in **stock BSW_DWLD** will crash on R740 (also Linux).
Apply the identical `$ENV{D}/...` patch when provisioning R740 user-env. Note: this is a per-machine source
edit on an instructor script → exactly the case for the **versioned user-env provisioning layer** (memory:
bernese-config versioning) — BSW_DWLD belongs in repo `opt/`/`script/` as a patched gold-standard file,
not hand-edited on each box. Add to orchestrator gaps (path-portability of instructor scripts = gap #8).

## 9. Module 9 — SNGDIF baselines — DONE

Ran 301-303 (INIT_BSL → SNGDIF phase OBS-MAX → SNGDIF code DEFINED). **Session finished OK, 0 errors.**
- **71 baselines from 72 stations = N−1 spanning tree** (complete, no isolated stations).
- Single-diff files landed in **OBS/** (not ORX): PSH/PSO 71 (phase), CSH/CSO 71 (code), identical baselines
  (303 reused 302's BSL via DEFINED). Zero-diff ZH/ZO 72 retained.
- `BSL_20260840.OUT`: Predefined `---` for phase (fresh OBS-MAX), coords `APR_20260840.CRD`.
- Output section title "ASSIGNMENT OF BASELINES TO **CLUSTERS**" = the subnetwork sense (terminology collision, §7 of UX doc) — live example.

### A priori non-issue (resolved)
User worried they "forgot to feed back better a priori." **Not needed — backwards for established CORS.**
SNGDIF used `APR_20260840.CRD` = PGN.CRD velocity-extrapolated to epoch (flag **R**, mm-level ITRF) — the
BEST a priori. CODSPP code "NEW" coords (flag **C**, ~2-5 m off) are WORSE for known stations; never fed
forward. CODSPP's real jobs = clock sync + QC (the bad-a-priori detector, gap #9), not coord improvement.
"Feed back coords" only applies to: (1) new/unknown stations, (2) two-pass continuous-GPS final-solution
feedback (Module 13+, not now).

## 10. Module 10 — MAUPRP phase preprocessing — THEORY covered (execution deferred)
Instructor covered theory; runbook marks it EXECUTION (PID 312, AIUB-default panels, quick run) — NOT run yet.
Concepts: carrier-phase integer ambiguity N (one/arc), cycle slips from loss-of-lock (esp. Philippine
equatorial scintillation/plasma bubbles), detect via triple-diff (time-difference cancels N → slip = spike)
+ geometry-free L4 + Melbourne-Wübbena; repair/split-arc/screen. Works on SNGDIF single-diffs (why M9 first).
A priori quality bites here (geometric slip prediction) — good APR coords confirmed feeding in.

## 10b. Module 10 MAUPRP — EXECUTED (full from-001 run, 30:04, OK)

Ran full chain 001→313 (incl MAUPRP 311/312 + MPRXTR 313). **Session OK, 0 errors, all 71 baselines processed.**
Summary: `OUT/MPR_20260840.SUM`. RMS 12–26 mm (healthy). But **heavy cycle-slip environment = Philippine
scintillation** — slips tens→277/baseline, deletions →4896, new ambiguities (#MA) →460. ~half baselines
flagged `<<-- CRD`.

### Interpretation (for tomorrow's Module 12 ambiguity resolution)
- `<<-- CRD` flags are **NOT bad a priori** (coords are flag-R mm-level established CORS, confirmed §9).
  They're the internal triple-difference coord check going noisy *because* of high slip count → scintillation
  symptom, not a coordinate problem. Don't chase a priori.
- High `#MA` (arc splits) = more ambiguity parameters for Module 12 → expect **lower ambiguity-fixing rate**
  than the ~80% benchmark; scintillation is the cause. Watch the QIF/L53/L12 fixing % tomorrow.

### ⚠️ Suspect stations to watch in Module 12 (flagged from MPR_20260840.SUM)
- **PBOR or PMOT** — baseline PBOR–PMOT (#61): #SL 277, #DL **4896**, #MA **460** = by FAR the worst, on a
  short 50 km baseline (geometry can't explain it). One of the two has a real problem (hardware / extreme
  local scintillation). Isolate which: check each station's other baselines.
- **PTCG** — OBS-MAX **hub** (PDIG/DARW/PMAI/PMRM/PMAT/PCOT/PGEN all difference against it), recurs in many
  `<<-- CRD`-flagged baselines. If PTCG itself is noisy, all its baselines inherit the flag → could look like
  a network-wide problem that's actually one bad hub station.
- **PMAI–PTCG** (#16): #SL 241 — second-worst slip count.
- Action tomorrow: if ambiguity-fixing rate is low, check whether dropping/down-weighting PBOR/PMOT/PTCG
  recovers it. Candidates for the CODXTR-style station-screening the orchestrator should automate (gap #9 family).

## Bernese training docs created/updated today
- `docs/project_documentation/bernese_modules_7_8_runbook.md` (Modules 7-17)
- `docs/project_documentation/bernese_ux_modernization.md` (NEW — menu-UX-moot-under-orchestration thesis, §7 terminology collisions)
- memory `bernese-orchestrator-r740-gaps.md`: gaps #8 (script path portability) + #9 (CODSPP-QC gate)

## State at end of session (Day 3, 2026-06-24)
- **Done today:** Module 6 full run, Module 7 (×3: static/kinematic/static-from-011), Module 9 (SNGDIF, 71 baselines), **Module 10 MAUPRP (full from-001, OK)**. Module 10 theory + execution both done.
- **Queued for tomorrow (Day 4):** **Module 11 (GPSEST float solution)** + **Module 12 (ambiguity resolution)** — see §10b suspect stations (PBOR/PMOT/PTCG) + expect scintillation-lowered fixing rate.
- Pipeline state: campaign `$P/PAGENET` processed **through MAUPRP (PID 313)**; phase obs cleaned + arcs/ambiguities set; APR coords good (flag R, mm-level). Ready for GPSEST float.
- ⚠️ **`CODSPP.INP` = STATIC** + `.CRD` (correct resting state). KINEMATIC `.KIN` from 11:30 retained.
- ⚠️ **BSW_DWLD patched** (Linux paths, §8). Backup `BSW_DWLD.orig`. Same fix needed on R740 (gap #8).
- Stale watch `bqff8x476` keyed on ORX (SD files went to OBS/ instead) → will time out at 1hr, harmless.
- PAGENET.PCF complete through 299; OPT panels for M9/10 (SNGDIF/MAUPRP) present in PGN_GEN.
- Uncommitted in repo: new runbook + this log. Earlier session docs untracked too.
- Watches `bbie91f6o` (old, timed out) + `b6f7ntzdv` (fired OK) both done.
