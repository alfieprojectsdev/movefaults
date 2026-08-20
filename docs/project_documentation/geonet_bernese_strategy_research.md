# GEONET (GSI Japan) Bernese Strategy — Research Brief for POGF/R740

**Date:** 2026-08-20
**Scope:** Address the queued research task — study Japan GSI's GEONET Bernese
processing workflow for POGF/R740 applicability. Answers the adopt-vs-adapt
question the task was left open on.
**Companion memory:** `research_gsi_geonet_bernese_workflow` (the queue entry),
`bernese_orchestrator_design`, `bernese_bpe_phases`, `bernese_inp_settings`,
`bernese_workflow_status`, `bernese_orchestrator_r740_gaps`.
**Sources:** primary GSI publications, fetched and read directly (citations
inline). Two stale personal notes reviewed and superseded — see §6.

---

## 0. Recommendation up front

**Adapt, not adopt** — for one concrete reason found in the research, not a
general preference: **GEONET's strategy has no equatorial ionosphere handling,
because Japan doesn't need any.** The one PHIVOLCS-specific piece of the current
Bernese config that actually matters most for solution quality — SIP every
epoch + HOI model in the QIF panel (`bernese_inp_settings`) — has **no GEONET
analogue to adopt**. Reproducing GSI's strategy "as closely as the Philippine
setting allows" would mean *removing* PHIVOLCS' own working equatorial handling
to match a template that was never built for it. That is a worse system, not a
more proven one.

What *is* worth adopting almost verbatim: the **tiering structure**, the
**semi-dynamic datum** concept, and the **administrative response to a large
earthquake** (§3, §4). Those are architecture, not modelling, and Japan's
plate-boundary setting makes them directly transferable.

---

## 1. What GEONET's tiering actually is (Q3/R3/F3)

Source: Imakiiire, T., "GNSS CORS and Reference Frame (GEONET by GSI: part 1)",
FIG Working Week 2013, and Tsuji et al., "Twenty-Year Successful Operation of
GEONET", *Bulletin of the GSI* Vol. 65 (2017).

| | Q3 (Quick) | R3 (Rapid) | F3 (Final) |
|---|---|---|---|
| Data window | 6 hours | 24 hours | 24 hours |
| Orbit product | IGS Ultra-Rapid | IGS Rapid | IGS Final |
| Schedule | every 3 hours | every day | every Sunday |
| Trade-off | fastest, least accurate | — | slowest, most accurate |

Historically Q3/R3 ran on IGS Ultra-Rapid/Rapid orbits and F3 on IGS Final,
arriving roughly two weeks after the observation day (Imakiiire, *Geospatial
World*, 2010). **F3 is the one comparable to what POGF runs today** — daily,
24-hour, IGS Final-orbit solutions. Q3/R3 exist purely to give a same-day or
same-week number before the accurate one is ready; POGF has never needed that,
since PHIVOLCS' Bernese output today is not consumed on a same-day cadence.

