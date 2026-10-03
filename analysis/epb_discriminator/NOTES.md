# Notes

## Stop 1 — 2026-10-03 (gps3, weekend branch `weekend/gps3-epb-spike`)

**Purpose, restated so session 2 measures the right thing:** what does a raw
per-satellite stream add over the station-level (LVM-style) data we already
receive? Every comparison should put the two feature sets side by side on the
same scenarios.

### Works

- `scenario.build` produces all five labels (`quiet`, `quake`, `epb`, `glitch`,
  `quake+epb`); same seed and config give identical output.
- Bubble satellites are chosen by sky position (nearest a random sky point), not
  uniformly at random.
- `quake+epb` starts the bubble term `coseismic_lag_s` (600 s) after the pulse.
- **Each scenario also carries LVM-style station outputs** (`scenario.station`:
  velocity, 3x3 covariance scaled by the a-posteriori variance factor, `cq`,
  `n_sats`) computed from the same epochs, so session 2 can compare both
  feature sets directly.
- **Null calibration passes:** over 20,000 quiet epochs, mean chi2/dof is 1
  within 2 %, and the false-reject rate at alpha = 1 % is 1 % within 0.3
  percentage points. Normalized residuals are unit normal per satellite.
- A bias in the column space of H leaves the residual unchanged (tested), which
  is the undetectable subspace. A single-satellite bias at the computed MDB is
  detected at the stated power, 80 % within 2 points (tested).
- Figure: `figures/epoch_quake_vs_epb_seed42.png`, with its config and seed.

### What the first figure shows

At the placeholder amplitudes (bubble 10 mm/s RMS on 3 of 10 satellites, noise
3 mm/s at zenith), the bubble lifts chi2/dof clearly over the whole bubble
window. But a **single epoch's** w-test does not isolate the affected
satellites: with 6 degrees of freedom the excess spreads into the others.
The quake leaves chi2/dof at noise level throughout, as the physics says it should.

So per-epoch data snooping is weak at this amplitude and a **time-aggregated
statistic** (chi2 summed over a moving window, or per-satellite w accumulated
over time) is the obvious next candidate. Not tuned to make the figure look
better.

### Stubbed or not started

- `ledger.py` (claim schema + verifier): not started (session 2).
- `eval.py`: power heatmap, true-quake cost table, blind-spot map (session 2).
- Cycle slips in the bubble model; correlated noise from time-differencing
  (white noise per epoch is a known simplification); geometry held fixed over
  a scenario (satellites move ~0.5 deg/min).

### Next (session 2)

1. True-quake cost first: fraction of quake scenarios wrongly rejected, per
   amplitude.
2. Power heatmap (bubble amplitude x n_affected), per-epoch vs moving-window.
3. Blind-spot map from `mdb` and `leakage` (both implemented and tested).
4. The same metrics computed from `scenario.station` alone (velocity,
   covariance, `cq`), to answer the purpose question.
5. Ledger stub, verified for one case.

### Separately requested

Check whether `cq` or the covariance tracks disturbed periods in the existing
local captures (station-level, never committed).

**Result (2026-10-03, local DGOS captures, nothing committed):** station-level
`cq` and covariance do not track disturbed periods. `cq` sits at 22-29 mm/s
every hour in both the October 2025 and January 2026 captures and did not react
to the M7.4 itself. The one post-sunset reading above 15 mm/s (2025-10-10
11:12:52 UTC, 15.4 mm/s, two epochs) is **seismic, not ionospheric**: USGS lists
an M6.7 (Mww) at 11:12:05 UTC, 12 km SE of Santiago, Davao Oriental, 47 km
deep. Worth carrying to the VADASE threshold evidence: a nearby M6.7 crossed the
15 mm/s threshold for only two epochs.


## Stop 2 — 2026-10-03 (same branch)

`epb/eval.py`, `epb/ledger.py`, `run_session2.py`; 26 tests. Every number below
is in `figures/session2_results.json` with its config and seeds (20 per cell,
alpha = 0.001, window 30 s). Placeholder amplitudes and white noise throughout,
so these are shapes, not calibrated rates.

### 1. Cost on true quakes (reported first, as the brief asks)

Neither residual test rejected a single quake-pulse epoch (0 of 420 per peak,
peaks 5–120 mm/s; ~0.4 expected at alpha 0.001). **This is true by
construction**: in this model a quake is an exact rigid motion. The real cost
comes from what the model leaves out (multipath, unmodelled satellite motion,
receiver dynamics during shaking) and can only be measured on recorded data
with per-satellite residuals. The current detector, for reference, alarms on
22 % of pulse epochs at 15 mm/s peak and 81 % at 60 mm/s.

### 2. Power: summing over time is what makes the test work

Share of bubble epochs flagged, bubble RMS (rows) by satellites affected (cols):

```
              per-epoch test              30 s window test
mm/s     1     2     3     5           1     2     3     5
   4   0.00  0.01  0.01  0.02        0.01  0.09  0.23  0.53
   6   0.01  0.02  0.04  0.09        0.10  0.38  0.68  0.93
  10   0.04  0.11  0.19  0.35        0.42  0.84  0.96  1.00
  20   0.18  0.40  0.58  0.80        0.85  0.99  1.00  1.00
```

A sustained bubble that one epoch cannot see, a 30 s window finds: at 6 mm/s
on 3 satellites, 4 % against 68 %. This answers stop 1's open question.

### 3. The purpose question: what per-satellite data adds

The current detector (horizontal speed >= 15 mm/s, station-level only) raises
**false quake alarms on bubble epochs**: 32 % at 20 mm/s on 3 satellites, 66 %
at 40 mm/s. From station-level data alone those epochs look like motion, and
the October captures showed `cq` does not move either.

Of the bubble epochs that trip the detector, the window test flags **98–100 %**
once the bubble reaches 10 mm/s on 3 or more satellites. It is weak only for a
single satellite at small amplitude (10 % at 6 mm/s), which is also where the
detector rarely fires. **So per-satellite residuals would veto most
bubble-driven false alarms, and station-level data cannot.**

### 4. Blind spots (500 random geometries each)

```
           MDB (mm/s)       horizontal fake at MDB (mm/s)
  N   median   p95          median   p95
  6     47     166            28     191
 10     29      67             8.5    23
 20     24      61             3.5     6.4
```

"Fake at MDB" is the horizontal velocity that a single-satellite bias just
below detectability produces. With 10 satellites, at least 5 % of geometries
let an undetectable fault fake more than 22 mm/s, enough to trip the 15 mm/s
detector. With 20, the 95th percentile is 6.4 mm/s. The October 2025 DGOS capture used about 40
satellites, so a multi-GNSS solve should sit well inside the safe end; this
model has been run only to N = 20.

### 5. Ledger

`ledger.py`: claims with status and confidence. A change is refused unless it
cites the SHA-256 of evidence stored for that same claim. Evidence results are
`support | reject | insufficient` (plus `reject_H_eq`). Tested, including that
quake + bubble evidence leaves both hypotheses open.

### Still simplified

White noise per epoch (real TDCP noise is differenced and correlated, which
will make windowed sums optimistic); static geometry; placeholder sigma0 and
amplitudes; no cycle slips. Calibrating sigma0 needs per-satellite residuals
from a quiet day, which needs the raw stream (stage 3 on the NTRIP page).

### Next

1. Correlated noise: rerun power with differenced noise to see how much of the
   window gain survives.
2. A real calibration day once raw observations reach gps3.
3. A cheap classifier baseline (brief, evaluation 5) on station features vs the
   same plus residual features.
