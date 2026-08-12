# Prep reading plan: processing the full PH network via subnetworks

**Written:** 2026-08-11, gps3. **Status as of 2026-08-12: all four tiers read,
findings recorded per tier below.** Written after the LUZON 5.4 reprocessing
exercise (see `docs/bernese54_luzon_reprocessing_runbook.md`) and after the
user asked whether the full PH network should be processed as subnetworks
combined later, rather than as one national cluster.

**Short answer to the question that prompted this: yes, subnetworks — and the
mechanism is one this pipeline already runs.** MKCLUS → GPSEST (with
`CORRECT` correlations, stopping after NEQ save) → ADDNEQ2 under minimum
constraint, with a HELMR1 reference-site verification loop. `LUZON_DLY`
already does this within a single campaign; national scale applies the same
pattern at a coarser, independently-executed grain. No new architecture, and
no architecture *decision* outstanding — the double-vs-zero-difference
question turned out to be a false premise (Tier 3).

**Two claims in the original plan were wrong and are corrected in place**
below rather than silently edited: clustering is not what defines a
subnetwork boundary (Tier 1), and the Tier 3 comparison was between two PCFs
that do entirely different jobs.

## Why subnetworks, in one paragraph

`ADDNEQ2.HLP` (installed with this Bernese 5.4 build) lists "combination of
overlapping networks (regional with global networks)" and "combination of
baseline-, or cluster-specific NEQs into a network solution" as core, intended
use cases — this is Bernese's own architecture, not a workaround. The
`LUZON_DLY` run already does a small version of this within one PCF
(`GPSCLU` → `GPSEST` per cluster → `ADDNEQ2` combines). Scaling to the
national network means the same combination at a coarser grain: independent
regional runs, combined afterward. The honest cost, from the same `.HLP`
text: cluster/regional combination "neglect[s] the inter-baseline, or
inter-cluster correlations" — a known, accepted approximation, not a free
lunch.

## Already resolved — do not re-derive

- **Station/receiver count is not a constraint.** Compiled limits in the
  installed `M_MAXDIM.f90`: `MAXSTA=3000`, `MAXREC=1000`, `MAXAMB=2000`,
  `MAXFLS=90`, `MAXSAT=170`. A full PH network (~135–425 stations) is nowhere
  near any of these except possibly `MAXFLS` ("files in a session") — not yet
  mapped to what actually counts against it per cluster; check if it becomes
  relevant, don't assume it will.
- **`MAXPAR` is a runtime allocation, not a compiled limit** — confirmed via
  `ADDNEQ2.HLP` and corrected in the session log (2026-08-11) after this
  document originally got it wrong.

## Reading plan, in the order it actually blocks work

Source: `/home/gps3/bernese-docs/DOCU52.pdf` (Bernese 5.2 manual, 858p — **not
version-matched to this 5.4 install**, cross-check anything procedural against
`.HLP` files or `README_V52V54.md`) and its `.txt` sibling for fast grep. See
`reference_bernese_manuals.md` in the memory system for how these were found.

### Tier 1 — subnetwork *partitioning* mechanics (read first)

| § | Pages | Question it answers |
|---|---|---|
| 22.12.2.1–3 | 527–529 | What panel/file actually defines "these N stations are Subnetwork A"? (Clusters of Baseline Obs Files / Regional Clusters / Global Clusters for Zero-Diff) |
| 6.4.1–6.4.2 | 140–144 | Do baselines form only within a cluster, or can they cross? Decides whether subnetwork boundaries need deliberate geographic overlap. |
| 22.12.1 | 525–527 | Mechanics for building N regional station lists from one master file without duplicated maintenance. |

### Tier 2 — how independently-run subnetworks *combine* (read second)

| § | Pages | Question it answers |
|---|---|---|
| 9.3.7 (Minimum Constraint Conditions) | 220–221 | How to configure each regional run so it produces a loosely-constrained NEQ, not an over-fixed one that breaks later combination. |
| 9.4.9 (SINEX Files) | 233–234 | Can our existing `FIN_*.SNX` output feed `SNX2NQ0` directly, or do the regional PCFs need to change what they save? |
| 9.5.1 (Cluster Combination) | 237 | Worked example for exactly this use case. |
| 10.2.2–10.2.3 | 244–256 | How regional subnetworks tie to one consistent datum. Also the most likely explanation for the S01R silent-exclusion finding (runbook §4b.9). |
| 22.12.3 | 529 | "Rejecting Stations from the Definition of the Geodetic Datum" — same S01R relevance. |

