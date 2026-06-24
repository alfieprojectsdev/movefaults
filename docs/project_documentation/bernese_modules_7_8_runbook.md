# Bernese PAGENET Runbook — Modules 7–17 (full processing chain)

Speed-run guide for the NAMRIA Bernese course, PAGENET.PCF campaign (session 2026/0840).
Everything here is GUI menu work — **identical on Linux and Windows**. Only path style differs:
course screenshots show `C:\Bernese\CAMPAIGN54\PAGENET\OUT`; on this T420 it is
`~/GPSDATA/CAMPAIGN54/PAGENET/OUT`. Open output files with **lite-xl** (course says Notepad++).

Prereq: Modules 4–6 done (PCF rows 001–222 present). Module 7 adds the first real *processing* step.

> **Execution vs theory:** **Module 7 is the work** — PCF rows + panels + run + verify on PAGENET data.
> **Module 8 is theory** — it processes nothing new. It explains parallel master/slave scripts and adds
> three *optional* conveniences (CPU-file Maxj, Start-From, Skip). Skim Module 8; the only thing worth
> doing is bumping Maxj for speed. The data progression Module 7 → Module 9 does not pass through any
> Module 8 step.

---

## Module 7 — Single Point Positioning (CODSPP)

Purpose: synchronise each receiver clock to GPS time via a code single-point position. First QC gate.

### 7.1 PCF rows — append at the end (BPE → Edit Process Control File → PAGENET.PCF)

```
231  CODSPPAP  PGN_GEN   CPU=ANY; WAIT=199 222
232  CODSPP_P  PGN_GEN   CPU=ANY; WAIT=231; PARALLEL=231
233  CODXTR    PGN_GEN   CPU=ANY; WAIT=232
299  DUMMY     NO_OPT    CPU=ANY; WAIT=233
```
Column grid: PID(3)+2sp, SCRIPT padded to 10, OPT_DIR padded to 10, then params. Save (Ctrl+S).

- `231 CODSPPAP` = parallel **master** (splits stations into clusters). `232 CODSPP_P` = **slave** (does the work) — note `PARALLEL=231` after `WAIT`.
- `233 CODXTR` = extraction/QC: collates all CODSPP outputs, flags + deletes bad stations.

### 7.2 CODSPP input panels — PID 232 (BPE → Edit PCF Program Input Files → PID 232)

