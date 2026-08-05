# Reprocessing the LUZON network under Bernese 5.4

**Written:** 2026-08-05, on gps3, after the Bernese 5.2 LUZON set was copied off
the DOSTB drive to `/srv/gnss-archive/processed/luzon-bern52/`.

**Goal**, in the user's words: *"i-reprocess ko sa GPS3 under Bernese 5.4 for
comparison ng results / adjustment (fine tuning) ng PCF."* Reprocess Abegail's
LUZON network under 5.4, reproduce her 5.2 numbers, and only then tune.

**Status: not yet run.** Everything below about *inputs* is measured on gps3.
Everything about *execution* is untested — §5 lists what only a run will settle.

**Revised 2026-08-05** after the T420 session found the reference solutions in
`SAVEDISK/`. §1.1 replaces an earlier conclusion that they did not exist; §1.1a
adds a gap that neither session had spotted. If you read an earlier version,
re-read §1 — the plan changed.

---

## 1. Read this before planning a run

Two findings from surveying the copied set change the shape of the exercise.
Both would have cost days if met mid-run.

### 1.1 The reference solutions exist — in `SAVEDISK/`, not in the campaign

> **This section was wrong on 2026-08-04 and is corrected here.** The first
> version concluded that no reference solutions existed for the raw RINEX,
> because `CAMPAIGN/LUZON/SOL/` contains none. That is true of *that directory*
> and false of the dataset. The T420 session found them in `SAVEDISK/`.

**Verified on gps3, 2026-08-05:**

```
GPSDATA/SAVEDISK/2025/SOL/   730 files, 365 distinct DOYs
                             F1_25<DDD>0.NQ0.gz and .SNX.gz
DOY 121-151 window:          31 of 31 days present
```

| Asset | Coverage |
|---|---|
| `DATAPOOL/LUZON/` raw RINEX | 2025 DOY **121–151** (31 days, 24–25 stations) |
| `SAVEDISK/2025/SOL/` daily finals | **all 365 days of 2025**, gzipped |
| `CAMPAIGN/LUZON/SOL/` | only DOY 029–033 and 2026 106–110 — the last run's leftovers |

**Why the campaign directory looked empty.** Bernese put the results where it is
configured to put them: `PHIVOL_REL.PCF` runs `902 R2S_SAV` to archive into
`SAVEDISK`, then `903 R2S_DEL` to clean the campaign. A campaign holding only
the most recent days is **normal operation, not a truncated delivery.**

**So the usable window is 31 contiguous days — 2025 DOY 121–151 — starting from
raw RINEX.** That is materially better than the `OBS/` fallback: it exercises
`RXOBV3`, station matching and QC, the stages the readiness doc calls the real
risk area. **This exercise can therefore produce BRN-001 acceptance evidence**,
which the `OBS/` path could not.

> **How three careful passes all missed it**, since the remedy generalises:
>
> 1. **T420, 08-03** — recorded the RINEX DOY range and the `F1_` filenames in
>    two separate inventories, never compared them.
> 2. **gps3, 08-04** — compared them, found no overlap, concluded no reference
>    existed. Right about `CAMPAIGN/LUZON/SOL`, wrong about the dataset.
> 3. **T420, 08-05** — looked in `SAVEDISK`. They were there all along.
>
> The question that short-circuits all three is not *"what is in this
> directory?"* but ***"where does this software put finished solutions?"*** —
> answerable from `PHIVOL_REL.PCF`, which both sessions had already read. Its
> `902 R2S_SAV` / `903 R2S_DEL` pair says exactly this, and both of us listed
> those PIDs while checking script availability without asking what they do.
>
> A new member of the §15.5 family: **a conclusion about a dataset drawn from
> one directory of it.**

### 1.1a Seven fiducial stations are NOT in the local RINEX

Reproducing her solution needs her network, and it is larger than the DATAPOOL:

```
F1_251210.SNX     30 stations
DOY 121 RINEX     24 stations
missing           AIRA ALIC BASC DAEJ DARW MCIL PNGM
```

These are IGS fiducials. Their only observations in the copied set are converted
`.CZH/.CZO` files for **DOY 029** — the older campaign block — so there is
nothing for DOY 121–151. `DATAPOOL_IGS/` holds 94 files, all `.sp3`/orbit
products, **no observation data**.

