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

**Result (2026-10-03, local DGOS captures, nothing committed):** station-level
`cq` and covariance do not track disturbed periods. `cq` sits at 22-29 mm/s
every hour in both the October 2025 and January 2026 captures and did not react
to the M7.4 itself. The one post-sunset reading above 15 mm/s (2025-10-10
11:12:52 UTC, 15.4 mm/s, two epochs) is **seismic, not ionospheric**: USGS lists
an M6.7 (Mww) at 11:12:05 UTC, 12 km SE of Santiago, Davao Oriental, 47 km
deep. Worth carrying to the VADASE threshold evidence: a nearby M6.7 crossed the
15 mm/s threshold for only two epochs.


Check whether `cq` or the covariance tracks disturbed periods in the existing
local captures (station-level, never committed). See the PR description for
what was found.
