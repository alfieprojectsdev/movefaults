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
| `circuit_breaker.py` | Decides after each failed day whether the run goes on: finds the failed step in the campaign's `BPE/`, looks it up in `bpe_errors.yaml`, and stops at once on an unknown or `configuration` error, after 3 consecutive days with the same `session` error, or after 5 consecutive failed days whatever their errors |
| `run_plan.py` | Plans a run and runs nothing: `python -m bernese_workflow.run_plan --campaign PHREF --year 2025 --pcf PHREF_DLY`. Excludes solved days and days with fewer than 3 reference stations (the PCF's `V_REFINF` `.FIX` set, read against the PCF's `V_RNXDIR`), splits the rest into blocks, names the busiest day as the preflight, and refuses a PCF with a dangling `WAIT=` or jump. Reports each ADDNEQ2 `MAXPAR` rather than checking it, because the parameter count is not known (`docs/bernese_maxpar_limit.md`). On PHREF 2025 it gives the same blocks and exclusions as `run_phref_year.sh` |
| `ledger.py` | Append-only JSONL record of every attempt (`run_days(..., ledger=Ledger(path))`): run start with host, pid and config hash, then each day's start and end with outcome, seconds, error and station count, then the halt reason. `python -m bernese_workflow.ledger status <file>` reads it and tells a slow day (2), a dead driver (3) and a halted run (4) apart; 0 running, 1 finished. The `.done` markers are kept alongside |
| `run_year.py` | Step F: runs a range of days as blocks of parallel sessions, each in its own private campaign (`REPR_MODE`, `MAXSESS`, driver `config/bernese/gpsuser/SCRIPT/sessions_pcs.pl`), on `run_days`' banking and breaker rules. `bernese-run-year --campaign PHREF --repr-prefix PHR --year 2025 --from 152 --to 181 --pcf PHREF_DLY --plan` (or `--run`) builds the same plan as `run_plan.py`, takes its results directory from the PCF's `V_RESULT`, and writes the run ledger to `$BPE_LEDGER_DIR/<campaign>-<year>.jsonl`. SIGTERM or SIGHUP kills the BPE's process group, records `run_end(halt="interrupted: …")` and exits 130 |
| `bpe_lock.py` | One BPE run per machine: `fcntl.flock` on `$BPE_LOCK` (default `~/.local/state/bernese-workflow/bpe.lock`), released by the kernel however the holder dies. A refused run is told who holds it and whether that pid is still alive |
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
                    sol_dir=Path("~/GPSDATA/SAVEDISK/LUZON/2025/SOL").expanduser(),
                    bpe_dir=Path("~/GPSDATA/CAMPAIGN54/LUZON/BPE").expanduser())
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

The five pieces `docs/project_documentation/bpe_orchestration_design.md` and
the roadmap (deliverable 1.3) listed are built:

1. an error-signature scanner for `*** SR` lines in BPE output (`bpe_scanner.py`);
2. a circuit breaker that stops after K identical failures (`circuit_breaker.py`);
3. an append-only run ledger, so a broken run can be told from a slow one (`ledger.py`, #300);
4. a plan phase: exclusions derived from data, `MAXPAR` reported against the
   busiest day, that day as the preflight (`run_plan.py`, #299);
5. parallel sessions, `REPR_MODE` and `MAXSESS` (`run_year.py`, #302).

None has run a production day. What is left:

- **the parity run:** one month already solved by `scripts/`, re-run through
  `bernese-run-year` and compared with `scripts/compare_solutions.sh`. It is
  the first proof of more than one session at a time; EXAMPLE (finch,
  2026-10-27) had a single day;
- **the `scripts/` drivers take the BPE lock**, so a service run and a shell run
  cannot share a machine, and `local_ci.py`'s `bpe_running()` reads it.

## Related documents

- `docs/bernese_orchestration_explainer.md`: for processing staff
- `docs/project_documentation/bpe_orchestration_design.md`: the decision layer
- `docs/project_documentation/bernese_orchestrator_r740_readiness.md`: the RH-00x gaps
- `docs/bernese54_luzon_reprocessing_runbook.md`: how production runs today
