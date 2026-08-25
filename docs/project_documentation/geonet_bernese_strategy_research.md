# GEONET (GSI Japan) Bernese Strategy — Research Brief for POGF/R740

**Date:** 2026-08-20 (verification pass same day — see §10)
**Scope:** Address the queued research task — study Japan GSI's GEONET Bernese
processing workflow for POGF/R740 applicability. Answers the adopt-vs-adapt
question the task was left open on.
**Companion memory:** `research_gsi_geonet_bernese_workflow` (the queue entry),
`bernese_orchestrator_design`, `bernese_bpe_phases`, `bernese_inp_settings`,
`bernese_workflow_status`, `bernese_orchestrator_r740_gaps`.

**Sources.** Every claim below is tagged with where it came from:

| Tag | Meaning |
|---|---|
| **[FIG13]** | Imakiire, T., "GNSS CORS and Reference Frame (GEONET by GSI: part 1)", FIG Commission 5 Technical Seminar *Reference Frame in Practice*, 2013. PDF read directly. |
| **[TSU17]** | Tsuji, H., Hatanaka, Y., Hiyama, Y., Yamaguchi, K., Furuya, T., Kawamoto, S., Fukuzaki, Y., "Twenty-Year Successful Operation of GEONET", *Bulletin of the GSI* Vol. 65, Dec 2017. PDF read directly. |
| **[TAK23]** | Takamatsu, N., Muramatsu, H., Abe, S., Hatanaka, Y., Furuya, T., Kakiage, Y., Ohashi, K., Kato, C., "New GEONET analysis strategy at GSI…", *Earth, Planets and Space*, 2023, DOI 10.1186/s40623-023-01787-7. **Abstract only** — full text bot-blocked on every route tried; metadata and abstract verified via OpenAlex and Semantic Scholar. |
| **[TOB15]** | Tobita, M., Suito, H., Kobayashi, T., Kawamoto, S., Yamanaka, M., Suzuki, A., Enya, T., Honda, M., Imakiire, T., Luis, A., Pelicano, A., Bacolcol, T., Ohkura, T., "Continuous GPS Observations on Mindanao", *Journal of Disaster Research* 10(1), 2015, DOI 10.20965/jdr.2015.p0067. **GSI–PHIVOLCS co-authored.** PDF read directly. |
| **[OHK15]** | Ohkura, T., Tabei, T., Kimata, F., Bacolcol, T.C., et al., "Plate Convergence and Block Motions in Mindanao Island…", *Journal of Disaster Research* 10(1), 2015. Companion campaign-GPS paper, same programme, no GSI authors. |
| **[REPO]** | Verified against this repository's own Bernese config, not from memory. |
| **[MEM]** | Project memory / prior session notes — second-hand, flagged where it matters. |

---

## 0. Recommendation up front

**Adapt, not adopt** — for one concrete reason found in the research, not a
general preference: **GEONET's strategy has no equatorial ionosphere handling,
because Japan is mid-latitude and does not need any.** No source reviewed
describes scintillation- or plasma-bubble-specific handling in the GEONET
processing chain. The one PHIVOLCS-specific piece of the current Bernese config
that matters most for solution quality — SIP every epoch + HOI model in the QIF
panel [MEM] — has **no GEONET analogue to adopt**. Reproducing GSI's strategy
"as closely as the Philippine setting allows" would mean *removing* PHIVOLCS'
own working equatorial handling to match a template that was never built for
it. That is a worse system, not a more proven one.

**Important caveat, found during verification:** this is a statement about
*GEONET*, not about *GSI*. GSI operates or installed CORS well outside Japan —
Mindanao (Philippines), Sumatra and Java (Indonesia), Tarawa and Kiritimati
(Kiribati), among others [FIG13] — all of them low-latitude, several of them
squarely in the equatorial anomaly belt. **GSI may hold exactly the equatorial
expertise GEONET's own strategy does not display.** That is now the single
sharpest question to put to them directly (§9, and the drafted enquiry) — and
§9 establishes that GSI is not a stranger to ask: PHIVOLCS and GSI are
**co-authors** on a Bernese-processed Philippine GNSS dataset [TOB15].

What *is* worth adopting close to verbatim: the **tiering structure**, the
**semi-dynamic datum** concept, and the **administrative response to a large
earthquake** (§4). Those are architecture and governance, not modelling, and
Japan's plate-boundary setting makes them directly transferable.

---

