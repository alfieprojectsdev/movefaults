# PHREF 2025 vs PHIVOLCS production — results

*Run 2026-09-01 on the unpatched BSW 5.4 build (release `2024-11-11`, none of
its 7 fixes applied), which is the build that produced the 360 daily solutions.
Method and its justification: `phref_vs_production_comparison_plan.md`.*

## What was compared

| | ours | theirs |
|---|---|---|
| software | BSW **5.4**, Linux, R740 | BSW **5.2**, Windows |
| cadence | 360 daily NEQ, stacked to weekly | weekly, as retained |
| stations | 33–41 per day; ~35 per week | 93 in `WK_2375` (2025 weeks: 87–95, median 91) |
| weeks | 53 | 53 |

**53 of 53 weeks compared. No week lacked a counterpart.** 1,979 station-week
residuals in total.

This is an **agreement test, not a reproduction test** — different version,
network and constraints. It cannot be bit-for-bit and is not presented as such.

## Headline

Post-Helmert residuals, per week, across all 53:

| component | median | mean | min | max |
|---|---|---|---|---|
| **North** | **1.26** | 1.32 | 0.67 | 2.38 |
| **East** | **2.28** | 2.43 | 1.57 | 6.47 |
| Up | 6.99 | 7.26 | 5.84 | 10.25 |
| **horizontal** | **2.70** | 2.79 | 1.80 | 6.73 |

mm. *Revised 2026-10-11: the outlier test now uses local North/East instead of
ECEF X/Y (see "Why outlier rejection was necessary"). The first version read
1.29 / 2.37 / 7.09 / 2.77 median and 3.10 mean horizontal; 7 of 53 weeks
changed, all by rejecting a station the old test kept.* **The two independent solutions agree horizontally at the few-millimetre
level in every week of 2025.** Vertical at ~7 mm is the expected GNSS
asymmetry, not a defect.

For a port between two Bernese versions on two operating systems with a
station set less than half the size, this is a strong result.

## The Helmert parameters are not incidental

A raw difference would have been meaningless. Typical values (GPS week 2375):

```
T = (-58.5, -3.0, -56.9) mm     scale -1.78 ppb
R = (-0.001, 0.048, -0.587) mas
```

The ~6 cm translation is the datum realisation differing between a 93-station
constrained solution and our 35-station one. Scale under 2 ppb (≈11 mm over an
Earth radius) and rotations under 0.6 mas mean there is **no systematic
geometric distortion** between the two — only an origin offset, which is
exactly what different constraint sets produce and carries no information about
processing quality.

## The one real finding: an East-only signature

**0.9% of station-weeks (18 of 1,979) exceed 15 mm horizontal. 17 of those 18
are East-dominated** (|E| > |N|). Overall RMS across all station-weeks is
**N 1.86 mm vs E 7.47 mm** — East is four times North.

That asymmetry is a signature. Real site motion, a coordinate offset or a
metadata error would not select the East component this strongly; **ambiguity
resolution does**, and East is the component most sensitive to it in a network
of this geometry.

Contributing sites:

| site | weeks > 15 mm | pattern |
|---|---|---|
| **LGYE** | **11 of 53** | alternating sign, **stops after WK_2375** |
| TGDN | 3 | East |
| GUMA | 2 | includes **-281 mm** in WK_2352 |
| VIGN, POLI | 1 each | — |

**LGYE** is the one to act on: `+18 -19 +20 -26 -19 -26 +44 +76 +61 -31 +30` mm
East across weeks 2347–2375, then nothing for the rest of the year. The
**alternating sign rules out a coordinate offset and rules out real
deformation**, both of which are one-directional. An intermittent
ambiguity-fixing problem that ends mid-year fits; so would an equipment or
firmware change around July 2025.

Note for anyone tempted by geology: LGYE is at Legazpi, beside Mayon. That
makes a volcanic story attractive and it is **not supported** — the sign
alternates, and LGYE's median across all 53 weeks is **3.60 mm**, entirely
normal. A single week (2375, +30 mm East) is what first drew attention, and the
population contradicted the impression the sample gave.

**GUMA in WK_2352 at -281 mm East** is a separate, single-week event, and it
was doing real damage: unrejected, it dragged the whole week's fit to E RMS
**46.77 mm**. Rejecting that one station brings the same week to **2.54 mm**.

## Why outlier rejection was necessary, and how it is bounded

The first pass fitted all common stations. AIUB document the failure mode for
their own `HELMR1`: *"if one of the stations has an exceptionally wrong
coordinate, the residuals for all stations may exceed the thresholds."* That is
precisely what WK_2352 showed — ANTP, PIMO and LGYE all looked elevated purely
because GUMA was dragging the transformation.

The fit is now iterative, rejecting at **4σ or 15 mm, whichever is larger**, so
a very clean week does not begin discarding good stations for being 4σ from an
already-tight mean. **14 weeks of 53 have any rejection at all**, and every
rejected station is named in the per-week output.

**The test is on local North/East.** Until 2026-10-11 it used ECEF X and Y,
which at these latitudes carry most of the vertical, so σ was inflated by the
Up scatter: WK_2370's σ came out at 9.2 mm on a week whose horizontal RMS is
nearer 3. That is why GUMA (33 mm East) survived in WK_2370, and why LGYE
(30 mm East) survived in WK_2375 while the PHDEN comparison of the same week
rejected it. With North/East, 6 more weeks reject LGYE, WK_2370 also rejects
GUMA, and WK_2388 rejects POLI. Week-level changes, before → after
(horizontal mm): 2347 3.60 → 2.08, 2351 4.61 → 2.31, 2357 4.40 → 2.80,
2370 6.31 → 3.02, 2373 6.05 → 2.76, 2375 5.79 → 2.58, 2388 3.90 → 2.70.

The threshold itself (4σ or 15 mm) was **not changed or tuned**; only the
components it is applied to.

## What this does not establish

- **Nothing about the patched build.** B_33 changes the geomagnetic model and
  B_38 touches `TRPSTORE` on the GPSEST/ADDNEQ2 path. This result belongs to
  release `2024-11-11` **unpatched**, and must be re-run after patching.
- **Nothing about the 58 stations we do not process.** Overlap is complete in
  one direction only: all of ours are in hers, not the reverse. Measured
  2026-09-24 for `WK_2375`: we hold 2025 RINEX for 53 of those 58 in the
  PHIVOLCS datapool archive, and only 4 of them are in NAMRIA's `PGN.CRD`. The
  gap is network selection, not missing data and not PAGENET.
- **Nothing about velocities.** This compares coordinates. Whether the velocity
  fields agree is a separate question on a longer baseline.
- **The vertical is not diagnosed.** ~7 mm is unsurprising, but no attempt was
  made to separate loading, troposphere and datum contributions.

## For Cass

1. **LGYE** shows intermittent East excursions up to 76 mm in 11 of 53 weeks of
   2025, alternating in sign, ceasing after mid-July. Worth checking against
   the site log for an equipment or firmware change around then.
2. **GUMA, week 2352** (DOY 057–063): -281 mm East in the production weekly.
3. **TGDN** — three weeks above 15 mm, also East.
4. Her `WK_2375` spans DOY **195–200**, not the full 194–200 week. Our stacks
   were matched to her span where it differs.

## Reproducing this

```bash
scripts/stack_phref_weekly.sh 2347 2399        # 360 dailies -> 53 weeklies
scripts/compare_all_weeks.sh                   # 53 Helmert comparisons
```

Per-week detail, including every station's N/E/U residual and any rejection,
is written to `~/weekly-comparison/WK_<gpsweek>.txt`.
