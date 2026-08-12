# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
  vadase-rt-monitor/           #   Real-time NMEA earthquake detection (hexagonal arch, async)
  ingestion-pipeline/          #   Celery-based RINEX ingestion (early stage, stubs)
  bernese-workflow/            #   Bernese BPE orchestrator (stub, Jinja2 PCF templating)

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

- **RINEX QC wraps `teqc`, not `gfzrnx`.** `qc/rinex_qc.py` shells out to
  `teqc +qc`. This matters: teqc **cannot read RINEX 3 at all** — it refuses on
  line 1 — and every IGS fiducial is RINEX 3. See
  `docs/project_documentation/gfzrnx_vs_teqc_rinex3_evidence.md`. `gfzrnx`
  is installed at `/home/gps3/gfzrnx/` but is **not wired into any module**.
- **`src/ingestion/` no longer exists** — the duplicate local ingestion module
  is gone and that consolidation is done. Earlier versions of this file listed
  it in the tree with a "consolidation pending" note.
- **The file server is the system of record**, not this repo and not gps3.
  `\\192.168.48.99` holds the national campaign (`CAMPAIGN52/PHIVOLCS`, 439
  stations catalogued / ~52 estimated daily) and 476 GiB of observations back
  to 2010.

### Implementation maturity

*Measured 2026-08-12 (modules / LOC excluding tests / test files), not estimated.*

| Component | Size | Status |
|---|---|---|
| drive-archaeologist | 26 / 3004 / 15 | ~60% — Phase 1 scanner works, archive support partial |
| **bernese-workflow** | 10 / 2277 / 9 | **~60%, not ~10%** — 198 passing tests; `backends.py` invokes BSW via `startBPE.pm`; campaign builder, PCF context, panel sanitizer, CODSPP QC, RINEX header validator, CPU config all implemented. **Not yet** the path production runs take (see above) |
| vadase-rt-monitor | 23 / 1796 / 7 | ~80% — parser, handler, core logic, smart integration, leaky integrator |
| **pogf-geodetic-suite** | 9 / 853 / 4 | ~75% — coordinates, IGS downloader, RINEX QC (teqc-based, RINEX 2 only), and `timeseries/` (CRD→ENU pipeline + segmented velocities **verified against PHIVOLCS' production MATLAB output**) |
| ingestion-pipeline | 7 / 612 / 3 | ~30% — architecture defined, not in the production loop |

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

# Run a single test file or test
uv run pytest services/vadase-rt-monitor/tests/test_nmea_parser.py
uv run pytest -k "test_rinex"

# Coverage
uv run pytest --cov=src --cov-report=html

# Lint & format
ruff check .
ruff check --fix .
ruff format .

# Type checking
mypy src/

# Infrastructure (TimescaleDB + Redis)
docker compose up -d
```

### CLI entry points (defined in root pyproject.toml)

```bash
uv run drive-archaeologist scan <path>    # or drive-arch
uv run vadase-ingestor                    # real-time NMEA ingestor
uv run rinex-qc <file>                    # RINEX quality check
uv run igs-downloader                     # IGS product downloader
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
| Project roadmap | `docs/project_documentation/roadmap.md` |

---

## VADASE-RT-Monitor: Deep Architecture

This is the most mature service. **Read this section carefully** — it contains multi-file architectural context that isn't obvious from any single file.

### Dual-Processor Architecture (Important!)

The codebase has **two processor classes** that evolved at different stages. Know which one you're editing:

| Class | File | Pattern | Smart Integration | Status |
|---|---|---|---|---|
| `IngestionCore` | `src/domain/processor.py` | Hexagonal (queue-based via `asyncio.Queue`) | Yes (leaky integrator) | **Active development target** |
| `IngestionProcessor` | `src/stream/processor.py` | Simpler (iterator-based via `DataSource`) | No | Legacy/simpler path |

`IngestionCore` is the one with Smart Integration, event detection state, and the leaky integrator. If you're working on detection logic or integration, **always edit `domain/processor.py`**.

### Two Source/Adapter Patterns

Similarly, there are two parallel input abstractions:

- **`src/ports/`** (InputPort, OutputPort) + **`src/adapters/inputs/`** (TCPAdapter, DirectoryAdapter) — queue-based, used by `IngestionCore`
- **`src/sources/`** (DataSource protocol) — async-iterator-based, used by `IngestionProcessor`

The hexagonal `ports/adapters` pattern is the intended architecture going forward.

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

The Smart Integration code at `domain/processor.py:120-133` detects quiet-time by checking `vel == disp` over a streak. **Known bug**: the one-way latch at line 130 (`self.manual_integration_active = True`) never resets — once activated, it stays on permanently and can't detect the transition from quiet→event when the receiver starts sending real displacement.

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