### Tier 3 — architecture choice, confirm deliberately rather than by inertia

| § | Pages | Question it answers |
|---|---|---|
| 23.4.2 vs 23.4.4 | 571–652 | `LUZON_DLY` is double-difference because that's what the 5.2 PCF it derives from used, not because anyone chose it for national scale. Compare against the Zero-Difference Network Processing Example before committing a national pipeline to the same pattern by default. |

### Tier 4 — quality/monitoring, adjacent, not blocking

| § | Pages | Question it answers |
|---|---|---|
| 11 (FODITS) | 273–293 | Not needed to get a national solution running, but needed before trusting it — §11.2.1.1 is literally titled "Earthquakes." Bernese's own purpose-built discontinuity/event detector, likely more complete than `scripts/network_coherence_scan.py`. |

## Tier 1 findings — 2026-08-11

**Read: DOCU52 §22.12.2.1–3 (pp. 527–529), §6.4.1–6.4.2 (pp. 140–144),
§22.12.1 (pp. 525–527).**

### The framing in this plan's own Tier 1 table was wrong, and worth correcting in writing

The plan asked whether "§22.12.2 clustering" and "§6.4 baseline formation"
together answer "what defines a subnetwork boundary." They don't — they
answer a narrower question than the one that matters for national scale, and
conflating them would have led to designing the wrong mechanism.

**What §22.12.2.1 actually describes is a purely computational partition
within ONE campaign, not a geographic/scientific boundary.** `SNGDIF` forms
baselines by minimizing length or maximizing common observations across the
**entire station set it is given** (§6.4.1–6.4.2) — it has no concept of
"cluster" at baseline-selection time. Cluster membership is assigned
*afterward*: "the cluster number of the **first station** in a baseline
defines to which cluster the baseline belongs." A baseline can freely connect
two stations from what a human would call different regions; it just gets
filed under whichever cluster its first station belongs to. **Clustering, at
this level, does not prevent cross-region baselines — it only determines
which GPSEST batch processes a baseline that has already been chosen.**

**The real mechanism for a hard subnetwork boundary is simpler than expected,
and it isn't a special "subnetwork" feature at all: it's just which stations
are in the campaign's observation-file set when `SNGDIF` runs.** §22.12.1
(RNXGRA preselection, RXOBV3 import-time exclusion, `TYPE 003` station
problems, MKCLUS station selection) is entirely about which files enter
processing — a station never included never gets a baseline formed to it, in
that run, at all. So: **an independent regional PCF run, given only that
region's station list, cannot form a cross-region baseline, full stop** — no
special partitioning logic needed beyond "give each regional run the right
station roster."

### The two mechanisms converge — this is the useful part

Immediately following §22.12.1, before §22.12.2 begins, the manual states the
architecture plainly: *"If a network with a lot of stations (baselines) has to
be processed not all observation files can be processed in one GPSEST run. In
that case the observation files may be grouped into clusters and processed
independently. The normal equations of the individual clusters may be
combined using the program ADDNEQ2 for most of the non-epoch parameters."*

