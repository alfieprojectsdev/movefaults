#!/usr/bin/env bash
# gps3_reconnect.sh — get the R740 back on the network, AT THE CONSOLE.
#
# The other gps3_* scripts are recon. This one changes things.
#
# WHY IT IS SAFE HERE AND WOULD NOT BE REMOTELY
# ---------------------------------------------
# Every remediation was deferred in the diagnostic plan for one reason: there is
# no out-of-band console, so a network change that goes wrong loses the machine
# until someone drives to it. Standing at the terminal, that argument inverts —
# you ARE the recovery path. This is the one moment when fixing is cheaper than
# diagnosing.
#
# The ordering still matters:
#
#   1. RUNTIME first. `ip link set up` / `ip addr add` do not survive a reboot,
#      which is exactly why they are safe: the worst case is a reboot away.
#      Get the box reachable, confirm it from another machine, THEN persist.
#   2. PERSIST second, and only after runtime is proven, using `netplan try`,
#      which auto-reverts if you do not confirm.
#   3. NEVER `netplan apply` blind, and never edit netplan before the runtime
#      fix has demonstrated what the right config actually is.
#
# USAGE
#   sudo bash gps3_reconnect.sh              # DRY RUN — diagnose and print the plan
#   sudo bash gps3_reconnect.sh --apply      # apply the runtime fix
#   sudo bash gps3_reconnect.sh --persist    # after --apply works: write netplan
#
# Dry run is the default on purpose. Read the plan before letting it act.

set -uo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

ADDR="${GPS3_ADDR:-192.168.48.98}"
CIDR="${GPS3_CIDR:-24}"
GW="${GPS3_GW:-192.168.48.5}"
IFACE_EXPECTED="${GPS3_IFACE:-eno4}"
PEER="${GPS3_PEER:-192.168.48.99}"     # file server: known-good ping target

MODE=dry
case "${1:-}" in
  --apply)   MODE=apply ;;
  --persist) MODE=persist ;;
  ""|--dry)  MODE=dry ;;
  *) echo "usage: $0 [--apply|--persist]"; exit 2 ;;
esac

[ "$(id -u)" = "0" ] || { echo "must run as root:  sudo bash $0 ${1:-}"; exit 1; }

say(){ printf '\n== %s\n' "$*"; }
do_or_show(){                       # the only place this script mutates anything
  if [ "$MODE" = dry ]; then printf '   WOULD RUN: %s\n' "$*"
  # eval on "$*": command strings, deliberately re-parsed, not arg vectors.
  else printf '   RUN: %s\n' "$*"; eval "$*" || echo "   ^ failed (continuing)"; fi
}

printf 'gps3 reconnect — %s\nmode: %s   target: %s/%s via %s on %s\n' \
  "$(date)" "$MODE" "$ADDR" "$CIDR" "$GW" "$IFACE_EXPECTED"

# ---------------------------------------------------------------------------
say "1. WHAT IS ACTUALLY THERE"
ip -br link
echo
ip -br addr | grep -v '^lo'

