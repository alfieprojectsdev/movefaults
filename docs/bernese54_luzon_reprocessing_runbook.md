# Reprocessing the LUZON network under Bernese 5.4

**Written:** 2026-08-05, on gps3, after the Bernese 5.2 LUZON set was copied off
the DOSTB drive to `/srv/gnss-archive/processed/luzon-bern52/`.

**Goal**, in the user's words: *"i-reprocess ko sa GPS3 under Bernese 5.4 for
comparison ng results / adjustment (fine tuning) ng PCF."* Reprocess Abegail's
LUZON network under 5.4, reproduce her 5.2 numbers, and only then tune.

**Status as of 2026-08-06: RUN, and it completes.** 30 of the 31 days processed
end to end with **zero failures** in 2h47m (§4b.8–§4b.10). Repeatability is
median N 2.8 mm, E 3.0 mm, U 10.9 mm.

Two things that section headings below will not tell you, so read them here:

1. **It ran under I20, not I14.** I14 cannot run on 5.4 at this epoch — the
   satellite tables end in 2023 and the ANTEX fails a consistency check 5.2 did
   not perform (§4b.6). **These coordinates are therefore NOT comparable with
   Abegail's `F1_25*` series**, and differencing them will show a frame and
   antenna-model change, not a Bernese-version effect. The stated goal at the top
   of this document — reproduce her numbers — is **not** what this run achieved.
2. **Only 31 days of 2025 can be reprocessed at all**, verified by census (§7).
   She solved 365. The rest of the sixteen-year series has solutions and no
   inputs.

Sections below marked "not yet run" or "untested" predate 2026-08-06 and are
left in place because the reasoning that led to them is still worth reading;
§4b.7 onward records what actually happened.

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

### 4b.5 The run now reaches CODSPP — and I14 is a retired model

Later attempts got through RINEX import, orbit preparation and observation
conversion (92 files, ~1m40s) before stopping at **PID 232 `CODSPP_P`**.

**`V_SATSYS` was the variable that mattered, and it was missed.** The first
override set copied `V_GNSSAR = ALL` from her PCF and reasoned that she resolved
ambiguities across all constellations. `V_GNSSAR` only selects which of the
*already-selected* systems get ambiguity resolution; **`V_SATSYS` selects the
systems**, and hers reads `GPS` where 5.4 ships `GRE`.