## 1. The tiering: Q3 / R3 / F3

**[FIG13]**, slide "Three routine analysis strategies":

| | Q3 (Quick) | R3 (Rapid) | F3 (Final) |
|---|---|---|---|
| Data window | 6 hours | 24 hours | 24 hours |
| Orbit product | IGS Ultra-Rapid | IGS Rapid | IGS Final |
| Schedule | every 3 hours | every day | every Sunday |
| Trade-off | fastest, least accurate | — | slowest, most accurate |

The tier names track the **strategy version number**, which is easy to trip
over: in the F2 era (from 2004) the same three tiers were called **Q2 / R2 /
F2** [TSU17, §2.2.5]. IGS Final orbits were published "more than two weeks
after the observation", which is what the slower tier is waiting for; IGS Rapid
arrived two days after [TSU17, §2.2.5].

Also from the same F3-era configuration [FIG13]: **Bernese Ver. 5.0**,
**ITRF2005**, GRS80, "GSI original absolute" PCV model, **30-second** epoch
data. F3 started in 2009 and introduced "the estimated atmospheric delay
gradient, an absolute PCV model, ITRF2005 as a new reference frame, and the new
fixed (reference) point" [TSU17, §2.2.5].

**F3 is the tier comparable to what POGF runs today** — daily, 24-hour,
IGS-Final-orbit solutions. Q3/R3 exist purely to give a same-day or same-week
number before the accurate one is ready.

**Applicability — corrected 2026-08-24.** This paragraph read: *"It solves a
problem POGF does not have yet: nothing downstream currently consumes a same-day
coordinate."* **That is wrong.** PHIVOLCS has run a rapid tier by hand since at
least 2013, staging ultra-rapid and rapid ephemerides manually after major
earthquakes.

The mistake was reasoning from a codebase survey to a claim about practice: no
consumer appeared in the repository because the consumer is a manual workflow
that no document records. The correct reading is that POGF already has the
requirement and pays for it in hand-work at the worst possible moment.

What remains true is the sequencing — the F3-equivalent should be reliably
automated first, and it now nearly is. See
`bernese_workflow_geonet_actions.md` §2.3 for the engineering, including the
hazard that matters most: tiers whose outputs are not distinguishable produce a
coordinate series that silently mixes accuracy levels.

### Strategy lineage
[TSU17, Fig. 2] gives the version history, which is itself the useful artefact —
each version is a documented, dated decision to change the processing:

`F0` (1996, ITRF94) → `F1` (2001, ITRF97) → `F2` (2004, ITRF2000) →
`F3` (2009, ITRF2005) → `F4` (ITRF2014) → **`F5`** (2023 paper, ITRF2014) [TAK23].

---

## 2. Network partitioning — "Backbone" + "Regional" clusters

**[FIG13]**, slide "2.2 Connection to the global frame". GEONET's stations are
not processed as one undifferentiated network. The architecture named on GSI's
own diagram:

- **Backbone cluster** — anchored by stations marked "BB station".
- **Regional clusters** — geographically subdivided, each containing "Basic
  cluster station" and "Additional cluster station" (and "New station").

**RESOLVED 2026-08-25 — the paper was reachable after all.** Nakagawa et al.
(2009), *国土地理院時報* 118, is at <https://www.gsi.go.jp/common/000054716.pdf>
and yields to `pdftotext`; it needed local extraction rather than a fetch. Full
account in [`geo006_network_architecture.md`](geo006_network_architecture.md).

The headline, because it does not survive being guessed at: **the partition is
by station AGE first, not by geography.** ~950 pre-2001 stations form the
基本網 (basic network) and everything later the 追加網 (additional network);
*each* is then split into five regional clusters, and the backbone is a few
stations drawn **from** the basic network's regional clusters.

The `ADDNEQ2` mechanics are settled too: V3 combined clusters pairwise with the
backbone and produced **non-unique troposphere solutions** at backbone stations;
V4 replaced this with a strict top-down hierarchy — backbone, then basic
regional, then additional regional — each layer fixed before the next is
solved. The change was gated on Bernese 5.0 allowing troposphere parameters in
normal-equation files.

**Still open:** stations per cluster (~190 implied, no stated rule), how many
stations form the backbone ("数点ずつ" — a few from each), and **the network
size at which partitioning becomes necessary** — the question that actually
decides whether the PH network needs this. Likely in Miyahara et al. (2009),
same issue, not yet retrieved.

