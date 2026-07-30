#!/usr/bin/env bash
# smartd_setup.sh — point smartd at the 16 PERC H750 member drives on gps3
#
# THE PROBLEM: the stock /etc/smartd.conf uses `DEVICESCAN`, which enumerates
# block devices the kernel can see. The PERC hides its members — the kernel
# sees only the virtual disk — so smartd runs happily while monitoring
# *nothing*. On a 16-wide RAID 5 with no hot spare, early warning of a failing
# drive is the primary defense, so this is worth fixing.
#
# THE FIX: explicit per-member lines using the `-d megaraid,N` transport,
# which tunnels SMART through the megaraid_sas driver. Members were enumerated
# by raid_enum.sh (device IDs 0-15, all Toshiba AL15SEB24EQY 2.4 TB SAS).
#
# Also installs a run.d hook that logs alerts to syslog and a file, because
# there is no MTA on this box — the stock 10mail hook would fail silently.
#
# Idempotent and re-runnable. Validates the new config with `smartd -q onecheck`
# BEFORE installing it, so a broken config can never take out the service.
#
# Usage:  sudo ./smartd_setup.sh > ~/smartd-setup.log 2>&1
#
# NOT using `set -e`: smartd and systemctl return non-zero in situations that
# are informational here, and an abort mid-way could leave a half-written
# config. Each step is checked explicitly instead.
set -uo pipefail

