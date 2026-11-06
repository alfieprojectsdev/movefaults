# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Read [`docs/SETTLED.md`](docs/SETTLED.md) first

It lists what is already established — ghosts that no longer exist, facts not to
re-measure, decisions not to re-argue, and known-and-accepted behaviour that is
not a defect. Re-deriving those is the most repeated waste in this project's
history; the "Corrections to earlier versions" block further down this file, and
the three separate "the mistake, this session's instances" catalogues in the
gps3 session log, are what that waste looks like written down.

It also carries a **Still open** section. Consult that before proposing work.

If evidence contradicts an entry, say so and update the entry in the same
change. Silently re-opening a settled question is the failure mode; correcting
one with evidence is the point.

## Core Directive

**YOU ARE A MENTOR, NOT AN AUTOMATON.**
Your primary goal is to ensure I understand the code you generate. You must prioritize my learning and long-term maintainability over speed.

## Absolute Prohibitions

1. **NEVER** run `git commit` or `git push` automatically.
2. **NEVER** assume I understand a complex refactor or new library.
3. **NEVER** provide the git commit commands until we have completed the **Verification Phase**.

---

## The Commit Protocol

When you have finished writing or modifying code, you must strictly follow this 3-step process. Do not skip steps.

### Step 1: The Debrief

Stop and provide a structured summary of what changed:

- **The "Why":** deeply explain the problem we solved.
- **The "How":** explain the specific implementation details, highlighting any clever logic, new dependencies, or potential side effects.
- **The "Gotchas":** point out any edge cases or fragility in the new code.

### Step 2: The Gauntlet (Verification Phase)

Before giving me the git commands, ask me **3 to 5 specific questions** about the code you just wrote.

- *Example:* "Why did we use a generator here instead of a list?"
- *Example:* "What happens to this function if the API returns a 500 error?"
- *Example:* "How does the new `uv.lock` change affect our CI pipeline?"

**STOP and wait for my answers.**

### Step 3: The Handover

- **If I answer correctly:** Generate the specific `git` commands for this repository (respecting our branch naming and commit message conventions).
- **If I answer incorrectly:** Re-explain the concept simply and re-test me.

---

## What This Project Is

**MOVE Faults / POGF (Philippine Open Geodesy Framework)** — a monorepo consolidating PHIVOLCS' geodetic workflows for earthquake monitoring, GNSS data processing, and crustal deformation analysis. Python 3.11+, built with Hatchling, managed with `uv`.

### Key domain terms

- **Campaign GPS:** Temporary GNSS deployments for measuring slow interseismic motion.
- **Continuous GPS (cGPS):** Permanent stations producing (a) proprietary raw data for Bernese post-processing, and (b) 1 Hz VADASE NMEA streams for real-time displacement detection.
- **Bernese Processing Campaign:** A software execution run in the Bernese GNSS Software (BPE), distinct from field "campaign GPS."
- **RINEX:** Receiver Independent Exchange Format — the standard interchange format for GNSS observations.
- **VADASE:** Variometric Approach for Displacement Analysis Stand-alone Engine — provides real-time velocity/displacement from GNSS.

---

## Monorepo Architecture

`ls` shows the layout. What it doesn't show:

- `services/field-ops/` is the only component a non-programmer uses directly.
- `packages/CORS-dashboard/` is legacy, kept as a forensic reference only.
- `scripts/sudo/` holds privileged scripts, handed over by absolute path (Claude
  Code has no tty; never pasted between shells).

### How components connect

**Read this as two things: the pipeline as designed, and what actually runs
today. They are not the same, and conflating them has cost real time.**

#### The designed flow

1. **drive-archaeologist** scans legacy drives → discovers GNSS files
2. Files feed into the **ingestion-pipeline** (Celery + Redis) → validated via
   **pogf-geodetic-suite** RINEX QC
3. Validated data lands in **PostgreSQL + TimescaleDB + PostGIS**
   (docker-compose: port 5433)
4. **bernese-workflow** orchestrates Bernese BPE for post-processing
5. **pogf-geodetic-suite** turns solved coordinates into ENU series and
   velocities
6. **vadase-rt-monitor** independently ingests real-time NMEA from CORS
   stations for rapid earthquake detection — **not** part of the chain above

#### What actually runs today (as of 2026-11-05)

**Production Bernese runs go through `services/bernese-workflow`** since
2026-11-04: the BPE step is the service's CLI, not a `scripts/` wrapper. The
rest of the path, before and after the BPE, is still `scripts/`. Steps 2 and 3
of the designed flow are still aspirational: nothing writes solutions into
TimescaleDB, and the ingestion pipeline is not in the loop.

