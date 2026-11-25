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
# It refuses unless the worker is idle with an empty queue. A restart mid-request
# would make systemd wait up to TimeoutStopSec=3h while the worker finishes its
# block (see install_bernese_worker_gps3.sh). A queued request counts too: the
# worker starts one within 5 s, so a non-empty queue means it is about to be busy.
# Queue new requests after the restart. A worker that is not running at all is
# restarted whatever the queue holds: there is nothing to interrupt.
set -euo pipefail
RUN_CHECKOUT=/home/gps3/repos/mf_run
STATE=/home/gps3/.local/state/bernese-workflow/worker

[ "$(id -u)" -eq 0 ] || { echo "FATAL: run with sudo" >&2; exit 1; }
echo "== $(date -Is) code: $(sudo -u gps3 -H git -C "$RUN_CHECKOUT" log --oneline -1)"
old=$(systemctl show -p MainPID --value bernese-worker)
echo "== old pid: $old"
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
if [ "$old" != 0 ]; then
  # A running worker with a request in active/ is mid-run; with one in queue/ it
  # claims it within 5 s. Both would make the restart wait up to TimeoutStopSec.
  [ -z "$active" ] || { echo "FATAL: a request is running ($active); not restarting" >&2; exit 1; }
  [ -z "$queued" ] || { echo "FATAL: $(echo "$queued" | wc -l) request(s) queued; the worker is about to start one" >&2; exit 1; }
else
  # No worker process: nothing can be interrupted. A request left in active/ is
  # what Worker.recover handles on start.
  echo "== worker not running; active: ${active:-none}; queued: $(echo -n "$queued" | grep -c . || true)"
fi
# Residual race: a request submitted between the check above and the restart
# below is claimed within 5 s, and the restart then waits for its block.
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
# status exits non-zero for an unhealthy unit and pipefail would turn that into
# the script's exit code after the checks above have already passed.
systemctl --no-pager status bernese-worker | head -6 || true
