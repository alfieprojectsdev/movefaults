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

| site | km | quiet sd | peak after | crossed 15 mm/s |
|---|---:|---:|---:|---|
| MAGU | 91 | 1.27 | 157.2 | +81 s |
| NCPC | 127 | 0.85 | 90.3 | +92 s |
| LORE | 269 | 0.94 | 82.6 | +142 s |
| CDOC | 287 | 1.04 | 32.0 | +152 s |
| LLOY | 353 | 0.94 | 11.2 | never |
| PMPL | 445 | 0.88 | 12.2 | never |
| DNGT | 461 | 0.87 | 10.7 | never |
| TRIN | 468 | 0.92 | 6.9 | never |
| SPLY | 512 | 1.12 | 11.9 | never |
| PTTN | 615 | 0.87 | 14.2 | never |

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

Arrival at 01:44:52 UTC is 09:44 PST. Excursions continue for nine hours after
the first, which is what an aftershock sequence looks like in this measurement.

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
  smallest motion these captures contain is the Sarangani signal at 353 km
  (11.2 mm/s), which the threshold correctly ignores as being within the
  station's own scatter.
- **Nothing about the current lowering of the threshold.** At 10 mm/s the
  Sarangani hour would have produced a false crossing at MAGU before the
  earthquake arrived, and the January day would have come within 1 mm/s of one.
  Any reduction needs per-station scatter behind it.
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

```bash
cd services/vadase-rt-monitor
# replay a capture through the detector
PYTHONPATH=. uv run python scripts/replay_events.py \
    --file data/NMEA_10SITE_20260607 --pattern '*.rtl'
```

The per-site figures above come from parsing `$GNLVM` directly and splitting
each file at the bulletin origin time; the captures' own `README.md` records
which event each belongs to.
