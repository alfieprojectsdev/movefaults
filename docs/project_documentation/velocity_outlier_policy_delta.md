# Outlier policy and Luzon velocities: what changes, and what it does not

**Decision, 2026-08-13:** velocities published from this pipeline exclude
detected outliers from the fit (`exclude_outliers=True`, the default in
`pogf_geodetic_suite.timeseries.analysis`). This departs from the numbers
currently in circulation. This document is the delta, so the departure is
something the team decided rather than something a colleague discovers.

Regenerate at any time:

```bash
scripts/compare_velocity_outlier_policy.py --data <plotfiles-dir> \
    --check '<...>/Velocity_rover(regress)_10'
```

## What the MATLAB actually did

`vel_line_v8_newvelduetooffset_v4.m` calls `rmoutliers`, assigns the result to
`cleaned_d`, writes the flagged epochs to the `outliers` file — and then fits
the regression against the **raw** data. The mask is computed, reported, and
discarded.

This is not a small stylistic difference. It explains a step in the work
instruction that otherwise looks like busywork: the analyst is told to delete
outlier points by hand in the browser and re-run, because the automatic
detection never fed the fit. The manual step exists to compensate for a
one-line bug.

## Headline numbers

| | |
|---|---|
| Sites compared | 54 |
| Unchanged to the last decimal | 40 |
| Changed | 14 |
| Largest change, **horizontal** | **1.486 mm/yr** (NVY9, North) |
| Largest change, **vertical** | **10.830 mm/yr** (BSCS, Up) |

Horizontal and vertical are quoted separately deliberately. Tectonic
interpretation runs on the horizontal, and a single worst-case figure lets the
noisy Up component stand in for the whole result. **The horizontal change is
under 1.5 mm/yr everywhere.** Every site with no flagged epochs in its final
segment is identical to the last decimal — the policy is a no-op for 40 of 54
sites.

> **Correction to an earlier statement.** The `analysis.py` docstring and a
> summary given on 2026-08-12 put the maximum divergence at "up to 2.18 mm/yr
> (AR17, Up)". That figure came from a partial sample. The true maximum is
> **10.830 mm/yr at BSCS (Up)**, roughly five times larger. The horizontal
> figure was never wrong, and the conclusion does not change — but anyone who
> accepted "about 2 mm/yr" as the worst case was working from a number too
> small.

## Two findings that matter more than the outlier policy

### 1. Six sites publish a velocity fitted to days of data

Marked `!` in the table below: **BR14, CCA5, LUZD, MAGA, TARL, ZBS1**.

Each has an offset near the end of its record, so the final segment — the one
`final_velocity` reports and the one that gets published — contains 3 or 4
epochs spanning **0.01 to 0.10 years**. TARL's published East velocity is
2008.754 mm/yr. ZBS1's Up is -4086.944 mm/yr. These are not tectonic rates;
they are the slope of two days of scatter.

Both implementations agree exactly on these numbers, because both are doing the
same meaningless thing. **The outlier policy is irrelevant here — the fit is
disqualified by span, and no treatment of outliers rescues it.** They should be
suppressed rather than published, and the tool now flags them.

The 1-year threshold used for the flag is deliberately permissive. Blewitt &
Lavallée put the threshold for unbiased rates nearer 2.5 years once annual
signals are present, which several more sites in this table would fail.

### 2. The 2026-07-29 catalog edit silently corrupted five sites

Five sites fail to reproduce the published reference even with
`exclude_outliers=False`: **BR14, IFG1, KA08, LUZD, LUZH**.

That set is not arbitrary. It is *exactly* the set of sites carrying the
`2022.5695 EQ` event — the M7.0 Abra earthquake, northern Luzon, 27 July 2022:

```
BR14 2022.5695 EQ    IFG1 2022.5695 EQ    KA08 2022.5695 EQ
LUZD 2022.5695 EQ    LUZH 2022.5695 EQ
```

The reference file was generated 2026-07-09; the catalog gained this event on
2026-07-29. So the disagreement is **catalog drift, not an implementation
difference** — the two runs were given different information about the world.

The edit did something worse than change five numbers, though. At BR14 and
LUZD the new record was *appended* rather than inserted in date order:

```
BR14 2022.8159 EQ     <- existing
BR14 2022.5695 EQ     <- added 2026-07-29, earlier date, listed second
```