**"Grouped into clusters and processed independently" is the same MKCLUS →
GPSEST → ADDNEQ2 pattern whether the clusters are computational batches within
one campaign (what `LUZON_DLY` already does) or genuinely independent regional
campaigns run separately, possibly on different schedules or machines.**
There is no second, different "subnetwork" mechanism to design — the national
PH network needs the same three-stage pattern LUZON already demonstrates,
applied at a coarser, independently-executed grain, using MKCLUS's *regional*
clustering options specifically (§22.12.2.1's "MKCLUS 3: Regional Cluster
Definition Options (Single Differences)" panel) rather than its default
distance-minimizing global mode.

One caveat carried forward rather than resolved: ADDNEQ2 combination is
qualified as covering "**most** of the non-epoch parameters" — epoch-wise
parameters (clock offsets per epoch, per Ch. 7.6.2/7.7.2 in the TOC) need
different handling (back-substitution) than a simple NEQ-level combine. Not
yet investigated; flagged so it isn't assumed away.

### Confirmed against our own pipeline, not just the manual

Clustering only preserves correlation information if GPSEST's "Correlation
strategy" is `CORRECT` — otherwise clustering is pure computational chunking
with zero scientific effect (§22.12.2.1, first paragraph). Checked directly:
`R2S_EDT`'s `GPSEST.INP` uses `CORREL=BASELINE`; **`R2S_FIN`'s uses
`CORREL=CORRECT`.** So the stage that actually produces `LUZON_DLY`'s daily
solution is genuinely preserving within-cluster correlations, not just
splitting work for speed. The same "neglect inter-cluster correlations"
caveat from `ADDNEQ2.HLP` applies at whatever grain clustering happens —
within one run today, between regional campaigns at national scale.

### Practical items surfaced, not yet acted on

- §22.12.1.5 confirms `V_BL_AMB`/`V_BL_QIF`/`V_BL_L53`/`V_BL_L12` (baseline-
  length thresholds per ambiguity-resolution strategy, already in
  `derive_luzon_pcf.py`) are exactly what program `BASLST` is described as
  configuring — the existing PCF's tiered-AR design matches documented
  practice, not an improvisation.
- §22.12.1.3: the recommended way to drop a misbehaving station is to delete
  its observation file **and rebuild the whole baseline set via `SNGDIF`**,
  not to just continue with the old baseline topology. Worth checking whether
  this step is actually happening correctly wherever S01R (runbook §4b.9)
  drops out silently — a network that isn't rebuilt after a station is
  removed could plausibly explain quiet, undiagnosed exclusion. Not confirmed;
  a lead for whoever picks up §4b.9 next, not a finding.
- §6.4.2: `OBS-MAX` with a short-baseline "bonus" option is the documented way
  to combine `SHORTEST`'s ambiguity-resolution benefit with `OBS-MAX`'s
  robustness for a network with regional densification — plausibly the right
  strategy for a national network with dense local clusters (Metro Manila,
  Cebu) inside a sparse national spread, rather than either pure strategy.
  Not yet checked against what `LUZON_DLY` currently uses.

## Tier 2 findings — 2026-08-11/12

**Read: DOCU52 §9.3.7 (pp. 220–222), §9.4.9 (pp. 233–236), §9.5.1 (p. 237),
§10.2.2–10.2.3 (pp. 246–251), §22.12.3 (p. 529). Cross-checked against our own
`R2S_FIN` panels and DOY 121/125/126/129/145 output, not just read.**

### The datum-definition recipe, complete and concrete

Four datum-definition types exist, ranked least to most rigid, and the manual
is explicit about which is recommended:

1. **Free network** — no datum info at all; only useful to produce NEQs whose
   datum gets defined *later* in ADDNEQ2, or for PPP with fixed clocks. Unusable
   on its own — "considerable translations for different days."
2. **Minimum constraint** — Helmert conditions on the **barycenter of an
   ensemble** of reference sites, not any single one. *"The best suited way for
   the datum definition of a network... recommended method to estimate final
   results, when the satellite orbits and EOPs are fixed."* Small errors at one
   reference site don't distort the whole network — that's the whole point.
3. **Constraining** — tunable tightness; a single-site constraint is a
   *degenerate special case* of minimum constraint, explicitly flagged as
   inferior: "an error in the position of the single reference site propagates
   into the positions of all other sites in the network."
4. **Fixing** — hardest, **not recommended**: removes the parameter from the
   NEQ entirely, freezing the datum irreversibly. Use tight constraints (e.g.
   0.01 mm) instead if a near-fixed effect is wanted.

**§9.5.1's worked recipe for exactly the subnetwork-combination case**: cluster
baselines with minimum inter-cluster overlap (to minimize the correlations
being neglected) → run each cluster in GPSEST with `CORRECT` correlations and
**"Stop program after NEQ saving"** enabled (panel `GPSEST 3.2`) so GPSEST
produces only a cluster NEQ file, not a solved result → combine via ADDNEQ2
using **minimum constraint**, not fixing → verify the reference-site set via
**`HELMR1`** (Helmert-transform comparison of estimated vs. a priori
coordinates) → exclude sites with significant deviations → **redo the
combination with the verified set**. This is an explicit loop, not a one-shot
combination.

**§22.12.3 closes the loop mechanically**: `HELMR1` can write an outlier list
directly, and the BPE can jump back to redefine the datum with the modified
station selection automatically — and *this exact quality-monitoring feature
is built into the stock `RNX2SNX.PCF`* that `derive_luzon_pcf.py` derives
`LUZON_DLY` from. We inherited this mechanism; nobody built it for this
project.

### This explains our own `HLM_*.FIX` file, and inverts what it looked like at first

Before reading this, `HLM_*.FIX` containing only `AIRA` on every day looked
like it might be a single-station-fixed datum anchor — exactly the fragile
pattern §10.2.2.3 warns against. **Checked against the actual `.PRC` output
rather than left as a guess**: the HELMR1 table on DOY 121 shows **seven**
fiducials evaluated (AIRA, ALIC, DAEJ, DARW, MCIL, PIMO, PNGM), flagged `I A`
(AIRA) vs. `I W` (the other six). AIRA's residual (East −32.77 mm) dwarfs the
ensemble RMS (East 3.38 mm); the other six sit within single digits.
**`HLM_*.FIX` is `HELMR1`'s verification *output* — the excluded-outlier list,
not an input anchor.** AIRA is being correctly identified and rejected every
day; the datum is genuinely defined by the barycenter of the remaining six —
the recommended minimum-constraint approach, working as designed, inherited
for free from the stock PCF.

**Checked whether AIRA's exclusion correlates with the DOY 126/129/145
network-wide spikes (runbook §4b.11) — it doesn't.** AIRA's East residual
across five spot-checked days: DOY 121 −32.8 mm, 125 −30.9 mm, **126 −28.5 mm**
(the worst spike day shows the *smallest* AIRA deviation of the five), 129
−32.7 mm, 145 −45.5 mm. Chronic, stable, day-independent. This rules out the
hypothesis that a single AIRA glitch drives the spike days — it's a separate,
real, still-unexplained finding (why is AIRA's a priori coordinate 30–45 mm
off in East, consistently, every day?) worth investigating on its own, not
folded into §4b.11's mystery.

### Practical answers to the Tier 2 table's original questions

- **Can `FIN_*.SNX` feed a later regional combination directly? YES — checked
  and confirmed, 2026-08-12.** Our 30 days of `FIN_*.SNX` are already in **NEQ
  representation**, the form that reuses cleanly.

  Getting this right required not trusting the first panel read. `R2S_FIN`'s
  `ADDNEQ2.INP` has `SNXCONT = "COV"` — the *less* usable form — which looked
  like the answer and would have been reported as such. But the produced file
  contains `SOLUTION/NORMAL_EQUATION_VECTOR` and `..._MATRIX` blocks and **no**
  `MATRIX_APRIORI`/`MATRIX_ESTIMATE` at all, contradicting that. Resolution:
  **`R2S_FIN` writes no SINEX whatsoever.** Its `SINEXRS` filename field is
  empty (`SINEXRS 0`), and `SNXCONT` is gated on `activeif = SINEXRS /= _`, so
  its `COV` value is **inert**. The same is true of `R2S_GEN`. The only panel
  with `SINEXRS` set is **`R2S_RED` (PID 521)**, which writes
  `$(FIN)_*.SNX` with **`SNXCONT=NEQ`** and `SNXREG=NO`.

  Lesson worth keeping: a panel value that is never consumed reads exactly like
  one that is. Verify against produced output, not the template.
- **A priori constraint matrix regularization** — §9.4.9 flags that a
  free/minimum-constraint solution can produce a singular `MATRIX_APRIORI`,
  needing `Regularize a priori constraint matrix = YES` (adds ~1e-7 to the
  diagonal). **Does not currently apply to us**: that block only exists in the
  `COV` representation, and we write `NEQ` (with `SNXREG=NO`). It becomes
  relevant only if someone switches `R2S_RED` to `COV` for external exchange —
  worth knowing before making that change, not a live issue.
- **How do regional subnetworks tie to one consistent datum?** Minimum
  constraint on the barycenter of whichever fiducials/reference stations are
  **shared across regions**, verified and pruned via the same HELMR1 loop each
  region already inherits individually. Not a new mechanism to design — the
  same one, applied to the union of each region's verified reference set.

## Tier 3 findings — 2026-08-12

**Read: DOCU52 §23.4.2.1 (p. 571) and §23.4.4.1 (pp. 607–608).**

### The Tier 3 question was based on a false premise, and dissolves on reading

This plan framed Tier 3 as "double- vs. zero-difference: `LUZON_DLY` inherited
double-difference by default, compare before committing a national pipeline to
it." **That comparison is not meaningful — the two example PCFs do different
jobs, not the same job two ways.**

- **`RNX2SNX.PCF` (§23.4.2, double-difference)** — *"designed for a
  double-difference based analysis of RINEX GNSS observation data from a
  **regional network**. Station coordinates and troposphere parameters are
  estimated and stored in Bernese and SINEX format... For each session, the
  corresponding normal equation information is saved for a subsequent
  multi-session solution (allowing the estimation of **station velocities**)."*
- **`CLKDET.PCF` (§23.4.4, zero-difference)** — *"a processing scheme for the
  **determination of station and satellite clock corrections**... The result
  file is a **clock RINEX file** including both station and satellite clock
  corrections."*

Coordinates and velocities versus clock corrections. For a deformation-
monitoring network — which is what MOVE Faults is — **`RNX2SNX.PCF` is
straightforwardly the right base, and it is what `LUZON_DLY` already derives
from.** The inheritance was correct, not accidental. Zero-difference
processing appears in this manual's examples for clock estimation and PPP, not
as a competing way to get a coordinate/velocity solution for a regional
network.

**No architecture change is needed for national scale on this axis.** Drop
this from consideration; it is not an open decision.

### What §23.4.2.1 confirms about the pipeline we already run

Three of its listed features map directly onto things this project has already
observed empirically, which is reassuring rather than new:

- **Automatic removal of observation files with gaps or large residuals** —
  the documented, intended behavior behind stations dropping out. Directly
  relevant to the still-open S01R question (runbook §4b.9): silent exclusion
  is a *designed* robustness feature of this PCF, not necessarily a defect.
  It does not explain *why* S01R specifically qualifies, but it does explain
  why nothing errors loudly when it happens.
- **The four-tier ambiguity-resolution ladder** (`V_BL_AMB` code-based WL →
  `V_BL_L53` phase-based WL → `V_BL_QIF` QIF → `V_BL_L12` direct L1/L2), with
  the manual's own example values 6000 / 200 / 2000 / 20 km. `LUZON_DLY`
  carries exactly these variables at exactly these defaults — confirming the
  earlier Tier 1 note that the tiered-AR design is inherited documented
  practice, not local improvisation.
- **Helmert comparison with three translations** for regional datum
  definition, plus comparison against previous solutions. This is the HELMCHK/
  COMPARF pair observed passing in the 30-day run, and the three-translation
  choice matches §10.2.2.2's no-net-translation recommendation for regional
  networks exactly.

One line worth carrying into any subnetwork work: *"The resulting SINEX data
should allow for both the reconstruction of the unconstrained, free network
solution and for the straightforward extraction of station coordinates of the
originally computed minimum-constraint solution."* That is a design guarantee
that the SINEX we already produce is suitable for later recombination — which
matches what was confirmed empirically about `SNXCONT=NEQ` above.

## Tier 4 findings — 2026-08-12

**Read: DOCU52 §11.1.3 (pp. 276–278), §11.2.1.1 (pp. 278–279). Applied
directly to our own 30-day solutions.**

### FODITS supersedes `network_coherence_scan.py`, and it isn't close

`scripts/network_coherence_scan.py` was written from scratch this session to
find coherent multi-station motion. FODITS does that and considerably more,
as a shipped, tested program:

- Reads coordinate time series from `CRD` files, **or** reconstructs them from
  the residual (`PLT`) file — note that **covariance information is only
  available via the `PLT` route**, which matters for weighting anything
  properly rather than treating every daily solution as equally good.
- Takes **predefined events** from four sources: equipment-change
  discontinuities straight from the station information file (`STA`), seismic
  events from a **USGS-derived earthquake list file** (`ERQ`, format described
  in §24.7.21), proposed seasonal/periodic signals, and a manual event list
  (`EVL`).
- Searches for **discontinuities, outliers, velocity changes, and periodic
  functions**, each with a significance test, iteratively adding and removing
  elements until every remaining one is statistically justified.
- Handles **aftershock screening** so a large event followed by aftershocks
  doesn't get modelled as a sequence of frequent discontinuities.

Our script does none of the significance testing, none of the seasonal
modelling, and has no notion of equipment changes or an earthquake catalog.
**It should be treated as a stopgap, and FODITS evaluated before any further
effort goes into extending it.** One caveat: FODITS is designed for
multi-year series (its purpose is velocity/discontinuity estimation over long
records) — on a 30-day window it has little to work with. It becomes the right
tool as the reprocessed archive grows, not immediately.

### The earthquake-detectability criterion, and what it actually means

§11.2.1.1 gives an explicit criterion (Eqn. 11.3) for whether an earthquake
should be considered capable of producing a permanent coseismic offset at a
station distance `d` metres:

```
M >= -5.60 + 2.17 * log10(d)
```

(Eqn. 11.2 is the Delle Donne et al. (2010) original at `-6.40`; AIUB shifts
the offset by +0.8 to be deliberately more inclusive, and both factors are
user-adjustable via "Earthquake factor A/B".)

**Applied to the confirmed M4.6 near General Nakar, Quezon on DOY 147** — the
event used earlier as a negative control for `network_coherence_scan.py` —
this predicts detectability out to **~50 km** (solving Eqn. 11.3 for M=4.6:
`d = 10^((4.6+5.60)/2.17)` = 50.2 km; this radius is independent of where the
epicentre actually is). Several of our stations are inside that. So this was
worth testing properly rather than assuming the earlier "no anomaly"
conclusion held.

**Epicentre caveat — the first version of this table was wrong.** It was
computed against General Nakar *town* (verified at 14.763 N, 121.635 E) rather
than the epicentre, which reporting placed **24 km northwest** of the town,
i.e. ≈**14.916 N, 121.477 E** assuming a 315° azimuth. Every distance below is
recomputed against that. The azimuth is an assumption from the word
"northwest," so distances carry roughly ±10 km of uncertainty — enough to move
a station across the threshold, not enough to change the conclusion.

**A proper pre/post step test (mean of DOY 121–146 vs. 147–151) finds no
coseismic signal at any station**, including the three that sit inside the
detectability threshold:

| STA | dist (km) | M required | ΔN | ΔE | ΔU | \|ΔH\| | inside threshold? |
|---|---|---|---|---|---|---|---|
| INFA | 26.3 | 3.99 | 1.9 | −0.1 | 6.9 | **1.9 mm** | yes |
| TANY | 38.9 | 4.36 | 0.5 | 0.1 | 1.2 | 0.5 mm | yes |
| ANTP | 46.3 | 4.52 | 0.7 | 1.6 | 10.6 | 1.7 mm | yes |
| PIMO | 53.0 | 4.65 | 1.2 | −1.1 | 1.8 | 1.6 mm | no (marginal) |
| POLI | 54.3 | 4.68 | 0.7 | −0.9 | 1.5 | 1.1 mm | no (marginal) |

**This is not a contradiction of the criterion — it is what the criterion is
for.** Eqn. 11.3 is a *candidate-proposal* threshold: it decides which events
get added to the list of elements FODITS will then subject to a significance
test. The manual is explicit that Eqn. 11.2 "is only roughly representing the
mean effect," and that AIUB deliberately loosened it further precisely because
"a significance test is added for each potential discontinuity." FODITS would
propose a discontinuity at INFA for this event and then reject it as
insignificant. Our observation matches that expected outcome exactly.

### A methodological correction to this session's own earlier analysis

The earlier DOY 147 check measured each station's deviation from its **30-day
mean**. That is the wrong statistic for detecting a step near the end of a
window: a genuine offset at DOY 147 would shift only 5 of 30 days, leaving the
mean dominated by the pre-event level and splitting the signal across both
sides. **The pre/post step test above is the correct method**, and it happens
to confirm the same conclusion — but the earlier conclusion was right partly by
luck, and the method should not be reused as-is.

One caution the step test itself surfaces: **LGYE shows a spurious 19.4 mm
"step"** purely because its known-bad DOY 151 outlier (runbook §4b.10) falls
inside the 5-day post-event window. At 182 km it is far below the threshold
anyway (M 5.81 required). Short post-event windows are badly exposed to
single-day outliers — another argument for using FODITS's tested outlier
handling rather than hand-rolled window statistics.

### Verification pass, 2026-08-12

All Tier 1–4 claims were re-checked against primary sources at the user's
request. Results:

- **`HLM_*.FIX` is the rejected-station list — CONFIRMED, and worth the
  re-check.** DOCU52 §22.12.3's wording ("a new station selection file
  containing only those stations that **passed** the outlier criterion")
  suggested the opposite reading. The panel settles it:
  `DESCR_LISTFIL 1 "List of rejected stations"` in `R2S_FIN/HELMR1.INP`.
  Confirmed end-to-end by content: `HLM_20251210.FIX` holds AIRA alone;
  `REF_20251210.FIX` — which `ADDNEQ2` consumes as `FREESTA_F` — holds exactly
  the six others (ALIC, DAEJ, DARW, MCIL, PIMO, PNGM). The datum really is
  the barycenter of six.
- **Three-translation datum — CONFIRMED at panel level**, not just from the
  manual: `HLM_1/2/3 = 1` (shifts), `HLM_4/5/6/7 = 0` (rotations, scale).
- **`CORREL` values — CONFIRMED**: `R2S_EDT` = `BASELINE`, `R2S_FIN` =
  `CORRECT`.
- **AIRA residuals — CONFIRMED exactly**: `13.25, −32.77, −19.04` mm, flagged
  `V`; component RMS `5.00, 3.38, 6.61`.
- **Ambiguity ladder — CONFIRMED**: `V_BL_AMB=6000`, `V_BL_QIF=2000`,
  `V_BL_L53=200`, `V_BL_L12=20` — identical to the manual's own example values.
- **SINEX representation — CONFIRMED**: only `R2S_RED` sets `SINEXRS`; it
  writes `NEQ`. `R2S_FIN`/`R2S_GEN` `COV` values are inert.
- **Step-test distances — ERROR FOUND AND CORRECTED** (see the epicentre
  caveat above). The conclusion — no coseismic step at any station — is
  unchanged and now rests on three in-threshold stations rather than four.



## Working with the BSW 5.2 manual (added 2026-08-12)

**Terminology note:** the user refers to the suite as **BSW**, version-qualified
where it matters — BSW 5.2 is the manual, BSW 5.4 is what runs on the R740.

### Figures need rendering, not text extraction

`pdftotext` silently destroys the flow diagrams, and several carry structure
the prose leaves implicit. **Printed page + 32 = PDF page** (verified across
both body and back matter: printed 9→41, 237→269, 821→853).

```bash
pdftoppm -f <pdfpage> -l <pdfpage> -r 130 -png /home/gps3/bernese-docs/DOCU52.pdf out
```

Two rendered so far, both of which changed or sharpened findings above:

- **Figure 1.1 (printed p. 9)** — the master functional flow diagram. Four
  input streams (orbit / EOP / observation / meta), five parts (ORBIT,
  SIMULATION, TRANSFER-CONVERSION, PROCESSING, SERVICE), an explicit
  **"iterations" feedback loop** from the session solution back to the ORBIT
  PART, and *multi-session solution* drawn **dashed** — i.e. optional, which is
  exactly the step a velocity series would need. Best single orientation
  artifact in the manual.
- **Figure 9.11 (printed p. 237)** — cluster combination. Confirms the Tier 2
  recipe and makes two things explicit the prose only implied: the **feedback
  arrow from HELMR1 back to ADDNEQ2**, and *"pre-eliminate parameters not
  supported in ADDNEQ2, e.g. **AMB**"* as a GPSEST pipeline step.

Worth rendering when the topic arises: 6.5 (p. 142, baseline strategies), 7.3
(p. 186, GPSEST flow), 9.5 (p. 224, ADDNEQ2 flowchart), 10.2 (p. 251, datum
options), 11.2 (p. 277, FODITS algorithm).

### End matter — and a warning: the indices are empty

PDF page numbers given directly (offset already applied), since that is what a
viewer takes:

| section | printed | PDF | state |
|---|---|---|---|
| Bibliography | 809 | **841–852** | populated |
| List of Abbreviations | 821–824 | **853–856** | populated, useful |
| Index of Program Panels | 825 | **857** | **EMPTY** |
| Index of Programs | 824 (per TOC) | — | **does not exist** |
| Index of Keywords | 825 (per TOC) | — | **does not exist** |

**The table of contents promises three indices that this PDF does not
contain.** PDF 857 has only the heading and the line "Bold printed page
numbers indicate a figure of the panel"; the rest is blank, and PDF 858 (the
last page) is blank. Printed page 824 is the final page of the abbreviations,
not an Index of Programs.

