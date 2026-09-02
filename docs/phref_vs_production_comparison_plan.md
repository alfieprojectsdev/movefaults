# Comparing the PHREF 2025 reprocessing against PHIVOLCS production

*Drafted 2026-08-29 while the run was at 309/359. Survey done; execution
deferred to completion.*

## The comparison that was assumed, and why it is not available

The plan had been "compare our daily solutions against Cass's daily solutions".
**There are no 2025 daily solutions on the file server.**

`\\192.168.48.99\Bernese\GPSDATA\CAMPAIGN52\PHIVOLCS\SOL` holds 2,160 files.
Daily `F1_` solutions are retained only for **2012, 2015, 2016, 2017, 2019 and
2026**. For 2025 what survives is:

| product | count | coverage |
|---|---|---|
| `WK_2347` – `WK_2399` weekly `.SNX` + `.NQ0` | **53 / 53 weeks** | complete, no gaps |
| `MO_2501` – `MO_2512` monthly `.SNX` + `.NQ0` | 12 / 12 months | complete |
| `F1_` daily | **0** | not retained |

So the comparison has to happen at **weekly** cadence. That is not a downgrade —
53 points across the year is ample — but it means an extra step on our side that
the naive plan did not include.

## Station overlap: complete

`WK_2375.SNX` (DOY 195–200) carries 93 stations. Our DOY 200 solution carries
33. **All 33 are in hers; none of ours is absent from hers.** Every station we
solve is directly comparable.

## Required step: stack our dailies into weeklies

Our run produces daily `FIN_2025DDD0.NQ0`. Hers are 7-day combined normal
equations. Comparing a daily against a weekly compares different quantities —
the weekly is more precise by roughly √7 and has different datum handling.

So: combine our daily NQ0s into weekly NEQs with ADDNEQ2, on the same GPS-week
boundaries she used (`WK_nnnn` = GPS week nnnn, Sunday–Saturday), then compare
weekly-to-weekly.

## The comparison must be Helmert-aligned, not differenced

A direct coordinate difference is meaningless here. The two solutions realise
their datum differently:

- hers: BSW **5.2**, 93 stations, her own constraint set
- ours: BSW **5.4**, 33–38 stations, multi-station minimum constraint

Different network geometry and different constraints produce a different frame
realisation, so raw XYZ differences would be dominated by translation, rotation
and scale that carry no information about whether our processing is sound.

The procedure:

1. Take common stations for the week.
2. Estimate a 7-parameter Helmert transformation (3 translation, 3 rotation,
   1 scale) from ours onto hers.
3. **Report the Helmert parameters** — they quantify the frame offset, and a
   large scale or rotation is itself a finding.
4. **Report post-fit residuals per station**, rotated into local North/East/Up.
   These are the actual agreement.

## What each outcome would mean

| residual pattern | reading |
|---|---|
| few mm, no spatial structure | the port reproduces production within noise |
| systematic in Up only | troposphere or ocean-loading model difference (5.2 vs 5.4) |
| systematic and spatially organised | network-geometry effect from our smaller station set |
| one or two stations far out | station-specific metadata — check `.STA`, antenna, BLQ |

## This is an agreement test, not a reproduction test

It cannot be bit-for-bit and should not be presented as though it could:
different Bernese version, different station set, different a priori
coordinates, different constraints. The question it answers is **"do the two
independent solutions agree to within the precision either of them claims?"**

If they do, the port is validated for production use. If they do not, the
residual structure localises the cause.

## Order of work

1. Finish the year (359 days).
2. Full-year verification: every DOY present, station counts, file sizes.
3. Stack dailies into 53 weekly NEQs.
4. Fetch her 53 `WK_*.SNX` — **after** the BPE is idle. Bulk transfer and a
   running BPE must not overlap (`~/HANDOVER.md` §4).
5. Helmert + residuals per week.
6. Write up, including the weeks that disagree.

## Open questions for Cass

- Which stations does she constrain, and how? Our datum handling differs and
  that difference will show up in the Helmert parameters.
- Were the 2025 dailies deleted deliberately, or are they on another volume?
  Weekly comparison works, but dailies would let us compare like-for-like.
