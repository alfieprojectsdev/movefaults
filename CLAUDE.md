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

```
packages/                      # Shared libraries
  pogf-geodetic-suite/         #   Coordinate transforms, RINEX QC, IGS downloader, velocity estimation
  CORS-dashboard/              #   Legacy React/GraphQL dashboard (forensic reference only)

services/                      # Long-running deployable services
  field-ops/                   #   Field logsheet PWA — FastAPI + React, offline-first.
                               #   The only component a non-programmer uses directly.
  vadase-rt-monitor/           #   Real-time NMEA earthquake detection (hexagonal arch, async)
  ingestion-pipeline/          #   Celery-based RINEX ingestion (early stage, stubs)
  bernese-workflow/            #   Bernese BPE orchestrator (real BSW invocation; ~60%)

tools/
  drive-archaeologist/         # CLI for excavating legacy GNSS data from old drives

scripts/                       # THE PRODUCTION PATH TODAY — campaign staging, PCF
                               # derivation, BPE drivers, product fetch, QC, the
                               # file-server transfer. See "How components connect".
  sudo/                        #   privileged scripts, handed over by absolute path
                               #   (Claude Code has no tty; never pasted between shells)

analysis/                      # Numbered research scripts (01-10): RINEX conversion, time series, dislocation models, bootstrapping
```

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
6. **vadase-rt-monitor** independently ingests real-time NMEA from 35+ CORS
   stations for rapid earthquake detection — **not** part of the chain above

#### What actually runs today (as of 2026-08-12)

The production path is **`scripts/` + Bernese**, not the service chain. Steps 2
and 3 above are aspirational: nothing currently writes solutions into
TimescaleDB, and the ingestion pipeline is not in the loop.

```
\\192.168.48.99 (Windows file server, the system of record)
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
    │  scripts/run_luzon_month.sh  →  perl $U/SCRIPT/*_pcs.pl  →  BSW BPE
    ▼
$S  SAVEDISK/<CAMPAIGN>/<year>/SOL/FIN_*.SNX|NQ0
    │  scripts/coord_repeatability.py      (precision QC)
    │  scripts/network_coherence_scan.py   (multi-station coherent motion)
    │  scripts/compare_solutions.sh        (bit-for-bit run comparison)
    ▼
pogf_geodetic_suite.timeseries
    crd_pipeline.py  CRD → ENU relative to a reference station
    analysis.py      offset-aware segmented velocities (verified against
                     PHIVOLCS' MATLAB output)
```

`services/bernese-workflow` **does** now invoke BSW for real —
`backends.py` calls `startBPE.pm` over Perl — but the month-long production
runs to date have gone through `scripts/`. Moving that logic into the service
is the standing direction, not a completed migration.

#### Corrections to earlier versions of this section

- **RINEX QC is `teqc`-first with a `gfzrnx` fallback.** `qc/rinex_qc.py` runs
  `teqc +qc` by choice: it is the more heavily exercised of the two and its
  output format is what everything downstream parses. But teqc was
  discontinued in 2019 and **cannot read RINEX 3 at all** — it refuses on line
  1 — and every IGS fiducial is RINEX 3. See
  `docs/project_documentation/gfzrnx_vs_teqc_rinex3_evidence.md`.

  So `gfzrnx` **is** wired in, on exactly two triggers: teqc refusing a file
  for being RINEX 3, and teqc not being installed at all (the R740, as of
  2026-08-13). Any *other* teqc failure still raises — "teqc broke" and "teqc
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
  **repo-root** `src/` is `src/db/` alone, four files; anything pointed at it
  (coverage, mypy) is therefore measuring near-nothing. Note that `src/` means
  something different inside vadase-rt-monitor, where it is the service's own
  package root — see *Import Paths* below.
- **The file server is the system of record**, not this repo and not gps3.
  `\\192.168.48.99` holds the national campaign (`CAMPAIGN52/PHIVOLCS`, 439
  stations catalogued / ~52 estimated daily) and 476 GiB of observations back
  to 2010.

