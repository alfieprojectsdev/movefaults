# What the GEONET research changes in `services/bernese-workflow`

**Date:** 2026-08-20
**Source:** `geonet_bernese_strategy_research.md` (verified brief) and the
co-authored SATREPS papers surfaced with it.
**Companion:** `bernese_orchestrator_r740_readiness.md` (tasks A–L),
`bernese_orchestrator_r740_gaps` [MEM].

This is the engineering half of the research. Every item below is tied to a
specific file or panel, and marked with whether it needs the R740.

---

## 0. The one conceptual correction

**`v_clu` / `v_clufin` are *compute* clustering. GEONET's clusters are *network
architecture*. These are different axes and the codebase currently only has the
first.**

`pcf_context.py` carries:

```python
v_clu: str = "10"      # files per parallel processing cluster
v_clufin: str = "A"    # final-solution clustering mode in GPSCLU
```

with a comment noting `"A"` produced "ONE giant single-core solve on the full
network", and readiness task K is to tune it against `USER.CPU` maxjobs. That is
correct and remains the biggest R740 performance lever
(`bernese_orchestrator_r740_readiness.md` §2.4: *"Without it, 270 stations/day
is infeasible"*).

What GEONET adds is a **second, independent** question that no amount of
`V_CLU` tuning answers: *which stations anchor which sub-network, and how do
sub-network solutions recombine into one national set?* GSI's answer at ~1,300
stations was a **backbone cluster + regional clusters** with basic/additional
station roles, and F5 later added **global network processing** alongside the
domestic solution.

**Action:** treat these as two tracked concerns, not one. Tuning `V_CLUFIN` is
a performance task. Designing a backbone/regional station hierarchy is a
*datum and network-design* task that changes what the solution means, and it is
not yet on any list. Neither blocks the other.

**Precedent already exists in Philippine work.** [Ohkura et al. 2015] processed
PHIVOLCS campaign data hierarchically: PIMO tightly constrained → **NMMB**
chosen as the Mindanao reference *because it had the longest observation period*
→ further site pairs chained by observation overlap. That is a backbone/regional
architecture in miniature, on our own data, with a stated selection rule.

---

## 1. Do now — no R740 required

### 1.1 Make the fiducial set part of the provenance record
**Files:** `campaign_builder.py`, `orchestrator.py`; see
`provenance_record_design.md`.

`ADDNEQ2.INP` resolves its datum from `FREESTA_F = ${P}/PHIVOLCS\STA\REF190110.FIX`
[REPO]. That file is **not in this repository**, and the project's own records
disagree about its contents — a 12-station list in `session_log_20260226.md`, a
nine-station set in `T420_REPLY_20260805b.md`, and one run logging "6 fiducials
accepted" in `session_log_20260626.md`.

A solution's datum is the least reproducible thing about it, and right now the
run does not record which fiducials defined it.

**Change:** at campaign build, read the resolved `.FIX` file, and record into
the provenance record: the filename, its content hash, and the station list it
contained. Fail loudly if it cannot be resolved rather than letting BPE fall
back silently.

> Bonus, already known: that path contains a Windows separator
> (`PHIVOLCS\STA\`), the same class `panel_sanitizer.py` exists to fix. Worth
> confirming the sanitizer covers `FREESTA_F`, not only the paths in gap #8.

### 1.2 Resolve the mapping-function inconsistency

> **SETTLED 2026-08-24 — measured, not argued. It does not matter.**
>
> Reprocessing 2025 DOY 121 with the three ambiguity panels set to `WET_GMF3`
> gives a **bit-identical** solution: the whole SINEX diff is four run-timestamp
> lines. The intermediate QIF output is identical too.
>
> The reason is that those panels do not estimate a troposphere — they
> *introduce* one from the float solution's `.TRP` and estimate only clock
> parameters. With no zenith delay estimated, `MAPPNG` has nothing to act on.
> It is a dead field there. The final panel, by contrast, estimates 870
> site-specific troposphere parameters, so `MAPPNG` is live there.
>
> **Close this as cosmetic** — and record it as *"the field is inert"*, not as
> *"GMF3 was chosen"*, or a later reader will infer an evaluation that never
> happened. Full evidence: `geo002_mapping_function_result.md`.



> **Correction, 2026-08-24 — the table below is measured from the wrong tree.**
>
> The panels quoted here come from `config/bernese/gpsuser52-luzon/OPT`, which
> is PHIVOLCS' **5.2** set. The live 5.4 tree the R740 actually runs
> (`/home/gps3/GPSUSER/OPT`) differs on the two panels that matter:
>
> | panel | doc / declared | **live 5.4** |
> |---|---|---|
> | R2S_EDT (float) | `WET_GMF` | **`WET_GMF3`** |
> | R2S_FIN (final) | `WET_GMF` | **`WET_GMF3`** |
>
> `WET_GMF` and `WET_GMF3` are both valid 5.4 cards and are different
> functions — GMF is the 2006 Global Mapping Function, GMF3 its GPT3/VMF3-era
> gridded successor. **Every LUZON solution produced on the R740 used GMF3**,
> the 30-day 2026-08-06 run included.
>
> GEO-003's drift test (`test_pcf_context.py`) compares the declared table
> against the same 5.2 files the table was read from, so it could not have
> caught this and never fired. A guard pointed at the wrong tree reads exactly
> like a guard.
>
> This does not change §1.2's conclusion — the ambiguity panels still disagree
> with the float/final panels, which is the point. It changes what "make them
> agree" means: the target is **`WET_GMF3`**, not `WET_GMF`. Being measured by
> `scripts/run_gmf_comparison.sh`.


**Files:** `config/bernese/gpsuser52-luzon/OPT/*/GPSEST.INP`

Measured across the panels [REPO]:

| Panel | `MAPPNG` | `NUMPAR` | `NUMGRD` |
|---|---|---|---|
| R2S_EDT (float) | `WET_GMF` | 02:00:00 | 24:00:00 |
| **R2S_FIN (final)** | `WET_GMF` | **01:00:00** | 24:00:00 |
| R2S_QIF / L53 / L12 | `WET_NIELL` | 02:00:00 | 24:00:00 |
| R2S_AMB (MW) | `COSZ` | 02:00:00 | — |

`COSZ` for Melbourne-Wübbena is unremarkable. The **`WET_GMF` vs `WET_NIELL`
split** between the final/float steps and the three ambiguity-resolution steps
looks unintentional — project memory records GMF as the PHIVOLCS standard, which
the ambiguity panels do not follow.

**Change:** decide deliberately, then make the panels agree — and once decided,
template it (§1.3) so it cannot drift again.

**Do NOT shorten the troposphere interval.** F5 reports that shortening drove
its accuracy gain, but POGF's final solve is **already hourly**, shorter than
the 3-hourly interval GSI used on PHIVOLCS' own Mindanao data [TOB15]. The
research says POGF is already on the right side of that finding. An earlier
draft of the brief recommended shortening; it was wrong.

### 1.3 Template the troposphere block in `PCFContext`
**File:** `pcf_context.py`

`PCFContext` templates the reference frame, sampling, HOI file, constellation
and clustering — but **not** the mapping function or parameter spacing, so those
live only as literals in six panel files and drift independently (§1.2 is the
evidence that they already have).

**Change:** add `v_mappng`, `v_numpar`, `v_numgrd` (or the panel-templating
equivalent), defaulting to the current values so the change is inert until
someone chooses otherwise. This is what makes an F5-style comparison a config
change instead of a hand-edit across six files. `WET_VMF` / `DRY_VMF` are
already available as `MAPPNG` cards, so no software change is needed to try VMF.

### 1.4 HELMCHK residual → provisional-solution gate
**New file:** `helmchk_qc.py`, mirroring the existing `codspp_qc.py`

`bernese_bpe_phases` [MEM] already identifies PID 513 HELMCHK as "a secondary
seismic sensor — if a reference station fails Helmert, it may indicate it moved"
and says the orchestrator "should flag this for human review". Nothing
implements that.

GSI's practice gives the missing half: a **stated threshold** triggering a
deliberate freeze, not an automatic recompute. Their criterion was 2 ppm
estimated strain, suspending survey data for 438 control stations until a
revised datum was published.

**Change:** parse HELMCHK residuals; above a configured threshold, mark the
session's solution **provisional** in the provenance record and refuse to feed
it to velocity estimation until a human clears it. `codspp_qc.py` is the pattern
to follow — same shape, different extractor.

This is the code half of the governance procedure the brief recommends
adopting; the threshold value itself is a PHIVOLCS decision, not an engineering
one.

### 1.5 Record coseismic offsets as first-class run inputs
**Files:** `campaign_models.py`, `campaign_builder.py`

[TOB15] removed the 2013 Bohol (Mw 7.1, 15 Oct 2013) coseismic offsets before
fitting velocities — manually, as a processing step outside the daily chain.
POGF has an event catalog at `docs/bern52/phivolcs-scripts/event-catalog/offsets`
and `velocity_pipeline` [MEM] notes the offsets file must be applied before
`vel_line_v8.m`.

**Change:** make the offset catalog an explicit, versioned input to a campaign —
recorded in provenance with its hash — rather than a file someone remembers to
apply downstream. Same argument as §1.1: the correction applied is part of what
the numbers mean.

---

## 2. Needs the R740 — which is available now

> **BRN-001 is DONE** (2026-07-29): Bernese 5.4 verified on the R740, and LUZON
> reprocessed 30/30 days unattended on 2026-08-06 at 5m33s/day. Nothing below is
> gated on hardware; it is gated on someone doing it. An earlier draft of this
> document and of the research brief both repeated a stale memory that BRN-001
> was still open.

### 2.1 Finish readiness task K with the right mental model — **actionable now**
Tune `V_CLUFIN` / `V_CLU` against `USER.CPU` maxjobs (`cpu_config.py`). Unchanged
by this research except for §0's warning: this is a **performance** fix. If
270 stations/day still does not fit after tuning, the next lever is
architectural (§2.2), not another knob.

**There is now a baseline to measure against:** the 2026-08-06 LUZON run,
30/30 days in 2h47m, 5m33s/day. Any clustering change can be scored against that
number rather than against an impression. `bernese_orchestrator_r740_readiness.md`
§2.4 measured ~40 min of a ~2 h daily run inside PID 502 alone on the T420 — the
equivalent measurement on the R740 is the first thing to take.

### 2.2 Evaluate a backbone/regional network architecture
Only worth designing once there is a machine to measure it on. Inputs: GEONET's
backbone/regional model, Ohkura's PIMO→NMMB→overlap-chained precedent, and
whatever GSI answers about cluster sizing and recombination (enquiry Q1).

### 2.3 A rapid tier
GEONET's Q3/R3 exist to give a number before the accurate one is ready. POGF has
no consumer for that yet. Revisit only if one appears — and after the
F3-equivalent tier is reliably automated.

---

## 3. Not `bernese-workflow` — but downstream of it

**Semi-dynamic datum correction model.** The highest-value idea in the research
(brief §4.3). It is a *product* built on the velocity output, not a change to
the processing chain — closer to `pogf-geodetic-suite/timeseries` than to this
service. Scope separately once the routine pipeline is stable.

---

## 4. Summary

| # | Change | File(s) | R740? |
|---|---|---|---|
| 1.1 | Fiducial `.FIX` set into provenance (hash + station list) | `campaign_builder.py`, `orchestrator.py` | No |
| 1.2 | Resolve `WET_GMF` / `WET_NIELL` panel inconsistency | `OPT/*/GPSEST.INP` | No |
| 1.3 | Template troposphere block (`MAPPNG`, `NUMPAR`, `NUMGRD`) | `pcf_context.py` | No |
| 1.4 | HELMCHK residual → provisional-solution gate | new `helmchk_qc.py` | No |
| 1.5 | Offset catalog as versioned campaign input | `campaign_models.py`, `campaign_builder.py` | No |
| 2.1 | `V_CLUFIN`/`V_CLU` tuning (readiness task K) | `pcf_context.py`, `cpu_config.py` | R740 **available** |
| 2.2 | Backbone/regional network architecture | design task | R740 available |
| 2.3 | Rapid tier | — | On demand only |

**Explicitly not doing:** shortening the troposphere interval (already shorter
than the Philippine precedent), and adopting GEONET's single-fixed-station datum
(POGF's multi-station minimum constraint is the stronger design).
