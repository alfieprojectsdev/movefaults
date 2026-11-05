# bsw-console: the Bernese processing console

A web page served from gps3 that shows what BSW 5.4 processing is doing, checks
a plan before it runs, and later starts one. It is the screens of the design
canvas *Bernese Processing Console* (26 October 2026), built on
`services/bernese-workflow`, following the design brief of the same date.

It makes no decisions. Every number on a screen comes from the processing
service's own code, the code its command line uses: the ledger, `run_plan`, the
scanner and known-errors list, `diagnose_day` and the BPE lock record. If the
console and `bernese-run-year --plan` ever disagree, the console is wrong.

## Run it

```bash
uv sync --extra bsw-console
cd services/bsw-console/frontend && npm install && npm run build && cd -
uv run bsw-console          # http://127.0.0.1:8002
```

It reads `$U`, `$D`, `$S` and `$P` from `~/BERN54/LOADGPS.setvar` (or the
environment, or `BSW_SETVAR`). It binds to 127.0.0.1 only, because sign-in
does not exist yet. From an office PC, tunnel to it:
`ssh -N -L 8002:localhost:8002 gps3@<gps3>`.

| Variable | Default | What it sets |
|---|---|---|
| `BSW_CONSOLE_CAMPAIGNS` | `LUZON:LUZON_DLY:LZY:LZFLT_DLY,PHREF:PHREF_DLY:PHR,PHDEN:PHDEN_DLY:PHD` | campaign, daily PCF, per-day campaign prefix, float PCF |
| `BSW_CONSOLE_HOST`, `PORT` | `127.0.0.1`, `8002` | where it listens |
| `BSW_CONSOLE_KB` | `config/bernese/bpe_errors.yaml` | the known-errors list |
| `BPE_LOCK` | bernese-workflow's default | the lock file it reads |
| `BSW_CONSOLE_STATE` | `~/.local/state/bsw-console` | where saved plans go |
| `BSW_CONSOLE_TRUSTED_PROXIES` | empty | comma-separated addresses of reverse proxies allowed to name the user in `X-Remote-User`. Empty: the header is ignored |
| `BSW_CONSOLE_TS_CRD_DIR` | unset | the directory of daily final CRD files the Time series page reads |
| `BSW_CONSOLE_TS_REFERENCE` | unset | the 4-character reference station the series are relative to |
| `BSW_CONSOLE_TS_OFFSETS` | unset | the offsets catalog. Until all three time-series settings are set, the page says the time series is not configured |
| `BSW_CONSOLE_EQUIPMENT_REPORT` | unset | the JSON written by `bernese-check-equipment --json`, shown on the Station files page. Unset: the page says there is no equipment report |

For frontend work, `npm run dev` proxies `/api` to the running server.

## What is wired, and what is a stub

| Screen | State |
|---|---|
| Campaigns | Wired: fixed, float and failed counts per year, last run and its state, recent activity from every ledger |
| Calendar | Wired: fixed and float from SAVEDISK, failed, running and queued from the ledger. **Excluded** is never shown, because the ledger does not record plans |
| Runs | Wired: days × PCF step groups, the failed PID from the protocol file, the running PID from the live BPE folder, the circuit breaker's counters. **Stop** is a stub |
| Day | Wired: attempts, the seven archived results with their 5.2 names, a text viewer with search and highlighting, stations in the solution and drops since the day before, HELMCHK RMS. **Run provenance:** who started each attempt's run, the command, the code commit (and whether the tree was dirty), the PCF and the IGS products, from that run's `run_start` (#318). An attempt from a run older than #318 says "not recorded for this run". **Not available:** the ambiguity fixing rate, because the AMB summaries are not archived |
| Failure | Wired: `diagnose_day` on the day's BPE folder, the known-errors entry, the raw lines with earlier attempts greyed. Falls back to the ledger's recorded label once a solved day's campaign is removed |
| Plan | Wired: `run_plan.plan_from_env`, PCF groups with a check of the skips chosen, products per day, MAXPAR. **Save plan** writes one JSON file. **Queue preflight** and **Start** are stubs |
| Redo | Wired preview: every file that would move, and where. **The move** is a stub |
| Known errors | Wired: the whole list, with how often each fired in the last 30 days and failures with no entry |
| Station files (stage 4) | Read-only and wired: station × file coverage of the eight files the PCF names, codes with two names, stations missing from the BLQ (anything after `$$ END TABLE` counts as missing). Add a site, use a CRD as a priori and the BLQ paste check are not built. **Equipment panel** (read-only): one station's part of the `bernese-check-equipment` report, with the field-ops export's time; it reads the report file and never the field-ops database |
| Time series (stage 5) | Read-only and wired: `pogf_geodetic_suite.timeseries.status` in-process on the daily final CRDs (`BSW_CONSOLE_TS_*`), per station the final-segment velocity with 1-sigma, each segment's epochs, fit and outlier counts, the offsets catalog's path and sha256, and the outlier mode (status's default, `record`). No plot yet; confirming or overriding an outlier is not built |

Stubs answer HTTP 501 with the reason, and the page shows it. Stage 3 waits on
the two prerequisites in the brief: a run worker on gps3 that holds the BPE
lock, and personal accounts so every action carries a name. The run worker
exists since #316 (`bernese_workflow/run_worker.py`, `uv run bernese-worker`,
taking the lock in `bpe_lock.BPELock`), but the console is not wired to it yet.

## Safety

- The browser never sends a path. A request names a campaign, a year and a
  day, and the server builds paths from the PCF. The file viewer serves only
  names it listed for that day.
- The BPE lock is read from `/proc/locks`, never taken. Taking it to test it
  would make a BPE starting at that instant find it held.
- The only write is a saved plan, under the console's own state directory. It
  accepts only a same-origin `application/json` body of at most 4 KB with known,
  typed fields. Any other content type is refused (415): `text/plain` and form
  posts are what a page on another site can send without a CORS preflight.
- `X-Remote-User` is believed only from `BSW_CONSOLE_TRUSTED_PROXIES`. Any
  client can send the header, so with no proxy in front it would let anyone on
  the network sign as anyone.

## Tests

```bash
uv run pytest services/bsw-console/tests             # API against a synthetic BSW tree
cd services/bsw-console/frontend && npm test          # every screen renders; routes
uv run python services/bsw-console/tests/make_frontend_fixture.py   # after an API change
```
