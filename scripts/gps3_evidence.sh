#!/usr/bin/env bash
# gps3_evidence.sh — run ON gps3 once SSH works (WORLD A). Collects evidence
# for the "SSH drops after the kernel update" question, in one pass, in a form
# that survives its own session dying.
#
# Implements §4 of gps3-ssh-diagnostic-plan-v2. Read-only: it changes nothing,
# starts nothing, and restarts nothing. Diagnosis first — every remediation in
# that plan is a separate, deliberate decision, and two of them require a
# reboot this machine currently cannot recover from.
#
# DELIVERY (repo relay protocol — file, not paste, so the far side can re-read
# and diff it):
#
#     rsync -av scripts/gps3_evidence.sh gps3@192.168.48.98:~/
#     ssh gps3@192.168.48.98 'md5sum ~/gps3_evidence.sh'    # compare to local
#
# RUN IT SO IT SURVIVES A DROP — the reported symptom is the session dying:
#
#     ssh gps3@192.168.48.98 -t 'tmux new -A -s diag'
#     sudo bash ~/gps3_evidence.sh
#   or fully detached:
#     sudo nohup bash ~/gps3_evidence.sh > /var/tmp/gps3-evidence.run 2>&1 &
#
# Retrieve the report with rsync from a fresh session.
#
# TWO THINGS THIS SCRIPT ASSUMES NOTHING ABOUT, deliberately:
#   * The Bernese environment. LOADGPS.setvar is sourced by ~/.bashrc for
#     INTERACTIVE shells only, so `ssh host 'cmd'` has no $P/$D/$U. Absolute
#     paths throughout; nothing is sourced.
#   * The interface name. eno4 is what SHOULD carry the address. Whether it
#     still exists under that name is one of the things being tested.

set -uo pipefail    # not -e: a failing probe must never end an evidence run
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

IFACE_EXPECTED="${GPS3_IFACE:-eno4}"
ADDR_EXPECTED="${GPS3_ADDR:-192.168.48.98}"
OUT_DIR="${1:-/var/tmp}"
STAMP="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo unknown)"
REPORT="${OUT_DIR}/gps3-evidence-${STAMP}.txt"

exec > >(tee "$REPORT") 2>&1

sec(){ printf '\n\n===== %s %s\n' "$1" "$(printf '=%.0s' $(seq 1 $((60 - ${#1}))))"; }
# eval on "$*" rather than "$@": these are command STRINGS with pipes and
# globs that must be re-parsed, not argument vectors.
run(){ printf '\n--- $ %s\n' "$*"; eval "$*" 2>&1 | sed 's/^/  /' || echo "  (failed: $*)"; }
IS_ROOT=0; [ "$(id -u)" = "0" ] && IS_ROOT=1

printf 'gps3 evidence — %s\nhost: %s\nreport: %s\n' "$(date)" "$(hostname)" "$REPORT"
[ "$IS_ROOT" = 1 ] || printf '\nWARNING: not root. auth.log, dmesg and conntrack will be empty.\n         Re-run with sudo — those are the highest-value sections.\n'

# ---------------------------------------------------------------------------
sec "0. DID THE REBOOT EVEN HAPPEN"
# The premise under test. If this still says 6.8.0-111 then the kernel upgrade
# never took effect and there is no kernel-induced fault to diagnose — the
# question becomes why GRUB is not booting the new one.
run "uname -r"
run "uptime -p; uptime -s"
run "last reboot | head -5"
echo
echo "  6.8.0-111-generic -> the reboot did NOT happen. Stop; check GRUB default."
echo "  6.8.0-136/-137    -> it did. Continue."
run "ls -1 /boot/vmlinuz-*"
run "grep -E '^GRUB_DEFAULT|^GRUB_TIMEOUT' /etc/default/grub"

# ---------------------------------------------------------------------------
sec "1. INTERFACE NAMING — the silent killer"
# A kernel upgrade can reshuffle predictable interface names. Netplan then
# configures a device that no longer exists: the box boots clean, has no
# address, and with no console nobody can see why.
run "ip -br link"
run "ip -br addr"
run "ip route"
IFACE_NOW="$(ip route get "$ADDR_EXPECTED" 2>/dev/null | grep -oE 'dev [^ ]+' | awk '{print $2}')"
printf '\n  expected: %s   actually carrying %s: %s\n' \
  "$IFACE_EXPECTED" "$ADDR_EXPECTED" "${IFACE_NOW:-NONE}"
