# Reprocessing the LUZON network under Bernese 5.4

**Written:** 2026-08-05, on gps3, after the Bernese 5.2 LUZON set was copied off
the DOSTB drive to `/srv/gnss-archive/processed/luzon-bern52/`.

**Goal**, in the user's words: *"i-reprocess ko sa GPS3 under Bernese 5.4 for
comparison ng results / adjustment (fine tuning) ng PCF."* Reprocess Abegail's
LUZON network under 5.4, reproduce her 5.2 numbers, and only then tune.

**Status: not yet run.** Everything below about *inputs* is measured on gps3.
Everything about *execution* is untested — §5 lists what only a run will settle.

**Revised twice on 2026-08-05.** §1.1 replaces an earlier conclusion that the
reference solutions did not exist — they are in `SAVEDISK/`. §1.1a replaces a
second wrong conclusion that seven fiducials were missing — they are in
`DATAPOOL/RINEX3/`, as RINEX 3. **Every input for the 31-day window is local and
nothing needs downloading.** If you read an earlier version, re-read §1 in full;
the plan changed twice, both times toward being easier.

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

### 1.1a Every station she used IS present — the fiducials are RINEX 3

> **Corrected 2026-08-05.** This section previously said seven fiducials were
> missing and had to be fetched from IGS. They were on disk the whole time, in
> `GPSDATA/DATAPOOL/RINEX3/` — a directory neither session had opened.
> `DATAPOOL/` has **fourteen** subdirectories; both of us searched only `LUZON/`.

**Verified on gps3:**

```
DATAPOOL/RINEX3/   281 files, 9 stations
                   AIRA ALIC BASC CLAV DAEJ DARW MCIL PIMO PNGM
                   RINEX 3 long-name Hatanaka:
                   AIRA00JPN_R_20251210000_01D_30S_MO.crx.gz
```

| Station | Coverage over DOY 121–151 |
|---|---|
| AIRA, ALIC, BASC, CLAV, DAEJ, DARW, MCIL, PIMO | **31 / 31** |
| PNGM | **26 / 31** — missing DOY 123, 131, 141, 143, 144 |

**Station reconciliation against her DOY 121 solution — the decisive check:**

```
she used, we lack:        (none)
we have, she did not use: PIMO TGDN
```

**Every input for the 31-day window is local.** Nothing needs downloading and
nothing needs requesting from anyone.

#### Why both sessions read this as an absence

The locals are **RINEX 2 short-name** (`ALAB1210.25o` — station, DOY, year-type).
The fiducials are **RINEX 3 long-name** (`AIRA00JPN_R_20251210000_...` — year and
DOY inside a date field). A search built on one convention returns zero for the
other, and zero was read as absence.

**This is the fifth instance this week of one shape** (§1.5).

#### Three caveats that do bite

**PNGM is short five days, and her solutions include it.** On DOY 123, 131, 141,
143 and 144 you will solve a different network than the reference. Exclude those
days from the comparison or record them as a known, explained difference — do
not let a five-day discrepancy be read as a 5.4-vs-5.2 effect.

**BASC and CLAV exist in BOTH conventions — de-duplicate before staging.**

```
DATAPOOL/LUZON/CLAV1210.25o                                  (RINEX 2, 30 files)
DATAPOOL/RINEX3/CLAV00PHL_R_20251210000_01D_30S_MO.crx.gz    (RINEX 3, 31 files)
DATAPOOL/LUZON/BASC*.25o                                     (RINEX 2, 20 files)
DATAPOOL/RINEX3/BASC*                                        (RINEX 3, 31 files)
```

Staging both gives duplicate observations for one station, which may fail
confusingly mid-BPE or not fail at all. **Decide one convention per station and
state it here before the first run.** Suggested: prefer RINEX 3 for both, since
its coverage is complete where RINEX 2's is not (BASC 31 vs 20).

**Local station coverage is 741 / 775 station-days** (25 × 31), so ~4% gaps —
normal CORS behaviour. Count per day before the run so a dropout is a known
input rather than a surprise inside `RXOBV3`.

### 1.1b Mixed RINEX 2 and 3 in one campaign

RINEX 2 short-name locals and RINEX 3 long-name fiducials process together.
`_resolve_station_code()` was hardened for exactly this during the C2 work, so
*validation* copes — but **staging is a different code path** and must glob both
patterns. That path has not been exercised.

