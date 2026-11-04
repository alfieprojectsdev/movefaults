# Run worker: how a BPE run is requested, queued, held and recovered

*Written 2026-11-04 for `services/bernese-workflow` (`run_queue.py`, `redo.py`,
`run_worker.py`). Read with `bpe_orchestration_design.md`, which explains the
circuit breaker and the ledger this builds on.*

## Why this exists

The BSW console (`services/bsw-console`) shows Start, Stop, Redo and Queue
preflight buttons that answer HTTP 501. The console must never run a BPE
itself: it is a web process, it may restart at any time, and a BPE takes
minutes to hours. What it needs is something on gps3 that

- accepts a request from anyone allowed to make one, and records who made it;
- runs requests one at a time, holding the machine's BPE lock (`bpe_lock.py`)
  for the whole of each, so no other run can start in the middle of one;
- stops a run only between BPE calls, never mid-day;
- redoes a day without ever leaving it with a mix of old and new results;
- after a crash, leaves the results exactly as they were before the request
  that was in progress, rather than in whatever state the crash caught them.

That is the run worker. It is a loop that reads a directory of request files.
It is not a scheduler: it runs only what a person asked for, so it does not
conflict with the settled decision that the scientific pipeline has no cron
(`SETTLED.md` §3).

## The queue is a directory of files

```
$BERNESE_WORKER_STATE            default ~/.local/state/bernese-workflow/worker
├── worker.lock     flock: one worker per state directory
├── status.json     what the worker is doing now (rewritten atomically)
├── HALTED          present only after a restore failed; see "When a restore fails"
├── tmp/            a request is written here first
├── queue/          pending requests, one <id>.json each
├── active/         the request being run (at most one)
└── done/           finished requests, with their outcome added
```

**Why files and not a database or a socket.** The console and the worker are
separate processes that may each restart. A file survives both, can be read
by a person with `cat`, and needs no server. The same state directory holds
the whole history of who asked for what.

**Writes are atomic.** A request is written to `tmp/`, fsynced, then renamed
into `queue/`. A rename within one filesystem is atomic, so a reader sees a
whole request or none. Every later move (`queue/` → `active/` → `done/`) is a
rename too, and every rewrite of a file (the active record, `status.json`, a
redo manifest) goes through a temporary file and a rename.

**Order.** A request's id is its UTC submission time to the microsecond plus
eight random hex digits (`20261104T021500.123456Z-1a2b3c4d`), so sorting the
file names is first-come-first-served. Stop requests are the exception: they
are handled before anything else, because a stop that waited its turn behind
the job it was meant to stop would be useless.

**The worker trusts no file.** A request is validated when it is submitted
and again when the worker reads it, because anything that can write to
`queue/` can write anything. Names (campaign, prefix, PCF) must match
`[A-Za-z0-9_]+`, so no request can carry a path; days must be in the year; a
request that fails validation is moved to `done/` as `rejected` with the
reason, not run and not deleted.

## Request kinds

Every request carries `id`, `kind`, `submitted` (ISO time), `submitted_by` and
an optional `reason`.

| kind | fields | what the worker does |
|---|---|---|
| `start` | `campaign`, `repr_prefix`, `year`, `from`, `to`, `pcf`, `maxsess` (default 6) | plans the range exactly as `bernese-run-year --run` does (`run_plan.plan_from_env`, days with any `FIN_*` left alone), then runs it with `run_year`, busiest day first |
| `preflight` | the same as `start` | plans the range and runs **only its busiest day**, the worst case for MAXPAR and memory (`SETTLED.md` §3, "a pre-flight test day must be the worst case"). A preflight that succeeds banks that day |
| `redo` | `campaign`, `repr_prefix`, `year`, `doy`, `pcf`, `maxsess`, and a `reason` (required) | moves the day's results aside and runs the day; see below |
| `stop-after-current-day` | optional `target` (a request id) | with no target, or the running request's id: the running request stops after the BPE call in progress. With the id of a queued request: that request is cancelled. Otherwise: recorded as having nothing to stop |

`repr_prefix` is in the request because `run_year` needs it and the console
already knows each campaign's prefix (its `Campaign.prefix`). The worker has
no campaign table of its own, which is one less copy to drift.

## Who may submit