**Applicability: real, but not urgent.** Standing up a Q3/R3-equivalent tier is
worth doing only once F3-equivalent (today's single-tier pipeline) is reliably
automated end-to-end on the R740 — i.e., after BRN-001. It solves a problem
POGF does not have yet (someone wanting a rough coordinate within hours of a
station reporting). Filed as a *later* roadmap item, not a BRN-001 blocker.

---

## 2. Network partitioning — "Backbone cluster" + "Regional clusters"

Same FIG 2013 source. GEONET's ~1,300 stations are not processed as one
undifferentiated network. The architecture named on GSI's own slides:

- **Backbone cluster** — a core set of stations (marked "BB station" on their
  network diagram) that anchors the whole solution.
- **Regional clusters** — subdivided geographically, each containing "Basic
  cluster stations" and "Additional cluster stations."

**What I could not extract from public sources:** exact cluster sizes, the
station-selection rule for cluster membership, or the precise `ADDNEQ2`
mechanics of how backbone and regional solutions are combined into one national
set. The papers that would carry that (Nakagawa et al. 2009, "Development and
Validation of GEONET New Analysis Strategy Version 4") are in Japanese and were
not accessible through the search/fetch tools available this session. **This is
a real gap, not a rounding-off** — the mechanics are the load-bearing part of
the answer to "how does Bernese scale past a few hundred stations," and I am
flagging rather than guessing at them.

**Applicability to POGF today: low urgency, real eventually.** At ~270 stations
POGF is well inside the range Bernese handles as a single network without
partitioning — GEONET's own predecessor networks ran unpartitioned up to
roughly 1,200 stations before the cluster architecture is described in these
sources. Partitioning becomes a real question only as POGF's network grows well
past its current size, or if daily wall-clock time on the R740 becomes the
constraint (see §5 on hardware scale, which argues this is further off than it
might sound).

---

## 3. Single-station fiducial vs. POGF's 12-station Helmert set

GEONET fixes **one** station — **TSUKUBA** — to the IGS global daily solution,
tied through a co-located VLBI antenna. Every other GEONET coordinate is
computed relative to that single fixed point (FIG 2013, §2.2 "Connection to the
global frame").

POGF's current config (`bernese_inp_settings`) uses a **12-station minimum-
constraint Helmert transformation** (translations only, no rotation/scale) against
a fixed reference list: `AIRA ALIC BTNG CUSV DAEJ DARW GUUG MCIL NTUS PIMO PNGM
TNML`.

This is a genuine architectural difference, not a version gap. A single
fiducial station is simpler and ties the whole network's absolute position to
one well-characterized site; a 12-station minimum-constraint solution is more
robust to any single station's local anomaly (equipment fault, monument
instability, an undetected small offset) propagating into every other station's
coordinate. **Given PHIVOLCS' Helmert set already includes IGS-quality regional
stations and the minimum-constraint approach is the more defensible choice for
a network this size, this is not a change to make** — POGF's current approach
is arguably *better* than GEONET's here, and adopting GEONET's single-fiducial
model would be a regression, not an upgrade.

---

## 4. What GSI does when a large earthquake happens

This is the part of the queued task ("coseismic and postseismic offset
handling") that turned out to have the clearest, most directly transferable
answer — and it is **not** primarily a Bernese processing-panel setting.

### 4.1 Real-time detection (separate system, not the daily Bernese solution)
**RAPiD** (Ohta et al., 2012), the algorithm behind GSI's real-time earthquake
response, is a short-term/long-term-average displacement detector:
- weighting time constants **α = 60 s**, **β = 600 s**
- detection threshold **D > 0.1 m** (difference between current position and
  the position 5 minutes prior)

This runs on 1 Hz real-time streams through **REGARD**, GSI's operational
system — built on **RTKLIB**, not Bernese (Kawamoto et al., 2015, 2017). For
the 2011 Tōhoku earthquake, GSI reports a magnitude estimate within ~2 minutes
(unstable) refining to a stable fault model within ~5 minutes.

**This is the closest published analogue to POGF's own VADASE real-time
detection** (`services/vadase-rt-monitor`) — both are real-time, both are
architecturally separate from the daily Bernese solution, and both exist to
answer "how big and where" within minutes rather than to feed the routine
coordinate product. Worth a direct comparison pass between RAPiD's STA/LTA
parameters and VADASE's own leaky-integrator/`ReceiverMode` state machine
thresholds (`STREAK_THRESHOLD`, `GOOD_THRESHOLD`, `SUSPECT_THRESHOLD`) as a
separate, smaller piece of follow-up — not part of this task, but a natural
next comparison now that both are documented.

### 4.2 The administrative response (this is the transferable part)
When the Tōhoku earthquake's estimated strain exceeded **2 ppm** in a given
prefecture, GSI **formally suspended survey data** for every control station in
the affected area — 438 GNSS-based control stations, ~44,000 triangulation
points — until revised coordinates could be issued (Imakiiire, FIG 2013,
§3.1–3.2). The revision itself took **from March 2011 to May 2011** for the
worst-affected region, and produced a new, explicitly-versioned coordinate set
("Japanese Geodetic Datum 2011"). This was administratively deliberate, not an
automatic recompute: a strain threshold triggers a formal, dated freeze-and-
reissue cycle.

**This is directly applicable to POGF and does not require R740 or any new
Bernese tier to adopt.** POGF has an event catalog
(`docs/bern52/phivolcs-scripts/event-catalog/offsets`) but — as far as this
research established — no equivalent formal *trigger and freeze* procedure:
a stated threshold (strain, or a simpler proxy like HELMCHK residual magnitude
at PID 513, which POGF's BPE already computes per `bernese_bpe_phases`) that
declares "this coordinate set is provisional as of `<event>`" and blocks
downstream velocity estimation until a human confirms the offset is resolved.
Recommend adding this as a governance procedure, not a code change — it
formalizes what `bernese_bpe_phases` already flags HELMCHK for ("orchestrator
should flag this for human review") into a stated organizational threshold and
freeze/reissue convention.

### 4.3 Semi-dynamic datum — the one genuinely new architectural idea here
Published April 2009, built from F3 results (Tsuji et al. 2017, §2.2.7). The
problem it solves: official survey coordinates are fixed at a past epoch for
legal/practical consistency, but real positions drift continuously under
ongoing crustal motion — so the gap between "the coordinate on the record" and
"where the monument actually is today" grows every year. GSI's answer is a
**correction model**, derived from the F3 daily time series, that converts a
survey result's epoch position to the present-day position and back, without
ever reissuing the official coordinate.

**POGF has nothing equivalent, and this is the single highest-value idea in
this research to bring back — genuinely new, not a re-statement of something
already in `velocity_pipeline`.** PHIVOLCS' segmented-velocity pipeline
produces rates and offsets but (per `velocity_pipeline`) there is no
"correction surface" a downstream consumer (a surveyor, a mapping agency) could
apply to translate an old PHIVOLCS-derived coordinate to its current position
without rerunning the whole reduction. This is worth its own scoped follow-up
once BRN-001 and the routine pipeline are stable — it is a *product* built on
top of the existing velocity output, not a change to the processing panels.

---

## 5. Scale and hardware — reassurance, not a blocker

GSI's own 2013 slide states their GEONET hardware at that point in time (already
processing over 1,200 stations, three tiers, daily): **six HP ProLiant DL380 G5
servers, each a quad-core Xeon X5355 @ 2.66 GHz, 8 GB RAM, 146 GB 10k-RPM
disks** (Imakiiire, FIG 2013, §2.2). That is a modest cluster by 2026 standards
— an R740 substantially outclasses any single one of those boxes on cores,
clock, and disk. **National-scale Bernese processing at Japan's density does
not require exotic compute.** BRN-001 (Bernese install on the R740) is blocked
on physical access to the console, not on the R740 being underpowered for this
class of workload at POGF's current or medium-term station count.

---

## 6. Two stale personal notes reviewed — superseded

The user pointed at two older Obsidian notes as possible triage material:

- `Replicating Japan's GEONET infrastructure.md` (Oct 2025) — generic,
  un-cited architecture advice (Airflow, PostgreSQL station metadata, a Flask
  dashboard, phased "6-12 months / Year 2 / Year 3+" roadmap). It does not cite
  any GSI publication and predates the actual monorepo build-out — nearly
  everything it proposes building already exists in some form
  (`pogf-geodetic-suite`, TimescaleDB, `drive-archaeologist`, the field-ops
  PWA, `bernese-workflow`'s 198 tests). **Superseded; nothing to carry forward.**
- `GEONET Nationwide GPS array of Japan.md` (clipped 2025-10-23, source: a 2010
  Geospatial World article by the same GSI author, Imakiiire, as the FIG 2013
  paper used above) — a decent primary-source-adjacent overview, consistent
  with what this brief found independently. Two details in it not captured
  elsewhere above and worth noting: **each GEONET pillar carries a tilt meter**,
  and 1 Hz real-time data is retained on-site for two weeks before being
  decimated and discarded. POGF's field-ops logsheet does not currently ask
  about tilt-meter or inclination status at a continuous station — `bubble_centred`
  covers the *tripod* setup for a campaign visit, not a permanent monument's own
  tilt sensor. Minor, low-priority note for a future field-ops iteration, not
  action here.

---

## 7. Summary table — what to do, and when

| Finding | Adopt / Adapt / Skip | When |
|---|---|---|
| Q3/R3/F3 tiering | Adapt (F3-equivalent only, for now) | After BRN-001; add faster tiers only if a same-day-number need appears |
| Backbone/regional cluster partitioning | Not yet — mechanics unresolved | Revisit if network size or wall-clock time becomes a real constraint |
| Single-station fiducial reference frame | Skip — POGF's 12-station Helmert set is already the stronger design | N/A |
| RAPiD real-time detection parameters | Adapt — compare against VADASE's own thresholds | Small follow-up, independent of R740 |
| Strain-threshold freeze-and-reissue procedure | Adopt | Can be written as a governance doc now, no code required |
| Semi-dynamic datum correction model | Adopt — highest-value new idea found | Scoped follow-up once routine pipeline is stable post-BRN-001 |
| GEONET hardware scale | Reassurance only | N/A |

## 8. What this brief could not establish

Recorded honestly rather than papered over, since the queued task named this
as the hard part:

- The exact `ADDNEQ2` mechanics for combining backbone and regional cluster
  solutions into one national set.
- Station-count thresholds or selection rules for cluster membership.
- GEONET's post-F3 tropospheric mapping-function change (F3→F5 moved from an
  empirical mapping function to VMF1, per a secondary source) in enough detail
  to compare against POGF's current GMF choice (`bernese_inp_settings`) —
  the primary paper describing this (Earth, Planets and Space, 2023,
  "New GEONET analysis strategy at GSI") was blocked behind a bot-challenge on
  every fetch route tried this session and could not be read.
- Any equatorial or low-latitude ionosphere handling in GEONET's strategy —
  because, as far as every source in this brief shows, **there isn't any**.
  Japan is mid-latitude. This is itself an answer, not a gap: it confirms §0's
  recommendation that PHIVOLCS' own SIP/HOI equatorial handling has no GEONET
  template to adopt and should not be weakened to look more like one.

## 9. A connection worth knowing about, found along the way

GSI has direct, existing history with Philippine GNSS stations. The FIG 2013
paper shows GSI-analyzed velocities for three Philippine sites — **PIMO
6.2 cm/yr, TNDG (Tandag) 6.1 cm/yr, BTUN (Butuan) 5.0 cm/yr** — and states GSI
installed CORS in Mindanao under a **JICA-funded cooperative project**.
**PIMO is already one of the 12 stations in POGF's own HELMCHK reference list**
(`bernese_inp_settings`). This is not a citation-only relationship — GSI has
processed Philippine coordinates and funded Philippine infrastructure before.
Worth mentioning to whoever owns the JICA/PHIVOLCS relationship: there may be
an actual channel to ask GSI questions directly, rather than reconstructing
their strategy from published papers alone.
