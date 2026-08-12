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


---

## Installed on gps3 — 2026-08-12, and an unreconciled disagreement

**Binary is now on the R740** at `/home/gps3/gfzrnx/gfzrnx_2.2.0_lx64`, relayed
from the T420 (`~/T420_NOTE_20260812_gfzrnx.md`, zip md5
`71f8cfe291a1c767bafa6e1cd0ec811e` — verified on arrival). **Not committed to
the repo**, consistent with the note above: it is licensed software.

Two T420 warnings, both confirmed here:
- **The zip strips the execute bit.** A first run fails "permission denied"
  with nothing pointing at the cause. `chmod +x` after unzipping.
- **The manual is a version behind** — docs are `2.0-8219`, binary is `2.2.0`.
  Check `-h` on the binary before believing a documented flag is broken.

Verified working against our own data: `AIRA00JPN_R_20251210000_01D_30S_MO`
(RINEX **3.02**, MIXED) decompressed with BSW's `CRX2RNX`, then
`gfzrnx -finp ... -stk_obs` returns full per-satellite statistics including
Galileo. Same result class as the CUSV test above, on a different fiducial.

### The disagreement, stated plainly rather than resolved

This document (2026-07-01) concludes the migration trigger is **MET**. The
T420 note (2026-08-12) states the standing decision as **"teqc stays primary,
gfzrnx is not a replacement and is not scheduled to become one,"** with the
trigger being "the first RINEX 3/4 file that teqc fails to handle."

**By that trigger's own wording, it has fired** — twice now, documented, on
files already on disk. The two statements are not reconcilable as written.

What they *do* agree on, and what is not in dispute:
- teqc cannot read RINEX 3.x at all — it is a version limit, not a multi-GNSS
  limit. The T420 note is right that "multi-GNSS alone is not the trigger."
- gfzrnx reads it cleanly.
- Local PHIVOLCS CORS still emit RINEX 2, which teqc handles.
- IGS fiducials are RINEX 3, which teqc cannot touch.

So in **practice** both tools are needed today and the disagreement is about
framing, not about which tool to run on which file. The operational rule that
follows from the facts: **teqc for the RINEX-2 local subset, gfzrnx for the
RINEX-3 fiducials and IGS products.**

### The part that actually blocks automation

**Licensing.** The free GFZ scientific licence covers manual and research use —
which is what PHIVOLCS (Cass) has done for years and what the verification
above is. **Automated/operational pipeline use requires a commercial licence,
which has not been obtained.**

**Direction given 2026-08-12: proceed with gfzrnx; do not treat the licence as
a blocker. Document all instances where it is *actually used* — as part of the
reproducibility goals of the GNSS pipeline orchestration, not as a procurement
exercise.**

The distinction matters. A speculative list of "places a licence would be
required" is a legal artifact that rots the moment the code changes. **A record
of what actually ran is a scientific artifact**: it answers "which tool, at
which version, with which flags, produced this file?" — the question a
successor or a reviewer will ask about a coordinate series in 2031. The licence
exposure is then a byproduct of that record rather than a separate thing to
maintain.

**What this means in practice.** Every pipeline stage that invokes an external
binary — gfzrnx, teqc, CRX2RNX, runpkr00, the BSW programs — should emit a
provenance record alongside its output, capturing at minimum:

- tool name and **version as self-reported by the binary**, not as assumed
- the exact argument vector
- input file(s) with a checksum
- output file(s) with a checksum
- timestamp and host

This is the same discipline the archive still lacks (no fixity — see the
succession audit), applied at the point of processing rather than retrofitted
afterward. It makes a run reproducible, makes a silent tool substitution
detectable, and incidentally makes the gfzrnx usage question answerable by
query instead of by memory.

Not yet implemented. It belongs in whatever orchestration layer
`services/bernese-workflow` grows into, and should be designed in rather than
bolted on.

### Missing from this repo

Both this document and the T420 note reference **`gfzrnx_teqc_decision.md`** as
the authoritative decision record. **It is not in this repository** — it lives
in the T420 session's memory. That absence is why two sessions hold different
views of the same decision. It should be brought into the repo so the decision
travels with the evidence.
