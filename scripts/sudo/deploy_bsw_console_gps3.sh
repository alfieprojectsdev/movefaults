#!/usr/bin/env bash
# deploy_bsw_console_gps3.sh -- step 3 of 3: serve the console from main, and
# switch its run buttons on only when steps 1 and 2 are in place.
#
#   step 1  install_bernese_worker_gps3.sh     the run worker as a service
#   step 2  setup_bsw_console_login_gps3.sh    Caddy login in front of the console
#   step 3  this script
#
# On a new machine, run this once before step 2: it writes the console's unit,
# with the buttons off, and step 2 changes that unit. Then step 2, then this again.
#
# Run:   sudo bash /home/gps3/repos/movefaults_clean/scripts/sudo/deploy_bsw_console_gps3.sh \
#            --operators AB,CD [--ts-reference CODE] > ~/bsw_console_deploy.log 2>&1
#   The Time series page reads each campaign year's own <V_RESULT>/STA (#343);
#   --ts-crd-dir is accepted for old command lines and ignored.
#   The reference station is chosen on the Time series page (#337); --ts-reference
#   only sets the one it starts with, and without it the unit's current one is kept.
# Undo:  sudo bash <same path> --undo > ~/bsw_console_deploy_undo.log 2>&1
#
# What it does:
#   1. Refuses to touch anything while a BPE runs, the BPE lock is held or the
#      worker has a request active: it moves the production checkout they depend on.
#   2. Stops the worker, so it cannot claim a queued request while its code
#      moves; moves ~/repos/mf_run (the production checkout the worker already
#      runs from) to origin/main, syncs its venv and builds the console frontend;
#      starts the worker again, also if a step here fails.
#      The console and the worker then run the same code.
#   3. Writes the equipment report once (bernese-check-equipment --json on
#      PHNAT.STA against the committed inventory sheet). The report is advisory:
#      if this fails the deploy goes on with a warning. Refreshing it nightly
#      is a separate cron decision; the page shows the report's time.
#   4. Rewrites the console's unit to run from mf_run, with the worker's queue,
#      the equipment report and, if given, the time-series inputs. The old
#      unit is kept as .pre-deploy-<time>.
#   5. Switches the buttons on (BSW_CONSOLE_ACTIONS=on, BSW_CONSOLE_OPERATORS)
#      ONLY IF the worker service is active, Caddy is active, the console
#      listens on 127.0.0.1 only and trusts only 127.0.0.1, and --operators is
#      given. Otherwise they stay off and the log says which check failed.
#
# Note: the console believes X-Remote-User from 127.0.0.1, which is where
# Caddy connects from. A shell user on gps3 could therefore name any operator
# with curl. That is no new power: such a user can run bernese-run-year
# directly. Keep gps3 shell access to the people who could anyway.
set -euo pipefail

RUN=/home/gps3/repos/mf_run
UNIT=/etc/systemd/system/bsw-console-alpha.service
SETVAR=/home/gps3/BERN54/LOADGPS.setvar
WORKER_STATE=/home/gps3/.local/state/bernese-workflow/worker
BPE_LOCK_FILE=/home/gps3/.local/state/bernese-workflow/bpe.lock
CONSOLE_STATE=/home/gps3/.local/state/bsw-console
REPORT=$CONSOLE_STATE/equipment_report.json
STA=/home/gps3/GPSDATA/DATAPOOL/REF54/PHNAT.STA
OFFSETS=$RUN/docs/bern52/phivolcs-scripts/event-catalog/offsets

[ "$(id -u)" -eq 0 ] || { echo "FATAL: run with sudo" >&2; exit 1; }
echo "== $(date -Is) $0 $*"
as_gps3() { sudo -u gps3 -H bash -c "$1"; }

if [ "${1:-}" = "--undo" ]; then
  last=$(ls -1t "$UNIT".pre-deploy-* 2>/dev/null | head -1 || true)
  [ -n "$last" ] || { echo "FATAL: no $UNIT.pre-deploy-* to restore" >&2; exit 1; }
  cp "$last" "$UNIT"; systemctl daemon-reload; systemctl restart bsw-console-alpha
  echo "== restored $last (mf_run is left where it is; the worker keeps running it)"
  exit 0
fi

