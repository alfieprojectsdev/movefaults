# GEO-006: how GEONET actually partitions 1,240 stations

**Established 2026-08-25** from the primary Japanese source, which earlier
research had flagged as unreachable.

**Source:** 中川弘之ほか (2009), 「GPS 連続観測システム（GEONET）の新しい解析
戦略（第４版）によるルーチン解析システムの構築について」, *国土地理院時報* **118**.
Nakagawa, Toyofuku, Kotani, Miyahara, Iwashita, Kawamoto, Hatanaka, Munekane,
Ishimoto, Yutsudo, Ishikura, Sugawara — Geodetic Observation Center and
Geography and Crustal Dynamics Research Center, GSI.
<https://www.gsi.go.jp/common/000054716.pdf>

`geonet_bernese_strategy_research.md` listed this paper by name and said it was
*"in Japanese and not reachable this session… this is the load-bearing part of
'how does Bernese scale past a few hundred stations'."* It is reachable; it
needed `pdftotext` rather than a fetch.

---

## 1. The partition is by station AGE, not by geography first

This is the part that does not survive being guessed at.

```
基本網   basic network       ~950 stations installed before 2001  → 5 regional clusters
追加網   additional network  everything installed after 2001      → 5 regional clusters
バックボーン・クラスター  backbone  ─ a few stations taken FROM EACH basic regional cluster
```

The stated reason, translated:

> *"By building the network from stations with long histories, changes in the
> shape of the base network are held to a minimum, and stable station
> coordinates are obtained."*

Geography enters second — each of the two networks is *then* split into five
regional clusters. And the backbone is not a separate installation: it is **a
few stations selected out of each basic-network regional cluster**, whose job
is to tie the regional clusters to each other.

---

## 2. How clusters combine — the V3 defect and the V4 fix

This is the concrete `ADDNEQ2` mechanics the research brief listed as
unestablished.

### Version 3 (2004–2009)

Each regional cluster's normal equations were combined **pairwise with the
backbone**, those results merged, and finally Tsukuba-1's coordinates fixed.
Troposphere parameters were estimated *during* the backbone↔regional merge.

Two defects, stated by GSI themselves:

1. Troposphere came out as **intermediate per-cluster output that did not
   strictly agree with the final coordinates**.
2. Backbone stations participate in several merges, so they ended up with
   **duplicate troposphere solutions — the solution was not unique**.

### Version 4 (2009–)

A strict hierarchy, solved top-down, each layer **fixed** before the next:

```
(1) backbone cluster
(2) basic-network regional clusters        ← backbone solution held fixed
(3) additional-network regional clusters   ← layers above held fixed
```

Coordinates *and* troposphere are determined together at each level. That is
what restores both consistency and uniqueness.

**What made it possible:** Bernese 4.2 → 5.0, because 5.0 lets normal-equation
files carry troposphere parameters. The architecture change was gated on a
software capability, not on insight. (GSI also rebuilt their automation in Perl
at the same version bump, for maintainability — the same reason `startBPE.pm`
is Perl.)

---

## 3. Was V3 sound? — how GSI answered a question about their own method

Worth reading closely, because V3 was **published and used operationally for
five years while carrying a known defect**, and the reasoning by which that was
acceptable is more transferable than the architecture.

### They bounded the error rather than eliminating it

The clearest worked example is not the troposphere but a Bernese 4.2 bug in the
solid-earth-tide module, reported by Bern in 2004. It produced a **~4 ppb
annual variation in solution scale**. GSI **deliberately did not fix it**, and
said why:

- on the short baselines used for crustal-deformation monitoring, a scale error
  of that size has almost no effect;
- what remained could be removed as an annual term.

So: *estimate the magnitude, compare it against the signal you care about, and
state the residual handling.* The defect was not denied, hidden, or corrected —
it was **bounded and declared**. It was fixed at the V4 system update, when the
cost of doing so was already being paid.

### They validated by reprocessing the same data both ways

V4's improvement was demonstrated by **reanalysing GEONET data under V4 and
comparing against the V3 solution** — the same controlled comparison used here
for DOY 036 and for GEO-002. Two results:

**Atmospheric inhomogeneity.** For the 2008-07-24 Iwate earthquake, the V3
displacement field showed a coherent **~2 cm northward vector across the Tōhoku
region**. GSI called this *"unnatural as a pattern of crustal deformation"* —
and the weather chart for that day put a **stationary front** precisely along
the boundary between the stations showing the vector and those not. Reanalysed
under V4, which estimates atmospheric gradients, the spurious vectors are gone.

> **This is the most instructive item in the paper for us.** A systematic,
> spatially coherent, physically plausible-looking displacement field that was
> entirely an artefact — identified because its *shape* matched a weather
> front rather than a fault. Correlating against an independent physical
> observable is what caught it, not internal statistics.

**Annual variation and scatter.** On the ~1,020 km 八郷–猿払 baseline, V4
reduced both the annual signal and the day-to-day scatter across all three
components.

### What this means for trusting V3-era numbers

V3 coordinates are not worthless — they are **coordinates with a characterised
error budget**. The troposphere non-uniqueness affected the parameter that was
non-unique, and the atmospheric artefacts appear where atmospheric gradients
are large. The F3→F5 systematic difference is separately documented at
**2–3 cm**, largely from a change in how fixed points are handled.

The practical test, and the one a physicist would recognise: **a constant
defect is absorbed into the reference frame; a defect that varies with
something physical contaminates the signal.** The scale bug varied annually and
was removable as an annual term. The atmospheric error varied with weather and
was not — which is why it needed a model change rather than a correction.

---

## 4. What transfers to the PH network

Our 76 stations against GSI's 1,240 is a different regime and the shape should
not be copied wholesale. Three things do transfer:

1. **Partition by station history, not only by region.** We have the same split
   — long-running CORS versus recent additions — and the same motive: let the
   older, better-determined stations define the frame's shape.
2. **Hierarchical top-down fixing, not pairwise merging.** If the PH network is
   ever partitioned, this is the mechanics to use, and the V3 defect is the
   reason.
3. **The backbone is drawn from the regional clusters**, not built separately.
   This matches [Ohkura et al. 2015]'s precedent on our own data:
   PIMO tightly constrained → NMMB chosen as the Mindanao reference *because it
   had the longest observation period* → further pairs chained by observation
   overlap. **Same selection rule, arrived at independently.**

### And one thing that does not

**At 76 stations, a single cluster is probably correct.** GSI partitioned
because 1,240 would not fit, and Cass's note that the PCF carries station
information for all of PH points the same way. The 2025 LUZON run processed 26
stations per day at 1.91 min/day; 76 is roughly 3× the network, not 16×.

**Partitioning is a scaling remedy with a cost** — the V3 experience is that
the combination step is where correctness is lost. Do not adopt it before the
network size demands it. The threshold at which GSI found it necessary is not
stated in this paper and remains open.

---

## 5. Still unestablished after this

- **The number of stations per regional cluster.** The paper gives ~950 for the
  basic network across 5 clusters (~190 each) but does not state a rule.
- **How many stations form the backbone** — "a few from each" (数点ずつ), not a
  number.
- **The network size at which partitioning becomes necessary** — the question
  that actually decides whether PH needs this at all.
- **What "global network processing" means in F5**, and how it interacts with
  the single-fixed-station datum.

The first three are in Miyahara et al. (2009), in the same issue, which this
session did not retrieve.
