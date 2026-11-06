# bernese-workflow

A Python orchestrator for the Bernese GNSS Software 5.4 Processing Engine (BPE).
It invokes BSW for real, through the Perl `startBPE.pm` API.

**Production's BPE step runs through this service since 2026-11-04**, via
`bernese-run-year`. The first production run was LUZON January 2026 (run
`7ca9ccb9`, 31/31 days ok in 53 min); PHREF 2025 was then reprocessed through
it (runs `3341af5c` and `0def7ca1`, all 360 planned days solved); its
coordinates differ from the solutions it superseded on every day (median
0.02 mm, maximum 40.5 mm), because of the binaries replaced on 2026-09-02
(tested on three days). Before 2026-11-04 every
production solution (LUZON 2025, 358 days; PHREF 2025, 360 days) came from the
shell and Perl drivers in the repo-root `scripts/`, which still do everything
around the BPE: staging, product fetch, BLQ merge, QC and comparison
(`docs/SETTLED.md` §2). The service still drives BSW through a Perl driver,
`sessions_pcs.pl`, and `startBPE.pm`. Its measured size, test count and status
are in `docs/project_documentation/implementation_maturity.md`.

## What is here

| module | what it does |
|---|---|
| `backends.py` | `BPEBackend` protocol (`prepare_campaign`, `run`, `collect_outputs`). `LinuxBPEBackend` runs a headless Perl driver against `$X`/`$U`/`$P`, with injectable PCF, CPU file and driver script, `MAXPAR` sized from the campaign's station count unless overridden, a pre-flight RINEX header check, and a timeout (default 7200 s) that kills the driver's **whole process group** (#271). `WindowsBPEBackend` is a stub that raises |
| `month_driver.py` | `run_days`: runs a range of days with day-level resume. A day counts as done only when its `FIN_*.NQ0` is intact **and** carries a `.done` marker this driver wrote; the circuit breaker stops it (#268). Single session at a time |
| `circuit_breaker.py` | Decides after each failed day whether the run goes on: finds the failed step in the campaign's `BPE/`, looks it up in `bpe_errors.yaml`, and stops at once on an unknown or `configuration` error, after 3 consecutive days with the same `session` error, or after 5 consecutive failed days whatever their errors |
| `run_plan.py` | Plans a run and runs nothing: `python -m bernese_workflow.run_plan --campaign PHREF --year 2025 --pcf PHREF_DLY`. Excludes solved days and days with fewer than 3 reference stations (the PCF's `V_REFINF` `.FIX` set, read against the PCF's `V_RNXDIR`), splits the rest into blocks, names the busiest day as the preflight, and refuses a PCF with a dangling `WAIT=` or jump. Reports each ADDNEQ2 `MAXPAR` rather than checking it, because the parameter count is not known (`docs/bernese_maxpar_limit.md`). On PHREF 2025 it gives the same blocks and exclusions as `run_phref_year.sh` |
| `ledger.py` | Append-only JSONL record of every attempt (`run_days(..., ledger=Ledger(path))`): run start with host, pid and config hash, then each day's start and end with outcome, seconds, error and station count, then the halt reason. `python -m bernese_workflow.ledger status <file>` reads it and tells a slow day (2), a dead driver (3) and a halted run (4) apart; 0 running, 1 finished. The `.done` markers are kept alongside |
| `run_year.py` | Step F: runs a range of days as blocks of parallel sessions, each in its own private campaign (`REPR_MODE`, `MAXSESS`, driver `config/bernese/gpsuser/SCRIPT/sessions_pcs.pl`), on `run_days`' banking and breaker rules. `bernese-run-year --campaign PHREF --repr-prefix PHR --year 2025 --from 152 --to 181 --pcf PHREF_DLY --plan` (or `--run`) builds the same plan as `run_plan.py`, takes its results directory from the PCF's `V_RESULT`, and writes the run ledger beside the results, `<V_RESULT>/ledger.jsonl` (`$BPE_LEDGER_DIR` or `--ledger` override). A day with any `FIN_*` is left alone, as `scripts/` decides (`--done fin`, the default); `--done banked` makes redoing `scripts/`' days a deliberate act. SIGTERM or SIGHUP kills the BPE's process group, records `run_end(halt="interrupted: …")` and exits 130 |
| `bpe_lock.py` | One BPE run per machine: `fcntl.flock` on `$BPE_LOCK` (default `~/.local/state/bernese-workflow/bpe.lock`), released by the kernel however the holder dies. A refused run is told who holds it and whether that pid is still alive |
| `orchestrator.py` | `BerneseOrchestrator`: renders a Jinja2 PCF template, runs the BPE through a backend, and runs the post-BPE `RUNX_v2.py` velocity step headlessly |
| `campaign_builder.py`, `campaign_models.py` | generate the campaign's station files (STA, CRD, ABB, …) as text |
| `pcf_context.py` | PCF template context, including the troposphere settings per GPSEST panel and drift detection between panels (GEO-003) |
| `rinex_header_validator.py` | before the BPE: cross-checks receiver and antenna types in RINEX headers against the `.STA` file, and raises rather than letting RXOBV3 silently drop a station |
| `codspp_qc.py` | after CODSPP: separates a bad a priori coordinate from bad observations (RH-005) |
| `panel_sanitizer.py` | makes Windows-authored `OPT/*.INP` panels safe on Linux (RH-004) |
| `cpu_config.py` | sizes `USER.CPU` `maxjobs` from physical cores and RAM (RH-006) |
| `fiducial_set.py` | resolves and records the `.FIX` fiducial set that defines a solution's datum, with its sha256 (GEO-001) |
| `equipment_check.py` | `bernese-check-equipment`: the `.STA` file's equipment against field-ops' records (the network inventory CSV, or a logsheet export). Advisory and read-only; see below |

`templates/basic_processing.pcf.j2` is the one PCF template.

### The equipment report (`bernese-check-equipment`)

Stage 1 of `docs/project_documentation/field_ops_sta_reconciliation_design.md`.
It lists where the `.STA` file and field-ops disagree about what is installed.
It writes nothing and never blocks a run: it exits 0 whatever it finds, and 2
only when an input cannot be read.

```bash
uv run bernese-check-equipment --sta $D/REF54/PHNAT.STA \
    --equipment-csv data/network_inventory/equipment.csv \
    --logsheet-export ~/.local/state/bernese-workflow/field_equipment.json [--json]
```

- **Current equipment:** each station's latest TYPE 002 row against the sheet
  (or, with only an export, its `equipment_history` rows). Receiver, antenna
  model and radome are judged separately, each as `equal`, `equal after name
  map`, `different` or `unmapped name`. A station takes the worst of its
  three; a code on one side only is `only in STA` or `only in source`.
- **Visits** (logsheet export): the row valid at the visit against `*_before`.
  When equipment was changed, it looks for a row from the visit's date on
  with the `*_after` equipment, and reports a missing one.
- **Station names:** a code with no `.STA` name, or more than one.

Free text such as `Leica AR20` becomes an IGS name through
`config/bernese/equipment_names.yaml`, which the processing lead owns. A name
not in it is listed as unmapped, never guessed. The logsheet export is written
by `scripts/export_field_equipment.py`, read-only, and its `exported_at` is
printed with the report so stale data shows.

It is a sibling of `bernese-check-stations` rather than an option on it
because the exit codes mean different things. `bernese-check-stations` exits 1
on a problem that refuses a run, while this report must exit 0 on any
disagreement.

## Email alerts (`bernese-notify`)

`bernese-notify` emails the person who started a run, and the maintainer: when it
starts, every 6 hours while it runs, when it ends, and at once if it fails, looks
stuck for 2 hours, or the worker goes down or halts. It runs from cron and only
reads the queue and ledgers, so a mail failure can't affect a run, and a dead worker
can still be reported. A run started directly with `bernese-run-year` has no named
person, so it emails only the maintainer.

To set it up on gps3, as the user that runs the worker:

```bash
mkdir -p ~/.config/bernese-workflow
cat > ~/.config/bernese-workflow/notify.toml <<'EOF'
mail_conf = "~/.luzon_mail.conf"
console_url = "https://<address>:8443"

[operators]
# AB = "ab@example.org"
EOF
chmod 600 ~/.config/bernese-workflow/notify.toml

~/repos/mf_run/.venv/bin/bernese-notify --test      # one message, to the maintainer
~/repos/mf_run/.venv/bin/bernese-notify --test AB   # and to that operator
~/repos/mf_run/.venv/bin/bernese-notify --dry-run   # what it would send; sends and records nothing
```

Then add this one line with `crontab -e`:

```cron
*/5 * * * * $HOME/repos/mf_run/.venv/bin/bernese-notify >> $HOME/bernese_notify.log 2>&1
```

The first pass only records what already exists, so it doesn't mail the history, and
a `--dry-run` before it has nothing to show and says so. An
operator with no address in the file is named in the message, and only the maintainer
gets it. Addresses stay in that file, not in this public repository. To send from a
different account, point `mail_conf` at another file with the same five `MAIL_` keys.
The Plan page says whether alerts are working. Details of a failed send are in
`~/.local/state/bernese-workflow/worker/notify/status.json`.

## Using it

Five command-line entry points (root `pyproject.toml`), then the library below them:

- `bernese-run-year` plans and runs a range of days as parallel BPE blocks (the
  production BPE step since 2026-11-04);
- `bernese-worker` runs queued requests one at a time under the BPE lock, and
  `bernese-worker submit` queues one;
- `bernese-check-stations` checks the station files the way Bernese reads them
  (read-only);
- `bernese-check-equipment` compares the `.STA` equipment with field-ops records
  (read-only, advisory);
- `bernese-notify` emails the person who started a run (above).

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

**The parity run is done** (gps3, 2026-10-27, #307): PHREF 2025 DOY 091–120
through `bernese-run-year`, 30/30 days ok in 1h15m, into a separate result tree
(PHRPAR). It was not identical to the August production run, because of the
binaries replaced on 2026-09-02 (tested on three days of the year, none in this
range). The control is what shows the service reproduces
`scripts/`: the `scripts/` driver re-ran DOY 094, 096 and 098 with the same
configuration, and its SNX and CRD files were identical to the service's, 3 of
3 (`docs/SETTLED.md` §2). The `scripts/` drivers take the same machine-wide BPE
lock (`scripts/bpe_lock.sh`, #308), so a service run and a shell run cannot
share a machine, and `local_ci.py`'s `bpe_running()` reads it from
`/proc/locks`. **The cutover is done too:** production ranges moved from
`scripts/` to `bernese-run-year` on 2026-11-04.

## Related documents

- `docs/bernese_orchestration_explainer.md`: for processing staff
- `docs/project_documentation/bpe_orchestration_design.md`: the decision layer
- `docs/project_documentation/bernese_orchestrator_r740_readiness.md`: the RH-00x gaps
- `docs/bernese54_luzon_reprocessing_runbook.md`: how LUZON was reprocessed through the `scripts/` drivers, before the 2026-11-04 cutover