### 1.1c `FTP_DWLD` does not gate this run

All products are already local, verified: orbits (`.sp3`, weeks 2364–2368), ERP
for all five weeks, clocks, ionosphere (`COD2364*` — **GPS-week named**, not
`*25121*`), DCB (`P1P22505`), the I14 ATX, the `LUZON.*` reference set, and the
reference solutions in `SAVEDISK`.

So `FTP_DWLD` — one of the eight missing scripts (§3.1) — joins `ADD_WK`,
`ADD_MON` and `PRETAB` in the "not needed when running from staged products"
category. **Dropping it from the PCF is a one-line change**, not a blocker.

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
time afterwards.**

> **Why not transform between frames instead?** The published IGS14→IGS20
> approach — 7-parameter Helmert plus epoch propagation plus consistent ATX —
> is the correct method when you have two *finished* products in different
> frames and must reconcile them. It is the wrong method here: it would leave
> transform residuals entangled with the PCF effect we are trying to measure.
> Running both sides under I14 removes the difference instead of correcting for
> it, and 5.4 ships `ANTENNA_I14.PCV`, so the option costs nothing.
>
> That method does apply to the **next** exercise — comparing LUZON (I14 /
> ITRF2014) against PAGENET (I20 / ITRF2020) — which is a genuine cross-frame
> comparison. Official parameters: <https://itrf.ign.fr/en/solutions/transformations>.
>
> External corroboration for the magnitude in the table above: the EPN switch-to-IGS20
> analyses report ground and satellite antenna calibration changes producing
> **centimetre-level offsets, up to ~3 cm and concentrated in the Up component**,
> independent of the frame translation itself (which is sub-centimetre globally). The file you need is local:

```
/srv/gnss-archive/processed/luzon-bern52/BERN52/GPS/GEN/ANT_COD_I14.PCV
```

(Note `ANT_COD_I14.PCV_out_of_service` sits beside it — do not stage that one.)

---

### 1.5 The naming-convention class

Five false absences this week, one shape: **searching with one convention and
reading zero results as absence.**

| # | Case | Convention that hid it |
|---|---|---|
| 1 | Validator saw no RINEX in DATAPOOL | `.gz`/`.Z` suffix vs bare extension |
| 2 | Station codes resolved wrongly | `MARKER NAME` vs `MARKER NUMBER` |
| 3 | ION files looked absent | GPS-week naming vs year-DOY |
| 4 | Reference solutions "did not exist" | archived to `SAVEDISK`, not the campaign |
| 5 | Fiducials "missing" | RINEX 3 long-name vs RINEX 2 short-name |

**The remedy was the same every time: look at actual filenames before writing
the pattern.** `ls | head` costs nothing; a false absence costs a day and a
wrong plan.

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
- **`FTP_DWLD`, `PRETAB`** — download and orbit tabulation. **Confirmed not
  needed** (§1.1c): every product for the window is already local — orbits, ERP,
  clocks, ionosphere, DCB. Dropping `FTP_DWLD` from the PCF is a one-line change.
  Four of the eight are therefore in the "not needed when running from staged
  products" category: `ADD_WK`, `ADD_MON`, `FTP_DWLD`, `PRETAB`. **The genuinely
  open ones are the four `H` variants.**

**Consequence:** do not expect to run `PHIVOL_REL.PCF` as-is. Either trim it to
the daily path (PID 001 → final solution) and remap the `H` scripts, or drive
the equivalent steps with 5.4's stock `RNX2SNX.PCF` configured for LUZON. The
second is likely faster to a first comparable number; the first stays closer to
what she actually ran.

---

## 4. Configuration checklist — what actually has to change

Investigated 2026-08-05. **Every input is local. Nothing needs downloading and
nothing needs requesting.** What remains is configuration, and most of it is
staging rather than authoring.

### 4.0 Things that turned out NOT to be problems

| Feared blocker | Reality |
|---|---|
| Provision `PHI_WK`/`PHI_MO`, remediate 72 hazardous panels | **Not needed.** Those two dirs are referenced *only* by PIDs 530 (`ADD_WK`) and 531 (`ADD_MON`). Stop at 514 and they never load. The `R2S_*` panels the daily path uses already ship with 5.4. |
| Mixed RINEX 2 / RINEX 3 staging | **Already handled by the PCF**: `V_RNXDIR=LUZON` and `V_RX3DIR=RINEX3` are separate variables. The design anticipated this. |
| Configure I14 vs I20 | **Already in the PCF**: `V_PCV=I14`, `V_MYATX=I14.ATX`. The model discipline is built in, not something to remember. |
| `ANTENNA_I14.PCV` | **5.4 already ships it** in `REF54`, alongside I20. |
| `FTP_DWLD` missing | Products are all local (§1.1c). One-line drop. |

