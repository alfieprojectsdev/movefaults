#!/usr/bin/env bash
# gps3_console_triage.sh — what to run at the R740 console when it is off the network.
#
# WHY THIS EXISTS
# ---------------
# On 2026-08-24, from the T420 on the PHIVOLCS WLAN (192.168.48.124), gps3 at
# 192.168.48.98 was ARP-FAILED while thirteen other hosts on the same /24
# answered — including 192.168.48.99, the file server. So the segment is
# reachable and gps3 specifically is not on it, under any address: no live MAC
# matched its documented NICs (e4:3d:1a:*) or its BMC (b0:7b:25:fe:2c:38).
#
# iDRAC has never been given a network address, so there is no out-of-band
# console. That makes this a physical trip, and this script is what to run when
# you get there.
#
# DESIGN CONSTRAINTS, because of where it runs
# --------------------------------------------
#   * No network. Every check is local.
#   * No dependencies beyond coreutils, util-linux, systemd. No Python, no pip,
#     no repo checkout required — copy this one file on a USB stick, or retype
#     the sections you need.
#   * Read-only. It changes nothing. Diagnosis first; fixes are a decision to
#     make with the output in hand, not something to automate blind.
#   * Writes a timestamped report next to itself so it can be carried back.
#
# USAGE
#   bash gps3_console_triage.sh              # report to stdout and ./gps3-triage-<stamp>.txt
#   bash gps3_console_triage.sh /mnt/usb     # write the report somewhere else
#
# Some checks need root and are skipped without it — the report says which.
# Re-run with sudo if you can; the unprivileged run is still worth having.

set -uo pipefail    # deliberately NOT -e: a failing check must not end the run

OUT_DIR="${1:-$(dirname "$0")}"
STAMP="$(date +%Y%m%d-%H%M%S 2>/dev/null || echo unknown)"
REPORT="${OUT_DIR}/gps3-triage-${STAMP}.txt"

# Everything below goes to the terminal AND the report.
exec > >(tee "$REPORT") 2>&1

rule() { printf '\n=== %s %s\n' "$1" "$(printf '=%.0s' $(seq 1 $((66 - ${#1}))))"; }
have() { command -v "$1" >/dev/null 2>&1; }
IS_ROOT=0; [ "$(id -u 2>/dev/null)" = "0" ] && IS_ROOT=1

printf 'gps3 console triage — %s\n' "$(date 2>/dev/null)"
printf 'report: %s\n' "$REPORT"
[ "$IS_ROOT" = 1 ] || printf '\nNOTE: not running as root. Privileged checks are skipped and marked.\n'

# ---------------------------------------------------------------------------
rule "1. IDENTITY AND UPTIME"
# Answers the first question: did it reboot, and into what?
printf 'hostname : %s\n' "$(hostname 2>/dev/null)"
printf 'kernel   : %s\n' "$(uname -r 2>/dev/null)"
printf 'uptime   : %s\n' "$(uptime -p 2>/dev/null || uptime 2>/dev/null)"
printf 'booted   : %s\n' "$(uptime -s 2>/dev/null)"
echo
echo "Expected: 6.8.0-137-generic if the pending reboot happened."
echo "6.8.0-111-generic means it booted the OLD kernel — the machine is fine,"
echo "it simply did not take. Check the GRUB default before trying again."
echo "Installed kernels:"
ls -1 /boot/vmlinuz-* 2>/dev/null | sed 's|.*/vmlinuz-|  |' || echo "  (cannot list /boot)"

# ---------------------------------------------------------------------------
rule "2. NETWORK — the reason for this trip"
# gps3 was absent from the subnet. Establish whether the interface is down,
# unconfigured, or configured-but-unplugged.
if have ip; then
  echo "-- links --"; ip -br link 2>/dev/null
  echo; echo "-- addresses --"; ip -br addr 2>/dev/null
  echo; echo "-- routes --"; ip route 2>/dev/null
else
  ifconfig -a 2>/dev/null; route -n 2>/dev/null
