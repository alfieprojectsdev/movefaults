# Velocity and displacement maps, and stacked time series, in the BSW console

*Design, 2026-11-15. Not built. Complements the Time series page
(`docs/bsw_console_work_instruction.md`, section 6), which shows one station at a
time.*

## Why, and for whom

Two readers, with different needs:

- **The processing team.** A velocity field is the first, basic product
  after the time series, and the one that shows a bad station or a bad
  reference fastest.
- **The local government units (LGUs) that host a CORS or a campaign site.**
  A common concern from them is that they can't see how their contribution
  shows up in the bigger system: they give a site, power and access, and get
  nothing back they can look at. They will never open the console. What reaches
  them has to be a finished, reviewed sheet in plain language (section 5).

The views below serve the team first. The host sheet is built from the same
numbers, so the two can't disagree.

## What this adds

Three views on the Time series page, beside the one-station plot. All three use
the same campaign, reference station, `offsets` catalogue and outlier mode as
that plot.

1. **Velocity field.** A horizontal arrow per station, with a 95% error ellipse,
   and vertical rates as a separate layer.
2. **Event displacement.** For one earthquake in the catalogue, each station's
   step as an arrow with its ellipse.
3. **Stacked time series.** Several stations' series in one figure, picked on the
   map, at one shared vertical scale.

A fourth, the **profile tool**, belongs to phase 2's port of `velproj_loop.m`
and is described here only where the map has to leave room for it.

## What exists to build on

| Piece | Where | What it gives |
|---|---|---|
| Station map | `frontend/src/pages/StationMap.tsx`, Leaflet 1.9.4 | Markers, the reference ring, click to choose. **No tile server**: the coastline is a bundled file, so the map works on the office network and sends nobody the stations' positions |
| One-station chart | `frontend/src/tsPlot.ts`, uPlot 1.6.31 | Series, fitted lines, outlier flags, offsets, zoom |
| Per-station fit | `timeseries.status.series_status` | Final-segment velocity and 1σ for E, N and U; segments; `short_span`; `covers_latest_epoch`; the catalogue's sha256; warnings |
| Step amplitudes | `analysis.estimate_velocity_joint` | `StepEstimate` per event: dE, dN, dU with 1σ, and `resolvable` (≥3 epochs and >0.1 yr on each side) |
| GMT output | `timeseries/gmt.py` | `psvelo -Se` for horizontals and a separate vertical file, with the reference and span in `#` header lines |

**Measured on gps3, 2026-11-15, LUZON 2025–2026 against PIMO:** one ENU pass
over all 32 stations and 388 daily CRD files takes 0.2 s, and a station's fit
about 0.1 s. A whole field takes about 3 s, and the national campaign's ~52
stations should take about 5 s. So the field is computed in the console's
process on request and cached. It doesn't need to be a run-worker job:
it's read-only and quick, the same as today's one-station view (design brief
section 1a keeps jobs for work that writes or runs long).

## Conventions, and what we take from each