```
Windows file server (the system of record)
    │  scripts/transfer_phivolcs_datapool.py   (SMB, sha256 at copy time)
    ▼
$D  DATAPOOL ──── scripts/fetch_igs_products.sh   (CODE products; AIUB FTP is
    │                                              firewalled, use the SWITCH
    │                                              S3 mirror)
    │             scripts/merge_blq.py            (ocean loading)
    │             scripts/stage_luzon_campaign.sh (RINEX 2 + RINEX 3 staging)
    ▼
$P  CAMPAIGN54/<CAMPAIGN>  ◄── scripts/derive_luzon_pcf.py  (generates the PCF
    │                          from 5.4 stock; refuses dangling WAITs)
    │  bernese-check-stations        STA/CRD/BLQ/ATL/ABB read the way Bernese
    │                                reads them; read-only
    │  bernese-run-year --plan|--run plan, BPE lock, ledger, circuit breaker,
    │                                banking (services/bernese-workflow)
    │  bernese-worker                the same run, for queued requests
    │                                (`submit`, or the BSW console's run
    │                                buttons, for its named operators)
    │     run_year → LinuxBPEBackend.run_sessions
    │       → perl $U/SCRIPT/sessions_pcs.pl → startBPE.pm → BSW BPE
    ▼
$S  SAVEDISK/<CAMPAIGN>/<year>/SOL/FIN_*.SNX|NQ0   (ledger.jsonl beside SOL/ by default)
    │  scripts/coord_repeatability.py      (precision QC)
    │  scripts/network_coherence_scan.py   (multi-station coherent motion)
    │  scripts/compare_solutions.sh        (bit-for-bit run comparison)
    ▼
pogf_geodetic_suite.timeseries
    crd_pipeline.py  CRD → ENU relative to a reference station
    analysis.py      offset-aware segmented velocities (verified against
                     PHIVOLCS' MATLAB output)
```

**Still Perl underneath.** The service does not drive BSW's server itself.
`bernese-run-year` and `bernese-worker` both go through `run_year.run_year`
to `LinuxBPEBackend.run_sessions`, which runs `perl $U/SCRIPT/sessions_pcs.pl`
(the repo copy is `config/bernese/gpsuser/SCRIPT/sessions_pcs.pl`, derived
from gps3's `phref_year.pl`/`luzon_year.pl` with campaign, PCF and prefix as
arguments), and that calls BSW through `startBPE.pm`. The single-session path,
`LinuxBPEBackend.run` (used by `month_driver.run_days`), defaults to stock
`rnx2snx_pcs.pl`. What moved is everything around the Perl: planning, the
lock, the ledger, the breaker and banking.

**`scripts/` still in the path:** the file-server transfer, product fetch,
BLQ merge, campaign staging, PCF derivation, and the QC and comparison scripts
after the run. **No longer the production path:** `scripts/run_luzon_year.sh`,
`scripts/run_phref_year.sh` (kept for comparison runs) and
`scripts/run_luzon_month.sh`.

**How the move was established:**