Anyone who can write to `queue/`. The request records a `submitted_by`
username (`[A-Za-z0-9._-]{1,64}`), and the worker copies it into the lock
record's purpose and the run's ledger entry, so every BPE run can be traced to
a name. **Nothing authenticates that name.** The console is expected to pass
the user its own sign-in established; `bernese-worker submit` defaults to the
login name. Until the console has per-person accounts, the state directory's
filesystem permissions are the only access control. That is deliberate scope,
not an oversight: authentication belongs in front of the console, not in a
directory of JSON files.

## The BPE lock is held for the whole job

The worker takes `BPELock` **before** it claims a request and releases it
only after the request is in `done/`. For a redo that span covers moving the
old results aside, the BPE, and moving them back if it failed: if another run
could start between those steps, it could bank the day, or overwrite it,
while the old set is out of place.

The lock is taken with the existing non-blocking `BPELock`. If someone else
holds it (a maintainer's `bernese-run-year`, a `scripts/` driver), the
request stays queued, `status.json` says who holds the lock, and the worker
tries again on its next poll. Nothing is failed for waiting. The worker does
**not** hold the lock while idle, so a maintainer can still run
`bernese-run-year` by hand between requests.

A second lock, `worker.lock`, stops two workers sharing a state directory.
Both are `flock`s, so the kernel releases them when the worker dies, however
it dies.

## Stop means after the current BPE call

The worker never kills a BPE. `run_year` takes a `stop` callable and checks it
before each BPE call; when it answers with a reason the run ends there, the
days not yet handed to BSW are recorded `not_run` with that reason, and the
ledger's `run_end` carries it as the halt.

**What "the current day" means with parallel sessions.** `run_year` hands BSW
a block of up to `2 × MAXSESS` consecutive days in one call (12 at the default
MAXSESS of 6), and BSW runs them six at a time. There is no point inside that
call at which nothing is running, so the honest granularity of a stop is
**the block in progress**, not one day. At PHREF 2025's measured rate (846 min
for 360 days at MAXSESS 6, `SETTLED.md` §2) a block of 12 is about half an
hour. A redo and a preflight are one day each, so for them
the two meanings coincide.

SIGTERM and SIGINT are treated as a stop of the running request followed by
the worker exiting. A second signal does not escalate: the only way to abandon
a BPE mid-day is SIGKILL, and that is handled as a crash. Whoever deploys the
worker under a service manager must give it a stop timeout longer than a
block, or the manager will escalate to SIGKILL itself.

## Redo

Deleting a day's FIN files is not a redo on 5.4: a day has seven archived
results, a redo that replaces two of them leaves five stale ones, and the
next combination picks them up by name. So a redo moves **all** of them aside
as one step. In the year directory (the PCF's `V_RESULT` for that year, the
parent of `SOL/`), each plain or `.gz`:

| folder | file | what |
|---|---|---|
| `OUT` | `R2S_<yyyy><ddd><s>.PRC` | BPE processing summary |
| `STA` | `FIN_<yyyy><ddd><s>.CRD` | final coordinates |
| `SOL` | `FIN_….SNX`, `FIN_….NQ0` | final SINEX and normal equations |
| `SOL` | `RED_….SNX`, `RED_….NQ0` | reduced SINEX and normal equations |
| `ATM` | `FIN_….TRO`, `FIN_….TRP` | troposphere, SINEX and Bernese formats |
| `SOL` | `FIN_….done` | the banking marker `month_driver` writes |

This is the console's `RESULT_KINDS` plus `RED_*.SNX` and the marker. The
marker moves with the set so a restore brings back a banked day, not a FIN
that `run_year` would no longer recognise as banked.

The sequence, all under the BPE lock:

1. **Check.** The day is planned with `plan_from_env` as a one-day range. A
   plan with problems, or a day the plan excludes for any reason but already
   being solved (too few reference stations, listed), is refused before
   anything moves. So is a day with nothing to move: that is a `start` of one
   day, not a redo.
2. **Name the destination.** `<year dir>/SUPERSEDED/<YYYYMMDD-HHMM>/`, local
   time, the form the console's preview shows. The manifest is
   `MANIFEST_<yyyy><ddd><s>.json` inside it. Two redos in one minute only
   collide if they are the same day; then the directory gets `-2`, `-3`.
   The manifest's path is written into the active request record **before**
   the manifest itself, so recovery can always find it.
3. **Write the manifest** (`state: moving`): every file's path relative to
   the year directory, size and sha256, computed before anything moves.
