# PHPAR 2025: Bernese 5.4 against the 5.2 run, results

**Status, 2026-11-09:** PHPAR complete (365 of 365 days). PHSUP, the superset run,
in progress. The processing team's version of these results, with the questions
put to them, is a separate document; this file is the record of how the numbers
were made and where they live.

## What was compared

| | 5.2 run (gps2) | PHPAR (gps3) |
|---|---|---|
| Software | Bernese 5.2, Windows | Bernese 5.4, Linux, `bernese-run-year` |
| Frame, antenna model | IGS14 (`IGS14_R`), `I14.ATX` | IGS20, `I20` |
| Daily solutions | `F1_25DDD0.SNX`, 365 | `FIN_2025DDD0.SNX`, 365 |
| Station-days | 32,546 | the same 32,546, staged per day |

Staging: `scripts/stage_parity_2025.py` links, for each day, exactly the stations
in that day's 5.2 solution (`stations_by_day.tsv` from the gps2 copy). Station sets
are identical on 363 days; on the other 2, IBAZ is in the 5.2 solution only.
Settings: `config/bernese/gpsuser/PCF/PHPAR_DLY.PCF`, which is `PHREF_DLY` with only
the six campaign lines changed. The run: ledger runs `9f1ceb6c` and `19b7edbb`,
2026-11-07 09:31 to 11-09 02:15, no failed day.

Referee: **PHREF**, the 5.4 production run of 2025 (a separate network, a median 36
stations a day, 360 days). It shares software and frame with PHPAR, so it judges
broken days, not mm-level software differences.

Method: every pair of daily solutions through the robust 7-parameter fit in
`scripts/compare_weekly_solutions.py` (reject at 4 sigma or 15 mm horizontal,
refit), residuals in N/E/U.

## Results

| | Value |
|---|---|
| Days both runs agree with PHREF to 10 mm | 259 |
| PHPAR vs 5.2 on those days, median daily RMS | 3.4 mm horizontal, 8.2 mm vertical |
| Median transformation on those days | Tx/Ty/Tz −5.7/−5.0/−8.6 mm, −0.9 ppb |
| 5.2 days above 10 mm against PHREF | 97 of 360 (55 above 50 mm), 73 of them in Feb–May |
| PHPAR days above 10 mm against PHREF | 9 of 360 (1 above 50 mm) |

- **The bad 5.2 days are distorted networks, not shifted ones.** Fitting the
  Philippine stations alone leaves 100–400 mm residuals and 60–440 ppb scale. The
  IGS stations agree with PHPAR to a few mm on the same days.
- **They go with the 5.2 fiducial check** (`HLM25DDD0.LST`): bad on 45% of days
  with 2 fiducials accepted, 37% with 3, 14% with 4, 11% with 5 or 6.
- **PPPC, NTUS, PLWN** scatter by about 200 mm about a line in the 5.2 dailies and
  by about 2 mm in PHPAR.
- **PHPAR's 9 days** are groups of 3–5 stations shifted together by 18–210 mm
  (ALAB, GUMA, MAUB, CBIM recur). Not yet traced.
- **Velocities**, as the robust slope of each station's aligned 5.2-minus-5.4
  residual over the 258 days both runs are sound: median difference 1.2 mm/yr
  horizontal, 2.2 mm/yr vertical. Seven stations above 5 mm/yr horizontal: PPPC,
  NTUS, PLWN, GUES, PNBO, MASM, SHAO. One-year slopes with February to May mostly
  missing, so seasonal model differences leak in; a loose check.

## Weekly solutions and the datum finding

Weeklies were stacked with `scripts/stack_phref_weekly.sh` from the PHPAR daily
normal equations, Monday to Saturday as the 5.2 weeklies are. The first stack's
template set a minimum-constraint datum (translations only, stations from a file)
but left `FREESTA_F` blank, so no station carried the condition and the datum
floated with the orbits. ADDNEQ2 did not complain. Changing the a priori
coordinates moved the estimates by less than 0.000001 mm, which is what exposed it.

| | `FREESTA_F` blank | `IGS20.FIX` |
|---|---|---|
| Weekly vs its own dailies, median 3D translation | 35.2 mm | 3.8 mm |
| vs the 5.2 weeklies, median Tx/Ty/Tz | −22.1/+5.8/−18.8 mm | −6.1/−5.1/−9.1 mm |
| vs the 5.2 weeklies, median RMS H/U | 2.57/6.39 mm | 2.48/6.35 mm |

The script now takes `STACK_FIX` and refuses a template that needs a station file
and names none. Weeks 2355 and 2361 fall entirely in the bad 5.2 block. Week 2377
differs in datum by about 19 cm with 5.1 mm horizontal RMS, not yet explained.

## Where things are

| What | Where (gps3) |
|---|---|
| PHPAR dailies and ledger | `$S/PHPAR/2025/` |
| 5.2 copy (read-only) | `~/gps2_2025_bsw52_20261106/` |
| Daily comparison tables | `~/phpar-daily-cmp/` (`days.tsv`, `stations.tsv`, `vs_phref.txt`, `vel_diff_aligned.tsv`) |
| Weeklies, blank and fixed datum | `~/phpar-weekly/six/`, `~/phpar-weekly/six_fix/` |
