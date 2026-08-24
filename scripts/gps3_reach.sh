#!/usr/bin/env bash
# gps3_reach.sh — run from the CLIENT. Answers "which world am I in?" in one go.
#
# Implements §1 and §5.1 of gps3-ssh-diagnostic-plan-v2. Do not diagnose
# anything until this has run: three of the four outcomes mean the problem is
# not on gps3 at all, and two of them cost seconds to rule out.
#
#   WORLD 0  wrong network      -> not a fault. Join the GNSS wifi and re-run.
#   WORLD C  no ARP / no ping   -> host is off the network. Server-room trip.
#   WORLD B  ping OK, SSH fails -> read the ssh -vvv tail this prints.
#   WORLD A  SSH connects       -> gps3_evidence.sh, and give the BMC an address.
#
# Read-only. Touches nothing on gps3. Safe to run repeatedly.
#
#   bash gps3_reach.sh            # classify, and write a timestamped log
#   bash gps3_reach.sh --sweep    # also ARP-sweep the /24 (see WORLD C below)
#
# RESULT ON 2026-08-24, from the T420 on wlp3s0 (192.168.48.124):
#   WORLD C. Thirteen hosts answered ARP on 192.168.48.0/24 including .99, the
#   file server, with SMB open. gps3 at .98 was ARP FAILED throughout, and the
#   sweep found no live MAC matching its documented NICs or its BMC. So the
#   segment is fine, gps3 is absent, and it has not moved address. That is the
#   §5.1 check already done: do not re-derive it, but DO re-run this to confirm
#   nothing has changed before making the trip.

set -uo pipefail

HOST_IP="${GPS3_IP:-192.168.48.98}"
HOST_USER="${GPS3_USER:-gps3}"
SUBNET="${GPS3_SUBNET:-192.168.48}"
IFACE_HINT="${GPS3_IFACE:-}"          # optional: force a client interface
SWEEP=0
[ "${1:-}" = "--sweep" ] && SWEEP=1

STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="${TMPDIR:-/tmp}/gps3-reach-${STAMP}.log"
exec > >(tee "$LOG") 2>&1

# gps3's documented hardware addresses. Used to tell "moved to another IP"
# apart from "gone". OS NICs are all e4:3d:1a:*; the BMC is a separate NIC.
# NOTE: the BMC has never been given a network address, so its absence proves
# nothing — it is listed only so a match would be recognised.
KNOWN_MAC_PREFIXES='e4:3d:1a|b0:7b:25'

rule(){ printf '\n=== %s\n' "$1"; }
verdict(){ printf '\n################  %s  ################\n%s\n' "$1" "$2"; }

printf 'gps3 reachability — %s\ntarget: %s@%s\nlog: %s\n' \
  "$(date)" "$HOST_USER" "$HOST_IP" "$LOG"

# ---------------------------------------------------------------------------
rule "1. AM I ON A NETWORK THAT CAN REACH IT? (cheapest possible check)"
# This fails IDENTICALLY to the server being down, and has bitten before: the
# T420's wired enp0s25 sits on 192.168.40.0/24 with no route to gps3's subnet.
ip -br addr show 2>/dev/null | grep -v '^lo'
echo
ROUTE="$(ip route get "$HOST_IP" 2>/dev/null | head -1)"
echo "route: ${ROUTE:-<none>}"
DEV="$(printf '%s' "$ROUTE" | grep -oE 'dev [^ ]+' | awk '{print $2}')"
SRC="$(printf '%s' "$ROUTE" | grep -oE 'src [^ ]+' | awk '{print $2}')"
command -v iwgetid >/dev/null 2>&1 && { printf 'wifi : '; iwgetid 2>/dev/null || echo '(not wireless)'; }

if [ -z "$DEV" ] || ! printf '%s' "$SRC" | grep -q "^${SUBNET}\."; then
  verdict "WORLD 0 — WRONG NETWORK" \
"No route to $HOST_IP from an address on ${SUBNET}.0/24.
This is NOT a gps3 fault and nothing else in this script means anything.
Join the GNSS wifi (the subnet gps3 is on) and re-run.
  src=${SRC:-none}  dev=${DEV:-none}"
  exit 0
fi
echo "OK: reachable-in-principle via $DEV from $SRC"

# ---------------------------------------------------------------------------
rule "2. IS THE HOST ANSWERING AT LAYER 2?"
# ARP is the honest test. ICMP is often filtered — the gateway here answers ARP
# but drops ping, so a ping-only test would wrongly condemn it.
ping -c 3 -W 2 "$HOST_IP" >/dev/null 2>&1 && PING_OK=1 || PING_OK=0
ip neigh show "$HOST_IP" 2>/dev/null || echo "  (no neighbour entry)"
NEIGH="$(ip neigh show "$HOST_IP" 2>/dev/null)"
case "$NEIGH" in
  *lladdr*) ARP_OK=1; MAC="$(printf '%s' "$NEIGH" | grep -oE '([0-9a-f]{2}:){5}[0-9a-f]{2}')" ;;
  *)        ARP_OK=0; MAC="" ;;
esac
printf 'ping: %s   arp: %s %s\n' \
  "$([ "$PING_OK" = 1 ] && echo OK || echo FAIL)" \
  "$([ "$ARP_OK" = 1 ] && echo RESOLVED || echo FAILED)" "$MAC"

if [ "$ARP_OK" = 1 ] && ! printf '%s' "$MAC" | grep -qE "^($KNOWN_MAC_PREFIXES)"; then
  echo "!!! $HOST_IP answers, but its MAC ($MAC) does not match gps3's documented"
  echo "!!! NICs. Another machine may now hold this address. Verify before trusting SSH."
