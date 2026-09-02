# PHREF 2025 vs PHIVOLCS production — results

*Run 2026-09-01 on the unpatched BSW 5.4 build (release `2024-11-11`, none of
its 7 fixes applied), which is the build that produced the 360 daily solutions.
Method and its justification: `phref_vs_production_comparison_plan.md`.*

## What was compared

| | ours | theirs |
|---|---|---|
| software | BSW **5.4**, Linux, R740 | BSW **5.2**, Windows |
| cadence | 360 daily NEQ, stacked to weekly | weekly, as retained |
| stations | 33–41 | 93 |
| weeks | 53 | 53 |

**53 of 53 weeks compared. No week lacked a counterpart.** 1,979 station-week
residuals in total.

This is an **agreement test, not a reproduction test** — different version,
network and constraints. It cannot be bit-for-bit and is not presented as such.

## Headline

Post-Helmert residuals, per week, across all 53:

| component | median | mean | min | max |
|---|---|---|---|---|
| **North** | **1.29** | 1.36 | 0.67 | 2.38 |
| **East** | **2.37** | 2.75 | 1.57 | 6.47 |
| Up | 7.09 | 7.31 | 5.84 | 10.25 |
| **horizontal** | **2.77** | 3.10 | 1.80 | 6.73 |

mm. **The two independent solutions agree horizontally at the few-millimetre
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
already-tight mean. **8 weeks of 53 have any rejection at all**, and every
rejected station is named in the per-week output.

The threshold was **not tuned to improve the result**. GUMA survives in WK_2370
at 32 mm (3.5σ against σ=9.2) and is reported as retained-but-notable rather
than quietly removed.

## What this does not establish

- **Nothing about the patched build.** B_33 changes the geomagnetic model and
  B_38 touches `TRPSTORE` on the GPSEST/ADDNEQ2 path. This result belongs to
  release `2024-11-11` **unpatched**, and must be re-run after patching.
- **Nothing about the 58 stations we do not process.** Overlap is complete in
  one direction only: all of ours are in hers, not the reverse.
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