**This is the same gap as one of the missing scripts.** `FTP_DWLD` — absent from
the 5.4 install (§3.1) — is precisely the step that downloaded these. Its absence
and this gap are one problem, not two.

**Consequence:** a run from local RINEX alone processes 24 stations against a
30-station reference. Coordinates would differ for legitimate
network-geometry reasons, and the comparison would be measuring the wrong thing.

**Fix before running:** fetch the seven fiducials' RINEX for 2025 DOY 121–151
from CDDIS/IGN. The repo already has a downloader — `pogf-geodetic-suite`'s
`igs-downloader` (deliverable 2.2, partial: needs IGS20 naming and mirror
fallback). ~7 stations × 31 days is a small fetch. **Do this before staging
anything**, because it determines whether the comparison is well-posed at all.

### 1.2 If you ever take the `OBS/` path instead — what it does and does not test

*Retained for reference. §1.1 means this is no longer the path you have to take,
but the reasoning applies to any run started from converted observations.*

Starting from converted `OBS/` rather than from RINEX means **`RXOBV3` never
runs**. This exercises the **estimation chain only**, not the full pipeline.
That cuts both ways:

| | |
|---|---|
| **Better** for PCF tuning | one less stage of confounders between input and result |
| **Worse** as a pipeline test | exercises none of the RINEX ingest, station matching or QC that the readiness doc identifies as the real risk area |

**A run started from `OBS/` is therefore not the BRN-001 acceptance test.**
(A run from RINEX, per §1.1, can be.) That test — *"one PAGENET
session end-to-end on gps3, clearing the station/MAXPAR/panel problems
automatically, not by hand"* — is a different exercise on different data, and it
remains outstanding. Two things are easily conflated here, so state it plainly:

> **A green LUZON comparison does not constitute pipeline acceptance.**

Reading it as such would be the same defect this project keeps finding — a check
reporting success without having inspected the thing it is supposed to be about.

### 1.3 Use the contiguous 31 days

~~Pick one of two disjoint five-day blocks~~ — **moot after §1.1.** Use 2025 DOY
121–151: contiguous, 31 days, one IGS product vintage, one station set, raw
RINEX with a reference solution for every day.

Thirty-one days is also enough signal to separate an I14→I20 model shift from a
genuine tuning effect, which five days would not have been. §1.4's discipline
still applies, but it is no longer fighting a thin sample.

**Start with a single day — DOY 121** — before committing to the run.

### 1.4 The comparison is invalid unless the models are controlled

|  | 5.2 LUZON (hers) | 5.4 PAGENET (this machine) |
|---|---|---|
| Antenna / PCV | **I14** | **I20** |
| GNSS for ambiguity resolution | **ALL** | **GRE** |
| Baselines, `V_CLU` | 6000/2000/200/20, 10 | identical |

The tuning parameters agree; the **models do not**. I14 → I20 is a cm-level,
largely vertical, systematic shift — comfortably inside the range a PCF change
could produce. A 5.4 run under I20 compared against her I14 result yields a
difference that is real, reproducible, and has nothing to do with the PCF.

**Reprocess under I14 first and reproduce her numbers. Change one thing at a
time afterwards.** The file you need is local:

```
/srv/gnss-archive/processed/luzon-bern52/BERN52/GPS/GEN/ANT_COD_I14.PCV
```

(Note `ANT_COD_I14.PCV_out_of_service` sits beside it — do not stage that one.)

---

## 2. Where every input lives

Nothing is blocked on the external drive any more; all of this is on the array
or in the repo.

| Input | Location |
|---|---|
| Campaign tree (5.2) | `/srv/gnss-archive/processed/luzon-bern52/GPSDATA/CAMPAIGN/LUZON/` |
| Converted observations | `…/CAMPAIGN/LUZON/OBS/` (2,064 files) |
| Orbits, ERP, DCB | `…/CAMPAIGN/LUZON/ORB/` (PRE, STD, TAB, CLK, ERP, IEP, DCB) |
| Troposphere / ionosphere | `…/CAMPAIGN/LUZON/ATM/` (TRO, TRP, ION) |
| Reference solutions | `…/CAMPAIGN/LUZON/SOL/` — 40 `F1_`, 725 `WK_`, 166 `MO_` |
| Station files | `…/DATAPOOL_REF52/LUZON.{STA,CRD,VEL,ABB,CLU,BLQ,ATL,PLD}` |
| Same, in git | `config/bernese/gpsuser52-luzon/STA/` |
| PCF | `config/bernese/gpsuser52-luzon/PCF/PHIVOL_REL.PCF` |
| OPT panels (5.2) | `config/bernese/gpsuser52-luzon/OPT/` |
| I14 antenna model | `…/luzon-bern52/BERN52/GPS/GEN/ANT_COD_I14.PCV` |
| IGS products | `…/luzon-bern52/DATAPOOL_IGS/` (94 SP3) |

