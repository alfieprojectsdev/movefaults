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
environment, or `BSW_SETVAR`). It binds to 127.0.0.1 only. On gps3 a login proxy
(Caddy, HTTPS on port 8443) sits in front of it and names the signed-in user in
`X-Remote-User`.

| Variable | Default | What it sets |
|---|---|---|
| `BSW_CONSOLE_CAMPAIGNS` | `LUZON:LUZON_DLY:LZY:LZFLT_DLY,PHREF:PHREF_DLY:PHR,PHDEN:PHDEN_DLY:PHD` | campaign, daily PCF, per-day campaign prefix, float PCF, and options joined by `+`. The one option, `allow-header-mismatches`, sends the worker `--allow-header-mismatches` with the campaign's Start, preflight and Redo, and the Campaigns card and Redo page say so; for a comparison campaign only (PHSUP). An unknown option stops the console from starting |
| `BSW_CONSOLE_HOST`, `PORT` | `127.0.0.1`, `8002` | where it listens |
| `BSW_CONSOLE_KB` | `config/bernese/bpe_errors.yaml` | the known-errors list |
| `BPE_LOCK` | bernese-workflow's default | the lock file it reads |
| `BSW_CONSOLE_STATE` | `~/.local/state/bsw-console` | where saved plans go |
| `BSW_CONSOLE_TRUSTED_PROXIES` | empty | comma-separated addresses of reverse proxies allowed to name the user in `X-Remote-User`, matched against the address that actually connects (the server ignores `X-Forwarded-For`; behind Caddy on gps3 this is `127.0.0.1`). Empty: the header is ignored |
| `BSW_CONSOLE_ACTIONS` | off | `on` lets the stage 3 buttons queue requests for the run worker. On for gps3, whose login proxy names the user |
| `BSW_CONSOLE_OPERATORS` | empty | comma-separated signed-in users who may press them. Empty: nobody, even with actions on |
| `BERNESE_WORKER_STATE` | the worker's default | the run worker's queue; must be the directory `bernese-worker run` reads |
| `BSW_CONSOLE_TS_REFERENCE` | unset | the reference station the page starts with. The page lets each viewer choose any estimated station in the CRD files as the reference; this only sets the first choice |
| `BSW_CONSOLE_TS_OFFSETS` | unset | the offsets catalog. Until it is set, the page says the time series is not configured. The daily final CRDs are not a setting: the page reads the chosen campaign year's `<V_RESULT>/STA` |
| `BSW_CONSOLE_EQUIPMENT_REPORT` | unset | the JSON written by `bernese-check-equipment --json`, shown on the Station files page. Unset: the page says there is no equipment report |

For frontend work, `npm run dev` proxies `/api` to the running server.

## What is wired, and what is a stub

