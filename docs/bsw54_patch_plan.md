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

---

## Prep completed 2026-09-01 — what changed in this plan

The comparison against production has landed on the unpatched build
(`phref_vs_production_comparison_results.md`), so the ordering constraint is
satisfied and patching may proceed.

### `UPDPAN` is not needed, so nothing here requires a tty

The plan said step 6 might need a person because `UPDPAN` is menu-driven. That
turned out not to apply. The only panel in the patch set is `ETRS89.INP`, and
its destination `$PAN` resolves to **`$C/SUPGUI/PAN`** — the *master* panels,
not `$U/PAN`. `UPDPAN` exists to propagate master panels into user space, and
we do not run ETRS89.

Consequence: **our `MAXPAR 3000` in `$U/OPT/R2S_FIN/ADDNEQ2.INP` is not at
risk**, and the whole procedure is non-interactive. The earlier warning about
diffing and re-applying MAXPAR is superseded — nothing writes to `$U`.

### The full file set — 15 files, 7 fixes

| bug | files | dest |
|---|---|---|
| B_33 | `IGRF14SYN.f` (new), `IONOSP2.f90` | `$LG` |
| B_34 | `O_RXOWRAP.f90`; `RNXGRA.f` | `$LG`; `$FG` |
| B_35 | `ETRSIN.f90` `GETCO3.f90` `ITRF2ETRF.f90` `ITRF2ITRF.f90`; `ETRS89.f`; `ETRS89.INP`; `ETRS89.HLP` | `$LG`; `$FG`; `$PAN`; `$HLP` |
| B_36 | `UPDMEA.f90` | `$LG` |
| B_37 | `D_RXNTYPE.f90` | `$LG` |
| B_38 | `TRPSTORE.f90` | `$LG` |
| B_39 | `D_GRID.f90` | `$LG` |

All 15 fetched (HTTP 200, non-empty) and **verified to differ from what is
installed** — 14 differ, 1 is new. None is identical, which independently
confirms the install is unpatched.

### Prepared and in place

| artefact | location |
|---|---|
| staged patch files | `~/bsw-patches-2024-11-11/` |
| rollback snapshots | `~/BERN54-{SOURCE,SUPGUI,EXE_GNU}-pre-patch-20260901.tar.gz` |
| pre-patch fingerprint, 88 executables | `~/bsw-patch-baseline/exe-sha256-pre.txt` |
| pre-patch PHREF DOY 200 solution | `~/bsw-patch-baseline/FIN_20252000-prepatch.SNX` |
| pre-patch EXAMPLE solution | `~/bsw-patch-baseline/EXAMPLE-FIN_20230100-prepatch.*` |

The executables are snapshotted as well as the source: a failed compile leaves
a half-built `EXE_GNU`, which is the actual risk, and re-compiling from restored
source takes far longer than restoring the binaries.

### Scripts

```
scripts/bsw/apply_bsw54_patches.sh --check   # preconditions, no writes (passes)
scripts/bsw/apply_bsw54_patches.sh --place   # copy files, no compile
scripts/bsw/apply_bsw54_patches.sh --all     # place + makemake.pl + CBERN COMPLINK
scripts/bsw/verify_bsw54_patches.sh          # markers, rebuild diff, day-level check
scripts/bsw/rollback_bsw54_patches.sh 20260901
```

`--all` refuses to run if any BSW process is live, if a snapshot is missing, or
if the staged set is not exactly 15 files. It keeps a `.pre-patch` copy of every
file it replaces, writes a manifest with sha256, and afterwards reports **which
executables actually changed** by diffing the fingerprints — including a warning
if any executable that existed before is missing after, which is what a failed
link looks like.

It is idempotent: files already identical to their patch are skipped, so a
re-run after a partial failure resumes.

### The remaining step is a decision, not a task

Nothing left requires a person at the terminal. What it does require is someone
choosing to change the software that produced 717 days of solutions, knowing
that **B_33 and B_38 can move the numbers**. `verify_bsw54_patches.sh` turns
that from a worry into a measurement: same day, same station set, re-run and
compare — the Helmert parameters should be ~zero and the residuals *are* the
effect of the patches.

---

## The first attempt failed and destroyed the install — 2026-09-02

Recorded because the failure is more instructive than the fix.

### What happened

`--check` passed. `--all` placed all 15 files, ran `makemake.pl` (exit 0), then
ran `CBERN COMPLINK`, which reported exit 0 while the log carried **6,080 error
lines**:

```
make: gfortran: No such file or directory
make: cc:       No such file or directory
```

**`CBERN COMPLINK` removes every executable before rebuilding.** With no
compiler, the removal succeeded and the rebuild did not. The install went from
88 working executables to **zero** — unable to run anything at all.

### Why the machine had no compiler

BSW was installed here from **prebuilt AIUB binaries**. Nothing had ever needed
to build, so nothing had ever revealed the absence.

### The evidence was visible for days and was misread

On 2026-09-01, `pytest` failed collecting `test_dc3d.py`:

```
FileNotFoundError: [Errno 2] No such file or directory: 'cc'
```

That was noted, the test excluded, and the session moved on. It is the same
fact — *this machine cannot compile* — reported plainly, two days before it
mattered, and read as an unrelated nuisance because it appeared in a test run
rather than in a build.