Verified by rendering PDF 857 to PNG and looking at it — text extraction alone
showed an almost-empty page, which could have been a layout failure rather
than a genuinely blank one. It is genuinely blank.

**Practical consequence: `grep` on `/home/gps3/bernese-docs/DOCU52.txt` is the
only working way to get from a program or panel name to its section.** Do not
flip to p. 825 expecting an index. The **List of Abbreviations** (PDF 853–856)
*is* populated and is worth using for the manual's dense acronyms; the
**Bibliography** (PDF 841–852) is intact for the underlying geodesy.

### Installation verification — §23.3 and §25.2 checked against this R740

**BSW 5.4 here passes every §25.2.1 system requirement except one, and the
exception matters later rather than now.**

| §25.2.1 requirement | state on gps3 |
|---|---|
| Perl 5 | v5.38.2 ✓ |
| tar / gzip / make | all present ✓ |
| Qt libraries | `QTBERN=/home/gps3/Qt4.8.7`, present; `MENU/menu` links cleanly ✓ |
| directory structure (`$P $D $S $T $U $C`) | all six present ✓ |
| **Fortran 90 compiler** | **only `gfortran-12`; no `gfortran`** ✗ |
| **C++ compiler** | **only `g++-12`/`gcc-12`; no `g++`/`cc`** ✗ |