---

## 3. What `PHIVOL_REL.PCF` needs, and what is missing

`PHIVOL_REL.PCF` has 84 PIDs. Its process table (lines 2–64) references **12**
OPT directories:

| Directory | Available from |
|---|---|
| `NO_OPT` | the 5.4 install |
| `R2S_AMB`, `R2S_EDT`, `R2S_FIN`, `R2S_GE2`, `R2S_GEN`, `R2S_L12`, `R2S_L53`, `R2S_QIF`, `R2S_RED` | both |
| **`PHI_MO`, `PHI_WK`** | **only the 5.2 capture** — PHIVOLCS-specific, must be provisioned from the repo |

> **A parsing trap, recorded because it cost a wrong answer first time.**
> `PHIVOL_REL.PCF` contains **three** tables. Line 1 is
> `PID SCRIPT OPT_DIR CAMPAIGN CPU F WAIT`, but line 65 begins
> `PID USER PASSWORD PARAM1 …`, where column 3 holds values like `$201`. Taking
> column 3 from every line starting with three digits yields 25 "OPT
> directories", twelve of which do not exist because they are not directories.
> Parse only lines 2–64.

### 3.1 Eight scripts referenced by the PCF do not exist in this 5.4 install

Checked against `$U/SCRIPT` (139 files) and the whole `BERN54` tree:

```
ADD_MON   ADD_WK   FTP_DWLD   ORBGENH
POLUPDH   PRETAB   RNXSMT_H   RXOBV3_H
```

41 of the 49 scripts are present. **`PHIVOL_REL.PCF` cannot run unmodified on
5.4.** The eight fall into three groups:

- **`ADD_WK`, `ADD_MON`** — weekly/monthly combination. This is readiness item M,
  which asks whether weekly/monthly stacking is even in scope for production
  (PHIVOLCS velocities come from MATLAB regression on daily ENU, not NEQ
  stacking). For a daily-solution comparison they are **not needed** — stop the
  PCF after the daily final solution.
- **`RNXSMT_H`, `RXOBV3_H`, `ORBGENH`, `POLUPDH`** — the `H` suffix suggests
  hourly variants. 5.4 ships the non-`H` forms (`RNXSMT`, `RXOBV3`). Whether the
  base scripts are drop-in replacements is **unverified**.
- **`FTP_DWLD`, `PRETAB`** — download and orbit tabulation. The products are
  already staged in `ORB/`, so a run from campaign `OBS/` should not need them.

**Consequence:** do not expect to run `PHIVOL_REL.PCF` as-is. Either trim it to
the daily path (PID 001 → final solution) and remap the `H` scripts, or drive
the equivalent steps with 5.4's stock `RNX2SNX.PCF` configured for LUZON. The
second is likely faster to a first comparable number; the first stays closer to
what she actually ran.

---

## 4. Provisioning `$U` — expect it to be refused

The 5.2 OPT tree is **not** a clean gold standard. Measured across all 105 live
`.INP` panels in `config/bernese/gpsuser52-luzon/`:

| Hazard | Instances |
|---|---|
| `hardcoded_campaign` | 820 |
| `foreign_abs_path` (`C:\Bernese\…`) | 200, across **50 panels** |
| `hardcoded_date` | 95 |
| **Panels affected** | **72 of 105** |

```bash
uv run python scripts/provision_gpsuser.py \
    --gold config/bernese/gpsuser52-luzon --stations 25
```

This will **refuse and exit 1**. That is the tool working — a panel carrying an
unresolvable hazard aborts the whole run before anything is written, so `$U` is
never left half-updated. Separator conversion is automatic; the hardcoded
campaign names, dates and `C:\Bernese\…` paths need deliberate remapping,
because a machine cannot know what they *should* say.

