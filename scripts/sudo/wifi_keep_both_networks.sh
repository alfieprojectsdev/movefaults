#!/usr/bin/env bash
# wifi_keep_both_networks.sh — stop finch killing its wifi when ethernet is up.
#
# WHAT IS THERE NOW
# /etc/NetworkManager/dispatcher.d/99-wifi-auto-toggle.sh runs on every
# NetworkManager event and, when enp0s25 comes up, executes:
#
#     nmcli radio wifi off
#
# That is a RADIO kill, not a route preference. While ethernet is up the
# machine has no wireless address at all.
#
# WHY THAT IS A PROBLEM, BEYOND the stated preference
# finch is dual-homed: enp0s25 on 192.168.40.x carries the default route, and
# wlp3s0 sits on 192.168.48.x -- the PHIVOLCS LAN, and the only subnet it
# shares with gps3. Killing the radio removes finch from 192.168.48.0/24
# entirely. When gps3 swept that subnet on 2026-09-07 and did not find finch,
# an unreachable-looking machine was the expected result of this script, quite
# apart from whether finch was also crashed at the time. Two different causes
# producing one symptom is exactly what makes an outage hard to read.
#
# It also matters for Tailscale: with the radio off, the direct LAN peering to
# gps3 (192.168.48.98, ~1 ms) is unavailable and traffic must relay.
#
# WHAT THIS DOES
# Disables the dispatcher script by removing its execute bit -- NetworkManager
# ignores non-executable files in dispatcher.d -- and turns the radio back on.
# The file is left in place, so `chmod +x` on it restores the old behaviour
# exactly. Nothing is deleted and no connection profile is edited.
#
# Usage:  sudo bash scripts/sudo/wifi_keep_both_networks.sh
# Safe to re-run.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run with sudo -- this changes a NetworkManager dispatcher script." >&2
    exit 1
fi

HOOK=/etc/NetworkManager/dispatcher.d/99-wifi-auto-toggle.sh

say() { printf '\n=== %s\n' "$*"; }

say "Before"
echo "  wifi radio : $(nmcli radio wifi 2>/dev/null || echo unknown)"
nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null | sed 's/^/  /'

say "Disabling the auto-toggle hook"
if [ ! -e "$HOOK" ]; then
    echo "  $HOOK does not exist — nothing to disable."
elif [ ! -x "$HOOK" ]; then
    echo "  already non-executable; NetworkManager is ignoring it."
else
    chmod -x "$HOOK"
    echo "  execute bit removed from $HOOK"
    echo "  (restore the old behaviour with: sudo chmod +x $HOOK)"
fi

say "Ensuring the wifi radio is on"
nmcli radio wifi on || true
echo "  wifi radio : $(nmcli radio wifi 2>/dev/null || echo unknown)"

say "Result"
nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null | sed 's/^/  /'
echo
ip -4 -o addr show scope global 2>/dev/null | awk '{print "  "$2"  "$4}'

cat <<'CLOSING'

Both interfaces should now stay up together. If wlp3s0 does not reconnect on
its own, it has no saved profile for the current network rather than a disabled
radio -- connect it once from the desktop and it will autoconnect after that.

Routing is unchanged: whichever interface has the lower metric still carries
the default route (enp0s25 at 100, wlp3s0 at 600). This only stops the radio
being switched off; it does not make wifi the preferred path.
CLOSING
