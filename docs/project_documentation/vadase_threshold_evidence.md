# VADASE alarm threshold: evidence from five real captures

*Measured 2026-10-06 on finch. Evidence, not a recommendation: this note reports
what real non-seismic and real earthquake signals reached against the 15 mm/s
threshold, and whether they separate. It proposes no replacement number.*

Companion to [`vadase_detection_validation.md`](vadase_detection_validation.md),
which measured the 2026-06-08 Sarangani event across ten sites. That note left
one gap explicitly open — *"no capture here contains [an anomalous non-seismic
spike], so nothing here says how the detector responds to a real excursion that
is not ground motion"* — and this one fills it, with TUA2. Measuring it also
corrected three claims in that note; see the end.

## What was measured

Horizontal speed, `sqrt(vE² + vN²)` in mm/s, from every `$GNLVM` sentence,
parsed by the service's own `src/parsers/nmea_parser.py`, so these are the
values the detector would see. The threshold is `threshold_mm_s: 15.0`.

**Events are identified from the USGS catalogue, not from the staff labels.**
The labels were written when the files were uploaded ("EQ-related spikes",
"anomalous spike"); each was checked against
`earthquake.usgs.gov/fdsnws/event/1` for its recording window. Distances are
great-circle, station to epicentre, computed here — not taken from the
catalogue's place descriptions.

Every figure below is reproduced by
`services/vadase-rt-monitor/scripts/threshold_evidence.py`. The captures are
PHIVOLCS field data and are not in the repository. (Corrected 2026-10-14: the
two DGOS captures were committed from 2026-01-31 until #277 removed them; they
remain in git history.)

## The five captures

| capture | staff label | what USGS shows in the window |
|---|---|---|
| TUA2 2025-10-06 15:00 UTC, 1 h | anomalous spike | **nothing**: no M4+ within 1,000 km |
| BOST 2023-12-02 14:00 UTC, 1 h | EQ-related | **M7.6** 14:37:04, 74 km, 40 km deep |
| PBIS 2023-12-03 14:00 UTC, 1 h | EQ-related | **M6.0** 14:35:56, 79 km, 13 km deep |
| DGOS 2025-10-09/10, 24 h | EQ-related | **M7.4** 01:43:59, 159 km; **M6.7** 11:12:05, 153 km |
| DGOS 2026-01-28, 24 h | *unlabelled* | **a swarm**: 25 events M4.5–5.9 within 300 km, at 169–191 km |

The TUA2 null was checked for being a null of the query rather than of the
earth: the same query widened to 4,000 km returns four events, the nearest
2,484 km away. The instrument was armed.

## The results

| capture | readings | ≥ 15 mm/s | longest run | peak (mm/s) | p99.9 | median |
|---|---:|---:|---:|---:|---:|---:|
| TUA2 (no earthquake) | 680 | **35** | 2 | **5,698.8** | 3,353.7 | 3.51 |
| BOST (M7.6, 74 km) | 3,598 | 16 | 3 | 52.4 | 32.5 | 2.21 |
| PBIS (M6.0, 79 km) | 3,599 | **0** | 0 | 6.9 | 6.3 | 1.70 |
| DGOS 10-10 (M7.4, M6.7) | 86,197 | 31 | 8 | 41.1 | 9.1 | 2.14 |
| DGOS 01-28 (M4.5–5.9 swarm) | 85,453 | **0** | 0 | 10.9 | 8.4 | 2.24 |

Per earthquake, measured over the 10 minutes after origin:

| event | km | peak | peak at | ≥ 15 | 30 min before: max |
|---|---:|---:|---:|---:|---:|
| M7.6, BOST | 74 | 52.4 | +26 s | 16 | 12.2 |
| M7.4, DGOS | 159 | 41.1 | +71 s | 30 | 9.5 |
| M6.7, DGOS | 153 | **15.4** | +47 s | **1** | 6.8 |
| M6.0, PBIS | 79 | 6.9 | +131 s | 0 | 6.4 |
| M5.9, DGOS | 182 | 9.3 | +529 s | 0 | 8.9 |
| M5.6, DGOS | 191 | 9.3 | +202 s | 0 | 8.5 |
| M5.4, DGOS | 169 | 7.3 | +395 s | 0 | 9.3 |

## What the threshold does

**It catches the two large earthquakes clearly.** M7.6 at 74 km: 16 readings over
15 mm/s, the first at +23 s (27.9 mm/s) and the peak at +26 s — about when an S
wave covers the 84 km from a 40 km-deep source. M7.4 at
159 km: 30 readings over about 70 s, from +53 s.

**It barely catches an M6.7 at 153 km.** One reading, 15.37 mm/s: 0.37 above the
threshold. #266's notes record it as crossing for two epochs; the count here, at
`>= 15`, is one.

**It does not see an M6.0 at 79 km, or M5.4–5.9 at 169–191 km, at all.** Not a
missed alarm on a recorded signal — no signal distinguishable from the noise. At
PBIS the highest reading across the M6.0's expected S arrival (+0 to +36 s) is
4.7 mm/s against a pre-event maximum of 6.4. The 6.9 mm/s peak at +131 s is a
single reading between neighbours of 2.3 and 2.6. The swarm events' peaks exceed
the 30 minutes before each by at most 0.8 mm/s, land minutes after any plausible
arrival (+202 to +529 s), and all sit below the day's own maximum — 10.9 mm/s at
18:18, when nothing is catalogued.

