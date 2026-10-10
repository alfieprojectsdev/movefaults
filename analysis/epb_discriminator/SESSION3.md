# Session 3: the window test under realistic noise

*2026-10-11, gps3. Synthetic, like sessions 1–2. `run_session3.py` reproduces
every number here in about 5 s; `figures/session3_results.json` holds them all.*

Session 2 found that a 30 s window test on per-satellite residuals flags 98–100 %
of the bubble epochs that trip the current detector, once a bubble reaches
10 mm/s on 3 or more satellites. That assumed white noise per epoch. Real range
rate from time-differenced carrier phase (TDCP) is not white, and real phase
carries multipath. This session asks whether the result survives both.

## Noise models

- **white**: sessions 1–2, independent per epoch.
- **tdcp**: range-rate error is the difference of consecutive phase errors.
  Same per-epoch σ, lag-1 correlation −0.5.
- **multipath**: a per-satellite sinusoid in phase, amplitude 10 mm, period
  `T` ± 30 %, added as its range rate `A·2π/T`. A long `T` means a nearby
  reflector, and a short `T` a distant one. Optionally scaled down to model
  what is left after a sidereal or sky-map correction.
- σ0 = 3 mm/s throughout (the session-2 placeholder) unless marked 1 mm/s.

## Result 1: the chi2 threshold cannot be used as is

| model | window false alarms at nominal χ² (α = 0.001) | calibrated threshold (nominal 244, 180 dof) |
|---|---|---|
| white | 0.0006 | 242 |
| tdcp | **0.0045** | 256 |
| tdcp + multipath 300 s | 0.0046 | 256 |
| tdcp + multipath 30 s | **0.034** | 278 |
| tdcp + multipath 30 s, 80 % removed | 0.0048 | 257 |
| tdcp, σ0 1 mm/s | 0.0045 | 256 |
| tdcp + multipath 30 s, σ0 1 mm/s | **0.95** | 576 |
| same, 80 % removed | 0.0098 | 263 |

**Correction to an earlier note.** It said differencing would *help* the window
test, because a phase error enters consecutive epochs with opposite signs and
cancels in a window sum. That is true of a sum of residuals. This test sums
**squared** residuals, and the squares of correlated errors are positively
correlated whatever the sign of the correlation. So differencing makes the
window statistic wider than χ² and over-alarms, here by 4.5×. The threshold
has to be calibrated on quiet data from the station, not taken from χ².

## Result 2: at a calibrated threshold, most of the power survives

Window test at the calibrated threshold, share of bubble-core epochs flagged
(rows: bubble RMS mm/s; columns: satellites in the bubble, 1 / 3 / 5):

| bubble mm/s | white | tdcp | tdcp + mp 30 s | tdcp + mp 30 s, σ0 1 | same, 80 % removed |
|---|---|---|---|---|---|
| 4 | .02 .25 .56 | .01 .16 .43 | .02 .16 .40 | .15 .71 .92 | .49 .99 1.0 |
| 6 | .11 .70 .93 | .06 .58 .89 | .07 .56 .86 | .39 .94 1.0 | .75 1.0 1.0 |
| 10 | .43 .97 1.0 | .35 .96 1.0 | .34 .94 1.0 | .70 1.0 1.0 | .96 1.0 1.0 |
| 20 | .86 1.0 1.0 | .82 1.0 1.0 | .79 1.0 1.0 | .98 1.0 1.0 | 1.0 1.0 1.0 |

The session-2 headline holds: of the bubble epochs that trip the current
detector, the calibrated window test flags 94–100 % at 10 mm/s on 3 or more
satellites under every model here (`window_given_station` in the JSON).
Differencing costs some power on small bubbles (6 mm/s on 3 satellites: 0.70 →
0.58).

## Result 3: multipath matters only for distant reflectors, and removal works

- **Slow multipath (300 s) changes nothing.** Its range-rate is 0.2 mm/s,
  invisible against 3 mm/s noise.
- **Fast multipath (30 s), about 2 mm/s range-rate**, raises false alarms
  7-fold at σ0 = 3 mm/s. At σ0 = 1 mm/s it dominates: 95 % of quiet windows
  alarm at the nominal threshold, and calibrating around it costs real power
  (4 mm/s on 3 satellites: 0.99 → 0.71).
- **Removing 80 % of it** (a sidereal or sky-map model) brings both back to
  the no-multipath case. That is the quantitative case for the multipath
  model: it matters exactly when the receiver noise is low, which is when the
  test is otherwise strongest.

## What this changes in the plan

1. **Calibrate the window threshold per station on quiet raw-stream data.**
   This is now a requirement, not a refinement, and it needs the same raw
   stream as σ0.
2. **Build the multipath map before trusting the test at low noise.** Which
   case applies depends on the real σ0 and on whether any station has a
   distant reflector (a short multipath period). Both are measurable from a
   quiet day of raw data.

## Still simplified

- The multipath model is a sinusoid with no elevation dependence.
- Geometry is static over the scenario. Real satellite motion changes the
  multipath period through the pass.
- No cycle slips.
- The bubble model is unchanged from session 2.
- All of it is synthetic: σ0, the multipath amplitude and the bubble
  amplitudes are placeholders until a raw stream exists.