**BSW 5.4 cannot currently be recompiled on this machine.**
`SCRIPT/EXE/Makefile.template` (GNU branch, and `F_VERS=GNU` here) invokes
`FC = gfortran`, `LD = gfortran`, `CC = cc` — all **unversioned**. Only the
versioned binaries exist, with no unversioned symlinks and no
`update-alternatives` entries; confirmed absent in a login shell too, so it is
not a PATH artifact of the tool environment.

**Nothing is broken today** — the binaries were built 2026-02-26 and the
30-day LUZON run proves they work. What is blocked is every path that needs a
rebuild:

1. **§25.3 "Updating Your Installation"** — AIUB ships bug fixes as source to
   recompile. Cannot be applied.
2. **§25.4.2 "Maximum Dimensions"** — changing `M_MAXDIM.f90` (`MAXSTA`,
   `MAXREC`, `MAXAMB`, `MAXSAT`) needs a rebuild. Not a live constraint, since
   `MAXSTA=3000` is far above any PH network size — but it is the escape hatch
   if a limit is ever hit, and it is currently unavailable.
3. **§25.2.5 "Compilation of Individual Modules and Programs"** — any local
   patch or debug build.

Fix prepared but **not run**: `scripts/sudo/install_bsw_build_toolchain.sh`
(`--check` is read-only and safe; the install path needs root). It adds
`build-essential` and `gfortran` rather than hand-made symlinks, so the
unversioned names come through the distribution's own alternatives mechanism
and survive a gcc upgrade. It deliberately does **not** rebuild anything, and
its output warns that a rebuild with a different compiler version than the
original may produce numerically different binaries — so the §23.3 EXAMPLE
verification should be re-run afterward.