**It does not fire on background.** On BOST, PBIS and both DGOS days, every
reading at or above 15 mm/s falls within 10 minutes of a catalogued earthquake:
zero unexplained. The closest background came is BOST's 12.2 mm/s before the
M7.6, 82% of the threshold — consistent with the companion note's 13.2 mm/s at
MAGU, 88%.

**It fires 35 times in one hour on TUA2, which had no earthquake.**

## Do non-seismic and seismic signals separate?

**By amplitude, no — and raising the threshold cannot make them.** TUA2's
anomalous readings are of two kinds:

- **31 moderate readings, 15.2–34.0 mm/s.** These overlap the real earthquakes'
  above-threshold readings (15.0–52.4) completely.
- **4 blunders: 482, 912, 2,245 and 5,698.8 mm/s**, the last with a vertical
  reading of 29.8 m/s. These are larger than any real earthquake here by a
  factor of 9 to 109.

A threshold separates signal from noise in one direction only. The moderate
anomalies are inside the earthquake range and the blunders are above it, so no
single threshold rejects TUA2 while keeping the M7.4.

**By run length, no.** TUA2's longest run is 2. BOST's is 3, and the M6.7's is 1.

**By `cq`, partly — and only for the blunders across stations.**

| | `cq` on readings ≥ 15 mm/s | `cq` overall, median |
|---|---|---|
| BOST M7.6 | max **28.5** | 24.9 |
| DGOS M7.4 | max **28.1** | 24.2 |
| TUA2 blunders | **270 – 4,788** | 33.8 |
| TUA2 moderate | 35.5 – 66.5 | 33.8 |
| PBIS, normal | — | **45.9** (max 52.5) |

`cq` does not rise when the ground moves: during both large earthquakes it stays
at its pre-event level. It **does** rise on TUA2's blunders, by one to two orders
of magnitude. So the blunders are separable by `cq`: the smallest, 270, is four
times the largest `cq` on **any** other reading in all five captures — 66.5, one
of TUA2's own moderate anomalies.

**The moderate anomalies are not separable by `cq` across stations.** Their
`cq` (35.5–66.5) is above the earthquake readings' 28.5, but PBIS's *ordinary*
`cq` runs at 45.9. `cq`'s baseline differs by station, so a cut-off fit to BOST
and DGOS would reject everything PBIS reports, earthquakes included. Relative to
TUA2's own baseline the moderate readings are about 1.3× elevated; one capture is
not enough to say whether that generalises.

## What a defensible threshold would need

None of these captures can supply a number. A defensible one would need:

1. **Verified quiet time, per station.** None of the five captures is quiet:
   the one that looked like it is a swarm. The companion note's only quiet window
   is 37 minutes before the Sarangani origin.
2. **Per-station baselines.** Median horizontal speed ranges 1.70–3.51 mm/s
   here, and `cq` 24–46 mm/s. A single network-wide threshold assumes these
   are the same.
3. **Events in the band where 15 mm/s is marginal.** M6–6.7 at 50–200 km is
   where it currently either barely fires or does not: one M6.7 crossed by
   0.37 mm/s and one M6.0 left nothing above noise.
4. **A cause for TUA2.** Its stream is also irregular — 412 of 679 intervals are
   1 s, 266 are 11–12 s and one is 42 s — while the earthquake captures are a
   clean 1 Hz. Whether
   that is related to the blunders is not established.
5. **A quality gate that actually runs.** See below.

## Found on the way

- **`max_component_quality` and `min_satellites` are configured and never
  applied.** `config/stations.yml` sets `max_component_quality: 0.5` and
  `min_satellites: 8` under `quality`. Nothing under `src/` reads either; only
  `min_completeness` is applied (`processor.py`, `handle_displacement`). A
  reader of the config would believe a `cq` gate exists. It does not — and at
  0.5 m/s it would reject only two of TUA2's four blunders (the 270 and 274 mm/s
  `cq` readings fall under it).
- **TUA2 and DGOS are not configured stations.** `stations.yml` defines PBIS,
  BOST, BTU2 and PAPI. As configured, the detector would not watch the two
  stations behind three of these five captures.
- **The parser's docstring example is wrong; the code is right.**
  `parse_time_date('113805.50', '030215')` is documented as 3 Feb 2015; the code
  reads `mmddyy` and returns 2 Mar 2015, which is what the data needs (BOST's
  `120223` is 2 Dec 2023). The example is never run as a doctest, which is why
  nothing caught it.
- **The alarm and the classifier disagree at exactly 15.0.**
  `_classify_signal` uses `>=`, `check_event_threshold` uses `>`. A reading of
  exactly 15.00 mm/s is classed high-velocity and does not alarm. No reading
  here lands on it.

## What this does not establish

- **Anything about magnitude or location**, as in the companion note.
- **A false-alarm rate.** One hour of one anomalous station is not a rate.
- **That `cq` gating is safe in production.** The blunder separation holds on
  five captures from four stations.
- **Latency.** These are file replays.