- **Parity, 2026-10-27** (merged in #307): `bernese-run-year` ran PHREF 2025
  DOY 091–120, 30/30 days ok in 1h15m, into a separate result tree (PHRPAR).
  It was not identical to the August production run, because of the Bernese
  patches (below). The cutover does not rest on that comparison.
- **Control, the same day:** the `scripts/` driver ran DOY 094, 096 and 098
  with the same configuration as the service, and its SNX and CRD files were
  identical to the service's, 3 of 3. **That is the evidence that the
  service reproduces `scripts/`.**
- **First production run, 2026-11-04:** LUZON January 2026 through
  `bernese-run-year`, run `7ca9ccb9`, 31/31 days ok in 53 min, 23–25 stations
  a day.
- **PHREF 2025 reprocessed, 2026-11-04 to 05:** runs `3341af5c` and
  `0def7ca1`; all 360 planned days solved. Compared with the solutions they
  superseded on 2026-11-05: the coordinates differ on every day (median of
  each day's largest station difference 0.02 mm, maximum 40.5 mm). **The cause
  is the 2024-11-11 patches applied on 2026-09-02:** the pre-patch binaries
  reproduce the August solutions exactly on the three days tested
  (`docs/phref_2025_reprocess_attribution_results.md`).

The run IDs are the ledger's `run` field. By default the ledger is
`ledger.jsonl` beside the year's `SOL/`; `$BPE_LEDGER_DIR` moves it.

Since #268 and #271 the service has resume at day level (a day is skipped
when its `FIN_*.NQ0` is intact **and** carries a `.done` marker the driver
wrote; failures stop the run through the circuit breaker, see
`bpe_orchestration_design.md`), and a BPE timeout kills the driver's whole
process group instead of only the Perl child. `run_year.py` runs blocks of
consecutive days in parallel (`REPR_MODE`, `MAXSESS`), each session in its
own campaign, under a machine-wide BPE lock (`bpe_lock.py`). It has also run
EXAMPLE end to end (finch, 2026-10-27, 0.0000 mm against the reference).
`month_driver.run_days`, the one-session-at-a-time driver, is not what the
production runs above used.

#### Corrections to earlier versions of this section

- **RINEX QC is `teqc`-first with a `gfzrnx` fallback.** `qc/rinex_qc.py` runs
  `teqc +qc` by choice: it is the more heavily exercised of the two and its
  output format is what everything downstream parses. But teqc was
  discontinued in 2019 and **cannot read RINEX 3 at all** — it refuses on line
  1 — and every IGS fiducial is RINEX 3. See
  `docs/project_documentation/gfzrnx_vs_teqc_rinex3_evidence.md`.

  So `gfzrnx` **is** wired in, on exactly two triggers: teqc refusing a file
  for being RINEX 3, and teqc not being installed at all (the R740's state on
  2026-08-13; teqc has since been installed in `~/bin`, which is not on the
  default `PATH`, so cron and scripts must add it). Any *other* teqc failure still raises — "teqc broke" and "teqc
  cannot read this format" are different problems and only one has a safe
  automatic answer. `allow_fallback` defaults to `True`; every result carries
  `tool` and `fallback_reason`, so which binary produced a number is
  recoverable from the record rather than from memory.

  Earlier versions of this file said gfzrnx was "not wired into any module".
  That stopped being true and the file did not follow. **Licence, unchanged:**
  gfzrnx's free licence covers research use; operational pipeline use needs a
  commercial licence.
- **`src/ingestion/` no longer exists** — the duplicate local ingestion module
  is gone and that consolidation is done. Earlier versions of this file listed
  it in the tree with a "consolidation pending" note. What remains under the
  **repo-root** `src/` is `src/db/` alone, two tracked files (`__init__.py`
  and `models.py`; "four" in earlier versions counted `__pycache__`); anything pointed at it
  (coverage, mypy) is therefore measuring near-nothing. Note that `src/` means
  something different inside vadase-rt-monitor, where it is the service's own
  package root — see *Import Paths* in `services/vadase-rt-monitor/CLAUDE.md`.
- **The file server is the system of record**, not this repo and not gps3.
  `\\192.168.48.99` holds the national campaign (`CAMPAIGN52/PHIVOLCS`, 439
  stations catalogued / ~52 estimated daily) and 476 GiB of observations back
  to 2010.

### Implementation maturity

Measured sizes, test counts and status per component are in
[`docs/project_documentation/implementation_maturity.md`](docs/project_documentation/implementation_maturity.md).
**Treat "does production use it?" as the real axis, not module count:**
`bernese-workflow` was listed at ~10% for months while carrying 198 tests.

---

## Build & Test Commands

`uv sync --all-extras`, `uv run pytest`, `ruff check .` and `ruff format .`. Extras,
CLI entry points and ruff settings are in `pyproject.toml`. What isn't obvious:

- **Suite selection is `testpaths` in `pyproject.toml`, not discovery**, so a new
  suite has to be added there to be run.
- **Frontend tests are vitest and pytest doesn't collect them:**
  `cd services/field-ops/frontend && npm test`, and the same in
  `services/bsw-console/frontend`. `uv run pytest` passing says nothing about these.
- **Compare the total, not the passed count.** Skips differ by machine: Postgres on
  5433, gps3's DATAPOOL, teqc or gfzrnx. The last measured total is in
  `implementation_maturity.md`, under *Test totals*.
- **`--cov=src` measures almost nothing**, because the repo-root `src/` is down to
  `src/db/`. Name what you want: `uv run pytest --cov=packages --cov=services
  --cov=tools --cov-report=html`. Same for type checking:
  `mypy packages/ services/ tools/`.
- `docker compose up -d` starts TimescaleDB on **5433** and Redis on **6380**, not
  their default ports.
- `bernese-run-year` and `bernese-worker run` need `LOADGPS.setvar` sourced first.

**`vadase-ingestor` does not exist**, and this file used to list it. The
vadase service deliberately has no console entry point: the hatch wheel maps
only `src/` dirs, so a `scripts.run_ingestor:main` target could never import.
`pyproject.toml` carries a comment saying so. Run it from the service
directory instead:

```bash
cd services/vadase-rt-monitor && PYTHONPATH=. uv run python scripts/run_ingestor.py
```

---

## Key Files Reference

Code is quicker to find by searching. These are the ones a search won't explain.

| Purpose | Path |
|---|---|
| Run worker (the console's Start/Stop/Redo/Preflight) | `services/bernese-workflow/src/bernese_workflow/run_worker.py`, `run_queue.py`, `redo.py`; design in `docs/project_documentation/run_worker_design.md` |
| PHIVOLCS event catalog | `docs/bern52/phivolcs-scripts/event-catalog/offsets` |
| Reprocessing runbook | `docs/bernese54_luzon_reprocessing_runbook.md` |
| Field deployment runbook | `services/field-ops/FIELD_RUNBOOK.md` |
| Project roadmap | `docs/project_documentation/roadmap.md` |

---

## VADASE-RT-Monitor

Its architecture notes are in `services/vadase-rt-monitor/CLAUDE.md`, which loads
when working there. One rule applies from anywhere: **`src` is a namespace package
and must stay one. Never add an `__init__.py` to the repo-root `src/` or to
`services/vadase-rt-monitor/src/`.** A regular package hides the other portion, and
`src.db` stops importing.

## Branching & Merge Policy

**Decided 2026-07-30. Applies to every machine and every session — the T420,
gps3, and any future clone.**

**All substantive work reaches `main` through a pull request.** `main` is the
default branch, is always complete, and is the only branch a newcomer needs to
clone. Its guarantee: *everything on `main` arrived via a reviewed PR.*

### Rules

1. **Branch, commit, PR, merge, delete.** Feature branches are working space,
   never storage.
2. **A branch lives at most one week.** If work outgrows that, land what is
   finished and open a new branch for the rest. This limit is not stylistic —
   see below.
3. **`git pull --rebase` before every push.** Two machines commit to this repo;
   plain merges between them produce an unreadable lattice, and the commit log
   doubles as the project's decision record.
4. **Never `>/dev/null` a gated git/gh operation** — a swallowed permission
   denial looks exactly like success. Use the wrappers in `scripts/`
   (`open_pr.sh`, `gh_pr_create_nopush.sh`, `merge_pr.sh`, `gh_retarget.sh`,
   `git_merge_main.sh`, `git_merge_ref.sh`).
5. **Verify after every merge and retarget.** Confirm `origin/main` actually
   advanced, and confirm `baseRefName` really is `main`. Do not trust the
   command's exit code alone.
6. **Merge through `scripts/merge_pr.sh`, which requires a `local-ci/gps3`
   success on the PR's head commit.** GitHub Actions has run nothing since
   2026-04-23 (the account is billing-locked), so the red `Tests` check on
   every PR says nothing about its code. `scripts/local_ci.py` on gps3 is the
   CI that actually runs (cron, every 10 minutes, at most two new commits
   per run, main first). Check it with `scripts/local_ci.py status` on gps3.
7. **Retarget a stacked PR to `main` before merging its base with
   `--delete-branch`.** Deleting the base branch closes the child PR rather
   than retargeting it (#146 in August, #273 in October).

### Why the one-week limit exists

On 2026-07-29 `docs/bernese-training-notes` had drifted **27 days** from
`main`: 22 commits on `main` the branch lacked, 39 on the branch `main` lacked.
Neither branch held the whole project. A fresh clone landed on `main` and got
none of the gps3 deployment; the branch checkout meanwhile carried an
unhardened `drive-arch` missing DA-002/DA-006.

Nothing was lost, but reconciling it took a full session (PR #57). The cause
was not the branch — it was the branch *outliving its purpose* and quietly
becoming a second trunk. Rule 2 removes that parking spot.

### Applies to docs too

Documentation is not exempt. This project's runbooks, handovers and decision
logs are the succession plan — the git history is where a successor learns
*why*, not just *what*. Write commit messages and PR descriptions for someone
arriving years from now with no context.

## Commit Message Style

Conventional Commits:

- `feat:` new features
- `fix:` bug fixes
- `refactor:` code changes that neither fix a bug nor add a feature
- `docs:` documentation only

- special mention: **NEVER** include **Claude or AI references** in commit messages

Scope with component name when relevant: `feat(vadase):`, `fix(drive-arch):`, `docs(roadmap):`

## User Preferences

- **Explanation Style:** Concise but high-context. Avoid fluff.
- **Architecture:** Prefer local-first, privacy-focused solutions.
- **Tone:** Collaborative but strict about code comprehension.
- **Package Manager:** Prefer `uv` over `pip`.
- **Testing:** Follow TDD approach where applicable.