### §23.3 verification status

§5.2 is "Preparation of Earth Orientation Parameters", not installation. The
relevant sections are **§23.3 "Installation Verification Using the BPE
Examples"** (p. 535) and **§25.2 "Installation Guide for UNIX/Linux/Mac"**
(p. 784).

§23.3 is **already effectively satisfied on this R740** — the EXAMPLE campaign
RNX2SNX BPE ran clean against the T420 reference (0.0000 mm) on 2026-07-28. If
it is ever re-run, note the ordering requirement: `PPP_BAS.PCF` first, and
`CLKDET.PCF` after `RNX2SNX.PCF`.

**One divergence found while checking:** §23.3 names `${X}/GEN/DE405.EPH` as a
prerequisite. BSW 5.4 here uses **`DE421.EPH` in `$MODEL`**
(`/home/gps3/BERN54/GLOBAL/MODEL`), per the shipped `README_JPL_EPH.md`. It is
present and correct — **do not "fix" a missing DE405.** Another instance of the
rule that where the 5.2 manual and the installed 5.4 files disagree on
anything procedural, the installed files win.

## PHIVOLCS' existing regional decomposition (2026-08-12)

**The subnetworks already exist.** The campaign time series on the file server
are organised by region, and this is PHIVOLCS' own partition — not something to
be invented here. Any subnetwork design should start from it.