### 4.1 The eight missing scripts — all resolved

| 5.2 script | Disposition |
|---|---|
| `FTP_DWLD` | **Drop.** Products staged. |
| `ADD_WK`, `ADD_MON` | **Drop.** PIDs 530/531, weekly/monthly combination, out of scope for a daily comparison. |
| `POLUPDH` | → **`POLUPD`** (exists; panel `POLUPD.INP`) |
| `ORBGENH` | → **`ORBGEN`** (exists; panel `ORBGEN.INP`) |
| `RXOBV3_H` | → **`RXOBV3`** (exists) |
| `RNXSMT_H` | → **`RNXSMT_P`** (exists; panel `RNXSMT.INP`) |
| `PRETAB` | → **`ORBMRG`** — the one genuine substitution |

**The `_H`/`H` suffix is on the script name only.** The OPT panels are named
without it (`R2S_GEN/RXOBV3.INP`), so panel lookups are unaffected by the rename.

**On `PRETAB` → `ORBMRG`:** `PRETAB` does not exist in 5.4 in any form — not as a
script, not as a program in `SOURCE/PGM/EXE_GNU`. 5.4's own stock `RNX2SNX.PCF`
runs `111 ORBMRG` then `112 ORBGEN` where 5.2 ran `112 PRETAB` then `113
ORBGENH`. Follow 5.4's own chain rather than inventing a replacement.

### 4.2 What must be staged

**Reference frame — the one real gap.** `PHIVOL_REL.PCF` wants `V_REFINF=IGS14`
and `V_REFPSD=IGS14`. **5.4's `REF54` ships IGS20 only** (8 files, no IGS14).
The I14 frame files are in the 5.2 capture and must be copied in:

```
DATAPOOL_REF52/IGS14.FIX   IGS14.PSD   IGS14.SIG   IGS14_R.CRD   IGS14_R.VEL
```

Without these the run either fails or silently falls back to IGS20 — which is
the I14/I20 confound of §1.4 arriving through the back door, and it would not
announce itself.

| Item | From | To |
|---|---|---|
| `IGS14.{FIX,PSD,SIG}`, `IGS14_R.{CRD,VEL}` | `DATAPOOL_REF52/` | `$D/REF54/` |
| `I14.ATX` | `BERN52/GPS/GEN/I14.ATX` | `$D/REF54/` (or per `V_MYATX`) |
| `LUZON.{STA,CRD,VEL,ABB,CLU,BLQ,ATL,PLD}` | `DATAPOOL_REF52/` or the repo | `$D/REF54/` |
| RINEX 2 observations | `DATAPOOL/LUZON/` | `$D/LUZON/` |
| RINEX 3 fiducials | `DATAPOOL/RINEX3/` | `$D/RINEX3/` |
| Orbits, weeks 2364–2368 | `DATAPOOL/IGS/` (76 `.sp3`) | `$D/IGS/` |
| Ionosphere | `DATAPOOL_BSW52/COD236*.ION.gz` (31) | `$D/BSW52/` |
| DCB | `DATAPOOL/COD/` | `$D/COD/` |

### 4.3 Settings to change

0. **`V_PCVINF`: `PCV` → `ANTENNA`.** The two versions name the antenna table
   differently: 5.2 resolves `{V_PCVINF}_{V_PCV}` to `PCV_I14.PCV`, 5.4 to
   `ANTENNA_I20.PCV`. Setting `V_PCV=I14` with `V_PCVINF=ANTENNA` resolves to
   **`ANTENNA_I14.PCV`, which 5.4 already installs** in `REF54`. Leaving
   `V_PCVINF=PCV` makes Bernese look for a file that does not exist in the 5.4
   tree.

   `002 ATX2PCV` runs in both PCFs — the table is built at runtime from the
   ATX — so `V_MYATX` and `V_PCV` must agree, or the table is built from one
   model and selected by another.

   > **`REF54` holds four antenna tables side by side**: `ANTENNA_I14.PCV`,
   > `ANTENNA_I20.PCV`, `ANTENNA_M14.PCV`, `ANTENNA_R20.PCV`. Mixing phase-centre
   > tables is a documented cm-level error source, largely in the Up component,
   > and `V_PCV` is the only thing keeping them apart. Verify which table the run
   > actually loaded from the BPE output rather than assuming the variable took.