**F5 adds a second axis:** its two headline changes are "incorporating **global
network processing**" and troposphere enhancements [TAK23, abstract]. So the
current architecture is not only regional clustering but a global network
solution combined with the domestic one. How those two are combined — and what
it did to the single-fixed-station datum of §3 — is not established here.

**Applicability to POGF today: not yet.** POGF's network is roughly **270
stations** [MEM, confirmed Dec 2024] against GEONET's ~1,300 — close to an order
of magnitude smaller. That is a reason not to borrow GEONET's partitioning
reflexively, but it is **not** evidence that POGF is below the threshold where
partitioning starts to matter, because **no source reviewed states where that
threshold is.** An earlier draft of this brief asserted GEONET ran unpartitioned
up to ~1,200 stations; that was an unsupported inference and has been removed.
The honest position: unknown, and worth asking.

---

## 3. One fiducial station, or several

**GEONET fixes a single station.** [FIG13] verbatim: *"Fix station (TSUKUBA) —
3D coordinates of Tsukuba station are fixed to IGS global daily solution in
F3."* Every other GEONET coordinate is computed relative to that one fixed
point.

Two adjacent facts that are **not** the same claim, and were conflated in the
first draft of this brief:

- TSKB/TSK2 are among the GSI-operated IGS sites that "locate near VLBI
  observation sites for co-location" [FIG13] — co-location is a property of the
  site, not the mechanism of the F3 datum.
- The Tsukuba **VLBI antenna's** ITRF2008 position was used as the reference for
  the **2011 datum revision** after Tōhoku [TSU17, §2.3.2] — a one-off datum
  reconstruction, not routine daily processing.

**POGF's approach differs, and the difference is verified from the actual
config, not from notes** [REPO], in
`config/bernese/gpsuser52-luzon/OPT/R2S_FIN/`:

- `HELMR1.INP`: `RESIDTYPE "NEU"`, `HLM_1/2/3 = 1` (three translations),
  `HLM_4/5/6 = 0` (no rotations), `HLM_7 = 0` (no scale) → **3-parameter,
  translations only**.
- `ADDNEQ2.INP`: `RADIO2_3 = 1` → **minimum constraint solution**;
  `FREESTA/SIGSTA/FIXSTA = FROM_FILE`, reading
  `${P}/PHIVOLCS\STA\REF190110.FIX`.

**The specific station list could not be verified.** That `.FIX` file lives on
the Bernese datapool and is not tracked in this repository, and the project's own
records disagree about its contents: a 12-station list
(`AIRA ALIC BTNG CUSV DAEJ DARW GUUG MCIL NTUS PIMO PNGM TNML`) appears in
`session_log_20260226.md` [MEM, RAG-derived]; a nine-station set including
Philippine stations (`AIRA ALIC BASC CLAV DAEJ DARW MCIL PIMO PNGM`) appears in
`T420_REPLY_20260805b.md`; and one Luzon run logged "6 fiducials accepted"
[`session_log_20260626.md`]. Resolving which is authoritative is separate work.

**The conclusion does not depend on the count.** Whether it is twelve, nine or
six, POGF uses *several* stations under a minimum constraint where GEONET fixes
*one*. A single fiducial ties the whole network's absolute position to whatever
that one station does — an equipment fault, a monument disturbance, an
undetected offset propagates everywhere. A multi-station minimum-constraint
solution is the more robust choice at this scale. **Adopting GEONET's
single-fiducial model would be a regression, not an upgrade** — recorded as a
deliberate skip, not an omission.

