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

## Explicitly out of scope for this plan

- Anything already answered for the 31-day LUZON exercise (directory
  structure, campaign setup, RINEX import) — not re-reading Ch. 3–4.
- Full read-through of either manual. This plan is deliberately partial;
  update it rather than starting over if a new question surfaces.