| Convention | Common practice | Here |
|---|---|---|
| Arrow scale | Length proportional to rate, fixed on paper (GMT `-Se<scale>`) with a labelled scale arrow | A fixed number of **screen pixels per mm/yr**, kept as you zoom, so arrows don't grow with the map. A scale arrow (e.g. "20 mm/yr") in a corner. Scale adjustable with − / + |
| Uncertainty | 95% confidence ellipse at the arrow tip (`psvelo -Se …/0.95`) | Same. The 2-D 95% ellipse's semi-axes are 2.448 × σ (√χ²₂(0.95) = √5.991), not 1.96 × σ |
| E–N correlation | From the daily covariance, when it is propagated | 0, as `gmt.py` writes it: East and North are separate fits, so their formal errors are uncorrelated. Ellipses are therefore axis-aligned. No fabricated tilt |
| Vertical | Never on the same arrows as horizontal; usually a separate map, coloured symbols or N–S bars | A separate layer, switched with **Horizontal / Vertical**: a circle at each station, red for up and blue for down, its size or shade by rate, the value on hover. Vertical is about three times noisier, and one map invites reading both at one confidence (`automation_stages.md`, item 4) |
| Frame | Captioned: ITRF, plate-fixed, or relative to a station. Philippine studies estimate in the current ITRF and display Sunda-fixed | Sunda-fixed by default once decision 1 is built; relative to a station and absolute IGS20 stay as staff options. **Always printed on the map and in every export:** the frame (and pole), the epoch span, the catalogue's sha256, the outlier mode. In relative-to-a-station mode the reference is drawn as a marked point with no arrow |
| Formal σ | White-noise least squares understates velocity uncertainty 2–11×, because GNSS series carry coloured (flicker) noise | Until decision 2 is built, labelled "formal 1σ, white noise only" wherever a σ or ellipse appears |
| Short or stale fits | Usually filtered out before mapping | A station whose final segment is under one year (`short_span`) or doesn't reach its latest epoch is drawn hollow and grey, listed under the map, and left out of exports unless ticked |
| Station names | Labels beside markers | Labels on hover; a toggle shows all labels |
| Stacked series | Stations stacked with an offset per trace, one component per panel, ordered by latitude or along a profile, at **one vertical scale** | See "Stacked time series" below |

## 1. Velocity field

**What the user does.** Picks the reference as today, presses **Velocity field**.
The map shows every station's arrow. A click on a station opens its plot in the
existing view; a shift-click adds it to the stack.

**Which rate.** By default the final segment's rate: the one published and the
one `vel_line_v8.m` reports. An **Interval** control offers "the segment that
contains a date". A station with no segment there is left off and counted
("4 stations have no data at 2024.5").

**Under the map:**
- the caption (frame, span, catalogue, mode, "formal 1σ");
- a table: station, Ve, Vn, Vu, σ for each, span, and a flag column (short, stale, far from reference), sortable;
- **Export**: the `psvelo` and vertical files from `gmt.py`'s writers, so a GMT
  figure matches the console exactly, plus the same table as CSV.

**Edge cases:**
- A station beyond the 5° ring gets the same orange marker as today. Its
  arrow is drawn, and the table flags it, since its axes are tilted.
- Stations the reference's absence removed days from: the existing warning, once,
  above the map.

## 2. Event displacement

**What the user does.** Chooses an event from a list built from the `offsets`
catalogue. Entries of type EQ whose dates agree within 0.003 yr (about a day)
are one event, listed by date with the number of stations that carry it.

**Numbers.** `estimate_velocity_joint(..., exclude_outliers=False)` per station,
so the fit uses the same epochs as the page's `record` mode. The step at that
event is the arrow: dE, dN with 95% ellipses from their σ, and dU on the vertical
layer. The scale is in mm, not mm/yr, and the scale arrow says so.

**Edge cases:**
- **A step that isn't `resolvable`** (too few epochs or too short a span on one
  side) is drawn hollow and grey, with the reason on hover. The ALBU case in
  `analysis.py` (a 7-day final segment after the 2025 Bogo earthquake) is what
  this guards against.
- **A station without that event in the catalogue** is drawn as a plain marker,
  with no arrow. The catalogue decides which stations have a step. The map
  doesn't add one.
- **Rate changes** after the event (`rate_changes=True`) are off by default. A
  tick turns them on, and the caption says so, because they change the step
  estimate.

**Later.** "Displacement between two dates" (for postseismic motion): the
difference of the fitted positions at two dates, with its σ. It needs the
model's covariance at both dates, which `status` doesn't return yet.

## 3. Stacked time series

**What it's for.** Seeing the same signal across stations: a step at one event,
a slow transient, a common wobble that one bad reference day puts in every
series. The one-station plot can't show those.

**Choosing stations.** Shift-click on the map, or shift-drag a box. The stack
lists them in a side panel where they can be removed. Capped at 20 in one
stack; beyond that it switches to small multiples (below).

**Layout, following common practice:**
- **One component per stack**: East, North or Up, switched with buttons. Mixing
  components in one stack makes amplitudes unreadable.
