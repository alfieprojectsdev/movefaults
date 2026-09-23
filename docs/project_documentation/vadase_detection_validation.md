# VADASE detection, measured against two real earthquakes and a quiet day

*Measured 2026-09-22 on gps3 from captures held at
`services/vadase-rt-monitor/data/`. The captures are PHIVOLCS field data and
are deliberately not committed; every figure here is reproducible from them.*

Until now the detector had only ever been exercised against synthetic
fixtures. These three captures are the first evidence about how it behaves on
real data: two earthquakes, and a full day with no earthquake in it.

## What was measured

Horizontal velocity, `sqrt(vE^2 + vN^2)`, from `$GNLVM` sentences parsed by
`src/parsers/nmea_parser.py`. The detector's threshold is `threshold_mm_s:
15.0` in `config/stations.yml`.

| capture | sites | records | what it contains |
|---|---|---|---|
| `NMEA_10SITE_20260607` | 10 | 30,213 | Mw 7.8 Offshore Maasim, Sarangani, 2026-06-08 07:37 PST |
| `NMEA_DGOS_10102025` | 1 (DGOS) | 86,197 | an event arriving 2025-10-10 01:44:52 UTC |
| `DGOS_NMEA_01282026` | 1 (DGOS) | 85,453 | 24 hours, no event |

## The quiet-time noise floor is about 0.9 mm/s

Taken from the 37 minutes before the Sarangani origin time, across ten sites:

```
median horizontal standard deviation   0.93 mm/s
range across sites                     0.85 to 1.27 mm/s
largest single quiet-time sample       13.2 mm/s (MAGU)
```

So a 15 mm/s threshold sits roughly sixteen standard deviations above the
noise. That is not the same as sixteen times the largest excursion: the
loudest quiet sample reaches 13.2 mm/s, which is 88% of the threshold.

## The Sarangani event, ten sites

Origin 2026-06-08 07:37 PST (2026-06-07 23:37 UTC), Mw 7.8, depth 33 km.
Distances are to the bulletin epicentre.

| site | km | quiet sd | peak after | peak in sd | peak at | crossed 15 mm/s |
|---|---:|---:|---:|---:|---|---|
| MAGU | 91 | 1.27 | 157.2 | 124.0 | 23:39:18 | +81 s |
| NCPC | 127 | 0.85 | 90.3 | 106.3 | 23:39:08 | +92 s |
| LORE | 269 | 0.94 | 82.6 | 87.4 | 23:40:28 | +142 s |
| CDOC | 287 | 1.04 | 32.0 | 30.7 | 23:39:45 | +152 s |
| LLOY | 353 | 0.94 | 11.2 | 12.0 | 23:39:48 | never |
| PMPL | 445 | 0.88 | 12.2 | 13.9 | 23:40:40 | never |
| DNGT | 461 | 0.87 | 10.7 | 12.2 | 23:41:15 | never |
| TRIN | 468 | 0.92 | 6.9 | 7.5 | 23:40:54 | never |
| SPLY | 512 | 1.12 | 11.9 | 10.6 | 23:40:55 | never |
| PTTN | 615 | 0.87 | 14.2 | 16.4 | 23:41:49 | never |

**All ten stations recorded the earthquake. Six declined to alarm.** Every
station's peak is between 7.5 and 124 standard deviations of its own quiet-time
scatter, and every peak falls between 23:39:08 and 23:41:49 against an origin
time of 23:37:00. The six that never crossed 15 mm/s are not stations that
missed the event; they are stations where a clearly recorded signal stayed under
the alarm threshold.

**PTTN is unexplained.** At 615 km it is the farthest station, and its peak of
14.2 mm/s is the largest of the six non-detections, 16.4 sd and 95% of the
threshold, louder than four stations nearer the source. Its peak is also the
latest of the ten, so the timing is ordinary and the amplitude is not. A later
phase, site response or something unrelated could produce it. This note does
not know which.

**Four of ten stations detect, and they are the four nearest the epicentre, in
order.** Detection time grows monotonically with distance. Nothing beyond
287 km crosses the threshold, and nothing crosses it during the preceding
37 minutes at any station.

That ordering is the result worth keeping. A threshold that fired at random
would not produce it.

## The DGOS event, 2025-10-10

```
86,197 records over 24 hours
31 samples at or above 15 mm/s
first 01:44:52 UTC, peak 41.1 mm/s at 01:45:10, last 11:12:52 UTC
```

Arrival at 01:44:52 UTC is 09:44 PST. **The event is not identified here.** The
date and the arrival time are measured; which earthquake produced them has not
been checked against the PHIVOLCS catalog, and this note does not name it.

Excursions continue for nine hours after the first. That is *consistent with* an
aftershock sequence and is interpretation, not measurement: the same data would
be produced by any repeated excursion above threshold.

## The quiet day, 2026-01-28

```
85,453 records over 24 hours
0 samples at or above 15 mm/s
largest single sample 10.9 mm/s
```

**This is the control, and it is the most important of the three.** Two
detections prove the threshold is not too high. A full day without a single
false crossing is the only evidence here that it is not too low.

## What this does not establish

- **Nothing about magnitude or location.** The detector answers "is the ground
  moving faster than 15 mm/s here", and these captures confirm that it does so
  correctly. Converting that to an event estimate is a different problem.
- **Nothing about smaller events.** Both earthquakes here are large. The
  smallest motion these captures contain is TRIN's 6.9 mm/s at 468 km, which is
  7.5 sd of that station's own scatter: clearly recorded, correctly not alarmed.
  An earlier version of this sentence called LLOY's 11.2 mm/s "within the
  station's own scatter". It is 12 sd above it. Caught by finch in review.
- **Nothing about PTTN's amplitude**, see above.
- **Nothing about receiver state 3.** `CLAUDE.md` records an anomalous,
  non-seismic spike as an empirically unconfirmed receiver behaviour. No capture
  here contains one, so nothing here says how the detector responds to a real
  excursion that is not ground motion.
- **Nothing about lowering the threshold, beyond one data point.** At 10 mm/s
  the Sarangani hour would have produced a false crossing at MAGU before the
  earthquake arrived, and the January day would have come within 1 mm/s of one.
  That case rests on a single sample: MAGU's 13.2 mm/s at **23:03:37**, 33
  minutes before the origin time and so not an early arrival. It is an isolated
  spike, the largest of 11 samples above 5 sd in that station's quiet window.
  One spike is a reason for caution, not a false-alarm rate.
- **Nothing about latency in production.** These are file replays. The
  detection times above are the arrival of the data in the file, not
  end-to-end latency from a live stream.

## A correction to an earlier reading of the same data

A first pass treated the ten-site capture as quiet-time data and reported a
noise floor of 1.84 mm/s, with MAGU singled out as an unusually noisy station
needing its own threshold. Both were wrong: the capture contains the
earthquake, and MAGU is the station nearest to it. Its apparent noise was the
signal.

The reading was corrected when Alfie noted the files were associated with an
event. The lesson is the ordinary one: a statistic computed over a window is a
statement about that window, and "quiet time" was an assumption about the data
rather than a property of it.

## Reproducing

The captures are not in the repository. To repeat any figure here you need the
three directories under `services/vadase-rt-monitor/data/`, holding Leica
`$GNLVM` and `$GNLDM` sentences, one file per station-hour.

The per-site figures come from parsing `$GNLVM` directly, computing
`sqrt(vE^2 + vN^2)` in mm/s, and splitting each file at the origin time below.
They do not come from the replay tool.

To replay a capture through the detector instead:

```bash
cd services/vadase-rt-monitor
PYTHONPATH=. uv run python scripts/replay_events.py \
    --file data/NMEA_10SITE_20260607 --pattern '*.rtl' \
    --station MAGU --dry-run
```

`--dry-run` matters: without it the replay writes to the database and imports
`asyncpg`. `--station` matters because it defaults to `TEST`.

**Origin times used for the splits:**

| capture | event | origin |
|---|---|---|
| `NMEA_10SITE_20260607` | Mw 7.8 Offshore Maasim, Sarangani | 2026-06-08 07:37 PST = 2026-06-07 23:37 UTC |
| `NMEA_DGOS_10102025` | not identified | first excursion 2025-10-10 01:44:52 UTC |
| `DGOS_NMEA_01282026` | none | not applicable |