1. **`V_REFDIR`: `REF52` → `REF54`.** 5.2 names it `${D}/REF52`; the 5.4 tree is
   `${D}/REF54`. Compare against `PAGENET_DLY.PCF`, which already uses
   `V_REFDIR = ${D}/REF54`.
2. **Create the LUZON campaign.** `$P` (`GPSDATA/CAMPAIGN54/`) holds only
   `EXAMPLE`. Register it in `$U/PAN/MENU_CMP.INP`, whose `CAMPAIGN` list
   currently names `EXAMPLE`, `INTRO`, `PAGENET`.
3. **Choose one convention for BASC and CLAV** (§1.1a). Prefer RINEX 3 — BASC's
   RINEX 2 coverage is 20 days against RINEX 3's 31.
4. **Check the three known 5.2↔5.4 panel differences** before trusting a
   comparison: `RNXGRA` `MINOBS`/`MAXBAD`, and `ADDNEQ2` `MAXPAR`. These were
   identified in the 2026-03-03 INP diff and are the parameters that differ
   between the PHIVOLCS 5.2 panels and the 5.4 EXAMPLE set.
5. **`USER.CPU` is already correct** — maxjobs 11, set 2026-08-03. `V_CLU=10`
   over ~30 stations gives three clusters, which is fine on 11 cores.

### 4.4 Order of work

1. Stage §4.2 (mechanical, scriptable, no decisions)
2. Create and register the campaign
3. Copy `PHIVOL_REL.PCF` → `LUZON_DLY.PCF`; apply §4.1 renames, drop PIDs
   515–999, substitute `ORBMRG` for `PRETAB`
4. Set `V_REFDIR=${D}/REF54`
5. Pre-flight inventory: station-days per convention, duplicates, PNGM's gaps
6. Run DOY 121 alone

## 4b. RESULTS OF THE FIRST RUN ATTEMPTS — 2026-08-05

Five attempts. The plan in §4.1 was **wrong in its premise** and is superseded
by §4b.1. Everything else in §4 stands.

### 4b.1 The 5.2 PCF cannot be adapted — the file format changed

Renaming scripts and repairing WAIT lists cannot bridge a **format change**:

```
5.2   PID SCRIPT   OPT_DIR  CAMPAIGN CPU      F WAIT FOR....
      3** 8******* 8******* 8******* 8******* 1 3** 3** ...
      501 GPSCLUAP R2S_FIN           ANY      1 499

5.4   501  GPSCLUAP  R2S_FIN   CPU=ANY; WAIT=499;  PARAM2=V_FIN
```

Fixed-column with a ruler, versus free-form `KEY=VALUE;`. **Handing 5.4 a 5.2
PCF segfaults the menu program** — it does not report a parse error, so the
incompatibility is not self-announcing.