Leaving it at the default made the run attempt GLONASS, and `CODSPP` died on
**GLONASS-M 861** — launched after I14's epoch and absent from every I14 table
(hers and 5.4's both stop at 860; only I20 has it). That looked like a missing
file and was a constellation-selection error. Had it been "fixed" by switching
to I20, the comparison would have acquired the exact I14/I20 confound §1.4
exists to prevent, and the numbers would have looked plausible.

**Processing GPS-only is therefore not a workaround — it is what she did, and it
is why I14 remains usable against 2025 data at all.**

#### The remaining blocker is model validity, not configuration

With GPS selected, `CODSPP` stops on `BLOCK IIR-A 044`. The satellite *is* in
`ANTENNA_I14.PCV`; what fails is the PRN→SVN resolution, which comes from the
satellite information table:

| Table | Latest entry |
|---|---|
| Her `SATELLIT.I14` (5.2) | **2023-01-31** |
| 5.4's `SATELLIT_I14.SAT` | 2023-08-10 |
| 5.4's `SATELLIT_I20.SAT` | 2024-09-17 |

**AIUB no longer publishes `SATELLIT_I14.SAT`** — `BSWUSER54/CONFIG/` returns
404 for I14 and 200 for I20. I14's supporting tables are retired, and hers was
already two years stale when she processed this day.

So the open question is no longer "what is misconfigured" but **"how did her
5.2 run handle satellites absent from its own tables?"** Bernese 5.4 halts
(`Processing stopped!`); 5.2 may have warned and excluded them. If so, that is a
5.2→5.4 behavioural difference of exactly the kind this exercise exists to find
— and it means reproducing her numbers under I14 on 5.4 may require either
updated I14 tables (which no longer exist publicly) or accepting satellite
exclusions and documenting them.

**Three options, none free:**

1. **Find how 5.2 tolerated it** — inspect her `OUT/` logs for DOY 121 for
   excluded-satellite messages. Cheapest, and it settles whether the two runs
   were ever processing the same satellites.
2. **Run under I20** — tables current to 2024-09, still short of 2025 but two
   years closer. Introduces the §1.4 frame confound, so it answers "does the
   pipeline work" and not "does it reproduce her numbers".
3. **Source updated I14 tables** from another archive.

Option 1 first. It is the only one that does not change what is being measured.

### 4b.6 Answered: how 5.2 tolerated it, and why 5.4 will not

Her retained processing summary — `SAVEDISK/2025/OUT/R2S251210.PRC`, 56,781
lines — settles the question §4b.5 posed.

**Her run completed with 26,172 warnings and 3 errors.**

```
### SR RCVOBS: Satellite/system not found      (x thousands)
                Receiver name    : TRIMBLE ALLOY
                PRN              : E02 / E03 / R01

*** SR R2RDOH : NUMBER OF SAT. (NUMLST) > MAXSAT   136 > 135
*** PG RXOBV3: TOO MANY OUTPUT FILES DEFINED       31 defined, 30 found
```

`###` is a warning in Bernese, `***` an error. **She had all three `***` errors
and still produced `F1_251210.SNX`.** So 5.2 pressed on through conditions 5.4
treats as fatal — the version difference is real, and it is one of tolerance
rather than capability.

The `RCVOBS` warnings also confirm her data *was* multi-GNSS (Galileo and
GLONASS PRNs on a TRIMBLE ALLOY): `V_SATSYS=GPS` meant those observations were
warned about and skipped, not absent.

#### The I14 model set is retired, and 5.4 enforces what 5.2 did not

Two independent blockers, neither a configuration error:

**1. Satellite tables end in 2023.** Hers 2023-01-31; 5.4's `SATELLIT_I14.SAT`
2023-08-10; `SATELLIT_I20.SAT` 2024-09-17. **AIUB no longer publishes
`SATELLIT_I14.SAT`** — `BSWUSER54/CONFIG/` returns 404 for I14, 200 for I20.
Against 2025 data the PRN→SVN resolution lands on stale entries, and CODSPP
stops on `BLOCK IIR-A 044` — a satellite that *is* in the antenna file.

**2. The I14 ANTEX fails 5.4's consistency check.** Her run logs *"Antenna phase
center model updated with: I14.ATX"*, so `V_MYATX=I14.ATX` and ATX2PCV merged it.
On 5.4 that is rejected outright:

```
*** PG ATX2PCV: Given SVN and PRN inconsistent in ANTEX file.
                File not converted!      PRN: 22   SVN: G041
```

All three variants in her tree fail it — `I14.ATX` carries four `G041` entries
with different PRN mappings across epochs; `I14-orig.ATX` and `I14_1.ATX` carry
one each and fail the same way. A file 5.2 consumed without complaint is invalid
to 5.4.

**Setting `V_MYATX` therefore fails EARLIER (PID 002) than leaving it blank
(PID 232).** It is left blank, with that reasoning recorded at the override.

#### What this means for the exercise

**Reproducing her I14 numbers on 5.4 is not a configuration problem to be
solved — it runs into a retired model that 5.4's stricter validation rejects.**
The honest options:

| Option | Cost |
|---|---|
| **Run under I20** | Tables current to 2024-09 and ANTEX consistent. Answers *"does the pipeline work"* — **not** *"does it reproduce her numbers"*, since it introduces the §1.4 frame difference the exercise exists to isolate. |
| Source updated I14 tables | They are not published. Would need another archive or a hand-repaired ANTEX. |
| Relax 5.4's validation | Not obviously possible, and it would mean processing data the software considers inconsistent. |

**Recommendation: run I20 first, explicitly as a pipeline test rather than a
comparison.** It establishes that the 31-day chain executes end to end on this
machine, which is BRN-001 acceptance evidence in its own right. The I14
comparison then becomes a separate question — and the finding that I14 cannot be
run on 5.4 at this epoch is itself a result worth reporting to Abegail, since it
bears on how the LUZON series can be continued at all.

### 4b.7 I20 pipeline test: the chain runs, and where each configuration stops

**I20 cleared the I14 blocker, confirming §4b.6.** Same PCF, same data, same
GPS-only selection; only the frame/antenna triple changed.

| Configuration | Furthest PID | Time | Result |
|---|---|---|---|
| **24 local stations** (RINEX 2 only) | **513 HELMCHK** | 4m12s | **`FIN_20251210.NQ0` produced** |
| **32 stations** (+ 9 RINEX 3 fiducials) | 322 GPSEDT | 3m22s | fails earlier |

**The 24-station run is the deepest yet and produced a final ambiguity-fixed
solution.** Its only failure is the closing QC gate:

```
*** PGM HELMR1: NO REDUNDANCY. NO VERIFICATION OF SITES POSSIBLE
```

Cause understood: **5.4's stock `RNX2SNX.PCF` has no `V_RX3DIR`** — that variable
is specific to her extended 5.2 PCF — so the RINEX 3 fiducials were never staged,
and none of the 24 locals is an IGS20 reference station. Nothing to transform
against.

`RNX_COP` in 5.4 *does* handle RINEX 3 natively (it globs long names from the
same `${rnxDir}`), so the fix is to stage RINEX 2 and RINEX 3 into **one**
directory rather than two. Done, with BASC/CLAV de-duplicated in favour of
RINEX 3 per §1.1a. All 32 stations then staged and **`RXOBV3` passed** — every
station matched a `LUZON.STA` entry, no hard abort.

#### But the fiducials introduce a new stop: ocean loading

```
*** SR GTOCNL: OCEAN LOADING CORRECTION VALUES NOT FOUND
               STATION NAME : ALIC 50137M001
               FILE NAME    : ${P}/LUZON/STA/LUZON.BLQ
```

**No `.BLQ` anywhere in her tree contains ALIC.** All four copies of
`LUZON.BLQ` are identical (1,544 lines) and cover only the local network. So
either her run did not process the fiducials' observations — using them purely
as datum constraints — or 5.2 warned where 5.4 errors. Given §4b.6's finding
that 5.2 completed with 3 `***` errors, the second is more likely.

**This is the same shape as everything else in §4b: a check 5.4 enforces and 5.2
did not.** It is now the fourth instance.

#### Consequence for scheduling

There is **no configuration that completes a single day cleanly**:

- 24 stations → reaches the end, produces `FIN_*.NQ0`, fails datum verification
- 32 stations → fails at baseline editing on missing ocean-loading coefficients

A multi-day batch is therefore **not yet worth running.** What a 31-day run of
the 24-station configuration would establish is throughput and stability — real,
but modest against what is already known from one day — and every solution it
produced would lack datum control.

**The next task is to obtain ocean-loading coefficients for the nine fiducials**
(free from the Onsala/Chalmers BLQ service) and merge them into `LUZON.BLQ`.
That closes the last known gap and makes both the datum verification and a
multi-day run meaningful at the same time.

### 4b.8 Closed — one day complete, and the month launched (2026-08-06)

The ocean-loading gap is closed. Coefficients for the nine fiducials came from
the Chalmers/Onsala service (FES2004, CMC:NO, Gutenberg-Bullen — chosen to match
the 135 existing stations, not for being newest) and merged into `LUZON.BLQ` via
`scripts/merge_blq.py`. **DOY 121 then completed cleanly:** `Sessions finished:
OK: 1 Error: 0`, 5m36s, 30 stations in `FIN_20251210.SNX` — the same count
Abegail's run produced — with `HELMCHK` and `COMPARF` both passing.

So both failure modes in the table above are resolved, and the answer to "is a
multi-day batch worth running" flipped. `scripts/run_luzon_month.sh` runs
2025 DOY 121–151 and was launched on 2026-08-06.

**Results go to `${S}/LUZON/$Y+0`, not the stock `${S}/RNX2SNX/$Y+0`.** Every
RNX2SNX-derived campaign shares the stock path, so `EXAMPLE`'s output would land
beside LUZON's with nothing in the filename to separate them.

**DOY 139 is excluded, and this is a data-holdings finding rather than a
processing one.** Our copy of her `DATAPOOL/LUZON` holds exactly one RINEX2
station for that day (`TGDN`) where every neighbouring day holds 25 — yet
`F1_251390.SNX` exists in her `SAVEDISK`, so the observations were present when
she processed. **Our copy of that day is short; the original was not.** Worth
raising alongside the I14 finding, because it means the transferred set is not a
complete mirror of what she worked from, and nothing else has yet checked for
other such days outside this 31-day window.

Running it anyway would have produced a solution from the nine fiducials plus
TGDN — whose own session is 43% of a day (§4b.10) — sitting in `SOL/` beside
thirty proper ones and distinguishable only by opening it. Ten stations of which
nine are fiducials is not a Luzon network solution.

*(An earlier version of this paragraph said TGDN was "one of the two stations
DOY 121 dropped" and would therefore be absent too. TGDN is dropped on DOY 121
only; it appears in the other nine solutions. The conclusion is unchanged —
the day is degenerate either way — but the reasoning was wrong.)*

### 4b.9 Two stations differ from her run, and neither is the frame

Comparing DOY 122 station-for-station against her `F1_251220.SNX`: **30 of 31
stations agree. She has `S01R` and not `PIMO`; we have `PIMO` and not `S01R`.**
The counts match at 31, which is why this went unnoticed — a station-count check
would have passed.

`PIMO` is straightforward: it is one of the nine fiducials we stage from
RINEX3, and her fiducial set did not include it.

**`S01R` is the one to look at.** It is absent from *all ten* of our solutions so
far, and present in hers. What is verified:

- Its RINEX samples at **15 s** where every other station samples at 30 s
  (5760 epochs against 2880).
- It is present in `LUZON.CRD`, `.STA`, `.BLQ`, `.CLU` and `.ABB`, and appears in
  `FIN_*.CRD` — but **carries no estimation flag**, i.e. it is the a priori value
  passed through, never solved. Estimated stations carry `G`.
- It has entries in `BSL_*.BSL` but produces **no observation files** under its
  `S0` abbreviation.
- **No `***` message anywhere in the BPE logs names it.** It leaves the solution
  silently.

Two more hypotheses were checked 2026-08-11 and both ruled out:

- **Not a stale station-info entry.** `LUZON.STA` TYPE 002 has a clean,
  unambiguous entry for S01R covering 2025-04-15 onward (`TRIMBLE ALLOY` /
  `LEIAR25 LEIT`, serial `6318R40040` / `09120019`) that matches the RINEX
  header exactly. (The log does have a real defect nearby — overlapping/
  duplicate entries for the 2017-11-16–2025-04-14 period, one open-ended to
  2099 and one properly closed — but that period predates our window and does
  not touch it.)
- **Not an unrecognized antenna model.** `LEIAR25 LEIT` is present in
  `REF54/ANTENNA_I20.PCV` (line 184270).

**What is now established, and changes the framing entirely: S01R is not a
chronically-failing station.** It carries an estimated velocity in
`LUZON.VEL` (`-0.02209 -0.00659 -0.01191` m/yr, EURA-relative), its equipment
log runs continuously back to 2002-01-01, and it appears in **364 of the 365
daily solutions she produced in 2025** — spot-checked across the full year,
not just this window. **It fails in all ten of our I20 reprocessing runs and
in none of her I14 runs over the identical calendar days.** The station is
not the anomaly; this pipeline is. Something specific to the 5.4/I20
derivation — not yet identified — regresses a station that has processed
reliably for over two decades under 5.2.

The consequence is worth stating plainly: a station that contributes to her
results every day contributes nothing to ours, and the pipeline reports
success either way. That is the same defect class as §19.3 of the session
log, this time in Bernese rather than in our own tooling — and here it is
regressing a real, long-standing contributor rather than excluding a
marginal one.

**Separately: is S01R needed at all?** Answered — the guess two paragraphs
above (Luzon Strait / Taiwan collision-zone science) was wrong. The real
reason is documented twice in this repo: once at the source, in PHIVOLCS's own
work instructions (authored by Cass, Dane and Abegail — GPS data-processing
staff, not the user), and again in `docs/work_instructions_review.md` (the
user's October 2025 technical review of that document).

The source text, verbatim:

> *"For this subsection until Subsection 5.5, we will keep using PHIVOLCS as
> the active Campaign. We will also use the RINEX observation data from
> multiple sites in the PHIVOLCS network, along with the S01R station in
> Taiwan. The continuously operating station S01R, which sits on the stable
> Chinese continental margin, will serve as the reference point for plotting
> the time series."*

> *"6.2.4.2. When prompted to 'Input the reference station', enter 'S01R'.
> This site in Taiwan is used as the reference point for velocity
> computations relative to the Eurasian Plate. Note that the choice of
> reference station for velocity computations is not fixed, as other stations
> may be used based on needs or the intended analysis. The resulting output is
> an ENU file compiling the daily XYZ-to-ENU converted coordinates of all
> sites, as well as individual files named after each site containing their
> respective daily ENU coordinates."*

Two things this adds beyond "S01R defines a Eurasia-relative velocity frame":
the reference role is used for **both** the time-series plotting step and
velocity computation, and mechanically it works by **converting every site's
daily XYZ into local ENU coordinates using S01R's position as the origin** —
an XYZ→ENU transform downstream of the daily positioning, not necessarily a
Bernese-level fixed-station constraint inside GPSEST/ADDNEQ2 itself. That
matters for how disruptive changing it would be: if reference-station choice
is a parameter to that ENU-conversion step (Section 6.2.7's MATLAB processing,
per `work_instructions_review.md`'s table of contents) rather than something
baked into the Bernese adjustment, switching it is a parameter change to a
downstream script, not a reprocessing-pipeline redesign — though this document
has not confirmed that script's actual mechanics, so treat it as likely rather
than verified.

The document itself already answers the follow-up: **the choice is not
fixed.** *"The choice of reference station for velocity computations is not
fixed, as other stations may be used based on needs or the intended
analysis"* — and the user's review names alternatives explicitly: **PIMO**
(Luzon-specific studies), an IGS global-network average (plate-motion
studies), or another PHIVOLCS site (relative baseline analysis).

PIMO is one of this network's own nine RINEX3 fiducials — already flowing
through this pipeline daily, with no foreign dependency. Switching the
documented default from S01R to PIMO would preserve a defensible reference
frame (Luzon-relative rather than Eurasia-relative — a real, different
scientific choice, not a downgrade) while removing the Academia Sinica
retrieval dependency and the pipeline regression in §4b.9 entirely, at zero
new infrastructure cost.

So: not superstition, but not a hard requirement either. The SOP already grants
permission to change it; nothing has acted on that permission. Whether
Eurasia-relative is scientifically preferable to Luzon-relative for PHIVOLCS's
actual hazard/fault-slip analysis is a real judgment call outside what this
document can settle — but continuing to retrieve S01R specifically, rather than
either fixing today's regression or switching to the alternative the SOP
itself already names, is the part that looks like inertia rather than an
active, reaffirmed choice.

### 4b.10 Repeatability: the solutions are good, and that is not the same as correct

`scripts/coord_repeatability.py` over the **completed 30 days** gives **median
N 2.8 mm, E 3.0 mm, U 10.9 mm** across 31 stations — ordinary for daily
double-difference solutions, and the first evidence that the derived PCF is not
merely executable but sound. Horizontal held steady as the series lengthened
(2.9/3.4 mm at ten days), which is what a stable configuration looks like.

**This is precision, not accuracy.** A solution in the wrong reference frame
would show the same repeatability, because every day would be wrong identically.
It is not evidence about I20 versus I14 and must not be quoted as such.

**By a single-station threshold, no day is bad network-wide** — see §4b.11 for
why that qualifier matters and turns out to be wrong for a different, more
consequential reason. Scanning all 30 days for stations more than 30 mm from
their own mean: **25 days are completely clean**, and the other five have
**exactly one** bad station each. Only two stations are ever involved.

| DOY | stations >30 mm | worst |
|---|---|---|
| 124 | 1 | TGDN 66 mm |
| 137 | 1 | LGYE 200 mm |
| 138 | 1 | TGDN 67 mm |
| 140 | 1 | LGYE 35 mm |
| 151 | 1 | LGYE 111 mm |

That distinction carries the weight. A bad *configuration* degrades every station
on every day; bad *stations* degrade themselves. This is the second pattern.

**TGDN is fully explained by session length**, and the 43% figure quoted from
DOY 122 understated it — sessions vary enormously day to day:

```
DOY 123: 875 epochs    DOY 124: 124 epochs   (~1 hour)
DOY 137: 1119 epochs   DOY 138: 112 epochs
```

Its two worst days are its two shortest. Nothing to fix in the pipeline.

**LGYE is not explained by session length.** It has a **full 2880 epochs on
every one of its bad days** (137, 140, 151). It is, however, **ruled out as a
seismic event** by §4b.11's neighbour check: BLN2 sits 51 km away and stays
within 3 mm on both of LGYE's worst days. A real earthquake large enough to
move LGYE 200 mm would move BLN2 too. **This is open as a station/processing
problem** — ambiguity resolution failing on that day, or a site-specific issue
at LGYE — but closed as a possible earthquake.

**ANTP** — 30.1 mm vertical with normal horizontals across the month, on
full-length sessions. Elevated but never an outlier by the 30 mm horizontal test;
older LEICA GRX1200GGPRO / LEIAT504 equipment.

### 4b.11 A single-station threshold misses the signal this project exists to
### detect — network coherence, checked properly

§4b.10's "no day is bad network-wide" used a 30 mm **single-station** threshold.
That is the wrong test for a seismic event: a real earthquake displaces several
**nearby** stations **together**, often by amounts well under what would flag
any one of them alone. `scripts/network_coherence_scan.py` checks for that
directly — pairs of stations within 120 km both exceeding 8 mm horizontal
(≈2.5× the median repeatability) in the same direction (cosine similarity >0.5).

**It found what the single-station scan missed. DOY 126 (2025-05-06): 14
stations moved together, 8–30 mm, dozens of coherent pairs across the entire
southern-to-central Luzon cluster** — ALAB, ANTP, BLN2, CAC2, GUMA, GUNG, IBAZ,
MAUB, MLPA, PIMO, SAPN, TANY, TGDN, and more. Smaller versions of the same
pattern appear on DOY 129 (8 stations) and DOY 145 (13 stations). None of these
were visible in §4b.10 — no single station on DOY 126 individually cleared
30 mm by much (ANTP peaked at 29.8), so a network-wide 14-station shift hid
inside a check built to catch one bad station.

**Distinguishing a real event from a processing artifact: is it a step or a
spike?** A coseismic offset is permanent — it persists in every subsequent
day's solution because the ground actually moved. Reading the day-by-day series
for the DOY 126 stations: DOY 125 is quiet (1–8 mm, ordinary), DOY 126 jumps to
9–30 mm across nearly the whole network — including BLN2, IBAZ and TGDN in the
north, so it is not confined to one geographic cluster — and **DOY 127 drops
straight back to 1–5 mm.** That is a spike, not a step, and a spike that
reverts completely in one day is the signature of something specific to that
day's processing, not of ground motion.

**Corroborated against the catalog.** A web search against PHIVOLCS/USGS
reporting found **no earthquake recorded on 2025-05-06, 05-09, or 05-25** — the
three flagged dates. There **is** a confirmed M4.6 near General Nakar, Quezon on
**2025-05-27 (DOY 147)**, and checking the stations nearest that epicenter
(POLI, MAUB, GUMA, and others) on that date shows **no anomaly at all** — 0.5 to
6.8 mm, ordinary noise. That is a useful negative control: a real but small
(M4.6) event at tens of km from the nearest station is below what daily static
GNSS resolves, and the scan correctly stays quiet for it rather than
manufacturing a signal out of noise. Both halves — flagging three unexplained
network-wide days with no earthquake behind them, and staying silent for a
real one too small to see — say the method is behaving sensibly.

**The technical cause of the DOY 126/129/145 spikes is not identified.** Two
candidates were checked and ruled out: the CODE SP3 orbit file for DOY 126 is a
normal size (no truncation), and the fiducial-fixing list in `HLM_20251260.FIX`
is identical to every ordinary day — just AIRA. Whatever produces a whole-day,
whole-network, fully-reverting shift remains open. Recorded as unexplained
rather than assigned a plausible-sounding cause, on the same principle as the
S01R and LGYE findings above.

**What this means for anyone using this pipeline for actual event detection**:
a single-station outlier check is not sufficient and will miss a coordinated
multi-station shift unless it happens to also blow past the single-station
threshold. Any future monitoring built on this pipeline needs the coherence
check as a matter of course, not as an afterthought — and needs the step/spike
distinction made explicit, since an automated system that flags DOY 126 as
"earthquake" without checking DOY 127 would have been wrong.

**The month is a pipeline test under I20, not a comparison.** §4b.6 stands: I14
cannot run on 5.4 at this epoch. Do not difference these coordinates against the
`F1_25*` series and attribute the residual to a Bernese version change — the
frame and antenna model both moved.

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

**Confirmed by census, 2026-08-06.** The claim above was carried forward from the
transfer handover; it has now been checked directly against both trees:

```bash
find /srv/gnss-archive /home/gps3/GPSDATA -name '????[0-3][0-9][0-9]0.25[oOdD]' \
  | sed 's|.*/....\([0-9]\{3\}\)0\.25.|\1|' | sort -u
```

Both return exactly DOY 121–151 and nothing else. Against 365 solved days in
2025 alone, **the reproducible fraction of that year is 8.5%**, and of the
sixteen-year series, well under 1%.

Within the reproducible month, one day is itself short: **DOY 139 holds one
RINEX2 station where its neighbours hold 25**, though she solved it — so even our
"complete" month is 30 days, not 31 (§4b.8). Her `DATAPOOL/LUZON` is a rolling
staging area holding roughly a month, not an archive; what was transferred is a
snapshot of that window, which is why the boundary falls where it does rather
than at anything meaningful in the data.
