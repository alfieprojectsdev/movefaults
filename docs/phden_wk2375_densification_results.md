# Densification trial, GPS week 2375 — results

*Run 2026-09-30 to 2026-10-01 on gps3, BSW 5.4 (locally compiled, 2024-11-11
patches applied). Campaign `PHDEN`. Compares a network matched to PHIVOLCS
production's station set against production's own weekly solution, and against
our 35-station PHREF network.*

## The question

`phref_vs_production_comparison_results.md` compared our ~35-station PHREF run
with production's ~91-station weeklies and could not separate two causes of the
difference: the software (5.4 vs 5.2) and the network (35 vs 93 stations). This
trial removes the network difference for one week: the same 93 stations
production used in `WK_2375` (2025 DOY 194–200), processed by us.

## What was matched, and what was not

| | ours (PHDEN) | production (`WK_2375`) |
|---|---|---|
| stations | the 93 in `WK_2375` | 93 |
| software | BSW 5.4, Linux | BSW 5.2, Windows (`PHIVOL_REL.PCF`) |
| reference frame / antenna model | **IGS20 / I20** | **IGS14 / I14** |
| orbits | CODE final (`COD0OPSFIN`) | `IGS`-prefixed, product not confirmed |
| troposphere | `DRY_GPT3` + Chen-Herring gradients | `DRY_GMF` + Chen-Herring gradients |
| elevation cutoff / weighting | 3°, `COSZ` | 3°, `COSZ` |
| datum | minimum constraint, translation only, 0.1 mm | same scheme |
| fiducials passing the daily check | 10–11 (6 on DOY 199 before the fix below) | 2–3 (ALIC, MCIL, DARW/PERT; DOY 082–086) |
| MAXPAR (final / preliminary) | 6000 / 4000 | 6000 / 4000 |

Frame and antenna model were **kept at ours deliberately** (Alfie, 2026-10-01),
so a systematic offset is expected and is absorbed by the Helmert alignment.
Production settings are as read from gps2's `GPSUSER52` panels on 2026-09-29.

## Data

642 of 651 station-days (93 × 7). The nine missing exist nowhere on gps3 or
gps2: BTNG, PMAT, TGDN, TNML one day each; LABO has 2 of 7. 37 files came from
gps2's `DATAPOOL\RINEX3` (BASC CLAV CUSV NTUS PERT MCIL), the rest from gps3's
datapool and archive. Every file's source path is recorded in
`$D/PHDEN/MANIFEST_PHDEN_wk2375.sha256`.

Ocean-loading coefficients for BTNG, PERT, SHAO and TNML did not exist anywhere
(BSW 5.4 stops on a missing station; 5.2 evidently does not). They were
computed by the Onsala service with the existing file's settings — FES2004,
CMC NO, Gutenberg-Bullen — on 2026-09-30.

## Results

### Daily runs

Seven days, 89–92 stations each in the final solution, datum RMS 5.5–7.6 mm.
A single day took 14 min; six days in parallel took 42.5 min.

### Against production's weekly (post-Helmert, mm)

| | used | N | E | U | horizontal |
|---|---|---|---|---|---|
| **PHDEN, 93 stations** | 92 of 93 | **1.38** | **1.71** | **6.62** | **2.20** |
| PHREF, 35 stations (for comparison) | 35 of 35 | 1.90 | 5.47 | 7.39 | 5.79 |

The one rejected station is LGYE (34 mm East), whose intermittent East
excursions through 2025 are already an open item in `SETTLED.md` §6.

MILA and MSBT sit **+20 and +27 mm Up** against production — the only two with
an Up difference that large. Both are Trimble 5700 / TRM41249 with 0 m antenna
height in our station file; production's height records for them have not been
compared. Open.

### Day-to-day repeatability (precision, not accuracy)

`scripts/coord_repeatability.py`, scatter of each station about its own mean
over DOY 194–200:

| | stations | median N | median E | median U |
|---|---|---|---|---|
| PHDEN, the 35 PHREF stations | 35 | **1.8** | **1.7** | **5.9** |
| PHREF, same 35 stations, same days | 35 | 2.1 | 2.3 | 7.0 |
| PHDEN, the 58 added stations | 58 | 1.6 | 1.8 | 6.5 |

27 of the 35 shared stations repeat better in the denser network. The added
stations are as precise as the original ones; densifying did not bring in a
noisy tail. Worst horizontal repeatability: LGYE (71.8 mm E, known), NAUJ,
SOGO, ALCO, IBAZ (6–8 mm).

## What this establishes

1. **Most of the PHREF-vs-production difference was the network, not the
   software.** Matching the station set brings horizontal agreement from 5.79 to
   2.20 mm RMS for this week, with frame, antenna model, orbits and troposphere
   still different.
2. **The denser network is also more precise** on the stations both share.
3. **The vertical difference (~6.6 mm) did not move** with the network, which
   is consistent with the frame/antenna-model/troposphere differences that
   remain.

One week, one comparison. This is an agreement test, not a reproduction test,
and it is not a statement about 2025 as a whole. Production is reprocessing
2025 on gps2 (late September 2026), so its `WK_2375` may be superseded.

## Defects found on the way

Each is recorded where it belongs; listed here so the trial's history is in one
place.

- **MILA's a priori coordinate was 97 m wrong** in `PHNAT.CRD` (inherited from
  production's `WK_2405.CRD`, February 2026). Every other station was within
  0.44 m. Six days recovered; on DOY 199 a weak network link (AROY had 332
  rejected observations) routed MILA through a 58 km baseline whose ambiguities
  resolved only 11 %, and MILA and MSBT floated ~10 m. Fixed in `PHDEN.CRD`
  only, from production's `WK_2375` position propagated with MILA's velocity;
  DOY 199 rerun resolved 94 %. `PHNAT.CRD` is unchanged because PHREF shares it.
  The daily datum check cannot see this for a station that is not a fiducial,
  and weekly stacking does not reject a bad day.
- Three reference-file traps, all reported by Bernese as NOT FOUND:
  `SETTLED.md` §2 (BLQ after `$$ END TABLE`; ATL header must equal the `.CRD`
  name; BLQ column alignment). `scripts/check_ref_coverage.py` (PR pending)
  checks for all three before a run.
- A long run launched as a tool's background job was killed at its time limit,
  orphaning the BPE workers. Long runs are now launched with `setsid nohup`.

## Open

- MILA / MSBT +2–3 cm Up against production: compare antenna heights with
  production's current `PHIVOLCS.STA`.
- Is production's February 2026 MILA a different monument, or an error? A
  question for the processing team.
- Repeat for more weeks before drawing conclusions for 2025.

## Reproduce

```
scripts/check_ref_coverage.py --pcf PHDEN_DLY --stations <WK_2375 site list>
perl $U/SCRIPT/phden_pcs.pl 2025 1940 PHDEN_DLY 7 6     # launch with setsid nohup
STACK_TEMPLATE=~/phden-weekly/ADDNEQ2_template.INP STACK_CAMP=PHDWK \
  STACK_SRC=$S/PHDEN/2025/SOL STACK_OUTDIR=~/phden-weekly \
  scripts/stack_phref_weekly.sh 2375 2375
scripts/compare_weekly_solutions.py --ours ~/phden-weekly/WKG_2375.SNX --theirs WK_2375.SNX
scripts/coord_repeatability.py '<FIN_*.SNX.gz for DOY 194-200>'
```

`phden_pcs.pl` and the `PHDEN.*` reference set live on gps3 under `$U` and
`$D/REF54`, which are not version-controlled.
