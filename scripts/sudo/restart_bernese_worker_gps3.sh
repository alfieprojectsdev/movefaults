#!/usr/bin/env bash
# restart_bernese_worker_gps3.sh -- restart bernese-worker.service on the code now
# checked out in ~/repos/mf_run.
#
# Run: sudo bash /home/gps3/repos/movefaults_clean/scripts/sudo/restart_bernese_worker_gps3.sh > ~/bernese_worker_restart.log 2>&1
#
# Deploying new code, first as gps3 (no sudo). Check that nothing is active or
# queued before the checkout (`~/repos/mf_run/.venv/bin/bernese-worker list`; not
# `uv run`, which syncs the venv without --all-extras): the checkout and the sync
# change the code under a running worker, before this script's own idle check
# gets a chance to refuse.
#   git -C ~/repos/mf_run fetch origin && git -C ~/repos/mf_run checkout --detach origin/main
#   cd ~/repos/mf_run && uv sync --all-extras --dry-run   # expect only the project reinstalled
#   uv sync --all-extras
# --all-extras matters: a plain `uv sync` removes the extras the console runs on.
# The console (bsw-console-alpha) runs from the same checkout; restart it separately
# if its own code changed.
#
# When it restarts. A restart while the worker runs a request would make systemd
# wait up to TimeoutStopSec=3h while it finishes its block (see
# install_bernese_worker_gps3.sh), so:
#   - running a request: refused.
#   - idle: restarted only with an empty queue. An idle worker claims a queued
#     request within one poll (5 s), so a queued one means it is about to be busy.
#   - stuck (halted, waiting for the BPE lock, blocked by a BPE running without
#     the lock): restarted whatever the queue holds. In these states the worker
#     holds no request and checks for SIGTERM before claiming one
#     (run_worker.Worker.step), so it exits within a poll.
#   - not running at all: restarted; there is nothing to interrupt. A request
#     left in active/ is what Worker.recover handles on start.
# The state comes from the worker's status.json, trusted only when it names the
# live pid and was written in the last 2 minutes (the worker rewrites it at least
# every 60 s). Otherwise the idle rule applies.
set -euo pipefail
RUN_CHECKOUT=/home/gps3/repos/mf_run

[ "$(id -u)" -eq 0 ] || { echo "FATAL: run with sudo" >&2; exit 1; }
echo "== $(date -Is) code: $(sudo -u gps3 -H git -C "$RUN_CHECKOUT" log --oneline -1)"
old=$(systemctl show -p MainPID --value bernese-worker)
echo "== old pid: $old"
# The worker's queue: $BERNESE_WORKER_STATE in its own environment (the unit
# sources LOADGPS.setvar with set -a), else run_queue.DEFAULT_STATE. sudo strips
# this shell's environment, so read the live process's.
STATE=
if [ "$old" != 0 ] && [ -r "/proc/$old/environ" ]; then
  STATE=$(tr '\0' '\n' < "/proc/$old/environ" | sed -n 's/^BERNESE_WORKER_STATE=//p')
fi
STATE=${STATE:-/home/gps3/.local/state/bernese-workflow/worker}
echo "== state dir: $STATE"
# Only *.json counts: that is all the worker reads (run_queue.Queue.pending), so a
# stray file must not block a restart forever. A missing directory is fatal, not
# empty: a wrong $STATE would otherwise pass every check below.
for d in active queue; do
  [ -d "$STATE/$d" ] || { echo "FATAL: $STATE/$d missing; is STATE right?" >&2; exit 1; }
done
# queue/ before active/: a claim renames queue/ -> active/, so reading active/ first
# could miss a request that moved between the two reads and see both empty.
queued=$(find "$STATE/queue" -maxdepth 1 -name '*.json' -printf '%f\n')
active=$(find "$STATE/active" -maxdepth 1 -name '*.json' -printf '%f\n')
# status.json -> "<state> <age in s>", or "unknown" when it is missing, unreadable,
# written by another pid, or older than 120 s.
wstate=$(python3 -I - "$STATE/status.json" "$old" <<'PY'
import datetime as dt, json, sys
try:
    s = json.load(open(sys.argv[1]))
    age = (dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(s["updated"])).total_seconds()
    ok = str(s.get("pid")) == sys.argv[2] and 0 <= age < 120
    print(f"{s['state']} {age:.0f}" if ok else "unknown")
except Exception:
    print("unknown")
PY
)
echo "== worker state: $wstate"
nq=$(echo -n "$queued" | grep -c . || true)
if [ "$old" != 0 ]; then
  case "${wstate%% *}" in
    running)
      echo "FATAL: the worker is running a request (${active:-see bernese-worker list}); not restarting" >&2; exit 1;;
    halted|waiting-for-bpe-lock|blocked-by-running-bpe)
      echo "== the worker is ${wstate%% *}: it holds no request, so it is restarted (active: ${active:-none}; queued: $nq)";;
    *)
      # idle, or a state that can't be trusted: the strict rule.
      [ -z "$active" ] || { echo "FATAL: a request is in active/ ($active) and the worker is ${wstate%% *}; not restarting" >&2; exit 1; }
      [ -z "$queued" ] || { echo "FATAL: $nq request(s) queued and the worker is ${wstate%% *}; an idle worker claims one within 5 s. If it is stuck, check bernese-worker list" >&2; exit 1; };;
  esac
else
  # No worker process: nothing can be interrupted. A request left in active/ is
  # what Worker.recover handles on start.
  echo "== worker not running; active: ${active:-none}; queued: $nq"
fi
# Residual race: a request submitted, or a BPE lock freed, between the check above
# and the restart below can be claimed in that moment, and the restart then waits
# for its block.
systemctl restart bernese-worker
# Check twice: a worker that dies on start (bad code, unsynced venv) shows a pid
# for a moment, then fails and waits RestartSec=30 with MainPID=0.
sleep 5
new=$(systemctl show -p MainPID --value bernese-worker)
echo "== new pid: $new"
if [ "$new" = "$old" ] || [ "$new" = 0 ]; then
  echo "FATAL: the worker did not come back with a new pid" >&2; exit 1
fi
sleep 15
again=$(systemctl show -p MainPID --value bernese-worker)
if [ "$again" != "$new" ] || ! systemctl is-active --quiet bernese-worker; then
  echo "FATAL: the worker did not stay up (pid $new, now ${again:-none})" >&2
  journalctl -u bernese-worker --no-pager -n 20 || true
  exit 1
fi
echo "== still up after 20 s: pid $again"
# A smoke check only: a fault on the first claimed request comes later. The state
# shows a worker that is already halted or recovering.
echo "== worker state now: $(python3 -I -c 'import json,sys; s=json.load(open(sys.argv[1])); print(s["state"], s.get("reason", ""))' "$STATE/status.json" 2>/dev/null || echo unreadable)"
# status exits non-zero for an unhealthy unit and pipefail would turn that into
# the script's exit code after the checks above have already passed.
systemctl --no-pager status bernese-worker | head -6 || true
