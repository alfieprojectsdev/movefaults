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

## Explicitly out of scope for this plan

- Anything already answered for the 31-day LUZON exercise (directory
  structure, campaign setup, RINEX import) — not re-reading Ch. 3–4.
- Full read-through of either manual. This plan is deliberately partial;
  update it rather than starting over if a new question surfaces.
