# Pilot: process one 1996 Luzon day with Bernese 5.4

**Status: proposed 2026-11-06. Nothing here has been run.** Every fact below was
read from gps3 or from AIUB's product description on that date. Anything not yet
known is listed as such.

## The question

Can Bernese 5.4 on gps3 process our 1990s observations, and how far is the result
from what was solved at the time?

One day answers most of it. The pilot doesn't start a reprocessing of the old
data, and it doesn't touch production's PCFs, reference files or results.

## Why this day

**1996 DOY 067 (7 March 1996, GPS week 843 day 4)** from the 1996 Luzon campaign:

```
/srv/gnss-archive/legacy/RECOVERED_HD-LBU2_WD20EARS_WCAZA4430660/toto_C/GPSR/1996 luzon/960307A/
```

- It has the most stations of the campaign: 14 RINEX 2 files. The campaign's 13
  days (`960307A` to `960319A`) have 10 to 14 each.
- It mixes our campaign marks with stations in the IGS20 frame.
- **It has a benchmark.** The folder holds the campaign as processed:
  `STA/FN960671.CRD` is the final solution, from Bernese 5.0, run on 10 April
  2009, in ITRF2005. All 14 stations are in it.
- Its orbit, clock and ERP files are still beside it (`ORB/igs08434.sp3`,
  `ORB/19960671.CLK`, `ORB/C04_1996.ERP`), so a product problem can be told from a
  processing problem.

| Station | Marker in file | Receiver | Antenna in file | Sampling (s) | In `IGS20.FIX`, with 1996 data |
|---|---|---|---|---|---|
| GUAM | GUAM | ROGUE SNR-8000 | DORNE MARGOLIN T | 30 | yes |
| PERT | PERT | ROGUE SNR-8100 | DORNE MARGOLIN T | 30 | yes |
| SHAO | SHAO | ROGUE SNR-8000 | DORNE MARGOLIN T | 30 | yes |
| TSKB | TSKB | ROGUE SNR-8100 | DORNE MARGOLIN T | 30 | yes |
| USUD | USUDA | ROGUE SNR-8000 | DORNE MARGOLIN T | 30 | yes |
| S01R | S01R | TRIMBLE 4000SSE | TRM14532.00 | 30 | no |
| TAIW | TAIWAN | ROGUE SNR-800 | DORNE MARGOLIN B | 30 | no |
| LUZA, LUZB, LUZE, LUZF, LUZL | same | TRIMBLE 4000SSE | TRM22020.00+GP | 15 | no |
| PLWN, VRC2 | same | TRIMBLE 4000SSE | TRM22020.00+GP | 15 | no |

Five reference stations is above the planner's minimum of three.

## How much data this could open up

File names with 1990s RINEX extensions under `/srv/gnss-archive`: 11,586, of which
10,191 names are unique. They run from 1991 to 1999. The largest groups are S01R,
TSKB, USUD, SHAO and GUAM. The `GPSR/` campaign trees hold 979 of them:

| Tree | Files | Tree | Files |
|---|---|---|---|
| 1995 leyte | 85 | 1998 luzon | 160 |
| 1996 luzon | 158 | 1999 luzon | 186 |
| 1997 luzon | 137 | 1999 masbate | 150 |
| 1997 masbate | 86 | `970530A`, `970531A` | 17 |

This is a count of names. None of these files has been quality-checked except by
reading the headers of this one day.

## What is ready, and what isn't

| Needed | State |
|---|---|
| Satellite table | Ready: `SATELLIT_I20.SAT` has GPS entries from 1978, 43 of them starting by 1995 |
| Satellite antennas | Ready: `ANTENNA_I20.PCV` includes Block I |
| Satellite problem file | Ready: `SAT_1996.CRX` is in `GLOBAL/CONFIG` |
| Receiver antennas | Ready under their IGS names: `AOAD/M_T`, `AOAD/M_B`, `TRM14532.00` and `TRM22020.00+GP` are in `ANTENNA_I20.PCV` |
| RINEX 2 | Ready in format: production already reads RINEX 2 |
| Orbits, clocks, ERP, biases | **Not on gps3.** CODE's `REPRO_2020` lists `COD0R03FIN_*` files for each day, with GPS orbits since 1994 |
| Satellite clocks | **Unknown.** AIUB describes 30 s clocks from 2000. What exists for 1996 has to be read from the files, and Selective Availability was on until May 2000 |
| Ionosphere map | **Unknown.** `REPRO_2020`'s description lists no `GIM.ION` file, and production's `COD0OPSFIN` set has one |
| Station information | **To write.** Only GUAM, PERT, PLWN and S01R are in `LUZON.STA`, and marker and antenna names need mapping |
| Ocean loading | **To obtain.** Of the 14, only PLWN and S01R have blocks in `LUZON.BLQ` |
| Atmospheric loading | **To check** per station, since the plan refuses a station with no ATL block |
| Receiver table | **To check:** whether 5.4 knows the ROGUE and 4000SSE entries |

## The two configurations to compare

`REPRO_2020` is in the IGSR3 frame with its own antenna file, not IGS20. The IGS
describes `igs20.atx` as a minor update of `igsR3.atx`, and neither source gives
its size for our stations. So the pilot runs the day twice:

- **A, consistent with the products:** `V_PCV=R20`, CODE's `ANT_COD_R20.PCV`,
  `SATELLIT_R20.SAT`, and the IGSR3 fiducials from `IGS14R3.SNX`.
- **B, the frame we want:** `V_PCV=I20`, `V_REFINF=IGS20`, with the same orbits.

A runs first, so a failure there can't come from mixing the two. The difference
between A and B is the first measurement of what that mix costs.

## Steps

Before starting: production idle, the BPE lock free, and only one BPE at a time.
Stop at any step that fails, and write down what it said.

1. **Download.** From `REPRO_2020`: `CODE/1996/` for DOY 067 (orbit, ERP, bias,
   clock), plus `BSWUSER54/REF` and `BSWUSER54/CONFIG`. A test request from gps3 to
   AIUB's page on 2026-11-06 returned nothing usable, so this may need another
   route. The product's use has to be acknowledged in anything published (reference
   in `docs/bern52/AIUB_AFTP.TXT`).
2. **Copy, don't move.** Copy the 14 RINEX files out of the recovered tree into
   `$D/LEG96`, and leave the tree unchanged.
3. **Write the campaign's own files:** `LEG96.STA`, `.ABB`, `.CRD`, `.BLQ` and
   `.ATL` in `$D/REF54`. Don't edit the `LUZON` or `PHNAT` files. Map
   `DORNE MARGOLIN T` to `AOAD/M_T` and `DORNE MARGOLIN B` to `AOAD/M_B`, and
   markers `USUDA` and `TAIWAN` to their codes. `STA/ABBREV.ABB` in the old campaign
   has its abbreviations, and `STA/FN960671.CRD` gives a priori positions.
4. **Create the campaigns and write the PCFs.** Create `$P/LEG96A` and `$P/LEG96B`.
   `derive_luzon_pcf.py` hardcodes LUZON's values, so copy stock
   `RNX2SNX.PCF` by hand to `LEG96A_DLY.PCF` and `LEG96B_DLY.PCF`, with
   `V_CRDINF`, `V_STAINF`, `V_BLQINF`, `V_ATLINF`=`LEG96`, `V_RNXDIR=${D}/LEG96`,
   `V_RESULT=${S}/LEG96A/$Y+0` (or `LEG96B`), `V_ORB` and `V_ORBDIR` for the
   products, `V_SATSYS=GPS` and `V_DEL=N`.
5. **Plan, from the production checkout:**

   ```bash
   cd ~/repos/mf_run
   source ~/BERN54/LOADGPS.setvar
   .venv/bin/bernese-run-year --campaign LEG96A --repr-prefix LGA --year 1996 \
       --from 67 --to 67 --pcf LEG96A_DLY --plan
   ```

   Its findings about the station files are the first real test of step 3.
6. **Run A,** with the same arguments and `--run` under `setsid nohup`, logging to
   `~/leg96a.log`. A LUZON day took about 5.5 minutes in August on a larger network.
7. **Run B** the same way, as `LEG96B` with prefix `LGB`.
8. **Compare.** See below.
9. **Record** in a results note, whatever happened, and add any new failure to
   `config/bernese/bpe_errors.yaml` as `proposed`.

## How to read the result

- **Did it finish?** Which step stopped it, with the message. Stations in the final
  solution, out of 14.
- **Against the 2009 solution:** `FIN_19960670.CRD` against `FN960671.CRD`, by
  7-parameter Helmert, as in `docs/phref_vs_production_comparison_results.md`. Bernese
  version, frame, antenna model and products all differ, so this is an agreement
  test. No pass mark is set in advance. Look for the size, and for any one station
  standing apart.
- **A against B:** the same comparison between the two runs.

| Outcome | What it means | Next |
|---|---|---|
| Stops before the BPE | Station files or products incomplete | Fix the file and re-run; this is the expected first result |
| Stops in `CODSPP` or preprocessing | Sparse clocks, Selective Availability, or the receiver table | Try the campaign's old clock file to tell which |
| Finishes without the campaign marks | Their files or data are the problem, and the old network is too sparse to tell | Check those marks' data before anything else |
| Finishes with all 14, near the 2009 solution | 5.4 can process this era | Try the rest of the 13 days, then ask whether reprocessing is worth doing |
| Finishes, far from the 2009 solution | Could be any of the differences | Separate them before trusting either |

## Decisions needed first

1. **Ocean loading.** The five LUZ marks, VRC2, TAIW and possibly the fiducials need
   BLQ blocks. `FES2014b.BLQ` in `REPRO_2020` may cover the fiducials. The rest would
   come from a request to an outside loading service, which sends those stations'
   positions outside PHIVOLCS. That needs the maintainer's go-ahead.
2. **Whether the frame for old data has to match production.** B assumes it does.

## Not in this pilot

- Files from before 1994, where `REPRO_2020` has no GPS orbits. That includes the 36
  files from 1991.
- Changing any published series, or how the IGS14/I14 and IGS20/I20 series join
  (`docs/SETTLED.md` §6).
- Adding the campaign to the console. It stays out of the console's campaign list, so
  the console doesn't change.