Only `PHI_MO` and `PHI_WK` are strictly required from this tree — the `R2S_*`
panels already exist in the 5.4 install. Remediating two directories is a much
smaller job than remediating 72 panels, and is the recommended starting scope.

---

## 5. Open questions — resolvable only by running it

These are the actual content of the exercise. None can be settled by inspection.

1. **Do the seven fiducials' observations fetch cleanly for DOY 121–151?**
   (§1.1a.) This is now the first thing to settle, because it decides whether the
   comparison is well-posed. `igs-downloader` needs IGS20 naming and mirror
   fallback per deliverable 2.2, so it may need work before it can do this.

   > **The earlier "ask Abegail for RINEX" mitigation is withdrawn.** §1.1 makes
   > it unnecessary — the reference solutions were never missing. What *is*
   > needed is fiducial observations from IGS, not anything from her. Do not
   > chase the original request.

2. **Can 5.4 read a 5.2 campaign's `OBS/` directly?** No longer blocking, since
   §1.1 gives a raw-RINEX path with references for every day. Still worth knowing
   for any future run started from converted observations.

3. **Are the non-`H` scripts drop-in for the `H` variants?**
4. **Do `PHI_MO`/`PHI_WK` work under 5.4 once remediated?** They are the two
   directories with no 5.4 equivalent.
5. **Does staging `ANT_COD_I14.PCV` into 5.4's `GEN/` suffice**, or does 5.4
   expect an ATX-derived PCV it will not accept from a 5.2 tree?

---

## 6. Suggested first run

Deliberately the smallest thing that produces a comparable number.

0. **Fetch the seven fiducials for DOY 121 first** (§1.1a). Without them the run
   processes 24 stations against a 30-station reference and the comparison is
   measuring the wrong thing. This step gates everything below.
1. **One day: 2025 DOY 121.** Raw RINEX present, reference is
   `SAVEDISK/2025/SOL/F1_251210.SNX.gz` — gunzip it first.
2. Create a LUZON campaign under `$P` (`GPSDATA/CAMPAIGN54/`) and stage the
   RINEX, orbits, ERP and station files for that day.
3. Stage `ANT_COD_I14.PCV` — **I14, not I20** (§1.4).
4. Provision `PHI_WK` only, remediated (§4).
5. Run the daily path from RINEX, so `RXOBV3` is exercised. Stop before `ADD_WK`.
6. Compare against `F1_251210.SNX` the way the 07-29 BPE re-verification did:
   extract `STAX/STAY/STAZ` from `SOLUTION/ESTIMATE`, difference, convert to mm.

**What counts as success:** not zero. Her run and yours differ in Bernese version
and possibly in scripts. Sub-millimetre agreement means models and inputs line
up; a systematic, largely-vertical centimetre-scale offset means I20 leaked in
(§1.4); a difference concentrated in particular stations points at the fiducial
set (§1.1a) rather than at the PCF.

**Record the number before tuning anything** — it is the baseline every later
comparison is measured against.

**Then, and only then, extend to the full 31 days.** At that point the run is
also BRN-001 acceptance evidence (§1.2), provided the station and panel problems
were cleared automatically rather than by hand.

---

## 7. What is not here, and cannot be reprocessed

`SOL/` holds **725 weekly and 166 monthly** solutions spanning **2010-02-28 to
2026-04-12** — sixteen years of results in 421 MB, plus `SAVEDISK/2025/` with all
365 daily finals for that year.

The raw observations behind them are **not on the array and not on the drive**,
with one exception: the 31 days of 2025 DOY 121–151 that §1.1 identifies. Every
other day of those sixteen years has a solution and no input. The rest is on
staff machines — roughly 4 TB by extrapolation from the one month present.

So apart from that one month, those sixteen years of results are, today,
**irreproducible**. They can be
copied and checksummed; they cannot be regenerated. That makes the 421 MB
`SOL/` directory the most valuable thing recovered from the drive per byte, and
it is why `scripts/sudo/processed_transfer.sh` copies it first and alone.

Capturing the raw archive from staff machines is a separate and larger piece of
work, and it is the precondition for ever reprocessing the full LUZON history.
