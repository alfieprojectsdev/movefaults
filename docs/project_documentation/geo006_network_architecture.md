# GEO-006: how GEONET actually partitions 1,240 stations

**Established 2026-08-25** from the primary Japanese source, which earlier
research had flagged as unreachable.

**Source:** 中川弘之ほか (2009), 「GPS 連続観測システム（GEONET）の新しい解析
戦略（第４版）によるルーチン解析システムの構築について」, *国土地理院時報* **118**.
Nakagawa, Toyofuku, Kotani, Miyahara, Iwashita, Kawamoto, Hatanaka, Munekane,
Ishimoto, Yutsudo, Ishikura, Sugawara — Geodetic Observation Center and
Geography and Crustal Dynamics Research Center, GSI.
<https://www.gsi.go.jp/common/000054716.pdf>

**Attribution:** `docs/external-sources/README.md` records which specific ideas
came from this paper and where each landed, alongside the extracted source text
(`nakagawa2009_gsi118_extracted.txt`, sha256 `4f62c0135922a7fa…`). The PDF
itself is GSI's to distribute and is not committed.

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

**At ~107 stations, a single cluster is probably still correct — but the
margin is thinner than an earlier draft of this section claimed.**

The number needs its scope stated, because the repository carries several and
they count different things:

| figure | what it counts | source |
|---|---|---|
| **107** | distinct stations with **2025** RINEX 2 in our local datapool copy | measured 2026-08-25, `/srv/gnss-archive/datapool/PHIVOLCS` |
| 110 | distinct stations, all years, same top-level directory | measured, same |
| 439 | stations **catalogued** at the file server, ~52 estimated daily | `CLAUDE.md` |
| 425–438 | national-network figures in planning documents | `national_network_subnetwork_prep_plan`, research brief |
| 26 | stations per day in the completed 2025 LUZON run | §24.1 |

**107 is the operative number for a 2025 national run** — it is what we hold
data for. The 439 is a catalogue including historical and non-continuous sites;
the planning figures sit between.

> **Correction, from review of PR #141.** This section first said "76
> stations… roughly 3× the network". **76 was a single day's count** — distinct
> stations with a `.25o` file on DOY 200 — presented as if it were the national
> total, with no scope and no source. Across the full year the figure is
> **107**, and the ratio to the 26/day already processed is ~4×, not 3×.
>
> The reviewer also caught that the paragraph argued against itself: it cited
> Cass's note that the PCF carries station information for **all of PH**, which
> is plainly not 76.

The conclusion survives the correction, and the reasoning is worth stating
rather than the number alone: GSI partitioned at **~1,240** stations. At ~107
we are an order of magnitude below that, and partitioning is a scaling remedy
whose cost is paid at the combination step — V3's non-unique troposphere (§2)
is what that cost looks like. **Do not adopt it before the network size demands
it.**

The threshold at which GSI found it necessary is still not established (§5), so
"an order of magnitude below 1,240" is an argument from distance, not from a
known limit.

**Partitioning is a scaling remedy with a cost** — the V3 experience is that
the combination step is where correctness is lost. Do not adopt it before the
network size demands it. The threshold at which GSI found it necessary is not
stated in this paper and remains open.

---

## 4b. The single fixed point is harder than it looks — and this favours our design

From **[KOT09]**, the companion paper on fixed-point coordinates, retrieved
2026-08-25 while chasing the cluster rule.

GEONET V4 constrains the whole national network through **one station,
Tsukuba-1 (92110)**. Under V3 that station's coordinates came from a
*piecewise-linear nominal model*, which did not capture its vertical annual
variation. GSI's own account of the consequence:

> the annual vertical variation was not reflected in the fixed point's
> coordinates, so **an apparent vertical annual variation appeared in the
> analysed coordinates of every GEONET station**

One station's unmodelled motion propagated into all ~1,240. Nor could a
piecewise-linear model absorb coseismic displacement or local ground
instability at that site. V4 replaced it by determining Tsukuba-1's coordinates
**daily inside a wide-area IGS solution** rather than from a model.

**This strengthens a conclusion the research brief already reached.** POGF uses
a multi-station minimum constraint; GEONET's single-fixed-station datum needs a
dedicated paper and a daily wide-area solution to be safe, and its failure mode
is *global* — every station in the country inherits the error. The brief called
the multi-station constraint "the stronger design" before this paper was read;
it now has the mechanism behind it.

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

**Not in Miyahara et al. (2009), as previously guessed.** That paper is
「…解析戦略（第４版）**から見た地殻変動について**」, 時報 118, 31-36 — deformation
*results*, not architecture. The title says so; the guess was made from the
author list.

**Where it is, narrowed to a section.** 測地観測センター (2004), *国土地理院時報*
**103**, 1-51 — specifically **§1.3.1「GEONETの定常解析戦略の変遷」(畑中雄樹)**,
"evolution of the GEONET routine analysis strategy". The issue's front matter
was retrieved and its table of contents names that section; the body is a
separate file, not yet found. Same Hatanaka who co-authored [NAK09], and
[NAK09] states the network structure was inherited unchanged, so a 2004
description should still hold for V4.

Retrieval method and URL-pattern notes are in
`docs/external-sources/README.md` under *Open lead*.

**What was tried, and failed** (per the sources-register rule that "not
reachable" needs a method attached):

- `vol103-main.html` → 302 redirect to the GSI homepage.
- `vol103-1.htm` is the special issue's *abstract only*, no article list.
- Targeted Japanese searches for cluster counts returned nothing specific.
- `curl` cannot reach `gsi.go.jp` at all from this machine — the server
  requires legacy TLS renegotiation that OpenSSL 3 refuses
  (`error:0A000152:SSL routines::unsafe legacy renegotiation disabled`).
  Retrieval works through WebFetch only, one document at a time, which is why
  the issue index could not be walked.

So the sizing rule remains open, and the obstacle is a retrieval problem rather
than an absence. **It is also not on the critical path** — see §4: at 76
stations the question is probably moot.
