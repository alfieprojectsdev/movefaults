#!/usr/bin/env bash
# install_finch_watch.sh -- make the finch liveness watcher survive a reboot.
#
# Run in YOUR OWN terminal, as root. Claude Code has no tty.
#   sudo bash /home/gps3/repos/movefaults_clean/scripts/sudo/install_finch_watch.sh
#
# The watcher itself needs no privilege -- it pings and appends to a file in
# $HOME. This script exists only to install the systemd unit that restarts it
# after a reboot or a crash. A watcher that dies silently is worse than none,
# because its silence is indistinguishable from finch being up.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "FATAL: run with sudo." >&2; exit 1; }

USER_NAME="${SUDO_USER:-gps3}"
SCRIPT_PATH="/home/${USER_NAME}/repos/movefaults_clean/scripts/finch_watch.sh"
[ -x "$SCRIPT_PATH" ] || { echo "FATAL: not executable: $SCRIPT_PATH" >&2; exit 2; }

cat > /etc/systemd/system/finch-watch.service <<UNIT
[Unit]
Description=Liveness witness for finch (T420) -- see scripts/finch_watch.sh
# Wants=, not Requires=: if the network is late the watcher should still start
# and record that it could not see finch, rather than not start at all.
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=${USER_NAME}
ExecStart=${SCRIPT_PATH}
# Always, not on-failure: a clean exit is still an unwatched finch.
Restart=always
RestartSec=10
Nice=10

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable --now finch-watch.service
sleep 2
systemctl --no-pager --lines=0 status finch-watch.service || true
echo
echo "  log: /home/${USER_NAME}/finch-watch.log"
echo "  Verify with the LOG, not with is-active:"
echo "    tail -3 /home/${USER_NAME}/finch-watch.log"
echo "  A unit that reports active while the script is wedged is exactly the"
echo "  failure mode this whole exercise is about."
