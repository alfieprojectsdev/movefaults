# PHREF 2025 reprocess: why the coordinates changed, and the I14/I20 join

*Measured on gps3, 2026-11-06. Dated results: not updated afterwards.*

## Results

1. **The reprocessed PHREF 2025 coordinates differ from the August ones because of
   the 2024-11-11 Bernese patches.** The pre-patch binaries reproduce the August
   solutions exactly on all three days tested, including the largest difference in
   the year (40.5 mm). The raised MAXPAR values aren't the cause.
2. **Velocities barely moved:** a median change of 0.01 mm/yr East and North and
   0.04 mm/yr Up in one-year rates. The largest is 0.61 mm/yr Up, at LGYE.
3. **The I14 to I20 antenna change shows up in the comparison with 5.2 production.**
   It accounts for about 60% of the station-to-station differences in the median Up
   residual. This is a correlation, not a controlled test.

## 1. The cause

Between the August run (29 Aug) and the reprocess (4 Nov), the products, `PHNAT.STA`
and `.CRD` and all but one RINEX file were unchanged. The BLQ and ATL edits of 30 Sep
touch only stations PHREF doesn't use. The LORE file changed on 4 Nov, after the parity
run. The reprocess also matches the parity run of 27 Oct on all 30 shared days, within
0.001 mm. That left two candidates: the patched binaries (2 Sep) and the MAXPAR values
in two `ADDNEQ2.INP` panels (29 Sep).

**The test.** Three days, chosen for a whole-network shift (DOY 329), the largest
single-station difference (DOY 089) and a quiet day (DOY 194). Each ran through
`bernese-run-year` into its own result tree.

| Run | Binaries | MAXPAR, `R2S_FIN` / `R2S_GEN` |
|---|---|---|
| Control | Patched | 6000 / 4000 |
| August MAXPAR | Patched | 3000 / 1000 |
| Pre-patch | Pre-patch | 6000 / 4000 |

Largest station difference and median, in mm, from `SOLUTION/ESTIMATE` of the `FIN` SINEX:

| DOY | November vs August | Control vs November | August MAXPAR vs November | Pre-patch vs August |
|---|---|---|---|---|
| 329 | 5.2334 / 4.9115 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | **0.0000 / 0.0000** |
| 089 | 40.5227 / 0.5412 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | **0.0000 / 0.0000** |
| 194 | 0.0066 / 0.0053 | 0.0000 / 0.0000 | 0.0000 / 0.0000 | **0.0000 / 0.0000** |

**How the runs were checked.** The pre-patch executables matched the fingerprint in
`~/bsw-patch-baseline/exe-sha256-pre.txt`, 88 of 88. A first attempt set `XG` in the
shell and still ran the patched binaries, because BPE jobs load their environment from
a file, not the calling shell. A sampler of `/proc/<pid>/exe` caught this, and that run
was thrown away. The valid run used Bernese's own `LOADGPS_$HOST.setvar` switch, and
the sampler saw only pre-patch binaries: 1,405 samples, none patched.

**What this doesn't settle.**

- It is three days, not 360, chosen to include the two kinds of large difference.
- The patch set was applied as a whole, so this doesn't say which patch. The patch plan
  names B_33 (geomagnetic model) and B_38 (`TRPSTORE`) as able to change numbers.
- It doesn't say which set of solutions is better. Patching was the right call on its
  own grounds, and these results only say the two aren't bit-comparable.

**The earlier check was too narrow.** `docs/SETTLED.md` recorded the patches as
"verified inert" from DOY 201 and EXAMPLE. DOY 201 is a quiet day: its largest
difference here is 0.01 mm.

### How the differences behave

Over all 360 days, 13,090 station-days:

| Days | Count | Median of each day's largest difference (mm) |
|---|---|---|
| Same observation and unknown counts | 230 | 0.01 |
| Unknown count differs, same observations | 115 | 0.6 |
| Observation count differs | 15 | 0.36 |

- 61 days have a station over 1 mm, 19 over 5 mm and 5 over 20 mm. Only 25 station-days
  exceed 5 mm.
- This fits a tiny change that occasionally tips a discrete choice, such as ambiguity
  fixing or data screening. That mechanism is inferred, not tested.
- **On DOY 102, 103 and 329 the daily fiducial check's station list changed:** the
  August list has PIMO on 102 and 103 and ALIC on 329, and the November list doesn't.
  DOY 102 and 329 move almost as a block. DOY 103 also has a large single-station
  change. DOY 172 and 200 also shift as a block with unchanged fiducial lists, which
  isn't explained.
- PIMO is in the final solution for DOY 200 only in November, with 2,948 more
  observations.

## 2. Velocities