- **One vertical scale for every trace.** A 10 mm step must be the same height
  on every station, or the stack misleads. Never autoscale per trace.
- **Spacing between traces**: automatic, at 6 × the largest robust scatter
  (1.4826 × the median absolute deviation of each trace's residuals), so traces
  don't overlap; or a fixed number of mm the user types.
- **Order**: by latitude (north at the top, the default), longitude, distance
  from the reference, or the order picked.
- **What is drawn**:
  - raw positions;
  - **detrended**: each station's own fitted model removed (rates and steps), so
    transients and common motion stand out;
  - **rate removed only**: steps stay, so an event's step reads straight off.
- **Labels**: the station code and its rate at the left of each trace, and the
  catalogue's events as dashed vertical lines across the stack.
- **One cursor**: hovering at a date shows every trace's value at that date
  (uPlot's cursor sync).

**Small multiples**, for more than 20 stations or by choice: a grid of small
charts, still with one shared y-range and a synced cursor. This is the
NGL / EarthScope style for scanning many stations.

**Later.** A **common-mode estimate**: the network's median detrended position
per day, drawn as an extra trace and optionally subtracted. It's useful for
seeing a bad reference day, but it changes the data shown, so it waits until
the rest has been used.

## 4. Room for the profile tool (phase 2)

The phase 2 port of `velproj_loop.m` projects velocities onto a profile line
across a fault, as input to the 2-D model. On the map it needs:
- a **Profile** mode: two clicks set the line;
- a width, so stations within N km of the line are used;
- the azimuth shown, and fault-parallel and fault-normal components plotted
  against distance.

The projection code lives in the package, shared by the map and the modelling
command. The map only draws it. Design brief section 1b lists this as
"Export of model inputs".

## 5. A sheet for host LGUs

**What it is.** One printable page per station, made from the console by
someone at PHIVOLCS, checked by a named person, then sent to the LGU or handed
over on a site visit. It isn't a public website and doesn't link back to the
console.

**What's on it:**
- **Title:** the station and the LGU that hosts it.
- **The map:** the regional network with every station's arrow. Theirs is drawn
  in the accent colour and labelled; the others are unlabelled.
- **One plain sentence about their station**, e.g. "Since 2019 this station has
  recorded 1,840 days of data. The ground here moves about 25 mm per year toward
  the northwest, relative to [frame]." Whole mm/yr, "about", no σ notation.
  The uncertainty decides whether a sentence appears at all (below).
- **Their contribution, counted:** days of data per year as a small bar chart,
  from the days each run solved, and how many stations are in the network.
- **What it's used for, in three lines:** measuring how the ground moves across
  faults, and so how much strain they store. **And one line on what it's not:**
  it doesn't predict earthquakes.
- **The date, the frame, the version of the numbers, and who checked it.**

**Rules, because this leaves the building:**
- **Frame:** "relative to PIMO" means nothing to a lay reader. The sheet uses
  decision 1's Sunda-fixed frame: "motion relative to the stable interior of
  the Sunda plate (Palawan, Borneo and the Malay Peninsula)".
- **An arrow only where the rate is known** (decision 6). Otherwise one of
  two sentences: "moves less than about 5 mm per year" when the rate is
  known and small, or "measured N times since YEAR; its rate will be clear
  after the next survey" (campaign) / "after about N more years of data"
  (continuous). That's honest, and it tells the host why staying in matters.
- **Uncertainty as a filter plus one legend line, not ellipses:** "Arrows are
  drawn only where years of measurements give the rate to within about ±2 mm
  per year." It names no span, so it stays true whichever minimum decision 6
  settles on. At sheet scale a 2 mm/yr ellipse vanishes beside a 60 mm/yr
  arrow. Ellipses stay on the staff map.
- **No vertical rates.**
- **No coordinates printed.** The map is at regional scale. Campaign marks
  can be vandalised, and other LGUs' sites aren't this LGU's business.
- **Nothing goes out unreviewed.** The console makes a draft. A named person
  approves it, and the approval is recorded with the sheet's version.

**How it's made.** A console page laid out for A4, printed to PDF from the
browser. That needs no new server component, and the numbers come from the
same cached field as the map.

## API

Both endpoints are read-only and answer like today's `/timeseries` endpoints:
`configured`/`available` and a message when they can't.

- `GET /api/campaigns/{c}/timeseries/field?reference=PIMO&kind=velocity|step&event=2019.8027&rate_changes=0`
  - Per station:
    - code, lon, lat, distance from the reference;
    - Ve, Vn, Vu and σ, or dE, dN, dU and σ;
    - span, segment index, `short_span`, `covers_latest_epoch`, `resolvable` for steps;
    - warnings.
  - Once per response: the caption fields (reference, span, catalogue path and
    sha256, outlier mode) and the stations left out, with why.
- `GET /api/campaigns/{c}/timeseries/stack?reference=PIMO&stations=A,B,C`
  - Per station: `series` (t and E, N, U in mm) and its fitted model (segment
    lines and steps), so the page can draw raw, detrended or rate-removed
    without asking again.

**Computing:**
- One `crd_directory_to_enu` pass for all stations, without the `station=` filter,
  then `series_status` per station on the arrays in memory.
- The cache key is the CRD folders' fingerprint (the one `timeseries.py` already
  keeps), the reference, the catalogue's sha256 and the outlier mode.
- The outlier decisions people record don't change the field. The map shows
  the published `record` fit until `SETTLED.md` section 6 is decided, as the
  one-station page does.

## Frontend

Pure helpers with vitest tests, as `stationMap.ts` and `tsPlot.ts` are today:

- **`vectors.ts`:** arrow geometry in screen pixels from a rate and a scale;
  ellipse polygons (2.448 σ, axis-aligned); the vertical colour scale; and
  choosing a scale arrow length that is a round number of mm/yr.
- **`stack.ts`:**
  - the robust spacing, the ordering, and detrending against the package's own
    fitted model (no fitting in the browser);
  - the shared y-range, and the step from offset stack to small multiples.

Drawing:
- **Arrows and ellipses:** a Leaflet SVG layer, redrawn on zoom since their
  length is in pixels.
- **The stack:** uPlot, which handles a few thousand points per trace across 20
  traces without trouble.

Everything takes its colours from the existing theme tokens, as the station
map does.

## Not proposed

- **Map tiles from an outside server.** The bundled coastline stays; a tile
  request would tell the provider where every station is.
- **Absolute IGS20 velocities as the default.** They are dominated by plate
  motion (about 30 mm/yr everywhere here) and hide the deformation. They are
  the input to the Sunda-fixed default and a staff option (decision 1).
- **A correlation or ellipse tilt not computed from data.**
- **Vertical rates on the horizontal arrows.**
- **Interpolated velocity or strain-rate grids.** They're a modelling product
  with their own choices of smoothing, and belong with phase 2's tools, not on
  this map.

## Decisions needed

Each with a recommendation; open until the project lead accepts or changes it.

1. **Plate-fixed frames.** *Recommended from the literature (review of
   2026-11-16), pending sign-off.*
   **Recommended:** velocities **relative to the Sunda plate** by default on
   staff maps, exports and host sheets, the convention of Philippine GNSS
   studies (Yu et al. 2013, doi:10.1016/j.jseaes.2010.12.007; Hsu et al. 2016,
   doi:10.1002/2016JB013082). Relative to a station (for fault-crossing work)
   and absolute IGS20 stay as staff options.
   - **Pole:** GSRM v2.1 Sunda in IGS08: 51.07929°N, 94.63186°W,
     0.33318°/Myr anticlockwise, i.e. ω = (−0.0609, −0.7511, 0.9332) mas/yr
     (Kreemer, Blewitt & Klein 2014, doi:10.1002/2014GC005407; values from
     the GSRM `poles.IGS08` file). IGS08 differs from IGS20 by translation
     rates only, at most 0.2 mm/yr here, so no correction.
   - **Method:**
     - Fit each station's **own** daily IGS20 XYZ (the final CRDs, whose
       daily datum is already tied to IGS20 reference stations),
       converted to ENU about the station itself. Never difference against
       a reference station for this.
     - Subtract ω × r, rotated to ENU, from the horizontals.
     - Unit test: at PUER (9.74°N, 118.73°E) the pole predicts about
       31.7 mm/yr east and −12.8 mm/yr north.
     - This is a new path beside today's relative-to-a-station series.
   - **Alternative:** Eurasia-fixed with the ITRF2020 plate model's Eurasia
     pole, ω = (−0.085, −0.519, 0.753) ± 0.003 mas/yr, **plus its origin-rate
     bias (0.37, 0.35, 0.74) mm/yr on the horizontals, vertical discarded**
     (Altamimi et al. 2023, doi:10.1029/2023GL106373). Native to IGS20, but
     every site behind it lies west of 59°E, and it shows Palawan and Borneo
     moving 5–7 mm/yr.
   - **Do not use:**
     - an "ITRF2020 Sunda" pole: ITRF2020's plate model has no Sunda plate,
       and the EarthScope calculator silently returns zero rotation for it;
     - poles in a no-net-rotation frame (e.g. NNR-MORVEL56) on IGS velocities;
     - Simons et al. 2007 (doi:10.1029/2005JB003868) as printed: its
       longitude must be read as **94.2°W, rotating anticlockwise**, despite
       the "°E, clockwise" in the abstract, and as an ITRF2000 pole it also
       needs the 1.7 mm/yr Z-rate correction.
   - **State on the map:** published Sunda poles agree to about 2 mm/yr, and
     the realisation misfit at Sunda reference sites is up to about 5 mm/yr
     until PHIVOLCS checks its own residuals at NTUS (Singapore) and the
     Palawan CORS (PPPC, PKLY, PNDO).
   - **Follow-up:** add NTUS and the Palawan CORS to the national solution as
     frame checks; re-estimate an IGS20 Sunda pole when enough stable-Sunda
     stations accumulate. Record the pole, its frame and the sign convention
     in `SETTLED.md` once signed off.