### Implementation maturity

*Measured 2026-08-18 (modules / LOC excluding tests / test files → tests
collected), not estimated. Re-measure when you update this; the previous
figures were carried forward by hand and three of five had drifted.*

| Component | Size | Tests | Status |
|---|---|---|---|
| drive-archaeologist | 25 / 2998 / 15 | 133 | ~60% — Phase 1 scanner works, archive support partial |
| **bernese-workflow** | 10 / 2277 / 9 | 198 | **~60%, not ~10%** — `backends.py` invokes BSW via `startBPE.pm`; campaign builder, PCF context, panel sanitizer, CODSPP QC, RINEX header validator, CPU config all implemented. **Not yet** the path production runs take (see above). **BRN-001 done 2026-07-29** — Bernese 5.4 verified on the R740; LUZON reprocessed 30/30 days unattended 2026-08-06 (5m33s/day) *via `scripts/`*, not via this service |
| vadase-rt-monitor | 20 / 1387 / 7 | 51 | ~80% — parser, handler, core logic, leaky integrator, `ReceiverMode` state machine (replaced the old one-way integration latch) |
| **pogf-geodetic-suite** | 10 / 1802 / 6 | 124 | ~75% — coordinates, IGS downloader, RINEX QC (teqc-first, gfzrnx fallback), and `timeseries/`: CRD→ENU, segmented velocities **verified against PHIVOLCS' production MATLAB output**, joint step+rate estimation, GMT velocity-field output |
| **field-ops** | 13 / 1869 / 2 | 13 + 69 | ~90% — offline-first logsheet PWA, exercised on a real handset. 13 backend tests plus **69 frontend (vitest)**, the only frontend tests that run — `packages/CORS-dashboard` carries one 2017 React test file that nothing executes |
| ingestion-pipeline | 7 / 612 / 3 | 33 | ~30% — architecture defined, not in the production loop |

**The maturity that matters is not module count.** `bernese-workflow` was
listed at ~10% for months while carrying 198 tests, and the genuinely
incomplete part is different from what that number implied: the code exists and
is tested, but the month-long runs still go through `scripts/`. Treat "does
production use it?" as the real axis.

---

## Build & Test Commands

```bash
# Install all dependencies (from repo root)
uv sync
uv sync --all-extras                          # everything (dev + all services)
uv sync --extra dev                           # dev tools only
uv sync --extra drive-archaeologist           # drive-arch deps
uv sync --extra vadase-rt-monitor             # vadase deps

# Run all tests
uv run pytest

# Run tests for a specific service
uv run pytest services/vadase-rt-monitor/tests/
uv run pytest tools/drive-archaeologist/tests/
uv run pytest services/field-ops/tests/        # needs `uv sync --all-extras`

# Frontend tests (field-ops PWA) — vitest, NOT collected by pytest.
# `uv run pytest` passing says nothing about these.
cd services/field-ops/frontend && npm test

# Run a single test file or test
uv run pytest services/vadase-rt-monitor/tests/test_nmea_parser.py
uv run pytest -k "test_rinex"

# Coverage. NOTE: `--cov=src` measures almost nothing — the repo-root `src/`
# is down to `src/db/` (4 files) and the real code lives in packages/,
# services/ and tools/. Name what you actually want measured:
uv run pytest --cov=packages --cov=services --cov=tools --cov-report=html

# Lint & format
ruff check .
ruff check --fix .
ruff format .

# Type checking — same caveat as coverage: point it at real code.
mypy packages/ services/ tools/

# Infrastructure (TimescaleDB + Redis)
docker compose up -d
```

### CLI entry points (defined in root pyproject.toml)

```bash
uv run drive-archaeologist scan <path>    # or drive-arch
uv run rinex-qc <file>                    # RINEX quality check
uv run igs-downloader                     # IGS product downloader
uv run field-ops-api                      # field logsheet API ($PORT, default 8001)
uv run velocity-reviewer                  # velocity review CLI
```

