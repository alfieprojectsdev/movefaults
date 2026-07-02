# Bernese Orchestrator — R740 Deployment Readiness Evaluation

**Date:** 2026-06-26 (post NAMRIA training week)
**Scope:** Consolidate empirical findings from a full hands-on PAGENET processing week on the
T420, and evaluate what must improve in `services/bernese-workflow` before BRN-001 (R740
production deployment in the PHIVOLCS MIS server room).
**Companion memory:** `bernese_orchestrator_r740_gaps` (gaps 1-11 + CPU tuning),
`bernese_orchestrator_design`, `bernese_workflow_status`, `gfzrnx_teqc_decision`.

---

## 1. Readiness verdict

**Engine: proven. Orchestrator: not yet R740-ready.** This week we ran the *entire* RNX2SNX
pipeline (Modules 1-14) headless, unattended, across 3 daily sessions — so the **execution
contract is validated end-to-end**. What's missing is the orchestrator's *robustness layer*:
pre-flight validation, panel sanitization, per-station QC auto-recovery, and multi-core
performance tuning. Every failure we hit this week was a **silent-data or config-portability
problem the orchestrator does not yet guard against** — and on R740's ~270-station network, each
would be worse, not better.

**Bottom line:** the happy path works. R740 deployment readiness = closing the un-happy paths,
which the training week mapped out concretely.

---

## 2. What the week empirically validated (new evidence)

### 2.1 The headless contract works (confirms gap #3 fix is correct)
`pagenet_pcs.pl` = the stock `rnx2snx_pcs.pl` with `PCF_FILE` + `BPE_CAMPAIGN` parameterized.
It drove 084/085/086 fully unattended via `setsid` + an idempotent runner
(`scripts/run_pagenet_week.sh`). **This is the orchestrator's subprocess contract, proven on real
data.** The runner's design (skip-if-output-exists, single-instance lock, halt-on-error with
diagnostics) is the blueprint for the orchestrator's per-session job scheduler.

### 2.2 RXOBV3 hard-aborts on any RINEX station missing from the station-info file
Day 086 died at PID 222 (RXOBV3) on station **PLG2**: present in the RINEX, **absent from
`PGN.STA`** → `SR RXOSTA: RINEX station name not listed` → fatal cluster abort. Two new lessons
beyond gap #11 (PTAG):
- This is the **loud** failure form (whole run dies), not the silent station-drop. Different
  trigger (missing record vs malformed record), same root family.
- **PLG2 is intermittent** — present only DOY 086 + 088 of the 7-day week. 084/085 passed because
  PLG2 wasn't there. **An intermittent station means the validator must run per-session, not once
  per campaign.** A campaign-level station list can't catch a station that appears mid-week.

### 2.3 Troposphere divergence (PTAG) is data-dependent, not structural
Day 084 died at PID 322 on the PIMO–PTAG 12 km baseline (unobservable differential troposphere →
zenith-delay overflow). Day 085, **same baseline, passed clean.** So the short-baseline tropo
failure is **per-day data-quality dependent** (scintillation-thinned epochs tip it over). The
orchestrator can't statically exclude the pair; it needs **per-session retry/quarantine**, not a
permanent rule.

### 2.4 The 502 GPSCLU_P final-solution single-cluster bottleneck (NEW — biggest R740 lever)
Every daily run spent **~40 min of its ~2 h in one step**: PID 502 GPSCLU_P, a single-core GPSEST
at 99% CPU solving the final clustered normal-equation system. Cause: `V_CLUFIN=A` auto-clustering
produced **one large cluster** for the whole network → one giant dense inversion, unparallelized.
On the T420's 2 cores this is unavoidable. **On the R740 this is the single highest-value tuning
win** — proper final-solution clustering + `USER.CPU` maxjobs turns the 40-min serial solve into
parallel sub-solves. Without it, 270 stations/day is infeasible.