2. **Noise model.** *Recommended from the literature (review of 2026-11-16),
   pending sign-off.*
   **Recommended:** never publish white-noise or ADDNEQ2 formal σ as a
   velocity uncertainty; it is 2–11× too small (Zhang et al. 1997,
   doi:10.1029/97JB01380; Mao et al. 1999, doi:10.1029/1998JB900033).
   - **Continuous stations:**
     - A white-plus-flicker maximum-likelihood fit per station and ENU
       component with Hector or its Python port HectorP (Bos et al. 2013,
       doi:10.1007/s00190-012-0605-0): rate, annual and semi-annual terms,
       and a step at every `offsets` catalogue epoch.
     - Store σ_white, σ_flicker, the span, days, offsets, model and tool
       version with each velocity.
     - Cross-check with MIDAS on the same step file (Blewitt et al. 2016,
       doi:10.1002/2015JB012552). Send a station to review when
       |v_Hector − v_MIDAS| > 2√(σ_H² + σ_M²) or σ_MIDAS > 3 σ_Hector.
       MIDAS returns the pre-event rate when an earthquake falls after the
       series' midpoint, which is why it checks rather than replaces Hector.
     - Hector is too slow for the on-request field, so it runs as a cached
       batch job after each run; the map reads its results.
   - **Campaign sites** (too few epochs to estimate noise):
     - Average each campaign; add a white floor of 2 mm horizontal (3 mm for
       tripod setups, 6 mm vertical) per campaign, and a random walk of
       1 mm/√yr horizontal. Replace the random walk with the median from
       PHIVOLCS' own continuous stations once measured.
     - Fit the rate only. Inflate σ by √(χ²/dof) and flag the site when
       χ²/dof > 3; never deflate.
     - Precedents: McCaffrey et al. 2007, doi:10.1111/j.1365-246X.2007.03371.x;
       Hammond et al. 2011, doi:10.1029/2010JB007817.
     - The span sets the precision; a third campaign mostly adds the ability
       to catch a blunder.
   - **Precondition:** today's IGS20 series span at most about 13 months
     (LUZON 2025 to January 2026, PHREF 2025), against a published minimum
     of 2.5–3 years (Blewitt & Lavallée 2002, doi:10.1029/2001JB000570, DOI
     to be confirmed). **No station qualifies for a public arrow until
     earlier years are reprocessed in IGS20.** Measure white against flicker
     on the longest reprocessed stations, not on PHREF 2025 alone.