if [ -n "$IFACE_NOW" ] && [ "$IFACE_NOW" != "$IFACE_EXPECTED" ]; then
  echo "  !!! INTERFACE MOVED — netplan almost certainly still names $IFACE_EXPECTED"
fi
ip link show "$IFACE_EXPECTED" >/dev/null 2>&1 \
  || echo "  !!! $IFACE_EXPECTED DOES NOT EXIST. This is the rename scenario."
run "ls -la /sys/class/net/"
run "cat /etc/netplan/*.yaml"
[ "$IS_ROOT" = 1 ] && run "dmesg -T | grep -iE 'renamed|eno[0-9]|ens[0-9]|eth[0-9]' | tail -20"

# ---------------------------------------------------------------------------
sec "2. WHICH DRIVER IS ACTUALLY IN PLAY"
# Plan v1 spent effort on a bnxt_en theory. That is only relevant if eno4 is a
# Broadcom NetXtreme-E port — the np0/np1 suffixes appear on eno1/eno2, not
# eno4. Settle it here before chasing any vendor bug report.
run "ethtool -i $IFACE_EXPECTED"
run "lspci | grep -i ethernet"
echo
echo "  Driver NOT bnxt_en -> discard the entire bnxt_en thread from plan v1."

# ---------------------------------------------------------------------------
sec "3. WHY DID THE SESSION END — highest-information single artifact"
if [ "$IS_ROOT" = 1 ]; then
  run "grep -iE 'sshd' /var/log/auth.log | grep -iE 'disconnect|closed|timeout|Broken pipe|Connection reset' | tail -40"
  run "journalctl -u ssh --no-pager -n 60"
else
  echo "  SKIPPED — needs root:  sudo grep sshd /var/log/auth.log | grep -i disconnect"
fi
echo
echo "  'Connection closed by <ip>'      -> the CLIENT went away (wifi, Doze, NAT)"
echo "  'Timeout, client not responding' -> the SERVER gave up on keepalives"
echo "  nothing logged at all            -> the path dropped it; neither end noticed"

# ---------------------------------------------------------------------------
sec "4. SSHD EFFECTIVE CONFIG"
# Keepalives are the highest-probability fix, and their absence is the default.
run "sshd -T 2>/dev/null | grep -iE 'clientalive|tcpkeepalive|logingracetime|usedns'"
echo
echo "  ClientAliveInterval 0 is the default and means NO server-side keepalive."
echo "  Note: ClientAliveCountMax=0 DISABLES the disconnect in current OpenSSH"
echo "  rather than making it immediate. Use interval 30 / countmax 6."

# ---------------------------------------------------------------------------
sec "5. LINK STABILITY AND NIC POWER MANAGEMENT"
run "ip -s link show $IFACE_EXPECTED"
echo "  (errors/dropped climbing over time is the signal, not the absolute count)"
run "ethtool $IFACE_EXPECTED | grep -iE 'speed|duplex|link detected'"
run "ethtool --show-eee $IFACE_EXPECTED"
run "ethtool -k $IFACE_EXPECTED | grep -iE 'tso|gso|gro|lro|rx-checksum'"
[ "$IS_ROOT" = 1 ] && run "dmesg -T | grep -iE 'link is (up|down)|NIC Link|tx timeout|reset adapter|hang' | tail -25"

# ---------------------------------------------------------------------------
sec "6. PCIe ASPM"
# pcie_aspm=off means "leave BIOS config untouched", NOT "force off".
# pcie_aspm.policy=performance is what actually forces links out of L1.
run "cat /proc/cmdline"
run "cat /sys/module/pcie_aspm/parameters/policy 2>/dev/null"
echo "  Changing this needs a reboot. With no out-of-band console, defer it"
echo "  until the BMC has an address — see the plan's remediation table."