**`vadase-ingestor` does not exist**, and this file used to list it. The
vadase service deliberately has no console entry point: the hatch wheel maps
only `src/` dirs, so a `scripts.run_ingestor:main` target could never import.
`pyproject.toml` carries a comment saying so. Run it from the service
directory instead:

```bash
cd services/vadase-rt-monitor && PYTHONPATH=. uv run python scripts/run_ingestor.py
```

### Ruff configuration (pyproject.toml)

- Line length: 100
- Target: Python 3.11
- Rules: E, F, I, B, C4, UP (ignores E501, B008)
- `__init__.py` ignores F401 (unused imports)

---

## Key Files Reference

| Purpose | Path |
|---|---|
| Root config & all deps | `pyproject.toml` |
| Infrastructure | `docker-compose.yml` (TimescaleDB on 5433, Redis on 6380) |
| NMEA parser | `services/vadase-rt-monitor/src/parsers/nmea_parser.py` |
| Ingestion domain core | `services/vadase-rt-monitor/src/domain/processor.py` |
| Station definitions (35+) | `services/vadase-rt-monitor/config/stations.yml` |
| Event thresholds | `services/vadase-rt-monitor/config/thresholds.yml` |
| Drive scanner | `tools/drive-archaeologist/src/drive_archaeologist/scanner.py` |
| File classifier profiles | `tools/drive-archaeologist/src/drive_archaeologist/profiles.py` |
| Coordinate transforms | `packages/pogf-geodetic-suite/src/pogf_geodetic_suite/modeling/coordinates.py` |
| BPE invocation (real) | `services/bernese-workflow/src/bernese_workflow/backends.py` |
| PCF derivation | `scripts/derive_luzon_pcf.py` |
| Month-long BPE driver | `scripts/run_luzon_month.sh` |
| Segmented velocities | `packages/pogf-geodetic-suite/src/pogf_geodetic_suite/timeseries/analysis.py` |
| CRD → ENU pipeline | `packages/pogf-geodetic-suite/src/pogf_geodetic_suite/timeseries/crd_pipeline.py` |
| PHIVOLCS event catalog | `docs/bern52/phivolcs-scripts/event-catalog/offsets` |
| Reprocessing runbook | `docs/bernese54_luzon_reprocessing_runbook.md` |
| GMT velocity field output | `packages/pogf-geodetic-suite/src/pogf_geodetic_suite/timeseries/gmt.py` |
| Velocity field CLI | `scripts/make_velocity_field.py` |
| Field-ops API | `services/field-ops/src/field_ops/main.py` |
| Field-ops logsheet form | `services/field-ops/frontend/src/components/LogSheetForm.tsx` |
| Field-ops offline queue | `services/field-ops/frontend/src/hooks/useOfflineQueue.ts` |
| Field deployment runbook | `services/field-ops/FIELD_RUNBOOK.md` |
| Project roadmap | `docs/project_documentation/roadmap.md` |

---

## VADASE-RT-Monitor: Deep Architecture

**Read this section carefully** — it contains multi-file architectural context that isn't obvious from any single file.

### One processor, one input pattern (this used to be two of each)

`IngestionCore` in `src/domain/processor.py` is **the** processor. Input goes
through **`src/ports/`** (InputPort, OutputPort) with **`src/adapters/inputs/`**
(TCPAdapter, DirectoryAdapter) — queue-based, via `asyncio.Queue`.

Earlier versions of this file opened with a section headed "Dual-Processor
Architecture (Important!)", warning you to check whether you were editing
`IngestionCore` or a second `IngestionProcessor` in `src/stream/processor.py`,
and likewise between `src/ports/` and a parallel `src/sources/` DataSource
protocol. **Both duplicates are gone** — `src/stream/` and `src/sources/` no
longer exist, and neither `IngestionProcessor` nor `DataSource` appears
anywhere in the tree. The consolidation the old section called "the intended
architecture going forward" happened. There is nothing to choose between.