| Directory | Region |
|---|---|
| `Luzon` | Luzon |
| `Ragay-Bondoc-Marinduque-Masbate` | Bicol / southern Luzon island group |
| **`CBPN`** | **Cebu, Bohol, Panay, Negros** — Central + Western Visayas |
| `Samar-Leyte` | Eastern Visayas |
| `Cotabato-Sindangan` | western / central Mindanao |
| `Eastern Mindanao` | eastern Mindanao |

`CBPN` is the only one whose meaning is not readable from the name, which is
exactly why it is written down here.

Together these span the archipelago, and the grouping follows island groups
rather than administrative regions — i.e. it already reflects the geography
that matters for a GNSS network, where baseline length and common satellite
visibility are what constrain clustering (§6.4).

Two consequences for this plan:

- **The station roster per region is already curated.** Each directory has its
  own `123` site index (snapshotted at
  `docs/bern52/phivolcs-scripts/event-catalog/`), which is precisely the
  "campaign roster" that Tier 1 established *is* the subnetwork boundary. The
  partitioning work is largely done; what is missing is the campaign plumbing
  around it.
- **These are campaign-survey groupings**, from the time-series side of the
  workflow. Whether the same partition suits the continuous (CORS) network,
  which is what the daily BPE processes, is **not established** — the six
  regional `123` files should be compared against the 52 stations actually
  estimated daily before assuming they transfer.

## Explicitly out of scope for this plan

- Anything already answered for the 31-day LUZON exercise (directory
  structure, campaign setup, RINEX import) — not re-reading Ch. 3–4.
- Full read-through of either manual. This plan is deliberately partial;
  update it rather than starting over if a new question surfaces.
