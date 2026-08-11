# Prep reading plan: processing the full PH network via subnetworks

**Written:** 2026-08-11, gps3. **Status: plan only — nothing in this document has
been read yet.** Written after the LUZON 5.4 reprocessing exercise (see
`docs/bernese54_luzon_reprocessing_runbook.md`) and after the user asked
whether the full PH network should be processed as subnetworks combined
later, rather than as one national cluster.

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

## Explicitly out of scope for this plan

- Anything already answered for the 31-day LUZON exercise (directory
  structure, campaign setup, RINEX import) — not re-reading Ch. 3–4.
- Full read-through of either manual. This plan is deliberately partial;
  update it rather than starting over if a new question surfaces.
