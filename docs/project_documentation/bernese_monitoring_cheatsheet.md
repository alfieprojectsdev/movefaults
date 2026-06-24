# Bernese BPE — Files & Folders to Monitor During Processing

Quick reference for watching a live RNX2SNX (or any PCF) BPE run. Paths are relative to the
campaign root `$P/<CAMPAIGN>/` (e.g. `~/GPSDATA/CAMPAIGN54/EXAMPLE/`). `<SYSOUT>` = the PCF's
sysout name (e.g. `RNX2SNX`). Per-step files are named `<SS>YYDDDS_<PID>_<SUB>.{PRT,LOG}`
(e.g. `RS230100_443_000.PRT` = RNX2SNX, year 23, DOY 010, session 0, PID 443, sub 000).

Verified against the EXAMPLE run on 2026-06-22 (20m40s, 18 stations, 0.0000 mm vs reference).

---

## 1. Live status — watch these first

| Path | What it tells you |
|---|---|
| `BPE/<SYSOUT>.RUN` | **The live dashboard.** One line per PID: `waiting` / `running` / `finished` / `error`. `tail` or refresh in editor to track progress. |
| `BPE/<SYSOUT>.OUT` | Master BPE log. Header (campaign/year/session/PIDs), `BPE finished at ...` line, and any fatal `### ERROR`. Grep `started on` / `finished` for runtime. |

Quick status count:
```bash
awk '{print $NF}' BPE/<SYSOUT>.RUN | sort | uniq -c    # counts waiting/running/finished/error
```

---

## 2. Per-step output (as each PID runs)

| Path | What it tells you |
|---|---|
| `BPE/<...>_<PID>_<SUB>.PRT` | Per-program protocol — timestamps, `PROGRAM STARTED/ENDED`, `### SR` warnings, errors. |
| `BPE/<...>_<PID>_<SUB>.LOG` | Short stdout/stderr capture for that step. |
| `BPE/*.BPE` | Per-step BPE control/marker files (e.g. `SPP_..._003.BPE`). |

A step that fails leaves its PID at `error` in `.RUN` and a non-clean `.PRT`. New `.PRT`/`.LOG`
files appearing = run progressing.

---

## 3. Quality gates — the PIDs that decide solution validity

Watch these specific per-step PRTs (map from BPE phase model):

| PID | Program | Gate | Watch for |
|---|---|---|---|
| **221 / 222** | RXOBV3 | **Station drop** | Stations silently dropped on header/STA mismatch. #1 staff pain point. Confirm expected station count survives. |
| **443** | AMBXTR | Ambiguity fixing | Fixing rate (target ~80%). |
| **513** | HELMCHK | Reference station motion | Helmert residuals < ~1 cm; no reference station rejected. |
| **514** | COMPARF | Daily repeatability | ENU repeatability < ~3 mm typical. |

---

## 4. Output products (appear progressively, finalize at end)

| Folder | Contents | Notes |
|---|---|---|
| `OUT/` | `SPP_*.OUT`, `OBS_*.OUT`, `SMT_*.OUT` program outputs; `RNX_*.ERR` | `RNX_*.ERR` often non-empty with **benign** header warnings (missing GLONASS COD/PHS/BIS, SYS/PHASE SHIFT) — not station drops. |
| `SOL/` | `FLT_*.NQ0` (float), `RED_*.NQ0` (reduced), **`FIN_*.NQ0`** (final normal eqns), **`FIN_*.SNX`** (final SINEX coords) | Final solution. `FIN_*.SNX` = deliverable coordinates. Appears only when run completes. |
| `ATM/` | troposphere / ionosphere products | |

End-state check — final files exist + clean:
```bash
ls -lt SOL/FIN_*.SNX SOL/FIN_*.NQ0
grep -iE "finished|error" BPE/<SYSOUT>.OUT
```

---

## 5. Inputs (verify before run; not "output" but monitor if a run fails early)

| Path | Contents |
|---|---|
| `STA/<CAMPAIGN>.STA` | Station info (TYPE 002 receiver/antenna) |
| `STA/<CAMPAIGN>.CRD` `.VEL` `.ABB` `.CLU` | A priori coords, velocities, abbreviations, clusters |
| `RAW/` | Input RINEX (`*.RXO`) |
| `ATM/*.ATX` | Antenna calibration |

---

## 6. Temp work area (transient)

| Path | Notes |
|---|---|
| `$T/BPE_<SYSOUT>_<...>/` (e.g. `~/GPSWORK/BPE_RNX2SNX_..._443_000/`) | Per-step scratch dirs. Appear/disappear as PIDs run. Existence = that PID active. Cleaned by `BPE_CLN` (PID 991) at end. |

---

## 7. Reference comparison (verification runs)

| Path | Notes |
|---|---|
| `$SAVEDISK/RNX2SNX/<YEAR>/SOL/FIN_*.SNX.gz_REF` | AIUB-distributed expected solution. Diff STAX/STAY/STAZ vs your `SOL/FIN_*.SNX`. **Not** `$DATAPOOL/REF54/*.SNX` (those are global frames IGS20/IGB14). |

---

## One-liner: open the key live files in an editor

```bash
cd $P/<CAMPAIGN>
lite-xl BPE/<SYSOUT>.OUT BPE/<SYSOUT>.RUN &
# add gates once they exist:  BPE/*_221_*.PRT BPE/*_443_*.PRT BPE/*_513_*.PRT BPE/*_514_*.PRT
```