fi
echo
echo "Expected: eno4 UP carrying 192.168.48.98/24."
echo "  NO-CARRIER      -> cable unplugged, or the switch port is dead"
echo "  DOWN            -> interface not brought up; check netplan/NM below"
echo "  wrong/no address-> DHCP or static config changed underneath it"
echo "  eno4 missing    -> interface RENAMED. A kernel upgrade can reshuffle"
echo "                     predictable names; the other three NICs are"
echo "                     eno1np0/eno2np1/eno3 and were down by design."
echo
echo "-- netplan / NetworkManager config (names only) --"
ls -1 /etc/netplan/*.yaml 2>/dev/null || echo "  no /etc/netplan/*.yaml"
have nmcli && nmcli -t -f NAME,DEVICE,STATE con show 2>/dev/null | head -10

# ---------------------------------------------------------------------------
rule "3. DATA VOLUMES — the silent failure"
# Every data volume is fstab'd `nofail`, so the machine boots clean and looks
# healthy with the data simply absent. Four lines expected.
df -h 2>/dev/null | grep -E 'gnss-archive|GPSDATA|GPSWORK|eil-data|Filesystem' \
  || echo "  none of the four data mounts are present"
echo
echo "Expected FOUR mounts:"
echo "  /srv/gnss-archive   20T   legacy archive, datapool, fixity manifests"
echo "  /home/gps3/GPSDATA  4.0T  DATAPOOL, CAMPAIGN54, SAVEDISK"
echo "  /home/gps3/GPSWORK  1.0T  BPE scratch (\$T)"
echo "  /srv/eil-data       —     separate project"
echo
echo "-- fstab sanity --"
have findmnt && findmnt --verify --verbose 2>/dev/null | tail -20 || echo "  findmnt unavailable"
echo
echo "-- block devices --"
have lsblk && lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT 2>/dev/null | head -30
echo
echo "A missing volume with healthy disks is usually a UUID mismatch — compare"
echo "the UUIDs above against /etc/fstab. A missing volume WITH I/O errors in"
echo "section 5 is a hardware problem: stop, and check the array before"
echo "mounting anything read-write."

# ---------------------------------------------------------------------------
rule "4. RAID / DISK HEALTH"
# 16 x 2.4TB SAS in RAID 5 behind a PERC, no hot spare. smartd cannot see
# through the controller with a stock DEVICESCAN config.
if [ "$IS_ROOT" = 1 ] && have smartctl; then
  echo "-- devices smartctl can see --"
  smartctl --scan 2>/dev/null | head -20
  printf 'count: %s (expect 16 behind the PERC)\n' "$(smartctl --scan 2>/dev/null | wc -l)"
  echo
  echo "-- per-member health (first 4 of 16) --"
  for i in 0 1 2 3; do
    printf '  slot %s: ' "$i"
    smartctl -d "megaraid,$i" -H /dev/sda 2>/dev/null \
      | grep -iE 'result|health' | head -1 || echo "unreadable"
  done
else
  echo "SKIPPED — needs root and smartmontools."
  echo "  sudo smartctl --scan            # expect 16 lines"
  echo "  sudo smartctl -d megaraid,N -H /dev/sda   # N = 0..15"
fi
echo
echo "-- smartd service --"
systemctl is-active smartd 2>/dev/null || echo "  smartd not active"
echo "NOTE: 'active' is not coverage. A stock DEVICESCAN config sees ZERO"
echo "drives behind a PERC while reporting itself perfectly healthy."
echo
echo "-- recent alerts --"
tail -5 /var/log/smartd-alerts.log 2>/dev/null || echo "  no /var/log/smartd-alerts.log entries"

# ---------------------------------------------------------------------------
rule "5. ERRORS WORTH SEEING"
if [ "$IS_ROOT" = 1 ]; then
  echo "-- boot-time failures --"
  systemctl --failed --no-pager 2>/dev/null | head -15
  echo
  echo "-- storage / filesystem errors this boot --"
  dmesg 2>/dev/null | grep -iE 'I/O error|xfs.*(error|corrupt)|megaraid|sd [a-z]+:.*error' \
    | tail -15 || echo "  none"
  echo
  echo "-- link state changes (did the NIC flap?) --"
  dmesg 2>/dev/null | grep -iE 'link is (up|down)|NIC Link' | tail -10 || echo "  none"
else
  echo "SKIPPED — needs root (dmesg_restrict=1 on this host)."
  echo "  sudo systemctl --failed"
  echo "  sudo dmesg | grep -iE 'I/O error|xfs|megaraid|link is'"
fi

# ---------------------------------------------------------------------------
rule "6. BERNESE — is the work still there"
BERN_VAR="/home/gps3/BERN54/LOADGPS.setvar"
if [ -r "$BERN_VAR" ]; then
  echo "LOADGPS.setvar present."
  # Sourced by ~/.bashrc for INTERACTIVE shells only, so a script must do it
  # explicitly — this is a documented trap.
  # shellcheck disable=SC1090
  . "$BERN_VAR" >/dev/null 2>&1
  printf '  $P = %s\n  $D = %s\n  $S = %s\n  $U = %s\n' \
    "${P:-unset}" "${D:-unset}" "${S:-unset}" "${U:-unset}"
  echo
  n=$(ls "${S:-/nonexistent}"/LUZON/2025/SOL/FIN_2025*.SNX.gz 2>/dev/null | wc -l)
  printf '  LUZON 2025 solutions: %s (expect 30)\n' "$n"
else
  echo "  $BERN_VAR not readable — either not this user, or GPSDATA is not mounted."
fi

# ---------------------------------------------------------------------------
rule "7. WHAT TO DO WITH THIS"
cat <<'GUIDE'
Take the report file back with you. The decision tree, shortest first:

  eno4 NO-CARRIER          reseat the cable, check the switch port. Nothing
                           is wrong with the machine.
  eno4 DOWN or no address  `sudo ip link set eno4 up`, then check
                           /etc/netplan/*.yaml still names eno4.
  eno4 missing entirely    the interface was renamed by the kernel upgrade.
                           Find the new name in section 2 and update netplan.
  machine was powered off  note WHY before powering on — an unexplained
                           power-off in a server room is its own finding.
  fewer than four mounts   do NOT start work. Diagnose section 3 first.
  I/O errors present       stop. Check the array before anything writes.

WHILE YOU ARE THERE, if the machine is otherwise healthy: give iDRAC a network
address. Its absence is why this trip was necessary at all, and the commands
are in RESUME_NEXT.md. Change the default password and the SNMP community
string before it touches the network — an unprotected BMC is a standard target
and this one has full power and console control.
GUIDE

rule "END"
printf 'report written to: %s\n' "$REPORT"