### Receiver mode: a state machine, not a latch

`IngestionCore` decides whether to trust the receiver's own displacement or
integrate velocity itself. That decision is `ReceiverMode` (`RECEIVER` |
`MANUAL`) in `src/domain/processor.py`, driven by streak counters —
`STREAK_THRESHOLD = 5`, `GOOD_THRESHOLD = 30`, `SUSPECT_THRESHOLD = 3` — and
it moves in **both** directions.

Earlier versions of this file recorded a "**Known bug**: the one-way latch at
line 130 (`self.manual_integration_active = True`) never resets — once
activated, it stays on permanently". That was true, and it was fixed: reset in
`934f8b3`, then replaced wholesale by the state machine in `a74c109`.
`manual_integration_active` no longer exists. Do not go looking for it, and do
not re-report the bug.

The leaky integrator is real and still there — `handle_velocity` integrates
velocity as `disp = disp * decay_factor + vel * dt`, a high-pass filter that
bleeds off accumulated drift. Two things about it are worth knowing before you
touch it: `decay_factor` **defaults to 1.0**, which is no leak at all (pure
integration), so the decay is opt-in per station rather than always on; and
integration is skipped entirely when the epoch gap is outside `0 < dt < 5s`,
so an outage cannot inject a step.

### Import Paths (Non-Obvious)

Due to Hatch source mappings in `pyproject.toml`, imports within vadase-rt-monitor use **bare `src.` prefixes**, not fully-qualified monorepo paths:

```python
# Correct (inside vadase-rt-monitor code):
from src.parsers.nmea_parser import parse_lvm
from src.ports.outputs import OutputPort

# WRONG (this won't resolve):
from services.vadase_rt_monitor.src.parsers.nmea_parser import parse_lvm
```

This is because `pyproject.toml` maps `"services/vadase-rt-monitor/src" = ""` in `[tool.hatch.build.targets.wheel.sources]`.

### Three-State Receiver Model (Domain Knowledge)

The CORS receivers (Leica) operate in three behavioral states — understanding these is critical for Smart Integration logic:

1. **Quiet-time**: Velocity is the default output. Displacement data echoes velocity values (`vel == disp`).
2. **Event-time**: Receiver's internal threshold crossed → sends real integrated displacement (`vel != disp`).
3. **Anomalous spikes**: Receiver behavior during anomalous (non-seismic) spikes is empirically unconfirmed.

The three states above are receiver behaviour and still hold — that is domain
knowledge about the hardware, not about our code.

**The implementation notes that used to follow here were stale and are gone.**
They cited `domain/processor.py:120-133` (today that range is sentence
dispatch) and a "Known bug" one-way latch on `manual_integration_active`
(fixed in `934f8b3`, then removed entirely by `a74c109`). See *Receiver mode: a
state machine, not a latch* above for what the code does now.

Line numbers in this file have proven to be the first thing to rot. Name the
symbol, not the line.

### NMEA Sentence Types

- `$GNLVM`/`$GPLVM` — velocity (East, North, Up in m/s)
- `$GNLDM`/`$GPLDM` — displacement (East, North, Up in meters)
- All use XOR checksum validation (`NMEAChecksumError` on failure)

### Testing & Replay Tools

All scripts live in `services/vadase-rt-monitor/scripts/`:
- `mock_ntrip_caster.py` — fake TCP server for NTRIP client testing
- `replay_events.py` — replay historical earthquake `.rtl`/`.nmea` files at 1Hz
- `stress_test_parallel.py` — simulate multi-station concurrent load
- `run_ingestor.py` — main entry point for the real-time ingestor

Config files in `services/vadase-rt-monitor/config/`. Use `stations_local_test.yml` for local dev.

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