CONF="/etc/smartd.conf"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="${CONF}.bak-${STAMP}"
NEWCONF="$(mktemp)"
HOOK="/etc/smartmontools/run.d/20log"
ALERTLOG="/var/log/smartd-alerts.log"
NMEMBERS=16          # device IDs 0..15, per raid_enum.sh
VD="/dev/sda"

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mERROR:\033[0m %s\n' "$*" >&2; rm -f "$NEWCONF"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root (use: sudo $0)"
command -v smartd >/dev/null 2>&1 || die "smartd not installed — run raid_enum.sh first"

# ── 1. Sanity: do the members still answer? ───────────────────────────────────
step "1. Confirm members respond before writing any config"
ALIVE=0
MISSING=""
FIRST_RC=""
for id in $(seq 0 $((NMEMBERS - 1))); do
    # Capture into a variable FIRST, then grep it — do not pipe smartctl
    # straight into `grep -q`.
    #
    # WHY (measured 2026-07-30, exit codes confirmed on this box). The piped form
    #     if smartctl -i -d "megaraid,$id" "$VD" 2>/dev/null \
    #        | grep -qiE '^(Device Model|Product|Vendor):'; then
    # reported 0 of 16 members alive on an array raid_enum.sh had just
    # enumerated cleanly. The chain is:
    #
    #   1. `grep -q` exits the instant it matches — "Vendor:" is line 5 of
    #      smartctl -i output.
    #   2. smartctl is nowhere near done. It goes on to issue further SCSI
    #      inquiries for Rotation Rate, Form Factor, Logical Unit id, SMART
    #      support (lines 6-26). Its next write hits a pipe with no reader
    #      and it takes SIGPIPE -> 141.
    #   3. `set -o pipefail` makes 141 the pipeline's status, so the `if` is
    #      false even though grep matched. Every member looks dead.
    #
    # Measured: piped form = 141; identical pipeline with pipefail off = 0;
    # capture form = smartctl 0, grep 0.
    #
    # The general rule, worth carrying elsewhere: under `pipefail`, `slow_cmd |
    # grep -q` is a landmine whenever slow_cmd keeps writing after the match.
    # It will NOT reproduce with a fast writer (echo, seq, cat of a small file)
    # because the writer empties into the 64 KB pipe buffer and exits before
    # grep can close the read end — there is no second write to fault on. That
    # is exactly why an initial attempt to reproduce this came back clean.
    #
    # Do not "simplify" this back into a pipe. raid_enum.sh uses the same
    # capture-first shape, which is why it worked all along.
    #
    # The per-id diagnostic below exists so a future failure says which member
    # and with what status, instead of just a bare count.
    out=$(smartctl -i -d "megaraid,$id" "$VD" 2>/dev/null)
    rc=$?
    [ -z "$FIRST_RC" ] && FIRST_RC="$rc"
    if printf '%s\n' "$out" | grep -qiE '^(Device Model|Model Number|Product|Vendor):'; then
        ALIVE=$((ALIVE + 1))
    else
        MISSING="$MISSING $id"
        printf '  id %-2s no identify data (smartctl exit %s)\n' "$id" "$rc"
    fi
done
printf '  %s of %s expected members answered\n' "$ALIVE" "$NMEMBERS"
printf '  smartctl exit status on member 0: %s  (non-zero here is normal — it is\n' "$FIRST_RC"
printf '  a bitmask, not a failure; see the comment above this check)\n'
[ -n "$MISSING" ] && warn "did not answer:$MISSING"
[ "$ALIVE" -eq "$NMEMBERS" ] || die "expected $NMEMBERS members, got $ALIVE.
Re-run raid_enum.sh — the array layout may have changed, which is itself
worth investigating before configuring monitoring around a stale assumption."
ok "all $NMEMBERS members reachable over the megaraid transport"

# ── 2. Alert hook (no MTA on this box) ────────────────────────────────────────
step "2. Install log-based alert hook"
cat > "$HOOK" <<'HOOKEOF'
#!/bin/sh
# Log smartd warnings to syslog and a dedicated file.
#
# gps3 has no MTA, so the stock 10mail hook silently discards alerts (it exits
# 1 when /usr/bin/mail is absent). This runs alongside it via run-parts and
# guarantees the warning is recorded where a human can actually find it.
#
# HOOK CONTRACT: smartd-runner spools the message to a temp file and invokes
# each run.d script with that FILE PATH as $1 (see /usr/share/smartmontools/
# smartd-runner). The message does NOT arrive on stdin. $2..$4 are the mail
# recipient args. smartd exports SMARTD_* into the environment.
MSGFILE="$1"
ALERTLOG=/var/log/smartd-alerts.log

{
    echo "=== $(date -Is) ==="
    echo "device   : ${SMARTD_DEVICE:-unknown} ${SMARTD_DEVICETYPE:-}"
    echo "failtype : ${SMARTD_FAILTYPE:-unknown}"
    if [ -n "$MSGFILE" ] && [ -r "$MSGFILE" ]; then
        cat "$MSGFILE"
    else
        echo "(no message file passed as \$1 — check smartd-runner)"
    fi
    echo
} >> "$ALERTLOG" 2>/dev/null

logger -t smartd-alert -p daemon.crit \
    "SMART ALERT on ${SMARTD_DEVICE:-?} ${SMARTD_DEVICETYPE:-}: ${SMARTD_FAILTYPE:-check} — details in $ALERTLOG"

exit 0
HOOKEOF
chmod 755 "$HOOK" || die "could not chmod $HOOK"
touch "$ALERTLOG" && chmod 640 "$ALERTLOG"
ok "hook installed: $HOOK"
ok "alert log     : $ALERTLOG"

# ── 3. Generate the new config ────────────────────────────────────────────────
step "3. Generate config for $NMEMBERS members"

{
cat <<HEADEOF
# /etc/smartd.conf — generated by smartd_setup.sh on ${STAMP}
#
# The 16 physical members of the PERC H750 RAID 5 array are invisible to the
# kernel (it sees only the virtual disk ${VD}), so DEVICESCAN finds nothing.
# Each member is addressed explicitly through the megaraid_sas SMART tunnel.
#
# Array: 16 x Toshiba AL15SEB24EQY 2.4 TB 10K SAS, RAID 5 (15 data + 1 parity).
# No hot spare. A single drive failure is survivable; a second failure during
# the rebuild is not. That is why this monitoring exists.
#
# Directives used:
#   -a         monitor health, error log and self-test log
#              (for SAS this is -H -l error -l selftest; the ATA-attribute
#               parts of -a do not apply and are ignored)
#   -W 4,50,60 log temperature changes of 4C; warn at 50C; critical at 60C
#   -s S/../.././HH   short self-test daily at hour HH, staggered one drive
#              per hour so no two members test at the same time
#   -m / -M    hand the alert to run-parts (/etc/smartmontools/run.d/),
#              which includes the 20log hook installed alongside this file
#
# Deliberately NOT scheduling long self-tests: the PERC runs its own patrol
# read for surface scanning, and 16 concurrent long tests would contend with
# it. To add them anyway, append |L/../../6/HH to the -s expression (long test
# Saturdays) once you have confirmed patrol read is disabled.

HEADEOF

for id in $(seq 0 $((NMEMBERS - 1))); do
    printf '%s -d megaraid,%s -a -W 4,50,60 -s S/../.././%02d -m root -M exec /usr/share/smartmontools/smartd-runner\n' \
        "$VD" "$id" "$id"
done
} > "$NEWCONF"

printf '  %s device lines written\n' "$(grep -c '^/dev/' "$NEWCONF")"
echo
echo "  first two lines:"
grep '^/dev/' "$NEWCONF" | head -2 | sed 's/^/    /'

# ── 4. Validate BEFORE touching the live config ───────────────────────────────
step "4. Validate the new config (smartd -q onecheck)"
echo "  This parses the config and runs one full check pass, then exits."
echo "  Nothing is installed unless every member registers."
echo
VALIDATE_OUT="$(smartd -q onecheck -c "$NEWCONF" 2>&1)"
VALIDATE_RC=$?

echo "$VALIDATE_OUT" | grep -iE 'Device:|Monitoring|Unable|error|fail|cannot' | sed 's/^/    /' | head -40

# Positive check, not just "no scary strings": count the distinct
# megaraid_disk_NN identifiers smartd actually opened. Absence of an error
# message is not evidence that anything registered.
REGISTERED=$(printf '%s\n' "$VALIDATE_OUT" \
             | grep -oE 'megaraid_disk_[0-9]+' | sort -u | wc -l)
printf '  distinct members smartd opened: %s of %s\n' "$REGISTERED" "$NMEMBERS"

if printf '%s\n' "$VALIDATE_OUT" | grep -qiE 'unable to register|cannot open|no devices to monitor'; then
    echo
    warn "validation reported problems — NOT installing. Full output:"
    printf '%s\n' "$VALIDATE_OUT" | sed 's/^/    /'
    die "config not installed; live smartd is untouched"
fi
if [ "$REGISTERED" -lt "$NMEMBERS" ]; then
    echo
    warn "only $REGISTERED of $NMEMBERS members registered — NOT installing."
    warn "Full validation output:"
    printf '%s\n' "$VALIDATE_OUT" | sed 's/^/    /'
    die "config not installed; live smartd is untouched"
fi
echo
ok "all $NMEMBERS members registered (smartd exit $VALIDATE_RC)"

# ── 5. Install ────────────────────────────────────────────────────────────────
step "5. Install config"
if [ -f "$CONF" ]; then
    cp -a "$CONF" "$BACKUP" || die "could not back up $CONF"
    ok "backed up existing config → $BACKUP"
fi
cat "$NEWCONF" > "$CONF" || die "could not write $CONF"
chmod 644 "$CONF"
rm -f "$NEWCONF"
ok "installed $CONF"

# ── 6. Restart and verify ─────────────────────────────────────────────────────
step "6. Restart smartd"
systemctl restart smartmontools 2>&1 | sed 's/^/    /'
sleep 2
if systemctl is-active --quiet smartmontools; then
    ok "smartmontools is active"
else
    warn "service is not active — restoring the previous config"
    [ -f "$BACKUP" ] && cp -a "$BACKUP" "$CONF" && systemctl restart smartmontools
    die "smartd failed to start; previous config restored from $BACKUP"
fi
systemctl is-enabled smartmontools >/dev/null 2>&1 || systemctl enable smartmontools >/dev/null 2>&1
ok "enabled at boot"

step "7. Confirm it is actually watching all $NMEMBERS"
sleep 3
WATCHING=$(journalctl -u smartmontools --since "-2 min" --no-pager 2>/dev/null \
           | grep -ciE 'Device: /dev/sda \[megaraid_disk_[0-9]+\].*(monitoring|SMART)')
printf '  members mentioned in the last 2 min of the service journal: %s\n' "$WATCHING"
echo
journalctl -u smartmontools --since "-2 min" --no-pager 2>/dev/null \
    | grep -iE 'megaraid_disk|Monitoring [0-9]+ (ATA|SCSI|NVMe)|device(s)? to monitor' \
    | tail -25 | sed 's/^/    /'

if [ "$WATCHING" -ge "$NMEMBERS" ]; then
    echo
    ok "all $NMEMBERS members are being monitored"
else
    echo
    warn "journal shows $WATCHING references; expected at least $NMEMBERS."
    warn "Not necessarily broken — log verbosity varies. Confirm with:"
    warn "  sudo smartd -q onecheck 2>&1 | grep -c 'megaraid_disk'"
fi

step "Done"
cat <<DONEEOF
  Config    : $CONF   (previous at $BACKUP)
  Alert hook: $HOOK
  Alert log : $ALERTLOG

  Check status any time:
      systemctl status smartmontools
      sudo smartctl -H -d megaraid,0 /dev/sda        # spot-check one member
      journalctl -u smartmontools --since today

  Test the alert path end to end (writes a fake alert, changes nothing else).
  Note the hook takes a FILE as \$1, not stdin:
      echo "test alert body" | sudo tee /tmp/smartd-test.msg >/dev/null
      sudo env SMARTD_DEVICE=/dev/sda SMARTD_DEVICETYPE=megaraid,0 \\
               SMARTD_FAILTYPE=TEST $HOOK /tmp/smartd-test.msg
      sudo tail $ALERTLOG
      sudo rm -f /tmp/smartd-test.msg

  Note: the stock 10mail hook exits 1 on every alert because there is no MTA,
  so run-parts will log "10mail exited with return code 1" alongside each real
  warning. Harmless. Silence it with:  sudo chmod -x /etc/smartmontools/run.d/10mail
  (or leave it, so alerts start mailing if an MTA is ever installed).

  To revert entirely:
      sudo cp -a $BACKUP $CONF && sudo systemctl restart smartmontools
      sudo rm -f $HOOK
DONEEOF
