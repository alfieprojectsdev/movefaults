# gfzrnx vs teqc — RINEX 3 evidence (migration trigger is MET, not pending)

**Date:** 2026-07-01
**Purpose:** Empirical demonstration that teqc cannot process the RINEX 3 data PHIVOLCS already
ingests, and that gfzrnx handles it cleanly — turning the teqc→gfzrnx migration trigger from
"when-not-if" into "already required today."
**See also:** `memory/gfzrnx_teqc_decision.md`, ticket **2.5 (RINEX QC)** in `deliverables_tracker.md`.

---

## The test

Same file through both tools: a PAGENET IGS fiducial, **CUSV 2026/087**, decompressed to RINEX.

- Input: `CUSV00THA_R_20260870000_01D_30S_MO.crx.gz` → (gunzip + CRX2RNX) → `*.rnx`
- Format: **RINEX 3.04**, multi-GNSS OBSERVATION DATA (M)
- Constellations present: GPS (G), GLONASS (R), Galileo (E), QZSS (J), **BeiDou (C, incl. BeiDou-3 C19–C62)**
- Size: ~48 MB, 30 s sampling, 1-day

Tools:
- **teqc** `2019Feb25` — UNAVCO, the final build (project discontinued 2019)
- **gfzrnx** `2.2.0` (lx64) — GFZ Potsdam, actively maintained

## Result

| | teqc 2019Feb25 | gfzrnx 2.2.0 |
|---|---|---|
| Read the RINEX 3.04 file? | **NO — hard refusal on line 1** | **YES** |
| Constellations QC'd | none (exits immediately) | GPS + GLONASS + Galileo + QZSS + BeiDou-3 |
| Runtime | instant fail | ~14 s for 48 MB |

**teqc output (verbatim):**
```
teqc: failure to read '     3.04           OBSERVATION DATA    M                   RINEX VERSION / TYPE'
        on line 1 of 'CUSV00THA_R_20260870000_01D_30S_MO.rnx'
        (unaccepted RINEX version or non-RINEX file; must be RINEX Version <= 2.11) ... exiting
```

**gfzrnx output (excerpt, per-satellite obs statistics, `-stk_obs`):**
```
 STP CUSV C TYP   C1X   C2I   C5X   C6I  ...
 STO CUSV C C19   980   985   999   991  ...   (BeiDou-3)
 STO CUSV C C38  2619  2630  2630  2621  ...
 STP CUSV E TYP   C1X   C5X   C6X   C7X  ...   (Galileo)
 STO CUSV E E04  1188  1188  1188  1188  ...
```

## Interpretation

- **teqc's own error is the whole case:** `must be RINEX Version <= 2.11`. It is a RINEX-2-era tool
  and cannot parse RINEX 3.x *at all* — it exits before reading a single observation.
- **This is not a future risk.** Every IGS fiducial in the PAGENET campaign is RINEX 3.04. teqc appears
  to "work" today only because the *PAGENET CORS* stations still emit RINEX 2 short-name files. The
  moment the data is RINEX 3 — which is all IGS/IGS20 product streams and the fiducials that tie the
  network to ITRF — teqc is blind.
- **teqc is frozen:** the binary self-reports `2019Feb25`, the last build. It will never support
  RINEX 3, by definition of being abandoned. No fix is coming.
- **This is why Cass (MOVE Faults COS staff) has run gfzrnx for years** — the RINEX 3 fiducials forced
  it. teqc was never viable for that half of the network.

## Consequence for the migration decision

The trigger defined in `gfzrnx_teqc_decision.md` — *"first RINEX 3/4 file teqc can't process"* — is
**MET now**, empirically, on data already on disk. It is not "months away." teqc remains usable only
for the GPS-only, RINEX-2 CORS subset; anything touching the fiducials or IGS products requires gfzrnx.

Licensing is unchanged (see `gfzrnx_teqc_decision.md`): free scientific license covers current manual
use (PHIVOLCS already practices this via Cass); the planned automated pipeline needs a commercial
campus license. Each user should hold their own free GFZ scientific registration.

## Reproduce

```bash
source ~/BERN54/LOADGPS.setvar
cp "$D"/PGN/CUSV00THA_R_20260870000_01D_30S_MO.crx.gz /tmp/ && cd /tmp
gunzip -f CUSV00THA_R_20260870000_01D_30S_MO.crx.gz
$C/SCRIPT/EXE/CRX2RNX -f CUSV00THA_R_20260870000_01D_30S_MO.crx
F=CUSV00THA_R_20260870000_01D_30S_MO.rnx
teqc +qc +quiet "$F"                 # -> refuses: must be RINEX <= 2.11
gfzrnx_2.2.0_lx64 -finp "$F" -stk_obs   # -> full multi-GNSS statistics
```

*Binaries: gfzrnx from `~/Downloads/gfzrnx/` (Cass); teqc `2019Feb25` from UNAVCO's teqc page
(https://www.unavco.org/software/data-processing/teqc/teqc.html). Neither binary is committed to the
repo — gfzrnx is licensed software, teqc is an external download.*
