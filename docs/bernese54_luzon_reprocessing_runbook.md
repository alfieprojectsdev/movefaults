# Reprocessing the LUZON network under Bernese 5.4

**Written:** 2026-08-05, on gps3, after the Bernese 5.2 LUZON set was copied off
the DOSTB drive to `/srv/gnss-archive/processed/luzon-bern52/`.

**Goal**, in the user's words: *"i-reprocess ko sa GPS3 under Bernese 5.4 for
comparison ng results / adjustment (fine tuning) ng PCF."* Reprocess Abegail's
LUZON network under 5.4, reproduce her 5.2 numbers, and only then tune.

**Status: not yet run.** Everything below about *inputs* is measured. Everything
about *execution* is untested — §5 lists what will only be settled by running it.

---

## 1. Read this before planning a run

Two findings from surveying the copied set change the shape of the exercise.
Both would have cost days if met mid-run.

### 1.1 The raw data and the reference solutions do not overlap

| Asset | Coverage |
|---|---|
| `GPSDATA/DATAPOOL/LUZON/` — raw RINEX | **2025 DOY 121–151** (31 days, 25 stations, 741 obs) |
| `GPSDATA/CAMPAIGN/LUZON/OBS/` — converted observations | 2025 DOY **029–033**, 2026 DOY **106–110** |
| `GPSDATA/CAMPAIGN/LUZON/SOL/F1_*` — daily solutions | 2025 DOY **029–033**, 2026 DOY **106–110** |
| Solutions for DOY 121–151 of 2025 | **none** |

**The RINEX on the drive was never processed into the solutions on the drive.**
Reprocessing DOY 121–151 under 5.4 therefore produces numbers with *nothing to
compare against*, which is not the exercise.

**Use the campaign `OBS/` instead.** It covers exactly the ten days that have
`F1_` solutions, so the comparison is well-posed:

- **2025 DOY 029–033** — five consecutive days
- **2026 DOY 106–110** — five consecutive days, and `WK_2413`/`WK_2414` combine
  the surrounding weeks

Start with a single day. **2026 DOY 110** is the most recent and its inputs are
the least likely to have drifted.

### 1.2 The comparison is invalid unless the models are controlled

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

1. **Can 5.4 read a 5.2 campaign's `OBS/` directly?** The directory layout is
   identical (`ATM GRD OBS ORB ORX OUT RAW SOL STA`) and the observation files
   are the usual `CSH/CSO/PZH/PZO` pairs, but whether the on-disk format changed
   between 5.2 and 5.4 is untested. **If it did not, this is the fast path.** If
   it did, re-convert from RINEX — but note §1.1: RINEX exists only for days
   with no reference solution, so a format incompatibility makes the comparison
   much harder, not merely slower.
2. **Are the non-`H` scripts drop-in for the `H` variants?**
3. **Do `PHI_MO`/`PHI_WK` work under 5.4 once remediated?** They are the two
   directories with no 5.4 equivalent.
4. **Does staging `ANT_COD_I14.PCV` into 5.4's `GEN/` suffice**, or does 5.4
   expect an ATX-derived PCV it will not accept from a 5.2 tree?

---

## 6. Suggested first run

Deliberately the smallest thing that produces a comparable number.

1. **One day: 2026 DOY 110.** Most recent, has `F1_261100.NQ0` and `.SNX` as the
   target, and campaign `OBS/` for `A2GG1100.*` and friends.
2. Create a LUZON campaign under `$P` (`GPSDATA/CAMPAIGN54/`) and stage `OBS/`,
   `ORB/`, `ATM/`, `STA/` for that day only.
3. Stage `ANT_COD_I14.PCV` — **I14, not I20** (§1.2).
4. Provision `PHI_WK` only, remediated (§4).
5. Run the daily path. Stop before `ADD_WK`.
6. Compare `F1_` output against `SOL/F1_261100.SNX` the same way the 07-29 BPE
   re-verification did: extract `STAX/STAY/STAZ` from `SOLUTION/ESTIMATE`,
   difference, convert to mm.

**What counts as success:** not zero. Her run and yours differ in Bernese
version and possibly in scripts. A sub-millimetre agreement means the models and
inputs line up; a systematic, largely-vertical centimetre-scale offset means
I20 leaked in somewhere (§1.2). **Record the number before tuning anything** —
it is the baseline every later comparison is measured against.

---

## 7. What is not here, and cannot be reprocessed

`SOL/` holds **725 weekly and 166 monthly** solutions spanning **2010-02-28 to
2026-04-12** — sixteen years of results in 421 MB. The raw observations behind
all but ten of those days are **not on the array and not on the drive**. They
are on staff machines, roughly 4 TB by extrapolation from the one month present.

So those sixteen years of results are, today, **irreproducible**. They can be
copied and checksummed; they cannot be regenerated. That makes the 421 MB
`SOL/` directory the most valuable thing recovered from the drive per byte, and
it is why `scripts/sudo/processed_transfer.sh` copies it first and alone.

Capturing the raw archive from staff machines is a separate and larger piece of
work, and it is the precondition for ever reprocessing the full LUZON history.