# Find a usable wired interface, preferring the expected one. Excludes loopback,
# virtual and wireless devices so a docker bridge cannot be mistaken for the NIC.
CANDIDATES=$(for d in /sys/class/net/*; do
  n=$(basename "$d")
  case "$n" in lo|docker*|veth*|br-*|virbr*|tun*|tap*|wl*) continue;; esac
  [ -e "$d/device" ] || continue     # must be a real hardware device
  echo "$n"
done)
echo
# Word splitting is the point: turn the newline-separated list into one line.
# shellcheck disable=SC2086
printf 'wired hardware interfaces: %s\n' "$(printf '%s ' $CANDIDATES)"  # word-split intended

if echo "$CANDIDATES" | grep -qx "$IFACE_EXPECTED"; then
  IFACE="$IFACE_EXPECTED"
  echo "  $IFACE_EXPECTED exists — no rename occurred"
else
  IFACE=$(echo "$CANDIDATES" | head -1)
  cat <<EOF
  !!! $IFACE_EXPECTED DOES NOT EXIST.
  !!! The kernel upgrade renamed the interface. This is very likely the whole
  !!! fault: netplan configures a device that is gone, so the box boots clean
  !!! with no address and nothing on the network.
  !!! Proceeding with: ${IFACE:-<none found>}
EOF
fi
[ -n "${IFACE:-}" ] || { echo "No wired interface found at all. This is hardware — see the physical checklist."; exit 1; }

# ---------------------------------------------------------------------------
say "2. LINK STATE — can software fix this at all?"
OPER=$(cat "/sys/class/net/$IFACE/operstate" 2>/dev/null)
CARRIER=$(cat "/sys/class/net/$IFACE/carrier" 2>/dev/null || echo 0)
printf '   %s: operstate=%s carrier=%s\n' "$IFACE" "$OPER" "$CARRIER"

if [ "$OPER" = down ] && [ "$CARRIER" != 1 ]; then
  do_or_show "ip link set $IFACE up"
  sleep 2
  CARRIER=$(cat "/sys/class/net/$IFACE/carrier" 2>/dev/null || echo 0)
fi

if [ "$CARRIER" != 1 ]; then
  cat <<EOF

   !!! NO CARRIER after bringing the link up.
   !!! No software change can fix this. It is physical:
   !!!   - cable unseated at the server, or at the switch
   !!!   - cable moved to a different port
   !!!   - switch port disabled or dead
   !!! Check the link LEDs on $IFACE's port, reseat the cable, then re-run.
EOF
  [ "$MODE" = dry ] || exit 1
fi

# ---------------------------------------------------------------------------
say "3. ADDRESS"
HAVE_ADDR=$(ip -4 addr show dev "$IFACE" 2>/dev/null | grep -oE 'inet [0-9.]+/[0-9]+' | awk '{print $2}')
printf '   currently: %s\n' "${HAVE_ADDR:-none}"

if [ "$HAVE_ADDR" = "${ADDR}/${CIDR}" ]; then
  echo "   already correct"
else
  [ -n "$HAVE_ADDR" ] && echo "   NOTE: a different address is present; adding the expected one alongside it"
  # Runtime only. Does not survive a reboot — which is the safety property.
  do_or_show "ip addr add ${ADDR}/${CIDR} dev $IFACE"
  do_or_show "ip link set $IFACE up"
fi

say "4. ROUTE"
if ip route show default | grep -q "$GW"; then
  echo "   default via $GW already present"
else
  do_or_show "ip route add default via $GW dev $IFACE"
fi

# ---------------------------------------------------------------------------
say "5. SSHD — is it even listening?"
if systemctl is-active ssh >/dev/null 2>&1; then
  echo "   ssh active"
else
  echo "   ssh NOT active"
  do_or_show "systemctl start ssh"
fi
ss -lntp 2>/dev/null | grep -E ':22\b' || echo "   nothing listening on 22"

# ---------------------------------------------------------------------------
say "6. DID IT WORK?"
if [ "$MODE" = dry ]; then
  echo "   (dry run — nothing was changed. Re-run with --apply.)"
else
  ip -br addr show dev "$IFACE"
  echo
  if ping -c 3 -W 2 "$PEER" >/dev/null 2>&1; then
    echo "   ping $PEER  OK  — the machine is back on the network"
  else
    echo "   ping $PEER  FAILED"
    echo "   ARP check (the file server answers ARP even when ICMP is filtered):"
    ping -c 1 -W 1 "$PEER" >/dev/null 2>&1
    ip neigh show "$PEER" | sed 's/^/     /'
  fi
  cat <<EOF

   Now confirm FROM THE OTHER MACHINE before you leave the room:
       bash scripts/gps3_reach.sh          # on the T420, expect WORLD A or B
   Do not trust this script's own opinion of its success.
EOF
fi

# ---------------------------------------------------------------------------
say "7. MAKING IT SURVIVE A REBOOT"
NETPLAN=$(find /etc/netplan -maxdepth 1 -name '*.yaml' 2>/dev/null | sort | head -1)
echo "   netplan file: ${NETPLAN:-none found}"
[ -n "$NETPLAN" ] && grep -nE 'eno|ens|eth|addresses|gateway|routes' "$NETPLAN" | sed 's/^/     /'

if [ "$IFACE" != "$IFACE_EXPECTED" ]; then
  cat <<EOF

   The interface is now '$IFACE' but netplan almost certainly still says
   '$IFACE_EXPECTED'. Until that is corrected, the address you just set is lost
   on the next reboot and the machine goes dark again.
EOF
fi

if [ "$MODE" != persist ]; then
  cat <<EOF

   NOT persisting yet, deliberately. Do it only after the runtime fix above is
   confirmed working from another machine. Then:

       sudo bash $0 --persist

   That writes a timestamped backup, edits the interface name, and applies with
   'netplan try' — which AUTO-REVERTS after 120s unless you press Enter. If the
   new config breaks the link, doing nothing restores it.
EOF
else
  [ -n "$NETPLAN" ] || { echo "   no netplan file to edit"; exit 1; }
  BAK="${NETPLAN}.bak-$(date +%Y%m%d-%H%M%S)"
  do_or_show "cp -a '$NETPLAN' '$BAK'"
  echo "   backup: $BAK"
  if [ "$IFACE" != "$IFACE_EXPECTED" ]; then
    do_or_show "sed -i 's/\\b${IFACE_EXPECTED}\\b/${IFACE}/g' '$NETPLAN'"
    echo "   rewrote $IFACE_EXPECTED -> $IFACE"
  else
    echo "   interface name unchanged; nothing to rewrite"
  fi
  echo
  echo "   Review it before applying:"
  sed 's/^/     /' "$NETPLAN"
  cat <<EOF

   Then, and ONLY from the console:
       sudo netplan try          # auto-reverts in 120s unless you confirm
       sudo netplan apply        # only after 'try' succeeded
       sudo reboot               # final proof it survives — you are here to watch
   Restore with:  sudo cp -a '$BAK' '$NETPLAN' && sudo netplan apply
EOF
fi

say "8. BEFORE YOU LEAVE"
cat <<'EOF'
   Give iDRAC an address. That is what turns the NEXT failure from this trip
   into a browser tab, and it is the only item here that stops this recurring.
   Change the default password and the SNMP community string first.
EOF