| Screen | State |
|---|---|
| Campaigns | Wired: fixed, float and failed counts per year, last run and its state, recent activity from every ledger |
| Calendar | Wired: fixed and float from SAVEDISK, failed, running and queued from the ledger. **Excluded:** a day the latest run to mention it left out of its plan (`run_start`'s `excluded`, reason `short` or `listed`), with no solution; the day panel gives the run and the reason. A day left out only because it was solved shows as solved |
| Runs | Wired: days × PCF step groups, the failed PID from the protocol file, the running PID from the live BPE folder, the circuit breaker's counters. **Stop** queues a stop for the request the run worker is running (stage 3; off by default) |
| Day | Wired: attempts, the seven archived results with their 5.2 names, a text viewer with search and highlighting, stations in the solution and drops since the day before, HELMCHK RMS. **Run provenance:** who started each attempt's run, the command, the code commit (and whether the tree was dirty), the PCF and the IGS products, from that run's `run_start` (#318). An attempt from a run older than #318 says "not recorded for this run". **Ambiguities resolved:** each method's totals (baselines, ambiguities, left unresolved, the share resolved) from PART 6 of the day's archived `R2S_*.PRC`, which repeats the AMB summaries; not added into one rate, because each method covers its own baselines |
| Failure | Wired: `diagnose_day` on the day's BPE folder, the known-errors entry, the raw lines with earlier attempts greyed. Falls back to the ledger's recorded label once a solved day's campaign is removed |
| Plan | Wired: `run_plan.plan_from_env`, PCF groups with a check of the skips chosen, products per day, MAXPAR. **Save plan** writes one JSON file. **Queue preflight** and **Start** queue requests for the run worker (stage 3; off by default) |
| Redo | Wired preview: every file that would move, and where. **Redo** queues the move and the rerun for the run worker (stage 3; off by default) |
| Known errors | Wired: the whole list, with how often each fired in the last 30 days and failures with no entry |
| Station files (stage 4) | Read-only and wired: station × file coverage of the eight files the PCF names, codes with two names, stations missing from the BLQ (anything after `$$ END TABLE` counts as missing). Add a site, use a CRD as a priori and the BLQ paste check are not built. **Equipment panel** (read-only): one station's part of the `bernese-check-equipment` report, with the field-ops export's time; it reads the report file and never the field-ops database |
| Time series (stage 5) | Wired: `pogf_geodetic_suite.timeseries.status` in-process on all the campaign's daily final CRDs (`<V_RESULT>/STA` of each year, read as one series), with the reference station chosen on the page, by dropdown or on a map of the stations (Leaflet, with a bundled Natural Earth coastline, `frontend/src/coastline.json`, and no tile server: `scripts/make_console_coastline.py`). A plot of East, North and Up (zoom, pan, jump to a year), per station the final-segment velocity with 1-sigma, each segment's epochs, fit and outlier counts, the offsets catalog's path and sha256, and the outlier mode (status's default, `record`). **Clicking an epoch records a decision** for anyone signed in, appended to `<state>/outlier_decisions.jsonl`; confirmed outliers change only a side-by-side fit marked not published (`docs/project_documentation/outlier_review_design.md`) |

Stubs answer HTTP 501 with the reason, and the page shows it.

**Stage 3** (Start, Queue preflight, Stop, Redo) writes one request into the
run worker's queue (`bernese_workflow.run_queue`) and returns its id; the worker
(`bernese-worker run`, a systemd service on gps3) carries it out under the BPE
lock. The console never runs a BPE. Every button passes one gate, in this
order (`bsw_console/actions.py`):

1. `BSW_CONSOLE_ACTIONS=on`, else 501 with the reason. **Off by default.**
2. someone is signed in (a trusted proxy's `X-Remote-User`), else 403;
3. they are in `BSW_CONSOLE_OPERATORS`, else 403;
4. a worker holds the queue's `worker.lock`, else 503 and nothing is queued.

The gate runs before the body is read or the campaign looked up. The proxy
must send a bare username (`[A-Za-z0-9._-]`, as the queue records it); anything
else counts as nobody signed in.

Start and preflight run the campaign's daily PCF whole: a plan that skips steps,
changes RNXGRA or names another PCF is refused (422) and runs from the command
line. The server re-runs the plan's checks and refuses a plan that fails them
(409). **Start needs a preflight for exactly those days that finished ok in the
last 7 days**, as the brief requires (409 otherwise). Stop applies only when the
run on the page is the one the worker is running, matched through the request
id the worker writes into the ledger's `run_start`; any other run, such as one
started with `bernese-run-year`, is stopped where it was started (409). Queued
requests are not listed in the console yet; cancel one on gps3 with
`bernese-worker submit stop --target <id>`.

The console and the worker must agree on the queue: set `BERNESE_WORKER_STATE`
for both (the console warns at start-up when actions are on and it is unset),
run them as the same user, and keep it on a local filesystem, since the
worker-alive check matches `worker.lock` in `/proc/locks` by device and inode. `GET /api/worker`
says whether a worker is alive and why the buttons are off.

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

## Deploying on gps3

Three scripts in `scripts/sudo/`, each with its usage and undo in its header. All
need sudo, and each records what it did in the log you send it to.

1. `install_bernese_worker_gps3.sh`: the run worker as a service.
2. `setup_bsw_console_login_gps3.sh`: Caddy, HTTPS and one login per person. Takes
   `--lan <address>/<prefix>`, so gps3's address stays out of this public repository.
3. `deploy_bsw_console_gps3.sh`: moves `~/repos/mf_run` to `origin/main` and serves the
   console from it. The buttons go on only when the worker, Caddy and `--operators`
   are all in place; otherwise the log says which is missing. The operator list is
   an argument too.

To update a running console, run only step 3. On a new machine, run step 1, then
step 3 to write the console's unit, then step 2, then step 3 again.

## Tests

```bash
uv run pytest services/bsw-console/tests             # API against a synthetic BSW tree
cd services/bsw-console/frontend && npm test          # every screen renders; routes
uv run python services/bsw-console/tests/make_frontend_fixture.py   # after an API change
```