`PAGENET_DLY.PCF` is 5.4-native and proven, but needs the `PGN_*` OPT
directories, which exist only on the T420 (PR #65 captured only `PGN_WK`).

**Derive from stock `RNX2SNX.PCF` instead** — same RNX2SNX workflow, 5.4-native,
and its `R2S_*` OPT dirs ship with 5.4. `scripts/derive_luzon_pcf.py` applies 14
variable overrides and nothing structural. It refuses to write if any row lacks
`CPU=`, so the format mistake cannot recur silently.

### 4b.2 §1.1c was wrong: `FTP_DWLD` does gate the run

§1.1c said every product was local so `FTP_DWLD` could be dropped. The products
are local **in 5.2-era legacy naming** (`igs22364.sp3.Z`); 5.4 reads long-name
(`IGS0OPSFIN_20251210000_01D_15M_ORB.SP3.gz`). Present but unusable — presence
was verified, usability was not.

`scripts/fetch_igs_products.sh` downloads the long-name set from BKG
(anonymous HTTPS; CDDIS needs an Earthdata login). Note the **ERP is weekly**,
`_<startDOY>0000_07D_01D_ERP`, so fetching "the ERP for DOY 121" means locating
the week containing it.

### 4b.3 Where it stands: one missing file

The fifth attempt reached **PID 001** and failed there. Everything before it
worked — `LUZON.BLQ/.ATL/.CLU` copied into the campaign, `ANTENNA_I14.PCV`
confirmed in use, orbit copied to `.PRE`, ERP to `.IEP`.

```
File .../DATAPOOL/BSW54/IAR23644.OSB cannot be provided (mandatory)
*** copyRef: 1 mandatory file is missing
```

`R2S_COP` *generates* `IAR_*.OSB` by running `BIA2OSB` over a bias-SINEX input:

```perl
putKey(... "BIASNX", "${orb}_${myYYYYDDD}");   # IGS0OPSFIN_2025121 -> the .BIA
putKey(... "OSBOUT", "IAR_${myYYYYDDD}0");     # -> IAR_*.OSB
```

So the mandatory file is missing **because its optional input is**:
`IGS0OPSFIN_2025121*_OSB.BIA`. Blanking `V_OSBFIL` does not help — the
requirement lives in the script's key list, not the PCF variable.

**BKG's IGS final set has no bias product at all** for GPS week 2364 — only
`CLK`, `SP3`, `ERP`, `SUM`. Satellite biases come from an analysis centre:

| Source | Status |
|---|---|
| AIUB (`ftp.aiub.unibe.ch`, CODE's home) | **unreachable from gps3** — timed out on http and https |
| CDDIS | has them, but needs an **Earthdata login** |
| BKG | does not carry them |

**This is the only thing standing between here and a run.** It needs either
Earthdata credentials, or a route to AIUB, or a CODE product set copied in by
hand. Note her 5.2 run used **DCB** files rather than OSB, so this requirement
is a 5.4-ism and not something inherited from her configuration.

### 4b.4 Three tool defects the failures exposed

| Defect | Consequence |
|---|---|
| `find_dangling_waits()` knew only the `WAIT=` dialect | Reported **0 dangling** on a 5.2 PCF having parsed **zero** PIDs and zero WAITs. Signed off a PCF with four broken WAIT lists. Fixed, +4 tests. |
| `REWAIT` regex captured 4 fields where the row has 3 | Old dependency survived, replacement appended after it: `1 112  101 111` |
| `BPE_CAMPAIGN` as a bare name | `startBPE` tests it with `-d` **relative to CWD**. The stock drivers are silently directory-dependent. Must be `'${P}/LUZON'`, single-quoted so Perl does not interpolate. |

The first is the week's eighth instance of a check reporting success without
having inspected anything — this time in the function written to prevent it.

---

## 5. Open questions — resolvable only by running it

Most of the original list closed during the 2026-08-05 configuration survey
(§4). What genuinely remains:

1. **Does `ORBMRG` produce what `ORBGEN` expects, in this campaign's layout?**
   The one real substitution. 5.4's own `RNX2SNX.PCF` chains them this way, so
   the pattern is sound; whether it works against 5.2-era staged products is
   untested.
2. **Do the 5.2 `R2S_*` panels load under 5.4 unchanged?** They exist in both,
   but the 2026-03-03 INP diff found three parameters differing (`RNXGRA`
   `MINOBS`/`MAXBAD`, `ADDNEQ2` `MAXPAR`). Whether anything else drifted between
   versions is unknown.
3. **Does `V_PCV=I14` resolve correctly** once the IGS14 frame files are staged
   into `REF54` beside the IGS20 set? Two frames in one directory is the
   configuration most likely to fail quietly rather than loudly.
4. **Do the RINEX 3 fiducials stage cleanly** via `V_RX3DIR`? The variable
   exists and the PCF was written for it, but this specific code path has not
   run on this machine.

Closed by §4: the eight missing scripts, the fiducial "gap", `FTP_DWLD`,
`PHI_WK`/`PHI_MO` provisioning, mixed RINEX conventions, and I14 model
selection.

## 6. Suggested first run

Deliberately the smallest thing that produces a comparable number.

0. **Decide the BASC/CLAV convention and run a pre-flight inventory** (§1.1a).
   Count station-days per source convention, flag the two duplicated stations,
   flag PNGM's five short days. One pass, catches all three caveats, and the
   step is reusable for PAGENET. ~~Fetch the fiducials~~ — not needed; they are
   local.
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
(§1.4); a difference concentrated in particular stations points at the station
set — PNGM's five short days, or a BASC/CLAV duplicate (§1.1a) — rather than at
the PCF.

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
