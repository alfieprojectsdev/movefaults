# bernese-workflow

A Python orchestrator for the Bernese GNSS Software 5.4 Processing Engine (BPE).
It invokes BSW for real, through the Perl `startBPE.pm` API.

**It is not the production path yet.** Every production solution to date (LUZON
2025, 358 days; PHREF 2025, 360 days) came from the shell and Perl drivers in the
repo-root `scripts/`. Moving production onto this service is the standing
direction; no production day has run through it (`docs/SETTLED.md` §2 and §6).
Status as of 2026-10-14: about 60%, 12 modules, 250 tests.

## What is here

| module | what it does |
|---|---|
| `backends.py` | `BPEBackend` protocol (`prepare_campaign`, `run`, `collect_outputs`). `LinuxBPEBackend` runs a headless Perl driver against `$X`/`$U`/`$P`, with injectable PCF, CPU file and driver script, `MAXPAR` sized from the campaign's station count unless overridden, a pre-flight RINEX header check, and a timeout (default 7200 s) that kills the driver's **whole process group** (#271). `WindowsBPEBackend` is a stub that raises |
| `month_driver.py` | `run_days`: runs a range of days with day-level resume. A day counts as done only when its `FIN_*.NQ0` is intact **and** carries a `.done` marker this driver wrote; the circuit breaker stops it (#268). Single session at a time |
| `circuit_breaker.py` | Decides after each failed day whether the run goes on: finds the failed step in the campaign's `BPE/`, looks it up in `bpe_errors.yaml`, and stops at once on an unknown or `configuration` error, or after 3 consecutive days with the same `session` error |
| `orchestrator.py` | `BerneseOrchestrator`: renders a Jinja2 PCF template, runs the BPE through a backend, and runs the post-BPE `RUNX_v2.py` velocity step headlessly |
| `campaign_builder.py`, `campaign_models.py` | generate the campaign's station files (STA, CRD, ABB, …) as text |
| `pcf_context.py` | PCF template context, including the troposphere settings per GPSEST panel and drift detection between panels (GEO-003) |
| `rinex_header_validator.py` | before the BPE: cross-checks receiver and antenna types in RINEX headers against the `.STA` file, and raises rather than letting RXOBV3 silently drop a station |
| `codspp_qc.py` | after CODSPP: separates a bad a priori coordinate from bad observations (RH-005) |
| `panel_sanitizer.py` | makes Windows-authored `OPT/*.INP` panels safe on Linux (RH-004) |
| `cpu_config.py` | sizes `USER.CPU` `maxjobs` from physical cores and RAM (RH-006) |
| `fiducial_set.py` | resolves and records the `.FIX` fiducial set that defines a solution's datum, with its sha256 (GEO-001) |

`templates/basic_processing.pcf.j2` is the one PCF template.

## Using it

There is no console entry point; it is a library.

```python
from pathlib import Path
from bernese_workflow.backends import LinuxBPEBackend
from bernese_workflow.month_driver import run_days

backend = LinuxBPEBackend(
    bernese_root="~/BERN54", user_dir="~/GPSUSER", campaign_dir="~/GPSDATA/CAMPAIGN54",
    pcf_file="LUZON_DLY", driver_script="~/GPSUSER/SCRIPT/luzon_pcs.pl",
)
outcomes = run_days(backend, "LUZON", 2025, range(1, 32),
                    sol_dir=Path("~/GPSDATA/SAVEDISK/LUZON/2025/SOL").expanduser())
```

**Do not point this at a range `scripts/` already solved.** Those days have
`FIN` files but no `.done` markers, so `run_days` would re-run every one of them
(LUZON 2025 above is exactly such a range; it is the shape of the call, not one
to run). Write the markers first, or use a new campaign.

The paths match gps3's `LOADGPS.setvar` (`$U` = `~/GPSUSER`, `$P` =
`~/GPSDATA/CAMPAIGN54`, `$S` = `~/GPSDATA/SAVEDISK`); the driver must be one
that exists in `$U/SCRIPT` and takes `year session PCF` as its arguments, as
`luzon_pcs.pl` does. The PHREF driver takes extra block arguments, so it cannot
be driven this way yet. **Launch a long run with `setsid nohup`**, never
as a Claude Code background job, which kills the process tree at its time limit
(`docs/SETTLED.md` §2).

## Tests

```bash
uv run pytest services/bernese-workflow/tests     # from the repo root
```

Most tests need no Bernese install. The real-panel tests in `test_fiducial_set.py`
skip when the captured panels are absent.

## What is missing before production

From `docs/project_documentation/bpe_orchestration_design.md` and the roadmap
(deliverable 1.3), none of which is built yet:

1. an error-signature scanner for `*** SR` lines in BPE output;
2. a circuit breaker that stops after K identical failures;
3. an append-only run ledger, so a broken run can be told from a slow one;
4. a plan phase: exclusions derived from data, `MAXPAR` against the network
   size, the worst-case day as the preflight;
5. parallel sessions (`REPR_MODE`, `MAXSESS`), which today exist only in the
   Perl drivers.

Then a parity run: one month already solved by `scripts/`, re-run through the
service and compared with `scripts/compare_solutions.sh`.

## Related documents

- `docs/bernese_orchestration_explainer.md`: for processing staff
- `docs/project_documentation/bpe_orchestration_design.md`: the decision layer
- `docs/project_documentation/bernese_orchestrator_r740_readiness.md`: the RH-00x gaps
- `docs/bernese54_luzon_reprocessing_runbook.md`: how production runs today