*(Incidental, unrelated to GEONET: that `.FIX` path contains a Windows
backslash — `PHIVOLCS\STA\` — the same class of portability defect already
logged in `bernese_orchestrator_r740_gaps`.)*

---

## 4. What GSI does when a large earthquake happens

The part of the queued task with the clearest transferable answer — and it is
mostly **not** a Bernese panel setting.

### 4.1 Real-time detection — a separate system
**RAPiD** (Ohta et al., 2012, cited in [FIG13]) is the automatic detection
method, running on 1 Hz data. Parameters, verbatim from the slide:

| Parameter | Value | Role |
|---|---|---|
| α | 60 s | short-term average (STA) weighting |
| β | 600 s | long-term average (LTA) weighting |
| D | > 0.1 m | detection threshold |

The slide defines **D as the difference between the short-term and long-term
averages**, which "increases just after the station records permanent
displacement"; separately it defines *Disp.* as the "difference between
positions now and 5 min. before the detection" [FIG13]. An earlier draft of this
brief described D itself as the 5-minute position difference — that conflated
the two rows and is corrected here.

This runs through **REGARD**, GSI's operational real-time system. REGARD uses
**GSILIB** — GSI's own modification of **RTKLIB** (Takasu, 2011) — not Bernese
[TSU17, §3.1.3, citing Furuya et al. 2013]. For Tōhoku 2011, GSI reports an
Mw 8.9 estimate within ~2 minutes ("but the result is unstable") and ~5 minutes
to "derive appropriate fault model" [FIG13].

**This is the closest published analogue to POGF's own VADASE real-time
detection** (`services/vadase-rt-monitor`) — both real-time, both architecturally
separate from the daily Bernese solution, both answering "how big, where" in
minutes. A direct comparison of RAPiD's STA/LTA constants against VADASE's
leaky-integrator and `ReceiverMode` thresholds is a natural small follow-up.

### 4.2 The administrative response — the transferable part
When estimated strain exceeded **2 ppm** in a prefecture, GSI **formally
suspended survey data** for the affected control stations — **438** GNSS-based
control stations and **~44,000** triangulation points — until revised
coordinates could be issued [FIG13]. Data were closed 14 March 2011; revised
results were published 31 May 2011 for an epoch of 24 May 2011, and the revised
set was named **Japanese Geodetic Coordinates 2011** [FIG13; TSU17, §2.3.2].
A stated threshold triggering a deliberate, dated freeze-and-reissue cycle — not
an automatic recompute.

**Directly applicable to POGF, and it needs neither the R740 nor a new tier.**
POGF has an event catalog (`docs/bern52/phivolcs-scripts/event-catalog/offsets`)
but no equivalent formal *trigger and freeze* procedure. A stated threshold —
strain, or a simpler proxy such as the HELMCHK residual POGF's BPE already
computes at PID 513 [MEM] — declaring a coordinate set provisional as of an
event and blocking downstream velocity estimation until a human confirms the
offset is resolved. This formalizes what `bernese_bpe_phases` already flags
HELMCHK for into a stated organizational threshold. **Governance, not code.**

### 4.3 Semi-dynamic datum — the standout idea
Published **April 2009**, its model "produced by using **F3** results from
GEONET analysis" [TSU17, §2.2.7]. The problem: official survey coordinates are
fixed at a past epoch for legal and practical consistency, while real positions
drift under ongoing crustal motion, so the gap between the coordinate on record
and the monument's actual position grows every year. GSI's answer is a
**correction model** that converts a survey result's epoch position to the
present-day position and back — *without ever reissuing the official
coordinate*.

**POGF has nothing equivalent, and this is the highest-value idea here.**
PHIVOLCS' segmented-velocity pipeline produces rates and offsets, but [MEM,
`velocity_pipeline`] there is no correction surface a downstream consumer — a
surveyor, a mapping agency, NAMRIA — could apply to translate an older
PHIVOLCS-derived coordinate to its present position without rerunning the whole
reduction. It is a **product built on top of existing velocity output**, not a
change to the processing panels. Worth its own scoped follow-up once the
routine pipeline is stable.

---

## 5. Scale and hardware — reassurance, not a blocker

GSI's stated GEONET analysis hardware, verbatim [FIG13]:

> Hardware: HP ProLiant DL380 G5 Quad Core (x6) — CPU (Xeon X5355 2.66GHz),
> L2 Cache (2x4GB), Memory (2GB), HDD (146GB, 10krpm 2.5", (x2))

Six quad-core servers, **2 GB of memory each**, processing 1,271 stations
[FIG13, April 2013] across three tiers daily. *(The "L2 Cache (2x4GB)" figure is
almost certainly a typo in the original slide for 2×4 **MB** — that is the
Xeon X5355's actual L2 cache. An earlier draft of this brief misread that line
as 8 GB of RAM; the slide says Memory (2GB).)*

**National-scale Bernese processing at Japan's density did not require exotic
compute.** An R740 substantially outclasses any single one of those machines.

**And POGF's R740 is already doing this work.** An earlier draft of this brief
repeated a stale memory that BRN-001 was still open and blocked on console
access. It is not: `deliverables_tracker.md` records **BRN-001 DONE 2026-07-29**
— Bernese 5.4 installed and verified on the R740 over SSH (EXAMPLE campaign,
0.0000 mm vs reference) — and **LUZON reprocessed 30/30 days unattended in
2h47m on 2026-08-06**, at 5m33s per day, with 2.8 / 3.0 / 10.9 mm repeatability.
The blocked-on-console item is iDRAC/BMC networking, a different thing.

This matters for the recommendations: work that would have waited for the R740
is **not gated**. The clustering tuning that `bernese_orchestrator_r740_readiness.md`
§2.4 calls the single highest-value lever can be measured now, against a real
30-day baseline.

---

## 6. Two stale personal notes reviewed — superseded

Two older Obsidian notes were flagged for triage. Both are **likely
Gemini-assisted** (confirmed by the user), and it shows:

- `Replicating Japan's GEONET infrastructure.md` (Oct 2025) — generic, uncited
  architecture advice (Airflow, a PostgreSQL station-metadata schema, a Flask
  dashboard, a "6-12 months / Year 2 / Year 3+" roadmap). It cites **no GSI
  publication** and contains **no GEONET-specific detail** — no tier names, no
  clusters, no RAPiD parameters, nothing that could only have come from studying
  GEONET. It also predates the monorepo build-out; most of what it proposes
  building already exists (`pogf-geodetic-suite`, TimescaleDB,
  `drive-archaeologist`, the field-ops PWA, `bernese-workflow`'s 198 tests).
  **Superseded; nothing to carry forward.**
- `GEONET Nationwide GPS array of Japan.md` (clipped 2025-10-23; source: a 2010
  *Geospatial World* article by Imakiire — the same author as [FIG13]) — a sound
  overview, independently consistent with what this brief found. Two details in
  it not captured elsewhere: **each GEONET pillar carries a tilt meter**, and
  1 Hz data is held on-site ~2 weeks before being decimated to 30 s and
  discarded. Minor, low-priority note: POGF's field-ops logsheet has no
  tilt-meter/inclination field for a *permanent monument* (`bubble_centred`
  covers a campaign tripod setup, a different thing).

---

## 7. Summary — what to do, and when

| Finding | Verdict | When |
|---|---|---|
| Q3/R3/F3 tiering | **Adapt** — a rapid tier is already run by hand after major earthquakes (corrected 2026-08-24) | Automate the existing manual practice; capture the procedure first |
| Backbone/regional cluster partitioning | **Not yet** — mechanics unresolved | Ask GSI; revisit if network size or wall-clock time becomes a constraint |
| Single-station fiducial reference frame | **Skip** — POGF's multi-station minimum constraint is the stronger design | N/A |
| RAPiD real-time detection parameters | **Adapt** — compare against VADASE's thresholds | Small follow-up, independent of R740 |
| Strain-threshold freeze-and-reissue | **Adopt** | Governance doc — can be written now, no code |
| Semi-dynamic datum correction model | **Adopt** — highest-value new idea | Scoped follow-up once routine pipeline is stable |
| Troposphere intervals | **No change** — POGF's final solve is already hourly, shorter than GSI's Philippine precedent (§8) | Ask GSI what F5 uses; do not shorten blindly |
| Troposphere mapping function consistency | **Fix** — `WET_GMF` vs `WET_NIELL` split across panels looks unintentional (§8) | Cheap, decide deliberately |
| GEONET hardware scale | Reassurance only | N/A |

---

## 8. What F5 settles — including one correction

The 2023 F5 paper [TAK23] was unreadable in full text but its **abstract is
verified**, and it resolves several items an earlier draft listed as unknown:

- **F5 is real and is the current strategy name** (previously "per a secondary
  source"; now confirmed from the paper's own abstract).
- Target: agreement with **ITRF2014 at several millimetres**.
- Two headline changes: **global network processing**, and **troposphere
  enhancements**.
- Troposphere: **VMF1** adopted, **and** the time intervals for troposphere
  estimates **shortened**.
- Accuracy achieved: **RMS 3.2 mm horizontal, 7.3 mm vertical** averaged over
  all GEONET stations; the vertical is "roughly 10%" better than the previous
  strategy.

**The correction — and it is actionable.** A secondary summary encountered early
in this research implied the improvement came from adopting VMF1 over F3's
empirical mapping function. The paper's own abstract says the opposite:

> "Sensitivity tests about troposphere estimates revealed that the reduced RMS
> was **completely due to the short time intervals, not the use of VMF1**, which
> contributed to partly suppressing the spurious vertical annual deformation."

So the lever that actually moved the numbers was the **troposphere estimation
interval**, not the mapping function.

**But checking POGF's actual panels reverses the obvious recommendation** [REPO,
`config/bernese/gpsuser52-luzon/OPT/*/GPSEST.INP`]:

| Panel | `MAPPNG` | `NUMPAR` (zenith spacing) | `NUMGRD` (gradient) |
|---|---|---|---|
| R2S_EDT (float) | `WET_GMF` | 02:00:00 | 24:00:00 |
| **R2S_FIN (final)** | `WET_GMF` | **01:00:00** | 24:00:00 |
| R2S_QIF / L53 / L12 (ambiguity) | `WET_NIELL` | 02:00:00 | 24:00:00 |
| R2S_AMB (Melbourne-Wübbena) | `COSZ` | 02:00:00 | — |

**POGF's final solution already estimates zenith delay hourly** — *shorter* than
the 3-hourly interval GSI used on our own Mindanao data [TOB15]. So "shorten the
interval" is largely already exercised where it matters most, and an earlier
draft of this brief recommending it as the first experiment was **wrong**. F5's
finding is better read here as *confirmation that POGF's existing hourly choice
is the right axis to have spent resolution on*, not as a change to make.

Two things the table does raise, neither of them from GEONET:

1. **The mapping function is not consistent across the pipeline** — `WET_GMF` in
   the float and final steps, `WET_NIELL` in all three ambiguity-resolution
   steps, `COSZ` in Melbourne-Wübbena. `COSZ` for MW is unremarkable, but the
   GMF/Niell split across QIF/L53/L12 versus EDT/FIN looks unintentional rather
   than reasoned. Project memory records "GMF is PHIVOLCS standard" [MEM], which
   the ambiguity panels do not follow. Worth a deliberate decision either way.
2. **The final solve estimates at 01:00:00 while everything upstream is at
   02:00:00.** That may well be intentional — the final solve can afford more
   parameters — but it is undocumented, and F5's result makes the interval a
   parameter worth reasoning about explicitly rather than inheriting.

`VMF` *is* available in these panels (`MAPPNG` cards include `WET_VMF` /
`DRY_VMF`), so an F5-style comparison is a panel edit, not a software change.
[TAK23]'s own sensitivity test says to expect little from it — which is useful
precisely because it saves the experiment.

**And there is now a Philippine anchor for it.** GSI processed PHIVOLCS'
own Mindanao data with **ZWD estimated every 3 hours and gradients every
24 hours** under the Niell mapping function [TOB15, §3.1] — see §9.4. That is a
concrete interval to compare against, on a Philippine dataset, from the same
institution that later found the interval mattered more than the mapping
function.

### Still unestablished
- ~~The `ADDNEQ2` mechanics for combining backbone/regional cluster
  solutions.~~ **Settled 2026-08-25** — top-down hierarchical fixing; see
  `geo006_network_architecture.md`.
- Cluster sizes and membership rules; **the network size at which partitioning
  becomes necessary** — still open, and the one that decides whether PH needs
  partitioning at all.
- What "global network processing" means concretely in F5, and how it interacts
  with the single-fixed-station datum.
- The actual troposphere estimation intervals in F5 (before and after) — the
  abstract states the finding without the numbers.
- Whether coseismic step detection is automated inside the routine daily
  pipeline, or whether the administrative path (§4.2) is the only mechanism.
- **Whether GSI applies different ionosphere handling at its own equatorial
  stations** (Mindanao, Sumatra, Java, Tarawa, Kiritimati). GEONET's strategy
  shows none, but GEONET is mid-latitude; GSI's out-of-Japan network is not.

Every one of these is a question in the drafted enquiry to GSI
(`temp/gsi-enquiry-draft.md`).

---

## 9. The GSI–Philippines connection is a co-authorship, not a citation

**This section was rewritten after the user surfaced a folder of co-authored
international publications. It changes the character of the finding entirely.**

### 9.1 The paper

> Tobita, M., Suito, H., Kobayashi, T., **Kawamoto, S.**, Yamanaka, M., Suzuki,
> A., Enya, T., Honda, M., **Imakiire, T.**, Luis, A., **Pelicano, A.**,
> **Bacolcol, T.**, Ohkura, T. (2015). "Continuous GPS Observations on
> Mindanao." *Journal of Disaster Research* **10**(1), 67–.
> DOI 10.20965/jdr.2015.p0067. Affiliations: Geospatial Information Authority
> of Japan; PHIVOLCS; Aso Volcanological Laboratory, Kyoto University.

Three of those names matter a great deal here:

- **Tetsuro Imakiire (GSI)** — the author of [FIG13], the presentation this
  brief leans on most heavily for GEONET's cluster architecture, tiering and
  fixed-station datum. We were reading his slides all day without knowing
  PHIVOLCS had published with him.
- **Satoshi Kawamoto (GSI)** — co-author on the REGARD real-time system cited
  throughout [TSU17] §4.1.
- **Teresito Bacolcol (PHIVOLCS)** — now **Director of PHIVOLCS**, and one of
  the officials to be copied on any enquiry.

A companion paper in the same journal issue — Ohkura, Tabei, Kimata, Bacolcol,
Luis, Pelicano, Jorgio, Tabigue, Abrahan, Jorgio, Gunawan (2015), "Plate
Convergence and Block Motions in Mindanao Island", *JDR* **10**(1), 59– —
covers the campaign-GPS side with Kyoto, Kochi, Tono and Nagoya collaborators.
Same programme, no GSI authors.

### 9.2 The programme

Both sit under **SATREPS** — the JST/JICA *Science and Technology Research
Partnership for Sustainable Development* — specifically the project
*"Enhancement of Earthquake and Volcano Monitoring and Effective Utilization of
Disaster Mitigation Information in the Philippines"* [Tobita 2015, §1].

**This is the JICA channel**, named. It is not a general aid relationship to be
traced; it is a specific project PHIVOLCS and GSI ran together and published
from.

### 9.3 The three Mindanao stations — inconsistency resolved

[Tobita 2015] settles what §9 previously flagged as a contradiction in [FIG13]:

| Station | Site | From |
|---|---|---|
| **BTUN** | DOST branch office building, Butuan | Dec 2010 |
| **TNDG** | Surigao del Sur State University lecture hall, Tandag | Dec 2010 |
| **TCGN** | Talacogon Municipal Hall building, Talacogon | Nov 2012 |

Three were installed. The deck's "two GNSS CORS sites" and its map's "Mindanao
(3 stations)" were both true at different times, exactly as the first-hand
account said.

### 9.4 GSI's own Philippine processing recipe — directly comparable to POGF's

This is the part with immediate technical value. [Tobita 2015, §3.1] states how
GSI processed Philippine GNSS data:

| Choice | GSI, Mindanao (2015) | POGF today [MEM/REPO] |
|---|---|---|
| Software | **Bernese 5.0**, relative positioning | Bernese 5.2 → 5.4 |
| Datum | **PIMO constrained** — coordinates *and velocities*, ITRF2008 | Multi-station minimum constraint; **PIMO is in the documented list** |
| Orbits | IGS final | IGS/CODE final |
| Troposphere | **ZWD every 3 h**, **gradient every 24 h** | interval not established here |
| Mapping function | **Niell** (Niell 1996) | **GMF** |
| Ocean loading | **FES2004** | BLQ via `merge_blq.py` |
| Reference frame | ITRF2008, then Sunda-relative via NNR-MORVEL56 | IGS14 / ITRF2014 |

Two things follow that could not have been guessed from the GEONET literature:

1. **GSI used a single constrained fiducial — PIMO — for Philippine work**, the
   same station POGF constrains. That is a much closer precedent than GEONET's
   TSUKUBA-fixed domestic strategy, and it is a Philippine dataset.
2. **The troposphere interval question now has an anchor — pointing the
   opposite way from what was first assumed.** GSI estimated ZWD **3-hourly**
   here with 24-hourly gradients under Niell. POGF's own final-solution panel
   estimates **hourly** (§8) — already shorter. So the question to GSI is not
   "should we shorten?" but "what does F5 use, given you chose 3-hourly on our
   data and later found the interval was the deciding factor?" That is a sharper
   question, and it stops POGF from "fixing" a setting that is already on the
   right side of the finding.

**And one connection to today's other work.** The Mindanao stations used
**Trimble 4000SSi receivers with Compact L1/L2 antennas** [Tobita 2015, §2].
The PHIVOLCS antenna workbook catalogues "Compact L1/L2" as
**`TRM22020.00+GP`** — the exact antenna whose vertical-offset constant was
found wrong and corrected on 2026-08-20 (3.5 mm, ground-plane bottom vs top).
If PHIVOLCS reduces any of that Mindanao archive itself, the corrected constant
applies to it.

### 9.5 Velocities from both sources

Not directly comparable — different reference frames — but consistent in
magnitude:

| Station | [FIG13], rel. NTUS | [Tobita 2015], rel. Sunda (NNR-MORVEL56) |
|---|---|---|
| BTUN | 5.0 cm/yr | 5.24 ± 0.03 cm/yr |
| TNDG | 6.1 cm/yr | 6.80 ± 0.02 cm/yr |
| TCGN | — | 6.24 ± 0.08 cm/yr |
| PIMO | 6.2 cm/yr | (constrained, not solved) |

[Tobita 2015] removed the coseismic offsets of the **2013 Bohol earthquake
(Mw 7.1, 15 October 2013)** before fitting velocity regressions — a worked
example of the offset handling POGF is designing a procedure for (§4.2).

### 9.6 What this does to the enquiry

The drafted letter was written as an approach from strangers. It is not one.
PHIVOLCS and GSI are **co-authors**, under a **named JICA/JST programme**, on a
**Bernese-processed Philippine GNSS dataset**, and the current PHIVOLCS Director
is on the author list. The enquiry has been rewritten accordingly
(`temp/gsi-enquiry-draft.md`).

## 10. Verification pass — what changed

This brief was audited against its own sources after first being written. Every
claim was re-checked; the following were **wrong or unsupported** and are
corrected above. Recorded because a brief that quietly self-corrects teaches
nothing about how much to trust the rest of it.

| # | First draft said | Verified position |
|---|---|---|
| 1 | GEONET hardware had "8 GB RAM" | Slide says **Memory (2GB)**; 8 GB was a misreading of the `L2 Cache (2x4GB)` line |
| 2 | TSUKUBA fixed "tied through a co-located VLBI antenna" | Fixed **to the IGS global daily solution**; VLBI co-location and the 2011 VLBI-referenced datum revision are two separate facts |
| 3 | RAPiD's `D > 0.1 m` = "difference between current position and position 5 min prior" | **D is the STA/LTA difference**; the 5-minute position difference is a separately defined quantity on the same slide |
| 4 | "GEONET ran unpartitioned up to roughly 1,200 stations" | **Unsupported inference — removed.** No source states where the partitioning threshold lies |
| 5 | POGF uses "a 12-station Helmert set" | **Transformation type verified from repo config** (3-param, translations only, minimum constraint); the **station list is not verifiable here** and project records give 12, 9, and "6 accepted" |
| 6 | Cited as "FIG Working Week 2013"; author "Imakiiire" | **FIG Commission 5 Technical Seminar, *Reference Frame in Practice*, 2013**; author **IMAKIIRE** |
| 7 | F5 named "per a secondary source"; VMF1 implied as the improvement | **F5 confirmed from the paper's abstract**; improvement was **completely due to shortened troposphere intervals, not VMF1** |
| 8 | Philippine velocities given without a reference frame | **Relative to NTUS** — added, since the numbers are meaningless otherwise |
| 12 | "BRN-001 is still open… blocked on physical console access", repeated from memory | **BRN-001 was completed 2026-07-29.** The R740 has since reprocessed LUZON 30/30 days unattended. Memory `bernese-install` and `bernese-workflow-status` were stale; the in-repo tracker was right |
| 11 | "shorten the troposphere estimation interval first" recommended for POGF | **Reversed.** POGF's final panel is already at 01:00:00, shorter than GSI's 3-hourly on Philippine data. The recommendation would have changed a setting that is already correct |
| 10 | GSI–Philippines described as worth "surfacing to whoever owns the JICA relationship" as a *possible* channel | **It is a co-authorship.** PHIVOLCS and GSI published together under the named SATREPS (JST/JICA) project; the current PHIVOLCS Director is a co-author [TOB15] |
| 9 | "GEONET has no equatorial ionosphere handling… there isn't any" | Correct **about GEONET**, but GSI operates equatorial CORS outside Japan; the institutional-knowledge question is open and is now the sharpest thing to ask |

**Held up unchanged under verification:** the Q3/R3/F3 tier table; the
backbone/regional cluster naming; the 2 ppm / 438 stations / ~44,000 points
freeze; the semi-dynamic datum origin (April 2009, from F3); REGARD's
independence from Bernese; the single-fixed-station datum; and the
adapt-not-adopt recommendation itself, which none of the corrections disturb.