One-year rates, August against November, for the 29 stations with at least 300 shared
days, using `analysis.estimate_velocity` with the `offsets` catalog. The ranges cover
PIMO and S01R as reference, with and without outlier exclusion.

| Change (mm/yr) | East | North | Up |
|---|---|---|---|
| Median | 0.009 to 0.013 | 0.006 to 0.007 | 0.035 to 0.042 |
| 90th percentile | 0.052 to 0.081 | 0.024 to 0.039 | 0.143 to 0.149 |
| Largest | 0.117 to 0.335 | 0.113 to 0.133 | 0.386 to 0.614 |

The largest is LGYE each time, already on the open list for East excursions. These are
one-year rates, so a multi-year rate would move less, but that wasn't measured. The 13
stations with fewer shared days weren't measured. Published velocities come from the
MATLAB and aren't affected.

**One boundary to remember:** LUZON 2025 was solved on the unpatched build, and LUZON
January 2026 on the patched one, so that series crosses this change.

## 3. The I14/I20 join

I14 can't run on 5.4 at these dates, so this can't be tested directly. It compares two
things already on hand:

- **Predicted:** the ionosphere-free (2.5457 L1 - 1.5457 L2) phase-centre offset, I20
  minus I14, per antenna, from `ANTENNA_I20.PCV` and `ANTENNA_I14.PCV` in `$D/REF54`.
- **Measured:** each station's median Up residual across the 53 weekly Helmert
  comparisons with 5.2 production (`docs/phref_vs_production_comparison_results.md`,
  residual = production minus ours).

| Antenna, radome | Up, mm | East, mm | PHREF stations |
|---|---|---|---|
| TRM55971.00 NONE | -7.50 | 1.26 | LGYE |
| LEIAT504 NONE | -5.07 | 3.29 | ANTP, GUMA, MARK, MAUB, SPAB |
| LEIAR20 LEIM | -2.54 | 0.30 | BOST, BTU2, CBIM, CTNU, DGOS, GUES, LLOY, LORE, MAGU, MONT, PMPL, SQJR |
| TRM57971.00 NONE | -2.18 | 0.35 | ALAB, AURA, BLN2, BRGC, ELNA, MLPA, PNBO, POLI, SAPN |
| TRM59800.00 SCIS, TRM59800.80 SCIS | -1.72 | -0.14 | AIRA, DAEJ, MCIL |
| JAVRINGANT_DM NONE | -1.45 | -0.69 | DARW, PNGM |
| TRM115000.00 NONE | 1.55 | 0.74 | CAC2, CLAV, VIGN |
| TRM29659.00 NONE | 3.01 | 0.92 | TNDG |
| ASH701945C_M NONE | 4.80 | 3.58 | PIMO |
| TWIVC6050, TRM41249.00, LEIAS10, LEIAR25 LEIT, LEIAX1202GG | 0.00 | 0.00 | ALIC, LLOR, TCDR, PAGP, S01R, TGDN |

**Result, 40 stations with at least 20 weeks:**

- The sign is the one expected: a larger offset in I20 lowers our height, which makes
  production minus ours positive.
- Correlation 0.79, rank correlation 0.64. Without LGYE 0.74, and without LGYE and PIMO
  0.69.
- Removing the fitted effect cuts the between-station scatter of the median Up residual
  from 5.7 to 3.5 mm.
- The slope is 2.1, with a bootstrap 95% range of 1.4 to 2.7.

**Limits.**

- It's a correlation, on the August (unpatched) solutions.
- It uses offsets only, not elevation-dependent variations or satellite antennas.
- **A slope of 2.1 isn't explained.** A pure offset would give about 1. Troposphere
  correlation or the variations could raise it, but neither was tested. So use the table
  above as a guide to direction and relative size, not as a correction to apply.
- The six stations with no offset change still have a spread of residuals, so the
  antenna change isn't the whole story.

**What this means.** A series crossing from I14 to I20 will probably step by an amount
that depends on the antenna, so it likely needs a per-station offset, like an equipment
change. How to handle that is a decision for the team.

## Reproducing this

The result trees are on gps3 in `~/phref_attrib/results/` (`PHT0`, `PHTB`, `PHTP`, 45 MB),
moved out of `SAVEDISK` so they aren't mistaken for production. The temporary PCFs,
panel copies and environment file were removed from `$U` and `$C`, and production's files
were confirmed to match `config/bernese/gpsuser/`. The analysis scripts weren't committed.
To repeat the pre-patch run: unpack `~/BERN54-EXE_GNU-pre-patch-20260901.tar.gz`, write
`$C/LOADGPS_<name>.setvar` with `XG` pointing at it, and run `bernese-run-year` with
`HOST=<name>` and a PCF whose `V_RESULT` is a new tree. Sample `/proc/<pid>/exe` to confirm.
