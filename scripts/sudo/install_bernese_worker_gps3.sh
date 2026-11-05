#!/usr/bin/env bash
# install_bernese_worker_gps3.sh -- run `bernese-worker run` as a system service
# on gps3, so requests queued with `bernese-worker submit` (and, later, by the
# BSW console's buttons) are carried out.
#
# Run:   sudo bash /home/gps3/repos/movefaults_clean/scripts/sudo/install_bernese_worker_gps3.sh > ~/bernese_worker_setup.log 2>&1
# Undo:  sudo bash <same path> --undo > ~/bernese_worker_undo.log 2>&1
#
# What it does:
#   A system service, bernese-worker, running as gps3 from the production
#   checkout ~/repos/mf_run (its own venv; nothing is synced or installed).
#   It sources ~/BERN54/LOADGPS.setvar first, as every BPE launch must.
#   Restarts on failure and at boot.
#
# What it does NOT do:
#   - start any run. With an empty queue the worker only polls every 5 s and
#     rewrites its status file every 60 s. It takes the BPE lock only while a
#     request runs, never while idle.
#   - change the console. Its Start/Stop/Redo/Preflight buttons stay off.
#
# Stopping it (systemctl stop, a reboot) never kills a BPE:
#   KillMode=mixed sends SIGTERM to the worker only. The worker then finishes
#   the block in progress (up to 2 x MAXSESS days) and exits. systemd waits
#   up to TimeoutStopSec=3h before SIGKILLing what is left. A shutdown
#   during a run can therefore take that long; that is deliberate. A killed
#   block leaves an orphan BPE the worker then refuses to work past.
set -euo pipefail

UNIT=/etc/systemd/system/bernese-worker.service
RUN_CHECKOUT=/home/gps3/repos/mf_run
WORKER_BIN=$RUN_CHECKOUT/.venv/bin/bernese-worker
SETVAR=/home/gps3/BERN54/LOADGPS.setvar

[ "$(id -u)" -eq 0 ] || { echo "FATAL: run with sudo" >&2; exit 1; }
echo "== $(date -Is) $0 $*"

if [ "${1:-}" = "--undo" ]; then
  systemctl disable --now bernese-worker 2>&1 || true
  rm -f "$UNIT"; systemctl daemon-reload
  echo "== removed; the queue under ~gps3/.local/state/bernese-workflow/worker is left as it was"
  exit 0
fi

[ -x "$WORKER_BIN" ] || { echo "FATAL: $WORKER_BIN missing (uv sync in $RUN_CHECKOUT first)" >&2; exit 1; }
[ -r "$SETVAR" ] || { echo "FATAL: $SETVAR not readable" >&2; exit 1; }
echo "== production checkout: $(sudo -u gps3 git -C "$RUN_CHECKOUT" log --oneline -1)"
# RUNBPE workers dial the BPE server by hostname; an unlisted hostname stalls a
# BPE (docs/SETTLED.md section 4). Warn, don't fail: the BPE has run like this.
getent ahostsv4 "$(hostname)" | head -1 | grep -qE '^127\.' \
  && echo "== hostname $(hostname) resolves locally: ok" \
  || echo "WARNING: hostname $(hostname) does not resolve to a local address"

cat > "$UNIT" <<EOF
[Unit]
Description=Bernese BPE run worker (queued requests, under the BPE lock)
After=network-online.target local-fs.target
Wants=network-online.target

[Service]
User=gps3
Group=gps3
WorkingDirectory=$RUN_CHECKOUT
ExecStart=/bin/bash -c 'set -a; . $SETVAR; set +a; exec $WORKER_BIN run'
Restart=on-failure
RestartSec=30
KillMode=mixed
TimeoutStopSec=3h
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now bernese-worker

sleep 8
echo "== after"
systemctl --no-pager status bernese-worker | head -12
journalctl -u bernese-worker --no-pager -n 20 || true
echo "== queue, as gps3 sees it"
sudo -u gps3 bash -c "set -a; . $SETVAR; set +a; $WORKER_BIN list" || echo "WARNING: bernese-worker list failed"