OPERATORS="" TS_REF=""
while [ $# -gt 0 ]; do
  case "$1" in
    --operators) OPERATORS=$2; shift 2 ;;
    --ts-crd-dir) echo "   note: --ts-crd-dir is ignored; the page reads each campaign year's own STA"; shift 2 ;;
    --ts-reference) TS_REF=$(echo "$2" | tr a-z A-Z); shift 2 ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 1 ;;
  esac
done
[[ -z "$OPERATORS" || "$OPERATORS" =~ ^[A-Za-z0-9._-]+(,[A-Za-z0-9._-]+)*$ ]] \
  || { echo "FATAL: --operators takes bare usernames, comma-separated" >&2; exit 1; }

echo "== 1. nothing running"
if pgrep -f 'startBPE|RUNBPE|sessions_pcs.pl' >/dev/null; then
  echo "FATAL: a BPE is running; deploy after it ends" >&2; exit 1
fi
# The machine-wide lock also covers bernese-run-year between two BPE calls, when
# no BPE process exists for pgrep to see. Idle workers do not hold it.
if [ -e "$BPE_LOCK_FILE" ] && ! flock -n "$BPE_LOCK_FILE" true; then
  echo "FATAL: the BPE lock is held; deploy after it ends: $(cat "$BPE_LOCK_FILE" 2>/dev/null)" >&2; exit 1
fi
# No status file means no worker has ever run. An unreadable one is not "idle".
active=""
if [ -e "$WORKER_STATE/status.json" ]; then
  active=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("active") or "")' "$WORKER_STATE/status.json") \
    || { echo "FATAL: cannot read $WORKER_STATE/status.json" >&2; exit 1; }
fi
[ -z "$active" ] || { echo "FATAL: the worker is running request $active; deploy after it ends" >&2; exit 1; }

echo "== 2. production checkout to origin/main"
before=$(as_gps3 "git -C $RUN rev-parse --short HEAD")
# GitHub over HTTPS, with gps3's gh login.
for t in 1 2 3; do
  sudo -u gps3 -H env GIT_CONFIG_COUNT=2 \
    GIT_CONFIG_KEY_0=url.https://github.com/.insteadOf GIT_CONFIG_VALUE_0=git@github.com: \
    GIT_CONFIG_KEY_1=credential.https://github.com.helper GIT_CONFIG_VALUE_1='!gh auth git-credential' \
    git -C "$RUN" fetch -q origin main && break
  [ "$t" = 3 ] && { echo "FATAL: could not fetch from GitHub" >&2; exit 1; }
  sleep 20
done
# A queued request must not start while the code and the venv move under it. The
# worker was idle a moment ago; if it just claimed a request, this waits for the
# block in progress (see install_bernese_worker_gps3.sh).
worker_stopped=0
if systemctl is-active -q bernese-worker; then
  systemctl stop bernese-worker; worker_stopped=1
  trap 'systemctl start bernese-worker' EXIT
fi
as_gps3 "git -C $RUN checkout -q --detach origin/main"
after=$(as_gps3 "git -C $RUN rev-parse --short HEAD")
echo "   mf_run $before -> $after"
as_gps3 "cd $RUN && /home/gps3/.local/bin/uv sync --all-extras --frozen -q"
as_gps3 "cd $RUN/services/bsw-console/frontend && npm ci --silent && npm run build --silent" >/dev/null
[ -f "$RUN/services/bsw-console/frontend/dist/index.html" ] || { echo "FATAL: frontend build missing" >&2; exit 1; }
[ -x "$RUN/.venv/bin/bsw-console" ] || { echo "FATAL: $RUN/.venv/bin/bsw-console missing" >&2; exit 1; }
if [ "$worker_stopped" = 1 ]; then systemctl start bernese-worker; trap - EXIT; echo "   worker restarted on $after"; fi

echo "== 3. equipment report"
if as_gps3 "mkdir -p $CONSOLE_STATE && $RUN/.venv/bin/bernese-check-equipment --sta $STA --equipment-csv $RUN/data/network_inventory/equipment.csv --json > $REPORT.tmp && mv $REPORT.tmp $REPORT"; then
  echo "   $(stat -c '%s bytes' "$REPORT") -> $REPORT"
else
  rm -f "$REPORT.tmp"
  echo "   WARNING: equipment report not refreshed; the page keeps the last one, if any"
fi