Reused AIUB panels; **verify** these values (don't change unless noted):

| Panel | Field | Value | Why |
|---|---|---|---|
| CODSPP 1 | Code obs files | `????$S+0` | placeholder; CODSPP_P replaces at runtime |
| | Standard orbits / Sat clocks / Pole | `$(ORB)_$YYYSS+0` | from Module 5 (ORBGEN/POLUPD) |
| | A priori coords | `$(APR)_$YYYSS+0` | constrains solution |
| | Code bias input | `$(OSBFIL)` | DCBs (instructor-supplied) |
| CODSPP 2 | **Frequency** | **L3** | ionosphere-free; eliminates 1st-order iono |
| | **Clock Polynomial Degree** | **E** (every epoch) | one clock offset/epoch — most critical |
| | **Save Clock Estimates** | **BOTH** | store in code+phase obs (CZO,PZO) — critical |
| | Estimate Station Coords | STATIC | one est/station/day (apriori not overwritten) |
| | Troposphere | GPT3 | required; non-grid model |
| | Ionosphere | **None** (unticked) | not needed with L3 |
| CODSPP 3 | Min sat elevation | 3° | default |
| | Sampling | 1 (every epoch) | default |
| CODSPP 4 | Outlier detection | **Ticked** | |
| | Max residual / Confidence / Min DOF / Max RMS kin | 30.0 m / 5.0σ / 1 / 5.0 m | screening defaults |

Save (Ctrl+S).

### 7.3 CODXTR input panels — PID 233 (adds QC not in AIUB defaults)

Panel **CODXTR 2** → **tick Bad Station Detection**, set:

| Field | Value |
|---|---|
| RMS limit for a good station | 20 m |
| Limit for number of OUT lines per station | 10 |
| List of bad files (deletion list) | `CXT_$YYYSS+0` (.DEL) |
| Add phase files to deletion list | Ticked |

Stations exceeding these get their CZO+PZO obs **deleted** by CODXTR. Save (Ctrl+S).

### 7.4 Run + verify

Run: BPE → Start BPE Process → Run (Ctrl+R). Should finish clean.

Verify in `~/GPSDATA/CAMPAIGN54/PAGENET/OUT/`:
- **`SPP_<yyyy><ddd>0.OUT`** (CODXTR summary) — end of file lists worst-RMS + worst-bad-obs stations.
  CORS rule of thumb: RMS > 1 m or bad-obs > 10% → investigate that station.
- **`SPP_<yyyy><ddd>0_001.OUT`** (per-cluster CODSPP) — per-station stats. The critical line:
  ```
  CLOCK OFFSETS STORED IN CODE+PHASE OBSERVATION FILES
  ```
  If present, clock sync worked. This is the whole point of Module 7.

```bash
ls -lt ~/GPSDATA/CAMPAIGN54/PAGENET/OUT/SPP_*.OUT | head
grep -l "CLOCK OFFSETS STORED IN CODE+PHASE" ~/GPSDATA/CAMPAIGN54/PAGENET/OUT/SPP_*_*.OUT
```

---

## Module 8 — More BPE (concepts + operational features)

**No new PCF rows.** Explains parallel processing + adds three time-savers. Read once, use forever.

### 8.1 Parallel processing (master/slave) — already in your PCF

Three parallel pairs so far: `211/212` (RNXSMT), `221/222` (RXOBV3), `231/232` (CODSPP).
- **Master** (`…AP`) runs first: builds a *Control File* (`ctrfil` in `$T/AUTO_TMP/`) — one line per
  file/cluster to process.
- **Slave** (`…_P`) runs once per Control-File line, in parallel. Must `WAIT` the master + carry
  `PARALLEL=<master_pid>`.
- Full list of AIUB parallel scripts: `GPSUSER54/SCRIPT` (CODSPPAP/_P, GNSAMBAP/_P, GPSESTAP/_P,
  MAUPRPAP/_P, etc.). Reuse these — don't write your own.

### 8.2 Start From… (skip re-running early steps while testing)

BPE → Start BPE Processing → **Next** (RUNBPE 2) → **Start with script** → pick a PID → OK → Run.
- e.g. start at **231 (CODSPPAP)** to skip re-importing orbits/ERPs/RINEX.
- ⚠️ **Never start on a slave (`_P`) script** — BPE crashes instantly. Start on the master (`…AP`) or a
  non-parallel script.

### 8.3 Skip scripts (end processing early / redo a section)

BPE → Start BPE Processing → Next (RUNBPE 2) → **Skip scripts** → click first PID, Shift+Click last →
OK (textbox shows `SELECTED`) → Run.
- e.g. select 231→299 to stop processing at 222.
- ⚠️ Skipped scripts may feed later ones → downstream crash. Skip from a clean boundary.

### 8.4 CPU file — `USER.CPU` (parallel job cap)

BPE → **Edit CPU File** → USER.CPU → set **Maxj** = number of **physical cores**.
- Course (Windows, single CPU) treats Maxj as jobs-per-CPU.
- **Linux same idea.** Match physical cores, NOT hyperthreads (BPE = FPU-bound Fortran).
  - **T420 (training): Maxj = 2** (2 physical cores / 4 threads).
  - **R740 (production): Maxj = 24** (24 cores / 48 threads) — see `bernese_orchestrator_r740_gaps.md`.
- `V_CLU` (PCF) sets files-per-cluster; size ≈ `ceil(N_stations / Maxj)`.

### 8.5 Reset CPU file (when BPE hangs)

If you killed the BPE / it waits indefinitely / machine crashed: BPE → **Reset CPU File** → USER.CPU →
OK, then retry. Clears stale job locks.

---

## Module 9 — Forming Baselines (SNGDIF) — EXECUTION

("Baseline Theory" title is misleading — this is hands-on.) Creates single-difference baselines
from zero-difference obs. Needs CODSPP clock offsets (Module 7) in place.

### 9.1 PCF rows — append at end

```
301  INIT_BSL  NO_OPT    CPU=ANY; WAIT=299
302  SNGDIF    PGN_GEN   CPU=ANY; WAIT=301
303  SNGDIF    PGN_GE2   CPU=ANY; WAIT=302
```
- `301 INIT_BSL` = deletes prior baseline files (no input panel). `302` = **phase** baselines,
  `303` = **code** baselines (same baselines as phase, by design).

### 9.2 SNGDIF PID 302 (phase) panels

| Panel | Field | Value |
|---|---|---|
| SNGDIF 1 | Measurement type | **PHASE** |
| | Processing strategy | **OBS-MAX** (auto-selects best independent baseline set) |
| | Zero-diff obs files | `????$S+0` (PZH) |
| SNGDIF 2 | Station coordinates | `$(APR)_$YYYSS+0` |
| | Cluster definition | `$(CRDINF)` |
| | Result file | `BSL_$YYYSS+0` (list of baselines formed — worth checking after run) |
| SNGDIF 3.1 | OBS-MAX options | defaults (use DEFINED strategy only if you want full manual control) |

### 9.3 SNGDIF PID 303 (code) panels — same as 302 except

- Measurement type = **CODE**
- Zero-diff obs files = `????$S+0` (CZH)
- SNGDIF 2: introduce the phase baselines `BSL_$YYYSS+0.BSL` as **Predefined baselines**
  (guarantees identical code+phase baselines)
- SNGDIF 2: both Result Files fields **blank**

Run, then check `OUT/BSL_<yyyy><ddd>0` to see which baselines Bernese formed.

---

## Module 10 — Phase Pre-Processing (MAUPRP) — EXECUTION

Screens phase obs for cycle slips, repairs where possible, else marks outlier + new ambiguity.

### 10.1 PCF rows — append at end

```
311  MAUPRPAP  PGN_GEN   CPU=ANY; WAIT=302
312  MAUPRP_P  PGN_GEN   CPU=ANY; WAIT=311; PARALLEL=311
313  MPRXTR    PGN_GEN   CPU=ANY; WAIT=312
```
Note `311` waits on **302** (phase baselines), not 303. `312` carries `PARALLEL=311`.

### 10.2 MAUPRP PID 312 panels (mostly AIUB defaults — verify)

| Panel | Field | Value |
|---|---|---|
| MAUPRP 1 | Zero/single-diff | `????$S+0` (PSH) |
| | Apriori coords | `$(APR)_$YYYSS+0` |
| | Orbits / Pole | `$(ORB)_$YYYSS+0` |
| MAUPRP 2 | Coordinate results | *blank* (apriori already good) |
| | Residual file | `MPR_$(CLUSTER)` |
| | Program output | `MPR_$(CLUSTER)` |
| MAUPRP 3 | Screening mode | **AUTO** |
| | Max baseline for BOTH mode | **20 km** (switch to L3-combined above this) |
| | Troposphere | **GPT3** |
| MAUPRP 4 | Elevation mask | **3°** |
| | Min interval for continuous obs | **301** s (10 epochs @30s) |
| | Max gap within continuous | **61** s (2× sampling) |
| MAUPRP 5 | Max time for poly fit | **2** min |
| | Original obs from file | **Unticked** |
| | Difference between satellites | **Ticked** |
| | Polynomial degree | **1** |
| | Discontinuity level | **0.01** |
| MAUPRP 6 | Frequency | **L3** (ionosphere-free) |
| | Max acceptable residual | **0.5 m**; constrain apriori; no kinematic |
| MAUPRP 8 | Min cycle slip correction | 10; Sigma L1/L2 0.002; search L1=5, L5=2 (defaults) |
| MAUPRP 9 | Mark consecutive outliers | 181 s |
| | If no slip correction → new ambiguity | **Ticked** |
| | After gap > | 181 s → new ambiguity |

(MAUPRP 7 is auto-skipped — kinematic only.) `313 MPRXTR` = extraction; defaults fine.

### 10.3 Run + verify

Run: BPE → Start BPE Process → Next → **Start with script = PID 311** (skip re-import) → Run.
⚠️ If it's been a while since the last run, start from the beginning instead.

Verify `OUT/MPR_<yyyy><ddd>0.SUM` (MPRXTR summary, per baseline):
- **OK?** column = `OK` per baseline (success)
- **#SL** = repaired cycle slips, **#DL** = deleted obs, **#MA** = new ambiguities, **RMS** = triple-diff RMS
- High #DL / #MA or missing OK → problem baseline, investigate that station pair.

```bash
ls -lt ~/GPSDATA/CAMPAIGN54/PAGENET/OUT/MPR_*.SUM | head
```

---

## Module 11 — Float Solution (GPSEST + ADDNEQ2) — EXECUTION

Cluster-based ionosphere-free float solution → apriori tropo + updated coords. Iterative residual
screening (GPSEDT loop screens at 400/40/4/0.4/0.04/0.004 m, 7 GPSEST passes).

### 11.1 PCF rows + new vars + new OPT dir
```
321  GPSEDTAP  PGN_EDT   CPU=ANY; WAIT=313; PARAM2=V_FLT
322  GPSEDT_P  PGN_EDT   CPU=ANY; WAIT=321; PARALLEL=321
323  GPSXTR    PGN_EDT   CPU=ANY; WAIT=322
331  RES_SUM   PGN_GEN   CPU=ANY; WAIT=322; NEXTJOB=301
341  ADDNEQ2   PGN_GEN   CPU=ANY; WAIT=331
342  GPSXTR    PGN_GEN   CPU=ANY; WAIT=341
399  DUMMY     NO_OPT    CPU=ANY; WAIT=303 323 342
```
New vars: `V_FLT=FLT`, `V_SAMPL=180`, `V_CLUEDT=5`. New OPT dir **`PGN_EDT`** must exist.
`PARAM2=V_FLT` passes the file-cluster prefix; `NEXTJOB=301` loops back to INIT_BSL if RES_SUM/RESCHK finds a bad station.

### 11.2 Key GPSEST settings (12 panels; verify, mostly defaults)
- 1.1: phase `????$S+0`, coords `$(FLT)_$YYYSS+0`, orbits/ERP `$(ORB)_$YYYSS+0`, iono `$(HOIFIL)`
- 2.1: NEQ output `$(FLT)_$(CLUSTER)`; 2.2: residuals `ED$(FL)_$(CLUSTER)`
- 3.1: **L3**, sampling `$(SAMPL)`, elev cutoff **3°**, sigma 0.001 m, residuals NORMALIZED, corr BASELINE
- 3.2: tropo **DRY_GPT3**, ambiguity resolution **NONE** (float only)
- 4: datum **Coordinates Constrained, ALL stations, 0.1 m**
- 5.1: coords/tropo pre-elim **NO**, ambiguities **PRIOR TO NEQ SAVING**
- 6.1.1: mapping **WET_GMF3** 2h spacing, gradients **CHEN-HERRING** 24h, rel sigma 5 m
- RESRMS 2: L3, 30 s sampling, min interval 361 s; ADDNEQ2 3.1: max params **1000**, sigma 0.001 m, compare NO; ADDNEQ2 5: **Minimum constraint**

Verify: `STA/FLT_<yyyy><ddd>0.CRD` (W=weighted IGS, A=adjusted PAGENET), `OUT/FLT_*.OUT`, `ATM/FLT_*.TRP/.TRO`.

---

## Module 12 — Ambiguity Resolution — EXECUTION

5-stage baseline-length AR scheme (re-init → Melbourne-Wübbena → WL/NL → QIF → direct L1/L2).

### 12.1 PCF rows (11) + new vars + 4 new OPT dirs
```
401  SATMRK    PGN_GEN   CPU=ANY; WAIT=399
411  GNSAMBAP  PGN_AMB   CPU=ANY; WAIT=401
412  GNSAMB_P  PGN_AMB   CPU=ANY; WAIT=411; PARALLEL=411
421  GNSL53AP  PGN_L53   CPU=ANY; WAIT=412
422  GNSL53_P  PGN_L53   CPU=ANY; WAIT=421; PARALLEL=421
431  GNSQIFAP  PGN_QIF   CPU=ANY; WAIT=422
432  GNSQIF_P  PGN_QIF   CPU=ANY; WAIT=431; PARALLEL=431
441  GNSL12AP  PGN_L12   CPU=ANY; WAIT=432
442  GNSL12_P  PGN_L12   CPU=ANY; WAIT=441; PARALLEL=441
443  AMBXTR    PGN_AMB   CPU=ANY; WAIT=442
499  DUMMY     NO_OPT    CPU=ANY; WAIT=443
```
New vars (baseline-length caps): `V_GNSSAR=GRE`, `V_BL_AMB=6000`, `V_BL_QIF=2000`, `V_BL_L53=200`, `V_BL_L12=20`.
New OPT dirs **`PGN_AMB`, `PGN_L53`, `PGN_QIF`, `PGN_L12`** must exist. SATMRK 401 = INITIALIZE all ambiguities, ALL GNSS, on `????$S+0` PSH. Panels mostly programmatic — verify SATMRK 401 + BASLST defaults.

---

## Module 13 — Final (Fixed) Network Solution — EXECUTION

Like Module 11 but ambiguity-fixed: `Introduce L1 and L2 ambiguities` TICKED, datum = minimum-constraint.

### 13.1 PCF rows + new vars + new OPT dir
```
501  GPSCLUAP  PGN_FIN   CPU=ANY; WAIT=499; PARAM2=V_FIN
502  GPSCLU_P  PGN_FIN   CPU=ANY; WAIT=501; PARALLEL=501
511  ADDNEQ2   PGN_FIN   CPU=ANY; WAIT=502
512  GPSXTR    PGN_FIN   CPU=ANY; WAIT=511
```
New vars: `V_FIN=FIN`, `V_CLUFIN=A`. New OPT dir **`PGN_FIN`**.
- GPSEST 3.2: ambiguity res **NONE**, **Introduce L1/L2 ambiguities TICKED** (critical — already fixed in M12)
- GPSEST 5.1: ambiguities pre-elim **AS SOON AS POSSIBLE**; tropo spacing 1h ZPD / 24h gradient
- ADDNEQ2 5: **Minimum constraint**, **FROM_FILE → `REF_$YYYSS+0.FIX`**, translation only, sigma 0.001 m

Verify: **`STA/FIN_<yyyy><ddd>0.CRD`** (final coords!), `OUT/FIN_*.OUT/.SUM`, `ATM/FIN_*.TRP/.TRO`.

---

## Module 14 — Coordinate Verification (COMPARF + HELMCHK) — EXECUTION

Repeatability (7-day sliding window) + Helmert fit onto IGS sites.

### 14.1 PCF rows + new vars + new OPT dir
```
513  HELMCHK   SOB_FIN   CPU=ANY; WAIT=511; NEXTJOB=511
514  COMPARF   SOB_FIN   CPU=ANY; WAIT=513
599  DUMMY     NO_OPT    CPU=ANY; WAIT=512 514
```
New vars: `V_MINUS=-6`, `V_PLUS=+0` (COMPAR window). OPT dir **`SOB_FIN`**. `NEXTJOB=511` → if HELMCHK finds a >10 mm outlier, delete station, loop to ADDNEQ2.
- COMPAR 1: coords `$(FIN)_$YYYSS~~` (**`~~` = sliding window, tolerates missing days**, unlike `+-`); COMPAR 2: weekly summary `CMP_$YYYSS+0`
- HELMR1 1: first `$(APR)_$YYYSS+0`, second `$(FIN)_$YYYSS+0`, ref `REF_$YYYSS+0.FIX`; HELMR1 2: NEU, shifts 1/2/3 only; HELMR1 3: outlier reject ON, **10 mm**

Verify `OUT/HLM_<yyyy><ddd>0.OUT` — residuals (I/W=IGS, R/A=PAGENET), dX/dY/dZ + sigmas. (COMPAR gives nothing meaningful until multi-day data exists — no error thanks to `~~`.)

---

## Module 15 — Combined Solutions (ADD_WK + ADD_MON) — EXECUTION

Weekly (7-session) + monthly (30-session) ADDNEQ2 stacks. Only meaningful once multiple days processed.

### 15.1 PCF rows + new vars
```
530  ADD_WK    PGN_WK    CPU=ANY; WAIT=514
531  ADD_MON   PGN_MO    CPU=ANY; WAIT=514
```
New vars: `V_WK=WK_`, `V_MO=MO_`. ⚠️ **OPT dir name disagrees between course table (`PGN_WK`/`PGN_MO`) and screenshot (`SOB_WK`/`SOB_MO`) — verify which exists in `$U/OPT/` and use that.**
- ADD_WK: NEQ `$(FIN)_$YYYSS~~.NQ0`; ADDNEQ2 3.1 max params **20000**, compare **YES**; 4.1 coords pre-elim NO; 5 min-constraint FROM_FILE `REF_$YYYSS+0.FIX`; 7 outlier N/E/U 15/15/30 mm resid, 10/10/20 mm RMS
- ADD_MON: same, NEQ `$(FIN)_$YYYSS~~.NQ0`, outputs `$(MO)_$M-1`

---

## Module 16 — Processing Report + Save/Cleanup — EXECUTION

Size-reduced NEQ, processing report, save to SAVEDISK, delete clutter, clean BPE/.

### 16.1 PCF rows (insert + modify 599) + new vars + new OPT dir
```
521  ADDNEQ2   PGN_RED   CPU=ANY; WAIT=511
522  GPSXTR    PGN_RED   CPU=ANY; WAIT=521
599  DUMMY     NO_OPT    CPU=ANY; WAIT=512 514 522 530 531   ← MODIFY existing 599
901  R2S_SUM   NO_OPT    CPU=ANY; WAIT=599
902  R2S_SAV   NO_OPT    CPU=ANY; WAIT=901
903  R2S_DEL   NO_OPT    CPU=ANY; WAIT=902
991  BPE_CLN   NO_OPT    CPU=ANY; WAIT=903
999  DUMMY     NO_OPT    CPU=ANY; WAIT=991
```
New vars: `V_RESULT=${S}/SOB/$Y+0`, `V_SAV=Y`, `V_SAVOBS=Y`, `V_RED=RED`, `V_DEL=Y`. OPT dir **`PGN_RED`**.
⚠️ `V_DEL=Y` + `R2S_DEL` **delete** campaign result files; `BPE_CLN` wipes `BPE/`. Confirm SAVEDISK path before running for real.
Verify: `OUT/R2S_<yyyy><ddd>0.PRC` — the consolidated processing report (RNXGRA + CODSPP + MAUPRP + HELMR1 etc.). First place to look for issues.

---

## Module 17 — Creating Campaign Files (PGN.*) — SETUP (one-time, not PCF)

How the campaign reference files are built. **Not a PCF/processing step** — done once per network via menu tools. **For PAGENET these already exist** (`$D/REF54/PGN.{STA,CRD,ABB,ATL,PLD,VEL,CLU,BLQ}` — verified present). Reference only; redo when building a new network.

| File | How (menu) | Notes |
|---|---|---|
| `PGN.STA` | Service → Station Info Files → Extract from RINEX (RNX2STA) | radome + marker-number ON |
| `PGN.CRD` + `PGN.ABB` | RINEX → Import to Bernese → Observation Files (RXOBV3), Update coords=PGN | from RAW + PGN.STA |
| `PGN.ATL` | Service → Coordinate Tools → Extract atmospheric tidal loading (GRDS1S2) | from PGN.CRD |
| `PGN.PLD` | Campaign → Edit Station Files → Tectonic Plate Assignment (EDITPLD) | manual: assign plate (PHIL/EURA…) per station |
| `PGN.VEL` | Service → Coordinate Tools → Compute NUVEL Velocities (NUVELO) | needs PLD; model NUVEL1A |
| `PGN.CLU` | Campaign → Edit Station Files → Cluster Definition (EDITCLU) | auto cluster 1 if <100 files |
| `PGN.BLQ` | **External**: barre.oso.chalmers.se/loading (FES2004), then splice into an EXAMPLE.BLQ header | only file made outside Bernese |

---

## ⚠️ Cross-cutting prerequisite — OPT directories

Modules 11–16 reference **new OPT dirs** that must exist in `$U/OPT/` (copies of the AIUB
R2S equivalents): `PGN_EDT`, `PGN_AMB`, `PGN_L53`, `PGN_QIF`, `PGN_L12`, `PGN_FIN`, `SOB_FIN`,
`PGN_WK`/`SOB_WK`, `PGN_MO`/`SOB_MO`, `PGN_RED`. If a run dies immediately at one of these PIDs with a
missing-INP/dir error, the OPT dir wasn't created. Check + create before the run:
```bash
for d in PGN_EDT PGN_AMB PGN_L53 PGN_QIF PGN_L12 PGN_FIN SOB_FIN PGN_WK PGN_MO SOB_WK SOB_MO PGN_RED; do
  [ -d ~/GPSUSER/OPT/$d ] && echo "OK $d" || echo "MISS $d"
done
```
Course tables and screenshots disagree on some names (PGN_* vs SOB_*) — trust whichever dir actually exists.

---

## Module → todo verdict

| Module | Type | PCF rows | New OPT dir | Todo? |
|---|---|---|---|---|
| 7 CODSPP | execution | 231–299 | — | ✅ |
| 8 More BPE | **theory** | none | — | ❌ skim |
| 9 SNGDIF | execution | 301–303 | — | ✅ |
| 10 MAUPRP | execution | 311–313 | — | ✅ |
| 11 Float (GPSEST) | execution | 321–399 | PGN_EDT | ✅ |
| 12 Ambiguity res | execution | 401–499 | PGN_AMB/L53/QIF/L12 | ✅ |
| 13 Fixed solution | execution | 501–512 | PGN_FIN | ✅ |
| 14 Coord verify | execution | 513–599 | SOB_FIN | ✅ |
| 15 Combined wk/mo | execution | 530–531 | PGN_WK/MO (verify) | ✅ |
| 16 Report/cleanup | execution | 521/522 + 901–999 | PGN_RED | ✅ |
| 17 Campaign files | **setup (one-time)** | none | — | ✅ (already done) |

---

## Quick reference — full PAGENET.PCF after Module 16

```
001 R2S_COP  002 ATX2PCV  003 COOVEL  004 COOVEL  005 CRDMERGE      (Mod 4)
011 RNX_COP  099 DUMMY                                               (Mod 6 insert)
101 POLUPD   111 ORBMRG   112 ORBGEN  113 SATCLK  199 DUMMY          (Mod 5)
201 RNXGRA   211 RNXSMTAP 212 RNXSMT_P 221 RXOBV3AP 222 RXOBV3_P     (Mod 6)
231 CODSPPAP 232 CODSPP_P 233 CODXTR  299 DUMMY                      (Mod 7)
301 INIT_BSL 302 SNGDIF   303 SNGDIF                                 (Mod 9)
311 MAUPRPAP 312 MAUPRP_P 313 MPRXTR                                 (Mod 10)
321 GPSEDTAP 322 GPSEDT_P 323 GPSXTR 331 RES_SUM 341 ADDNEQ2 342 GPSXTR 399 DUMMY  (Mod 11)
401 SATMRK   411 GNSAMBAP 412 GNSAMB_P 421 GNSL53AP 422 GNSL53_P
            431 GNSQIFAP 432 GNSQIF_P 441 GNSL12AP 442 GNSL12_P 443 AMBXTR 499 DUMMY  (Mod 12)
521 ADDNEQ2  522 GPSXTR                                              (Mod 16 reduced NEQ)
501 GPSCLUAP 502 GPSCLU_P 511 ADDNEQ2 512 GPSXTR                     (Mod 13)
513 HELMCHK  514 COMPARF                                             (Mod 14)
530 ADD_WK   531 ADD_MON                                             (Mod 15)
599 DUMMY    901 R2S_SUM  902 R2S_SAV 903 R2S_DEL 991 BPE_CLN 999 DUMMY  (Mod 16 report/cleanup)
```
(PID order in the file follows the 500/900 numbering; WAIT/NEXTJOB define actual execution order.)

Day-1 status (2026-06-24): **Module 6 BPE ran OK in 20 min** (rows ≤222). Modules 7→16 still to add.

Monitoring during runs: see `bernese_monitoring_cheatsheet.md`
(`BPE/RUNBPE.OUT` flags the failing `<PID>_<sub>`; open its `.LOG` for the error).
Quality-gate benchmarks: HELMCHK <1 cm (M14), ambiguity fixing ~80% (M12), COMPARF repeatability (M14/15).
