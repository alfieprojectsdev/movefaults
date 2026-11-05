# VADASE-RT-Monitor: architecture notes

**Read this file carefully** — it contains multi-file architectural context that isn't obvious from any single file.

## One processor, one input pattern (this used to be two of each)

`IngestionCore` in `src/domain/processor.py` is **the** processor. Input goes
through **`src/ports/`** (InputPort, OutputPort) with **`src/adapters/inputs/`**
(TCPAdapter, DirectoryAdapter) — queue-based, via `asyncio.Queue`.

Earlier versions of the repo-root `CLAUDE.md`, where these notes used to live,
opened with a section headed "Dual-Processor
Architecture (Important!)", warning you to check whether you were editing
`IngestionCore` or a second `IngestionProcessor` in `src/stream/processor.py`,
and likewise between `src/ports/` and a parallel `src/sources/` DataSource
protocol. **Both duplicates are gone** — `src/stream/` and `src/sources/` no
longer exist, and neither `IngestionProcessor` nor `DataSource` appears
anywhere in the tree. The consolidation the old section called "the intended
architecture going forward" happened. There is nothing to choose between.

## Receiver mode: a state machine, not a latch

`IngestionCore` decides whether to trust the receiver's own displacement or
integrate velocity itself. That decision is `ReceiverMode` (`RECEIVER` |
`MANUAL`) in `src/domain/processor.py`, driven by streak counters —
`STREAK_THRESHOLD = 5`, `GOOD_THRESHOLD = 30`, `SUSPECT_THRESHOLD = 3` — and
it moves in **both** directions.

Earlier versions of the repo-root `CLAUDE.md` recorded a "**Known bug**: the one-way latch at
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

## Import Paths (Non-Obvious)

Due to Hatch source mappings in `pyproject.toml`, imports within vadase-rt-monitor use **bare `src.` prefixes**, not fully-qualified monorepo paths:

```python
# Correct (inside vadase-rt-monitor code):
from src.parsers.nmea_parser import parse_lvm
from src.ports.outputs import OutputPort

# WRONG (this won't resolve):
from services.vadase_rt_monitor.src.parsers.nmea_parser import parse_lvm
```

This is because `pyproject.toml` maps `"services/vadase-rt-monitor/src" = ""` in `[tool.hatch.build.targets.wheel.sources]`.

**`src` is a namespace package and must stay one.** Two directories supply
portions of it: `src/db/` at the repo root, which the ingestion pipeline
imports as `src.db.models`, and this service's `src/`. Neither may contain an
`__init__.py` — a regular package wins the path scan outright and hides the
other portion, so adding one here makes `src.db` unimportable in any process
that also has this service on its path. `services/vadase-rt-monitor/src/__init__.py`
was exactly that, an empty marker; removing it is what lets a repo-root
`uv run pytest` collect both suites. It was also being mapped to a top-level
`__init__.py` at the wheel root by the `sources` rule above, which made the
whole wheel root a package.

The service's own path is added by `services/vadase-rt-monitor/conftest.py`,
so `src.*` resolves from the repo root as well as from the service directory.

## Three-State Receiver Model (Domain Knowledge)

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

Line numbers in these notes have proven to be the first thing to rot. Name the
symbol, not the line.

## How many stations, really

**`config/stations.yml` defines 4.** Earlier versions of the repo-root `CLAUDE.md`
described it as "35+" in two places, which conflated two different numbers:

- **35+** is roughly what PHIVOLCS *operates* as a CORS network. It is a fact
  about the agency, not about this repository.
- **4** is what this service is *configured to ingest* today, all on
  `192.168.1.10x:5017` — LAN addresses that only mean anything inside one
  building.

Both numbers are real and neither is a typo for the other. Quote the one you
mean, and check the file rather than this sentence, because the configured
count is the one that will drift.

## Where the thresholds live

`threshold_mm_s` is set per station in `config/stations.yml`. `config/thresholds.yml`
is **0 bytes**, so it is not where the value is.

`scripts/threshold_evidence.py` measures the alarm threshold against real captures,
which are not committed. It produces every figure in
`docs/project_documentation/vadase_threshold_evidence.md` at the repo root.

## Local testing

Replay and stress tools are in `scripts/`. Use `config/stations_local_test.yml` for local dev.