echo "== 4. may the buttons go on?"
why=()
systemctl is-active -q bernese-worker || why+=("the bernese-worker service is not active (step 1)")
systemctl is-active -q caddy || why+=("Caddy is not active (step 2)")
grep -qs '^Environment=BSW_CONSOLE_HOST=127.0.0.1$' "$UNIT" || why+=("the console does not listen on 127.0.0.1 only (step 2)")
grep -qs '^Environment=BSW_CONSOLE_TRUSTED_PROXIES=127.0.0.1$' "$UNIT" || why+=("the console does not trust only 127.0.0.1 (step 2)")
[ -n "$OPERATORS" ] || why+=("no --operators given")
if [ ${#why[@]} -eq 0 ]; then ACTIONS=on; echo "   yes: operators $OPERATORS"
else ACTIONS=off; printf '   no, they stay off: %s\n' "${why[@]}"; fi

# No unit yet (a new machine): 127.0.0.1, with no proxy trusted, so nobody can act.
host=127.0.0.1 proxies=""
if [ -f "$UNIT" ]; then
  host=$(sed -n 's/^Environment=BSW_CONSOLE_HOST=//p' "$UNIT"); host=${host:-127.0.0.1}
  proxies=$(sed -n 's/^Environment=BSW_CONSOLE_TRUSTED_PROXIES=//p' "$UNIT")
  [ -n "$TS_REF" ] || TS_REF=$(sed -n 's/^Environment=BSW_CONSOLE_TS_REFERENCE=//p' "$UNIT")
  cp "$UNIT" "$UNIT.pre-deploy-$(date +%Y%m%d-%H%M%S)"
fi
{
  echo "[Unit]"
  echo "Description=BSW 5.4 processing console (from the production checkout)"
  echo "After=network-online.target bernese-worker.service"
  echo "Wants=network-online.target"
  echo
  echo "[Service]"
  echo "User=gps3"
  echo "Group=gps3"
  echo "WorkingDirectory=$RUN"
  echo "Environment=BSW_CONSOLE_HOST=$host"
  echo "Environment=PORT=8002"
  echo "Environment=BSW_SETVAR=$SETVAR"
  [ -n "$proxies" ] && echo "Environment=BSW_CONSOLE_TRUSTED_PROXIES=$proxies"
  echo "Environment=BERNESE_WORKER_STATE=$WORKER_STATE"
  echo "Environment=BSW_CONSOLE_EQUIPMENT_REPORT=$REPORT"
  echo "Environment=BSW_CONSOLE_TS_OFFSETS=$OFFSETS"
  [ -n "$TS_REF" ] && echo "Environment=BSW_CONSOLE_TS_REFERENCE=$TS_REF"
  if [ "$ACTIONS" = on ]; then
    echo "Environment=BSW_CONSOLE_ACTIONS=on"
    echo "Environment=BSW_CONSOLE_OPERATORS=$OPERATORS"
  fi
  echo "ExecStart=$RUN/.venv/bin/bsw-console"
  echo "Restart=on-failure"
  echo "RestartSec=10"
  echo "NoNewPrivileges=true"
  echo
  echo "[Install]"
  echo "WantedBy=multi-user.target"
} > "$UNIT"
systemctl daemon-reload
systemctl enable -q bsw-console-alpha
systemctl restart bsw-console-alpha

echo "== 5. checks (direct, on 127.0.0.1:8002 or the console's own address)"
url="http://$host:8002"
up=no
for i in $(seq 30); do curl -sf -o /dev/null "$url/api/session" && { up=yes; break; }; sleep 1; done
if [ "$up" != yes ]; then
  echo "FATAL: the console did not answer on $url in 30 s (--undo restores the previous unit)" >&2
  journalctl -u bsw-console-alpha --no-pager -n 20 || true
  exit 1
fi
echo "   session:     $(curl -s "$url/api/session")"
echo "   worker:      $(curl -s "$url/api/worker" | head -c 300)"
echo "   equipment:   $(curl -s "$url/api/equipment-report" | head -c 200)"
echo "   time series: $(curl -s --max-time 30 "$url/api/campaigns/PHREF/time-series" | head -c 200)"
[ "$host" = 127.0.0.1 ] && echo "   from outside: use https://<gps3>:8443 with a login (step 2)"
echo "== done: console on $after, buttons $ACTIONS"