The MATLAB builds its segment bounds in file order. A descending range makes
its `for N=length(...)` loop never execute, leaving the **previous** segment's
design matrix `G` in place — so the regression silently fits stale timestamps
against current data. No error, no warning. BR14 and LUZD's published
velocities (-165.671 and -115.455 mm/yr East) are products of that defect.
`estimate_velocity` sorts segment bounds and is unaffected.

**Operational consequence: a velocity file is only interpretable alongside the
exact catalog that produced it.** Recording that pairing is precisely what the
provenance record is for.

## Full table

Sorted by largest absolute change. `n` = epochs in the final segment, `span` =
its length in years, `n_out` = flagged epochs within it. `repro` compares the
`exclude_outliers=False` branch against PHIVOLCS' published file. `!` marks a
final segment under one year.

| site | n | span | n_out | Ve pub | Ve new | dVe | Vn pub | Vn new | dVn | Vu pub | Vu new | dVu | repro |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| BSCS | 15 | 9.46 | 3 | -75.534 | -76.189 | -0.656 | 37.598 | 38.459 | +0.861 | 16.721 | 5.891 | -10.830 | ok |
| NVY9 | 10 | 9.64 | 2 | -69.864 | -70.640 | -0.775 | 25.312 | 26.798 | +1.486 | 11.556 | 1.980 | -9.576 | ok |
| LUN1 | 7 | 3.49 | 1 | -63.926 | -63.230 | +0.695 | 17.305 | 16.220 | -1.085 | -2.344 | 5.713 | +8.057 | ok |
| SMAT | 10 | 8.52 | 2 | -73.305 | -74.003 | -0.698 | 37.687 | 38.453 | +0.766 | 9.599 | 3.677 | -5.922 | ok |
| CRLN | 14 | 9.67 | 2 | -69.405 | -69.812 | -0.407 | 29.745 | 30.479 | +0.734 | 9.693 | 4.826 | -4.867 | ok |
| MRIK | 17 | 9.66 | 1 | -71.227 | -72.485 | -1.258 | 32.053 | 32.279 | +0.226 | 13.391 | 8.530 | -4.862 | ok |
| ISB4 | 16 | 9.67 | 3 | -75.480 | -75.845 | -0.366 | 38.120 | 38.749 | +0.629 | 9.997 | 6.070 | -3.927 | ok |
| ITGN | 13 | 9.65 | 2 | -75.302 | -76.322 | -1.020 | 18.308 | 18.617 | +0.309 | 2.152 | -1.229 | -3.382 | ok |
| KA08 | 12 | 9.61 | 1 | -71.985 | -71.998 | -0.013 | 36.193 | 37.126 | +0.933 | 14.447 | 11.104 | -3.343 | DIFF 2408.25138 |
| TRC3 | 15 | 9.67 | 2 | -57.922 | -58.029 | -0.107 | 13.878 | 14.289 | +0.412 | 5.496 | 2.449 | -3.047 | ok |
| ZBS3 | 14 | 9.64 | 2 | -57.417 | -57.612 | -0.195 | 10.256 | 10.532 | +0.276 | 1.291 | -1.001 | -2.292 | ok |
| AR17 | 17 | 10.77 | 1 | -73.447 | -73.690 | -0.243 | 32.955 | 33.295 | +0.341 | 15.389 | 13.208 | -2.181 | ok |
| NE21 | 15 | 9.69 | 2 | -63.436 | -63.464 | -0.028 | 16.683 | 16.757 | +0.074 | 1.194 | -0.123 | -1.317 | ok |
| SUAL | 17 | 11.39 | 1 | -60.732 | -60.792 | -0.060 | 13.077 | 13.190 | +0.113 | 6.266 | 5.433 | -0.833 | ok |
| ANQ0 | 12 | 9.67 | 0 | -74.537 | -74.537 | +0.000 | 38.699 | 38.699 | +0.000 | 30.926 | 30.926 | +0.000 | ok |
| AR30 | 14 | 10.75 | 0 | -67.046 | -67.046 | +0.000 | 25.199 | 25.199 | +0.000 | 4.266 | 4.266 | +0.000 | ok |
| BARA | 14 | 9.67 | 0 | -61.196 | -61.196 | +0.000 | 13.460 | 13.460 | +0.000 | 11.089 | 11.089 | +0.000 | ok |
| BGB1 | 21 | 18.03 | 0 | -72.165 | -72.165 | +0.000 | 27.974 | 27.974 | +0.000 | 5.826 | 5.826 | +0.000 | ok |
| BNBA | 19 | 10.15 | 0 | -65.825 | -65.825 | +0.000 | 21.791 | 21.791 | +0.000 | 5.984 | 5.984 | +0.000 | ok |
| BR14! | 6 | 0.10 | 0 | -165.671 | -165.671 | +0.000 | 118.327 | 118.327 | +0.000 | 38.905 | 38.905 | +0.000 | DIFF 69.08832 |
| BUCA | 36 | 19.03 | 0 | -47.457 | -47.457 | +0.000 | 18.472 | 18.472 | +0.000 | 5.773 | 5.773 | +0.000 | ok |
| BURG | 29 | 11.38 | 0 | -49.919 | -49.919 | +0.000 | 21.810 | 21.810 | +0.000 | 7.967 | 7.967 | +0.000 | ok |
| CCA5! | 3 | 0.01 | 0 | 202.953 | 202.953 | +0.000 | 241.296 | 241.296 | +0.000 | 2618.114 | 2618.114 | +0.000 | ok |
| CRIS | 14 | 19.10 | 0 | -72.199 | -72.199 | +0.000 | 25.283 | 25.283 | +0.000 | 3.596 | 3.596 | +0.000 | ok |
| CUYP | 18 | 9.00 | 0 | -62.195 | -62.195 | +0.000 | 14.438 | 14.438 | +0.000 | 11.280 | 11.280 | +0.000 | ok |
| DINA | 8 | 7.76 | 0 | -76.485 | -76.485 | +0.000 | 37.232 | 37.232 | +0.000 | 10.602 | 10.602 | +0.000 | ok |
| DIPA | 20 | 9.66 | 0 | -76.233 | -76.233 | +0.000 | 35.907 | 35.907 | +0.000 | 9.802 | 9.802 | +0.000 | ok |
| IFG1 | 8 | 9.60 | 0 | -70.861 | -70.861 | +0.000 | 31.231 | 31.231 | +0.000 | 14.022 | 14.022 | +0.000 | DIFF 2.03942 |
| ILN3 | 11 | 13.14 | 0 | -76.555 | -76.555 | +0.000 | 27.599 | 27.599 | +0.000 | 9.877 | 9.877 | +0.000 | ok |
| LAG1 | 22 | 10.58 | 0 | -57.552 | -57.552 | +0.000 | 16.090 | 16.090 | +0.000 | 1.478 | 1.478 | +0.000 | ok |
| LUBU | 9 | 5.05 | 0 | -70.329 | -70.329 | +0.000 | 30.963 | 30.963 | +0.000 | 19.065 | 19.065 | +0.000 | ok |
| LUN2 | 5 | 3.49 | 0 | -62.855 | -62.855 | +0.000 | 10.388 | 10.388 | +0.000 | -9.355 | -9.355 | +0.000 | ok |
| LUZA | 37 | 23.23 | 0 | -59.492 | -59.492 | +0.000 | 11.839 | 11.839 | +0.000 | 2.322 | 2.322 | +0.000 | ok |
| LUZC | 34 | 22.11 | 0 | -68.581 | -68.581 | +0.000 | 18.237 | 18.237 | +0.000 | 4.333 | 4.333 | +0.000 | ok |
| LUZD! | 3 | 0.10 | 0 | -115.455 | -115.455 | +0.000 | 21.818 | 21.818 | +0.000 | 329.197 | 329.197 | +0.000 | DIFF 129.61012 |
| LUZE | 26 | 20.24 | 0 | -68.956 | -68.956 | +0.000 | 20.671 | 20.671 | +0.000 | -0.250 | -0.250 | +0.000 | ok |
| LUZF | 39 | 22.61 | 0 | -72.368 | -72.368 | +0.000 | 29.677 | 29.677 | +0.000 | 7.729 | 7.729 | +0.000 | ok |
| LUZG | 36 | 23.20 | 0 | -75.596 | -75.596 | +0.000 | 38.792 | 38.792 | +0.000 | 7.064 | 7.064 | +0.000 | ok |
| LUZH | 30 | 23.19 | 0 | -82.189 | -82.189 | +0.000 | 37.336 | 37.336 | +0.000 | 8.152 | 8.152 | +0.000 | DIFF 0.12424 |
| MACR | 18 | 9.66 | 0 | -64.401 | -64.401 | +0.000 | 20.486 | 20.486 | +0.000 | 5.255 | 5.255 | +0.000 | ok |
| MAGA! | 4 | 0.01 | 0 | 411.788 | 411.788 | +0.000 | -37.280 | -37.280 | +0.000 | 3145.970 | 3145.970 | +0.000 | ok |
| N132 | 8 | 7.78 | 0 | -61.344 | -61.344 | +0.000 | 14.689 | 14.689 | +0.000 | -4.059 | -4.059 | +0.000 | ok |
| NVY2 | 17 | 10.73 | 0 | -74.545 | -74.545 | +0.000 | 35.529 | 35.529 | +0.000 | 8.103 | 8.103 | +0.000 | ok |
| NVY3 | 14 | 9.67 | 0 | -70.683 | -70.683 | +0.000 | 26.161 | 26.161 | +0.000 | 12.110 | 12.110 | +0.000 | ok |
| ODON | 10 | 6.69 | 0 | -57.352 | -57.352 | +0.000 | 13.243 | 13.243 | +0.000 | 6.438 | 6.438 | +0.000 | ok |
| PABL | 15 | 19.11 | 0 | -69.553 | -69.553 | +0.000 | 25.806 | 25.806 | +0.000 | 3.349 | 3.349 | +0.000 | ok |
| PANC | 16 | 9.62 | 0 | -81.300 | -81.300 | +0.000 | 28.310 | 28.310 | +0.000 | 14.210 | 14.210 | +0.000 | ok |
| QN42 | 31 | 20.15 | 0 | -50.772 | -50.772 | +0.000 | 30.898 | 30.898 | +0.000 | 11.149 | 11.149 | +0.000 | ok |
| QZN3 | 10 | 4.06 | 0 | -52.887 | -52.887 | +0.000 | 19.666 | 19.666 | +0.000 | 7.086 | 7.086 | +0.000 | ok |
| SISN | 16 | 9.64 | 0 | -64.200 | -64.200 | +0.000 | 15.706 | 15.706 | +0.000 | 7.675 | 7.675 | +0.000 | ok |
| SMDS | 15 | 9.46 | 0 | -73.454 | -73.454 | +0.000 | 35.956 | 35.956 | +0.000 | 16.576 | 16.576 | +0.000 | ok |
| SRQE | 15 | 8.52 | 0 | -64.270 | -64.270 | +0.000 | 17.585 | 17.585 | +0.000 | 11.102 | 11.102 | +0.000 | ok |
| TARL! | 4 | 0.01 | 0 | 2008.754 | 2008.754 | +0.000 | -1402.319 | -1402.319 | +0.000 | 1135.749 | 1135.749 | +0.000 | ok |
| ZBS1! | 3 | 0.01 | 0 | 1339.664 | 1339.664 | +0.000 | -1483.298 | -1483.298 | +0.000 | -4086.944 | -4086.944 | +0.000 | ok |

sites compared: 54   unchanged: 40   changed: 14
largest change, horizontal: 1.486 mm/yr at NVY9
largest change, vertical:   10.830 mm/yr at BSCS

FINAL SEGMENT UNDER 1 YEAR (6) -- marked ! in the table. These velocities are unusable regardless of
outlier policy; both implementations agree because both are fitting days of scatter:
  BR14 CCA5 LUZD MAGA TARL ZBS1
reproduces published (exclude_outliers=False): 49/54   MISMATCH: KA08 BR14 IFG1 LUZD LUZH

`DIFF` values in `repro` are the catalog-drift sites explained above, not
implementation error. The remaining 49 of 54 reproduce the published file to
better than 1e-4 mm/yr, which is the reference file's own precision.

## What to do with this

1. **Publish the `exclude_outliers=True` column.** It is the statistically
   defensible choice and what the MATLAB evidently intended.
2. **Suppress the six short-span sites** rather than publishing a number that
   is wrong by three orders of magnitude.
3. **Re-run BR14 and LUZD** — their published values come from the stale-`G`
   defect, and this pipeline already fixes it.
4. **Sort the `offsets` catalog by date** and keep it sorted. The out-of-order
   records are a live hazard to anyone still running the MATLAB.