3. **Fault traces layer.** *Settled 2026-11-16:* PHIVOLCS' geomatics group
   will provide the traces as KMZ/KML. Still to confirm on receipt: whether
   they may be bundled in this public repository, or must be loaded on gps3
   from a file kept outside it.
4. **Who approves a host sheet before it goes out**, and whether PHIVOLCS'
   public-information rules apply to it.
   **Recommended:** the project lead names one or two approvers. The console
   records the approver and the sheet's version, and only approved sheets
   print without a "DRAFT" mark.
5. **Language.** English, Filipino, or both, on one sheet?
   **Recommended:** English with a Filipino version of the plain-language
   lines, written once and checked by a native speaker, not machine-translated.
6. **The thresholds for drawing a host's arrow** (section 5). *Recommended
   from the literature (review of 2026-11-16), pending sign-off.* This
   replaces the earlier "σ under a third of the rate", which depends on the
   frame: in Sunda-fixed it would tell a stable Palawan host its rate is
   "not yet known" when it is known to be near zero.

   | | Continuous station | Campaign site | The sheet shows |
   |---|---|---|---|
   | **Arrow** | final segment ≥ 3 yr (≥ 2.5 yr with no steps); σ_E and σ_N ≤ 2 mm/yr; Hector and MIDAS agree; no unmodelled catalogue event; \|v\| ≥ max(3σ, 5 mm/yr) | ≥ 3 campaigns over ≥ 3 yr; modelled σ ≤ 2 mm/yr; no χ² or offset flag; \|v\| ≥ max(3σ, 5 mm/yr) | an arrow and "about N mm per year toward the [direction]" |
   | **Known, barely moving** | the same precision tests, \|v\| < 5 mm/yr | the same, \|v\| < 5 mm/yr | a dot: "moves less than about 5 mm per year" |
   | **Provisional** (staff map only) | 1–2.5 yr, σ from the network-median flicker; or a Hector–MIDAS disagreement under review | 2 campaigns over ≥ 3 yr, or ≥ 3 over 2–3 yr; σ ≤ 3 mm/yr | no arrow; "its rate will be clear after the next survey / about N more years" |
   | **Unknown** | < 1 yr, σ > 2 mm/yr, or an unresolved flag | < 2 yr, one campaign, σ > 3 mm/yr, or a flag | no arrow; "measured, rate not yet known" |

   The 5 mm/yr floor is the frame's realisation misfit (decision 1), rounded
   up; lower it once NTUS and the Palawan CORS confirm a smaller one. Span
   and σ thresholds follow Blewitt & Lavallée 2002, GAGE's 3-year rule,
   Hammond et al. 2011 and McCaffrey et al. 2007; the tiers themselves are a
   synthesis, not a published standard.

## Stages

1. Velocity field, its table and exports, relative to a station (as today's
   series) with formal σ labelled.
2. Absolute IGS20 velocities and the Sunda-fixed frame (decision 1), and the
   Hector/MIDAS batch job (decision 2).
3. The host sheet, as a draft-only page, once decisions 4 and 6 are made and
   reprocessing has given IGS20 series of at least 3 years.
4. Stacked series, with map selection.
5. Event displacement.
6. The profile tool, with phase 2's `velproj` port.
7. Later: an IGS20 Sunda pole of our own, common-mode, displacement between
   dates.

Each stage is one PR with its own tests and a work-instruction update.
