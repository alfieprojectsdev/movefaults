# PHIVOLCS Bernese 5.2 production assets — LUZON network

**Delivered 2026-08-03, captured into the repo 2026-08-04** from
`/run/media/finch/DOSTB20150918/processing_files/` — a 22 GB set produced by
**Abegail** (she handles the Luzon network) at PHIVOLCS and delivered on the
DOSTB external drive.

**This is the production workflow of record.** Not a training example, not a
reconstruction — `GPSTEMP/` on that drive holds **1,203 `BPE_PHIVOL_REL_*`
work directories**, so these panels drove real BPE runs. `PHIVOL_REL.PCF` is
dated **2025-09-12**.

Its counterpart, the 5.4 PAGENET set captured 2026-08-03 from the T420, is in
`../gpsuser/`. Read both PROVENANCE files before comparing results — the two
runs do **not** use the same models (§4).

---

## 1. What is here

| Path | Contents |
|---|---|
| `PCF/PHIVOL_REL.PCF` | **the production PCF**, 84 PIDs, 2025-09-12 |
| `PCF/PAGENET.PCF` | 2015-07-23, 77 PIDs — ancestor |
| `PCF/PAGENET2.PCF` | 2019-10-03, 81 PIDs — ancestor |
| `OPT/` | the 11 option directories `PHIVOL_REL.PCF` references |
| `STA/LUZON.{STA,CRD,VEL,ABB,CLU,BLQ,ATL,PLD}` | the network's reference set — **152 stations** in `LUZON.STA` |

`*.bck` editor backups (44 files) were dropped.

**One deliberate modification: operator names were scrubbed.** Bernese panels
carry a free-text `"USER"` field in the `ENVIRONMENT` block recording whoever
last saved the panel from the menu. Across this tree it held four different
PHIVOLCS staff names and workstation accounts, in 72 files. All were replaced
with `"<operator>"`.

This repository is **public**, and a colleague's name published without her
knowing is not something a capture is entitled to do. The field is menu
metadata — it does not affect processing, and it is not the provenance that
matters here. What ran, and against which models, is recorded in this document
and in git history; who happened to press save is not.

Everything else is byte-for-byte.

---

## 2. Why this PCF matters more than the one it was compared against

`../gpsuser/PCF/PAGENET_DLY.PCF` (the 5.4 training-week file) has **46 PIDs**.
This one has **84**, and the difference is not padding — it is the entire
back half of an operational workflow:

```
521 ADDNEQ2  R2S_RED     size-reduced NEQ branch
522 GPSXTR   R2S_RED
530 ADD_WK   PHI_WK      weekly combination
531 ADD_MON  PHI_MO      monthly combination
901 R2S_SUM  902 R2S_SAV  903 R2S_DEL      summarise / save / clean
991 BPE_CLN  999 DUMMY
```

Two open project questions are answered by this file:

1. **`docs/gps3-sessions/SESSION_LOG_20260729_storage.md` §14.5** worried that
   `PAGENET_DLY.PCF` might be an unsafe by-eye truncation leaving `599 DUMMY`
   waiting on an undefined 522. It is not: `PAGENET_DLY` is a deliberate
   reduction of *this* lineage, with 521/522 removed **and** 599 rewired to
   compensate. Confirmed from the other direction.
2. **Readiness item M** — *"decide Module 15/16 scope before building
   weekly/monthly plumbing"* — has a reference implementation here:
   `530 ADD_WK`/`PHI_WK` and `531 ADD_MON`/`PHI_MO`.

One structural difference worth noting when diffing the two: `513`/`514` are
**swapped**. This file runs `513 COMPARF`, `514 HELMCHK` with `NEXTJOB=511` on
514; `PAGENET_DLY` runs `513 HELMCHK` (NEXTJOB=511), `514 COMPARF`. Both are
coherent; they are not the same iteration structure.

---

## 3. ⚠ These panels are Windows-origin and NOT sanitized

Six **live** `.INP` files (not backups) carry `C:\Bernese\…` absolute paths:

```
OPT/PHI_WK/ADDNEQ2.INP        "U" "C:\Bernese\GPSUSER52"
                              "T" "C:\Bernese\GPSTEMP"
OPT/R2S_EDT/GPSEST.INP
OPT/R2S_EDT/RESRMS.INP
OPT/R2S_EDT/SATMRK.INP
OPT/R2S_GEN/CODSPP.INP
OPT/R2S_GEN/RNXSMT.INP
```

This is the same defect class as `../gpsuser/OPT/PGN_WK/MENU.INP`, and it is
recorded in the readiness notes as gap #8: **on Linux a backslash is a literal
character, not a separator**, so these do not fail loudly — they resolve to
filenames that happen to contain backslashes.

**Do not run these panels unmodified on gps3.** `scripts/provision_gpsuser.py`
sanitizes `OPT/**/*.INP` separators and should be pointed at this tree before
any use. Expect it to reject on first pass; that is the tool working.

The `ENVIRONMENT` block needs more than separator conversion — the `U`/`T`
values are a different machine's install layout, not just a different slash.

---

## 4. Model differences — read before comparing any results

The tuning parameters agree between the 5.2 and 5.4 sets; the **models do not.**
Reprocessing the LUZON data under 5.4 will move coordinates for reasons that
have nothing to do with PCF tuning.

| | this set (5.2 LUZON) | `../gpsuser/` (5.4 PAGENET) |
|---|---|---|
| Antenna / PCV | **I14** (`V_PCV=I14`, `V_MYATX=I14.ATX`) | **I20** (`ANTENNA_I20.PCV`, `SATELLIT_I20.SAT`) |
| GNSS for ambiguity resolution | **ALL** | **GRE** |
| Max baseline MW/L3, QIF, L5/L3, L1&L2 | 6000 / 2000 / 200 / 20 | identical |
| Stations per cluster (`V_CLU`) | 10 | identical |

I14 → I20 is a cm-level, largely vertical, systematic shift. **Reprocess with
I14 first and reproduce Abegail's numbers**, then change to I20 as a separate,
deliberate run. Comparing a fresh I20 result against her I14 result and
attributing the difference to PCF tuning would be wrong, and plausibly wrong —
the magnitude is in the range a tuning change could produce.

---

## 5. The rest of the delivery, not committed here

Left on the drive (too large for git, and data rather than configuration):

| | |
|---|---|
| `GPSDATA/CAMPAIGN/LUZON/` | ATM 154, OBS 2064, ORB 554, **SOL 1944**, OUT 6582 |
| `GPSDATA/DATAPOOL/LUZON/` | 741 RINEX obs, **DOY 121–151 of 2025** (31 days), 25 stations |
| `DATAPOOL_IGS/` | 94 SP3 |
| `DATAPOOL_BSW52/` | 39 ION |
| `BERN52/GPS/GEN/` | `C04_*.ERP` (1986→), `BULLET_A.ERP`, `ANT_COD_I14.PCV`, `ANT_COD_I20*.PCV` |
| `BERN52/` | full software tree, `update_2020-08-27.zip`, `exe_aiub_64_2021.zip` |

`SOL/` is the comparison target — `F1_*.NQ0` daily finals plus `WK_2413`/`WK_2414`
weekly `.NQ0`/`.SNX`.

`CAMPAIGN/LUZON/RAW`, `ORX` and `GRD` are **empty**. `RAW` does not matter —
`OBS` holds the converted observations. This is not a truncated delivery.

### Version, and how it was run

Neither had to be asked. `BERN52/` contains `update_2020-08-27.zip` and
`exe_aiub_64_2021.zip`; the 1,203 `BPE_PHIVOL_REL_*` directories in `GPSTEMP/`
establish it was BPE-driven, not GUI.

---

## 6. Transfer hazard, already realised

The drive is **NTFS**. A `find` across all 67,553 files returns **zero
symlinks** — every one was flattened in transit, the same failure that hit the
BERN54 thumb-drive transfer and forced the REF54 links to be rebuilt by hand on
gps3.

Impact is limited: `DATAPOOL_REF52/` lost its `EXAMPLE.CRD → EXAMPLE.CRD_REF`
style links (the `_REF` targets survive as real files), which only matters for
the Bernese *example* campaign. **LUZON's `STA/` holds real files, so the
campaign that matters is intact.**

If anything is copied onward from that drive, `tar` it first — copying loose
compounds the flattening and loses permissions too.
