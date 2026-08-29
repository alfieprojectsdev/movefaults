# Applying the 2024-11-11 bug fixes to the R740 BSW install

*Written 2026-08-29 while the PHREF year was finishing. **Not yet executed.***

## Current state

Our install is release `2024-11-11` with **none of its 7 published fixes
applied**. Verified rather than assumed:

- `$LG/IONOSP2.f90` carries `IGRF10`–`IGRF13`, not `IGRF14` → B_33 absent
- `$LG/O_RXOWRAP.f90` is dated **Oct 2023**, predating the release → B_34 absent

## What is on offer

| id | kind | component | why we care |
|---|---|---|---|
| B_33 | improvement | `IONOSP2.f90`, `IGRF14SYN.f` (HOI ionosphere) | **changes results** — geomagnetic field model |
| B_34 | improvement | `O_RXOWRAP.f90`, `RNXGRA.f` | **RNXGRA runtime ÷5–6**; we run RNXGRA once per session |
| B_35 | improvement | ETRS89 transformation, 8 files incl. panels | not on our path today |
| B_36 | bug | `UPDMEA.f90` (RXOBV3 calibration reporting) | reporting only, partial constellations |
| B_37 | bug | `D_RXNTYPE.f90` (RXN2PRE unhealthy-satellite detection) | **correctness**, satellite screening |
| B_38 | bug | `TRPSTORE.f90` (GPSEST, ADDNEQ2) | on our path; station-ID lookups when tropo SINEX off |
| B_39 | bug | `D_GRID.f90` NaN handling in GRD files | halts with a message instead of undefined behaviour |

Patch files are **publicly downloadable** (verified HTTP 200) from
`https://www.aiub.unibe.ch/download/BERN54/BUGS/2024-11-11/`. The
`UPDATE54` directory is **401-protected**, but that is only needed to bring an
*older* release current — we are on the latest release, so we need the
individual fixes, which are public.

## Three constraints that shape the whole thing

### 1. Cumulative — all seven, or none

`README/README_UPDATE.TXT` §3, verbatim:

> "Note: these updates are cumulative! You have to consider all of them. It may
> damage your installation if you try to establish only selected bug-fixes,
> corrections, or improvements."

So the tempting move — take B_34 for the RNXGRA speedup and leave the rest —
is explicitly the damaging one. **Do not cherry-pick.**

### 2. This changes the software mid-project

B_33 alters the geomagnetic field model used for higher-order ionosphere
corrections. B_38 touches `TRPSTORE.f90`, which is on the GPSEST/ADDNEQ2 path.
**Both can change numbers.**

The 2025 LUZON year (358 days) and PHREF year (359 days) were produced on the
**unpatched** build. After patching, new solutions are no longer bit-comparable
with them. That is not an argument against patching — it is an argument for
doing it at a **boundary**, and for recording which build produced which
product.

Consequences to accept before starting:
- The PHREF↔production comparison
  (`phref_vs_production_comparison_plan.md`) must be run on the **current,
  unpatched** build, or re-run entirely afterwards. Do not split it across a
  patch.
- Record the build identity in the run ledger from now on (see
  `bpe_orchestration_design.md` — the ledger already reserves a `config hash`
  field; the BSW build date belongs in it).

### 3. Never while a BPE is running

Recompiling replaces executables under a running BPE. **Confirm the machine is
idle before step 1**, not just that the driver has exited.

## The local modification that must survive

`$U/OPT/R2S_FIN/ADDNEQ2.INP` was changed today: `MAXPAR 1000 → 3000`. Backup at
`ADDNEQ2.INP.pre-maxpar-20260829`.

B_35 ships **updated panels**, and the documented panel-update path is the
`UPDPAN` program, run from the Bernese menu **twice** (once for `$U/PAN`, once
for `$U/OPT/*`). That can overwrite our MAXPAR change.

**Therefore:** diff `$U/PAN` and `$U/OPT/*` before and after, and re-apply
MAXPAR explicitly. Do not assume it survived — check it.

## Procedure

Steps 1–5 are scriptable. Steps 6–7 are not fully, and the plan says so rather
than pretending.

**0. Preconditions**
   - PHREF year complete and verified
   - no BSW process running: `ps -u $(id -un) | grep -E 'RUNBPE|GPSEST|ADDNEQ2'`
   - `$S` and `$P` quiescent

**1. Snapshot for rollback** — the whole point is that a failed update is
   recoverable:
   ```
   tar czf ~/BERN54-pre-patch-20260829.tar.gz -C /home/gps3 BERN54/SOURCE
   cp -a $U/PAN $U/OPT ~/GPSUSER-pan-opt-pre-patch-20260829/
   ```
   `SOURCE` is what recompiles; `$U/PAN`+`$U/OPT` are what UPDPAN touches.
   Record sha256 of every `.f90`/`.f` to be replaced.

**2. Fetch all seven patches** into a staging directory, never straight over
   the tree. Verify each is HTTP 200 and non-empty before moving anything.

**3. Place files** at the destinations AIUB give — `$LG` for library sources,
   `$FG` for program sources. Keep a manifest of what replaced what.

**4. Refresh dependencies** (B_33's instruction, applies once for all):
   ```
   $EXE/makemake.pl -r $C
   ```

**5. Recompile.** B_33 requires a full `CBERN COMPLINK`; per-program builds
   like `CBERN RNXGRA` are insufficient once library sources changed. Do the
   full link — it is slower and it is the only consistent option.

**6. Panels (`UPDPAN`) — partly manual.** Documented as a menu program run
   twice. Whether it can be driven headless is **unverified**; if not, this
   step needs a session at the machine. Afterwards, diff against the step-1
   copy and re-apply `MAXPAR 3000`.

**7. Verify against the EXAMPLE campaign.** `$P/EXAMPLE` exists and BRN-001
   established the acceptance bar: **0.0000 mm vs the shipped reference** on
   this machine. Re-run it and compare. This is the regression test, and it is
   the reason patching is safe to attempt at all.

**8. Re-run one PHREF day** already solved on the unpatched build (pick a
   completed DOY) and diff the solution. This quantifies constraint 2 — it
   turns "results may change" into a measured number instead of a worry.

## What this session can and cannot do

**Can**: preconditions, snapshot, fetch, place, `makemake.pl`, `CBERN
COMPLINK`, the EXAMPLE regression, the step-8 day-level diff, and the whole
audit trail. All of it is non-interactive.

**Cannot**: `UPDPAN` if it proves to be menu-only, and `configure.pm`, which is
an interactive chooser. Both need a person at a terminal — Claude Code has no
tty.

So this is **mostly** automatable, not fully. The honest split is above; the
plan does not claim step 6 is solved when it is not.

## Order relative to other work

The PHREF↔production comparison should run **first**, on the unpatched build
that produced the year. Patch after that lands. Otherwise the comparison
straddles a software change and neither result means what it says.