fi

# ---------------------------------------------------------------------------
if [ "$ARP_OK" = 0 ]; then
  rule "3. WORLD C CONFIRMATION — is the segment itself alive?"
  # Distinguishes "we are isolated" from "gps3 specifically is gone".
  GW="$(ip route show default dev "$DEV" 2>/dev/null | grep -oE 'via [^ ]+' | awk '{print $2}' | head -1)"
  echo "gateway: ${GW:-unknown}"
  [ -n "$GW" ] && { ping -c 2 -W 2 "$GW" >/dev/null 2>&1 && echo "  gateway pings" \
      || echo "  gateway does not ping (often filtered — check ARP instead)"; }
  [ -n "$GW" ] && ip neigh show "$GW" 2>/dev/null

  if [ "$SWEEP" = 1 ]; then
    echo
    echo "-- ARP sweep of ${SUBNET}.0/24 (populating cache, ~15s) --"
    for i in $(seq 1 254); do (ping -c1 -W1 "${SUBNET}.$i" >/dev/null 2>&1 &); done
    sleep 15
    echo "live hosts:"
    ip neigh show dev "$DEV" 2>/dev/null | grep -v FAILED \
      | grep -E "^${SUBNET}\." | sort -t. -k4 -n | sed 's/^/  /'
    echo
    echo "-- does gps3 hold a DIFFERENT address? (plan v2 §5.1) --"
    HIT="$(ip neigh show dev "$DEV" 2>/dev/null | grep -v FAILED \
           | grep -iE "$KNOWN_MAC_PREFIXES" || true)"
    if [ -n "$HIT" ]; then
      echo "  MATCH — gps3 appears to have moved:"; printf '  %s\n' "$HIT"
      echo "  Likely cause: interface renamed, netplan failed to apply the static"
      echo "  address, and DHCP handed it a different one. SSH to the address above."
    else
      echo "  no MAC matching $KNOWN_MAC_PREFIXES — gps3 is not on this subnet at all"
    fi
  else
    echo
    echo "Re-run with --sweep to check whether gps3 came up on a different address"
    echo "before accepting a server-room trip. (Done 2026-08-24: it had not.)"
  fi

  verdict "WORLD C — HOST IS OFF THE NETWORK" \
"gps3 does not answer ARP. If the sweep above shows other hosts alive, the
segment is fine and gps3 specifically is absent: powered off, cable out, or
the interface renamed/downed by the kernel upgrade.

There is no out-of-band console (iDRAC has no address), so which of those it
is CANNOT be established from here. Next step is physical:

    scripts/gps3_console_triage.sh   — run it at the terminal
    docs/gps3-sessions/...           — the server-room checklist

While you are there, give the BMC an address. Its absence is the entire reason
this needs a trip."
  exit 0
fi

# ---------------------------------------------------------------------------
rule "4. DOES SSH WORK? (verbose, tail only)"
SSHLOG="${TMPDIR:-/tmp}/gps3-sshv-${STAMP}.log"
timeout 25 ssh -vvv -o BatchMode=yes -o ConnectTimeout=10 \
  -o StrictHostKeyChecking=accept-new \
  "${HOST_USER}@${HOST_IP}" 'echo SSH_OK; uname -r; uptime -p' \
  > "$SSHLOG" 2>&1
RC=$?
echo "exit: $RC   full log: $SSHLOG"
echo "-- last 12 lines --"; tail -12 "$SSHLOG"

if grep -q 'SSH_OK' "$SSHLOG"; then
  verdict "WORLD A — SSH CONNECTS" \
"You have a shell, and it may be the last one you get. In this order:

  1. Give the BMC a network address. This is worth more than any diagnostic
     here: it converts every future failure from a drive to the server room
     into opening a browser. Commands are in RESUME_NEXT.md (read them there;
     do not quote that file anywhere outbound).
  2. ssh ${HOST_USER}@${HOST_IP} -t 'tmux new -A -s diag'   — survives a drop.
  3. Confirm the symptom is even real: uname -r. If it still says 6.8.0-111
     the reboot never happened and there is no kernel fault to find.
  4. Then scripts/gps3_evidence.sh, delivered by rsync + md5, run under tmux."
  exit 0
fi

# Classify the failure from the verbose log rather than making the reader hunt.
REASON="unclassified — read $SSHLOG"
grep -qi 'REMOTE HOST IDENTIFICATION HAS CHANGED\|Host key verification failed' "$SSHLOG" \
  && REASON="HOST KEY CHANGED. Verify the new fingerprint OUT OF BAND before trusting it —
a changed key on a box nobody reinstalled deserves a moment's thought. Then:
  ssh-keygen -R $HOST_IP"
grep -qi 'Connection refused' "$SSHLOG" \
  && REASON="CONNECTION REFUSED — host is up, sshd is not listening. It failed to
start after boot, or is bound to an interface that got renamed."
grep -qi 'Connection timed out\|Operation timed out' "$SSHLOG" \
  && REASON="TIMED OUT at TCP stage — firewall, or the address now belongs to
something else. The MAC check in section 2 is the discriminator."
grep -qi 'Permission denied' "$SSHLOG" \
  && REASON="AUTH failure, not network. Key/agent on the client, or
authorized_keys permissions on the server. The host is healthy."
grep -qi 'no matching host key type\|no matching key exchange\|no matching cipher' "$SSHLOG" \
  && REASON="CRYPTO POLICY MISMATCH after an upgrade. The log names the algorithm;
negotiate it explicitly rather than weakening the server."

verdict "WORLD B — PING/ARP OK, SSH DOES NOT" "$REASON"