4. **Move** each file with `rename`, keeping its folder
   (`SUPERSEDED/<stamp>/SOL/FIN_….NQ0.gz`), and check its sha256 at the new
   place. If any move fails, the ones already made are moved back and the
   request fails. Then `state: moved`, and a `superseded` entry in the ledger.
5. **Run the day** through `run_year` with preflight off.
6. **On success** the new files stay, the old set stays in `SUPERSEDED/`,
   `state: succeeded`.
7. **On failure** (the day not `ok`, or `run_year` raising), restore:
   - verify every file in `SUPERSEDED/` against the manifest **first**; if any
     differs, stop without touching anything (see below);
   - delete every result file of that day now at its original place, except
     an original that never moved (only possible after a crash mid-move);
   - move each old file back and verify its sha256 again where it landed;
   - `state: restored`, and a `restored` entry in the ledger.

   The failed attempt's private campaign under `$P` is **kept**: `run_year`
   keeps a failed session's campaign for autopsy, and a redo is no different.

`SUPERSEDED/<stamp>/` is never deleted by the worker. After a successful redo
it is the only copy of the old results; after a restore it holds the manifest
as the record that the redo happened and failed.

### When a restore fails

If a superseded file no longer matches the manifest, or an original is
missing from both places, the worker cannot put the day back without
guessing. It stops guessing: the manifest gets `state: restore-failed`, the
request goes to `done/` as `restore-failed` with the file named, and the
worker writes `HALTED`. While `HALTED` exists the worker claims no new run
(stop and cancel requests are still applied). A person inspects the year
directory and the manifest, puts the day right, and deletes `HALTED`.

## Crash and restart

On start, after taking `worker.lock`, the worker looks in `active/`. Because
`worker.lock` is held, anything there belongs to a worker that is dead. It is
recovered **under the BPE lock** (if the lock is held elsewhere, recovery
waits, and nothing new is claimed until it has run):

| what is in `active/` | what recovery does |
|---|---|
| `start` or `preflight` | records `interrupted`. **Nothing is re-run automatically.** Days banked before the crash stay banked; the ledger shows the run without a `run_end`. Re-submitting resumes, since banked days are skipped |
| `redo`, no manifest written | records `interrupted`; nothing had moved |
| `redo`, manifest `moving` or `moved` | restores, exactly as after a failure (this is the half-moved case: originals still in place are recognised by their sha256 and left alone), and records `interrupted` |
| `redo`, manifest `succeeded` | the redo finished; records `ok` |
| `redo`, manifest `restored` | the restore finished; records `failed` |
| `redo`, manifest `restore-failed` | records `restore-failed` and writes `HALTED` |

**Stale requests.** A request still in `queue/` when it is more than
`--max-age-hours` old (default 24) is moved to `done/` as `expired` instead of
run. A start somebody pressed yesterday, while the worker was down, should not
begin today without them knowing. Files left in `tmp/` by a submitter that
died mid-write are not requests and are ignored; the worker removes them once
they are an hour old.

**What recovery does not see.** A worker killed with SIGKILL can leave its BPE
running: the driver runs in its own process group (so a timeout can kill all
of it, #271), which also means it survives the worker. The BPE lock is
released when the worker dies, so a new worker could start a second BPE
beside the orphan. Recovery does not look for orphaned BPE processes. Until it
does, after a SIGKILL check `pgrep -f startBPE` (or the campaign's `BPE/`
directory) before restarting the worker.

## What the worker records, and where

- `done/<id>.json`: the request as submitted, plus `started`, `finished`,
  `outcome`, `detail`, a per-day status map, and for a redo the manifest path.
- The run's ledger (`<year dir>/ledger.jsonl`, as `bernese-run-year`):
  `run_start` gains `request`, `submitted_by`, `kind` and `reason`; a redo adds
  `superseded` and, after a failure, `restored` entries. Existing readers
  filter on event names they know, so the new entries are invisible to them.
- `SUPERSEDED/<stamp>/MANIFEST_*.json`: what was moved, its checksums, and
  each state the redo passed through, with times.
- The BPE lock record: `worker <id> <kind> <campaign> <year> <days> by <user>`,
  which is what the console shows as the holder.

## Not in scope

Authentication; a systemd unit or any sudo file (deployment is done on gps3);
the console's HTTP endpoints, which will write requests with
`run_queue.submit` and read `status.json` and `done/`.