### 2.5 PCF/panel portability bugs bite Linux specifically (extends gap #8 to panels)
The `PGN_WK/ADDNEQ2.INP` weekly-combine panel shipped with: **Windows `\` path separators**
(`${P}/SOB\SOL\…` — literal chars on Linux), a **dangling `WAIT=522`** (PID never defined →
would hang BPE), and **hardcoded foreign sessions** (`20261030/40/50` = the instructor's demo
week). Gap #8 flagged Windows paths in `SCRIPT/`; this extends it to **`OPT/*/​*.INP` panels**. Any
orchestrator that renders or copies these panels must sanitize `\`→`/`, strip dangling WAITs, and
never carry hardcoded session/campaign literals.

### 2.6 Mixed-RINEX-version reality in one campaign
The PAGENET week is **RINEX 2 (PAGENET CORS, short names `pzam0810.26d`) + RINEX 3 (IGS fiducials,
long names `CUSV00THA_R_…`) simultaneously**. Staging, station-ID extraction, and validation must
handle both schemes in the same run. Also reinforces the `gfzrnx_teqc_decision`: teqc's weak
RINEX-3 handling is a live constraint, not hypothetical.

---

## 3. Orchestrator improvement plan (prioritized for BRN-001)

### P0 — blocks any correct full-network run on R740
| # | Improvement | Evidence | Component |
|---|---|---|---|
| A | **Per-session pre-flight station validator** — every RINEX station has a `PGN.STA` entry (else RXOBV3 hard-aborts); run per session (intermittent stations); flag blank DOMES / RINEX2-3 mismatch / duplicate markers / too-short (<~15 km) baselines | 2.2 PLG2, 2.3 PTAG, gaps #11 | new `pre_flight()` stage |
| B | **MAXPAR sized from station count** in all ADDNEQ2 panels (≈ N_sta×4 + margin; ~270 sta ⇒ well above the 1000 default) | gap #10 | panel templating |
| C | **Validator targets the DATAPOOL source dir**, not pre-BPE empty `RAW/` | gap #1 | `validate_rinex_headers()` |
| D | **prepare_campaign() adds GEN/ + SESSIONS.SES** | gap #2 | `prepare_campaign()` |
| E | **Parameterize PCF_FILE / BPE_CAMPAIGN / CPU_FILE=USER** (run PAGENET, not just RNX2SNX) | gap #3, 2.1 | `backends.run()` |

### P1 — correctness/robustness on real data
| # | Improvement | Evidence | Component |
|---|---|---|---|
| F | **CODSPP-QC auto-recovery gate** — parse RMS + (NEW−APRIORI) delta; re-seed a priori & retry on bad-a-priori, alert human on bad-obs | gap #9 | per-station QC layer |
| G | **GPSEST/tropo quarantine + retry** — on PID 322 overflow, quarantine the malformed/short-baseline non-IGS partner for that session, re-pair, retry; never drop an IGS fiducial | 2.3, gap #11 | job scheduler error-handler |
| H | **Panel/script sanitizer** — `\`→`/`, strip dangling WAIT PIDs, reject hardcoded session/campaign literals; gold-standard panels+scripts versioned in repo, synced to `$U`, never hand-edited | 2.5, gap #8 | config-versioning layer |
| I | **Stage + pre-flight-check GEN/CONFIG model files** (SAT_YYYY.CRX, .NUT/.SUB/mean-pole) from BSWUSER52 endpoint | gap #6 | IGS-001 / pre_flight |
| J | **Idempotent per-session job scheduler** — skip-if-FIN-exists, lock, halt-on-error-with-diagnostic, resumable (the `run_pagenet_week.sh` pattern, productized) | 2.1, 2.2 | orchestrator core |

### P2 — performance + scope
| # | Improvement | Evidence | Component |
|---|---|---|---|
| K | **Final-solution clustering tuning** — set `V_CLUFIN`/`V_CLU` so GPSCLU splits the final solve across cores instead of one giant cluster; size against `USER.CPU` maxjobs | 2.4 | panel templating + CPU config |
| L | **USER.CPU maxjobs = R740 physical cores** (not threads; FPU-bound), RAM-ceiling-aware | gaps CPU-tuning | BRN-001 install |
| M | **Module 15/16 scope decision** — PHIVOLCS velocity uses MATLAB regression on daily ENU, NOT NEQ stacking, so weekly ADD_WK/monthly ADD_MON may be **out of scope** for production; confirm before building the SOB-accumulation + V_RESULT plumbing | velocity_pipeline, 2.x | scope gate |
| N | **Mixed RINEX 2/3 staging + ID extraction** in ingestion | 2.6 | ingestion-pipeline |

---

## 4. R740-specific deployment deltas (vs the T420 baseline)

- **Install is EASIER than T420.** R740 is a clean Ubuntu 24.04 server, no GCC-15 PPA conflict →
  apt `gfortran-13/14` works; **no x86-64 ISA objcopy patch** if the CPU is Haswell-or-newer
  (verify with `lscpu` — note the gaps memory flags uncertainty: R740 is often Skylake/Cascade-Lake,
  which is fine, but confirm the ISA level on the actual box). Only the 2 Qt symlinks + DATAPOOL ref
  symlinks + DE421/CRX2RNX steps remain. See `bernese_install` R740 plan.
- **Performance is the inverse story.** T420 (2 cores) made the 502 bottleneck invisible-but-tolerable
  at ~2 h/day for ~54 stations. R740 (24 physical cores per the gaps memory — **confirm with
  `lscpu`**) only pays off if clustering + maxjobs are tuned (P2-K/L). Untuned, R740 would run the
  same single-core 502 solve, just on a bigger network = far worse. **The multi-core win is a config
  task, not a free hardware win.**
- **Disk is the real R740 constraint** (DL-012): ~270 stations × daily campaigns × intermediate BPE
  files. Compression + retention policy needed before live — independent of orchestrator code.
- **MIS instability risk** (the reason `hardline` exists): the MIS team reconfigures the box. The
  orchestrator + its provisioned `$U` env must be **reproducible from the repo** (config-versioning,
  P1-H) so a MIS reset is recoverable by re-running provisioning, not by re-debugging by hand.

---

## 5. Phased go-live checklist

1. **Install + verify** Bernese on R740 (EXAMPLE campaign sub-mm SINEX diff) — `bernese_install` plan.
2. **Provision `$U` from repo** gold-standard PCFs/panels/scripts (P1-H) — sanitized, no Windows paths,
   no hardcoded sessions. Patch BSW_DWLD/ADD_MON per gap #8.
3. **Tune `USER.CPU` + clustering** for the R740 core count (P2-K/L) — confirm `lscpu`, RAM headroom.
4. **Wire P0 (A-E)** into the orchestrator; re-run the PAGENET week on R740 as the acceptance test
   (it must clear PLG2/PTAG/MAXPAR automatically, not by hand as we did this week).
5. **Wire P1 (F-J)** — QC gates + resumable scheduler.
6. **Decide M** (Module 15/16 scope) before building weekly/monthly plumbing.
7. **Disk policy** (DL-012) before turning on continuous 35→270-station ingestion.

---

## 6. The one-line synthesis
The training week proved the BPE runs headless and produces correct mm coordinates. Every problem
we solved **by hand** this week — missing station records, data-dependent tropo blowups, undersized
MAXPAR, Windows-path panels, single-core final solves — is a thing the **orchestrator must do
automatically** before it can be trusted unattended on R740. The readiness gap is exactly the list
of manual interventions from this week's logs.