# ---------------------------------------------------------------------------
sec "7. SUSPEND / LOGIND"
run "systemctl status systemd-logind --no-pager | head -12"
run "grep -iE '^#?(IdleAction|IdleActionSec)' /etc/systemd/logind.conf"
[ "$IS_ROOT" = 1 ] && run "journalctl -b | grep -iE 'PM: suspend|Freezing|suspend entry' | tail -10"
echo "  Headless 24.04 with no display manager: expect nothing here. Only act"
echo "  on an actual 'PM: suspend entry'."

# ---------------------------------------------------------------------------
sec "8. THE nofail TRAP — four volumes expected"
# Unrelated to SSH, but this reboot is the first real test of the July fstab
# rewrite and the failure is silent: box boots clean, logins work, data absent.
run "df -h | grep -E 'gnss-archive|GPSDATA|GPSWORK|eil-data|Filesystem'"
run "findmnt --verify --verbose 2>&1 | tail -15"
run "grep -v '^#' /etc/fstab"
run "systemctl --failed --no-pager"
[ "$IS_ROOT" = 1 ] && run "journalctl -b | grep -iE 'mount|fstab|nofail|dependency failed' | tail -30"

# ---------------------------------------------------------------------------
sec "9. WHAT ELSE CHANGED IN THAT UPGRADE"
# openssh-server, systemd and netplan in the same transaction are as plausible
# as the kernel, and much easier to check than to theorise about.
run "grep -hE ' (upgrade|install) ' /var/log/dpkg.log /var/log/dpkg.log.1 2>/dev/null | grep -iE 'linux-image|linux-modules|openssh|systemd|netplan|libc6' | tail -30"
run "zgrep -hE ' (upgrade|install) ' /var/log/dpkg.log.*.gz 2>/dev/null | grep -iE 'linux-image|openssh|systemd|netplan' | tail -15"

# ---------------------------------------------------------------------------
sec "10. CONNTRACK / FIREWALL ON THIS HOST"
if [ "$IS_ROOT" = 1 ]; then
  run "conntrack -L 2>/dev/null | grep -c . || echo 'conntrack tool absent'"
  run "sysctl net.netfilter.nf_conntrack_tcp_timeout_established 2>/dev/null"
  run "ufw status 2>/dev/null | head -5"
  run "nft list ruleset 2>/dev/null | head -20"
else
  echo "  SKIPPED — needs root."
fi
echo "  A 300s established-flow timeout on intermediate gear is a documented"
echo "  cause of exactly this symptom, and it is NOT visible from this host."

# ---------------------------------------------------------------------------
sec "11. BERNESE — is the work intact"
BV=/home/gps3/BERN54/LOADGPS.setvar
if [ -r "$BV" ]; then
  # Sourced in a SUBSHELL so this script's environment stays clean.
  # Path is runtime-determined by design; nothing to follow statically.
  # shellcheck disable=SC1090
  ( . "$BV" >/dev/null 2>&1
    # $P/$D/$S/$U here are literal labels for the reader, not expansions.
    # shellcheck disable=SC2016
    printf '  $P=%s\n  $D=%s\n  $S=%s\n  $U=%s\n' \
      "${P:-unset}" "${D:-unset}" "${S:-unset}" "${U:-unset}"
    printf '  LUZON 2025 solutions: %s (expect 30)\n' \
      "$(find "${S:-/nonexistent}/LUZON/2025/SOL" -name 'FIN_2025*.SNX.gz' 2>/dev/null | wc -l)" )
else
  echo "  $BV unreadable — wrong user, or GPSDATA did not mount (see section 8)."
fi

# ---------------------------------------------------------------------------
sec "12. NEXT"
cat <<'GUIDE'
Retrieve this report, then decide. Reading order, most decisive first:

  §0   still 6.8.0-111?          -> no kernel fault exists. Check GRUB instead.
  §1   eno4 missing or moved?    -> that is the whole answer. Fix netplan.
  §3   what auth.log says        -> splits client / server / silent-path.
  §2   driver not bnxt_en?       -> discard plan v1's Broadcom thread entirely.
  §8   fewer than four mounts?   -> unrelated to SSH, and more urgent.

DO NOT remediate from this script. Two of the candidate fixes need a reboot,
and this machine has no out-of-band console to recover one. The first action
in WORLD A is giving the BMC an address; everything else waits behind it.
GUIDE

printf '\nreport written to: %s\n' "$REPORT"