### What the safety machinery got right

- **Snapshotting the executables, not just the source.** This is what made
  recovery possible. Restoring `SOURCE` alone would have left a tree that still
  could not be built into anything runnable. That decision was made because "a
  failed compile leaves a half-built `EXE_GNU`, which is the actual risk" — it
  turned out to be more right than intended.
- **The missing-executable guard.** `apply` compares the executable
  fingerprint before and after and warns when anything that existed before is
  gone. It printed `WARNING: 88 executable(s) present before and MISSING now`,
  which is how the failure was noticed immediately rather than at the next run.
- **Single-command rollback.** Restored all three trees; verified **bit-for-bit
  identical** across all 88 executables by sha256, and confirmed functionally by
  re-running a weekly stack and reproducing an earlier result exactly.

Two things the rollback did not cover, now handled: `IGRF14SYN.f` is a **new**
file, so restoring the old tarball did not remove it; and 14 `.pre-patch`
copies were left behind. Both cleaned by hand.

### What it got wrong

**`--check` verified everything except the prerequisite the operation depends
on.** It confirmed snapshots existed, files were staged, and no BPE was
running — then authorised an operation whose first act is deleting every
executable, without checking that anything could rebuild them.

That is the same shape as the DOY 200 pre-flight in §25.5: a guard that
inspects what is convenient rather than what the operation actually needs.

`--check` now requires `gfortran`, `gcc`, `make` and `perl` on `PATH`, **and
compiles a trivial program** — a compiler on `PATH` is not proof it can build.

### Consequence to weigh, not just note

The toolchain was installed on 2026-09-02. This machine's BSW is therefore no
longer purely the AIUB prebuilt binaries that **BRN-001 verified at 0.0000 mm
against the shipped reference**. After a rebuild it becomes a locally compiled
build with `gfortran 13.3.0`, and that verification no longer describes it.

Re-running the EXAMPLE campaign after patching is therefore not optional
box-ticking — it is what re-establishes the claim BRN-001 made.

---

## Applied and verified — 2026-09-02

With the toolchain installed, `--all` completed: 15 files placed, `makemake.pl`
clean, `CBERN COMPLINK` **exit 0 with zero hard errors in 28,610 log lines**,
and **88 of 88 executables rebuilt** with none missing.

All 88 binaries changed, which is expected: every one is now compiled locally
with gfortran 13.3.0 rather than being an AIUB prebuilt.

### Verification — three tests, because one would not have been enough

| test | result |
|---|---|
| patch markers in source | `IGRF14` in `IONOSP2.f90`, `IGRF14SYN.f` present, `.pre-patch` copies kept |
| **our production path** — PHREF DOY 201, identical 35-station network | **0.00 mm** RMS; Helmert T = (−0.01, 0.00, −0.01) mm, scale −0.00 ppb |
| **AIUB's own campaign** — EXAMPLE, 340 stations | max 3-D difference **0.010 mm** at JOZ2; **1 station of 340** differs by more than 0.001 mm |

The 0.010 mm is the CRD format's 5-decimal print precision — a last-digit
rounding difference, not a numerical disagreement.

**The patched local build reproduces the AIUB prebuilt binaries**, on our
pipeline and on a campaign we did not design.

### Why zero and not merely small

B_33 changes the geomagnetic field model used for **higher-order ionosphere
corrections**, which this PCF does not apply. B_38 removes redundant station-ID
lookups when troposphere SINEX output is disabled — a no-op for the numbers.
The two fixes that *could* have moved results do not touch this configuration.

That is a finding, not a disappointment: it means the 2025 year and the
production comparison remain valid statements about this pipeline, and future
reprocessing on the patched build is comparable with them.

### The first comparison was confounded, and would have been reported wrongly

`verify` nominates **DOY 200** as the baseline day. DOY 200 is the one day in
the year whose stored solution predates PIMO's addition to the campaign — 33
stations against the year's 35. The re-run therefore compared **34 stations to
33**, and produced 1.88 mm North with ANTP at 10.8 mm.

None of that was the patches. Re-running **DOY 201**, which the year run solved
*with* PIMO, gives 0.00 mm. Reporting the DOY 200 figure as "the effect of the
patches" would have been wrong by its entire magnitude.

`verify_bsw54_patches.sh` should choose a baseline day from the main run rather
than the pre-flight test day. Recorded rather than silently patched, because
the same trap will recur for anyone re-verifying later.

### Test days restored

The re-runs overwrote `FIN_20252000` and `FIN_20252010` in `$S`, leaving 358
unpatched days and 2 patched ones. Both were restored from the saved baselines,
so **the 2025 year is homogeneous unpatched** and still matches what
`phref_vs_production_comparison_results.md` describes.

### Correction to this document's earlier claim

Earlier revisions cited BRN-001's "0.0000 mm vs reference" as the acceptance
bar. **The distribution ships empty `EXAMPLE/SOL` and `EXAMPLE/STA`** — there is
no AIUB expected-solution file, so what BRN-001 compared against is not
recoverable from what is on disk. The EXAMPLE test above is the defensible
substitute: same campaign, same input, AIUB binaries versus this build.
