#!/usr/bin/env bash
# List the 2025 comparison campaigns on the BSW console (Campaigns, Recent activity):
# PHPAR (the 5.2 run's station set, the 5.4-vs-5.2 parity run) and PHSUP (every 2025
# file on hand, the superset run).
#
# Uses a systemd drop-in, so re-running deploy_bsw_console_gps3.sh, which rewrites
# the main unit, doesn't remove it. Touches only the console: the worker and any
# BPE run are left alone. Safe to re-run: it rewrites the same drop-in. To undo,
# delete the drop-in and restart the console.
#
# Usage: sudo bash scripts/sudo/add_phpar_console_gps3.sh > ~/phpar_console.log 2>&1
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }

UNIT=bsw-console-alpha
DROPIN_DIR=/etc/systemd/system/$UNIT.service.d
DROPIN=$DROPIN_DIR/phpar-campaign.conf
CAMPAIGNS="LUZON:LUZON_DLY:LZY:LZFLT_DLY,PHREF:PHREF_DLY:PHR,PHDEN:PHDEN_DLY:PHD,PHPAR:PHPAR_DLY:PPR,PHSUP:PHSUP_DLY:PSU"

mkdir -p "$DROPIN_DIR"
printf '[Service]\nEnvironment=BSW_CONSOLE_CAMPAIGNS=%s\n' "$CAMPAIGNS" > "$DROPIN"
echo "wrote $DROPIN"

systemctl daemon-reload
systemctl restart "$UNIT"

for _ in $(seq 1 30); do
  out=$(curl -s --max-time 5 http://127.0.0.1:8002/api/campaigns || true)
  case "$out" in
    *'"PHPAR"'*'"PHSUP"'*) echo "ok: the console lists PHPAR and PHSUP"; exit 0 ;;
  esac
  sleep 2
done
echo "FAILED: the console did not list PHPAR and PHSUP within 60 s"
systemctl status "$UNIT" --no-pager | tail -15
exit 1
