#!/usr/bin/env bash
# finch_diagnostics_hardening.sh — make the NEXT hang answerable.
#
# WHY THIS EXISTS
# finch has ended 7 of its last 10 boots abruptly, and no diagnosis has been
# able to say whether that is power loss, PSU failure, or a wedged kernel. The
# journal cannot tell them apart because in all three cases the machine stops
# writing before it can record anything. See docs/finch/.
#
# The one observation that looked like a discriminator -- Alt+SysRq REISUB
# doing nothing on 2026-09-07 -- turned out to be void: `kernel.sysrq` is 438,
# and both S (0x008) and B (0x040) are masked off. B is the only key whose
# effect a person could observe, and it never had permission to fire. A healthy
# kernel would have been equally silent.
#
# So this script is not about uptime. It installs the instruments that make the
# next failure legible.
#
# THE OVERRIDE TRAP, which is why the file is named 99-
# /etc/sysctl.d/10-magic-sysrq.conf on this machine asks for 176 and does not
# get it. systemd-sysctl applies files in lexical order BY FILENAME across all
# directories, and /etc beats /usr/lib only for the SAME filename. Since
# /usr/lib/sysctl.d/50-default.conf sets 0x01b6 and sorts after `10-`, the
# vendor default wins. A fix dropped in as `10-` or `50-` would read correct in
# the file and be wrong in /proc. Hence 99-.
#
# Usage:  sudo bash scripts/sudo/finch_diagnostics_hardening.sh
# Safe to re-run. Reboot required for the watchdog and panic settings.

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: run with sudo." >&2
    exit 1
fi

CONF=/etc/sysctl.d/99-finch-diagnostics.conf
say() { printf '\n=== %s\n' "$*"; }

# ---------------------------------------------------------------- pstore
# FIRST, and before changing anything: this is the one piece of evidence the
# unprivileged investigation could not reach. /sys/fs/pstore is root-only, and
# efi_pstore IS registered on this machine (EFI firmware), so a panic from a
# previous crash may be sitting here unread. It persists through firmware, so
# it survives exactly the failure that destroys everything else.
say "pstore — checking for an unread panic record"
if [ -d /sys/fs/pstore ]; then
    n=$(find /sys/fs/pstore -type f 2>/dev/null | wc -l)
    echo "  backend: $(dmesg 2>/dev/null | grep -oE 'Registered [a-z_]+ as persistent store backend' | tail -1)"
    echo "  records: $n"
    if [ "$n" -gt 0 ]; then
        echo "  *** A PANIC RECORD EXISTS. This may answer the whole question. ***"
        mkdir -p /root/pstore-capture
        for f in /sys/fs/pstore/*; do
            [ -f "$f" ] || continue
            echo "  --- $(basename "$f") ---"
            head -40 "$f" | sed 's/^/      /'
            cp -a "$f" /root/pstore-capture/ 2>/dev/null || true
        done
        echo
        echo "  Copied to /root/pstore-capture/ . These are NOT auto-cleared;"
        echo "  leave them until they have been read and committed."
    else
        echo "  Empty. No panic was captured, which is itself informative: a"
        echo "  kernel that panics writes here, so the crashes are either power"
        echo "  loss, or a hang so hard the panic path never ran."
    fi
else
    echo "  /sys/fs/pstore absent — no backend."
fi

# ---------------------------------------------------------------- sysctl
say "Writing $CONF"
cat > "$CONF" <<'EOF'
# finch diagnostics — see docs/finch/ for why each of these is here.
#
# Named 99- deliberately. /usr/lib/sysctl.d/50-default.conf sets
# kernel.sysrq = 0x01b6 (438) and systemd-sysctl applies files in lexical
# order by filename across directories, so anything sorting before 50- loses.
# /etc/sysctl.d/10-magic-sysrq.conf on this machine is the worked example: it
# asks for 176 and does not get it.

# All SysRq functions. Not a mask: the previous mask silently disabled S
# (sync) and B (reboot), which made REISUB useless as a diagnostic on
# 2026-09-07 without anyone knowing.
#
# Residual risk, stated rather than implied: anyone at the console can then
# reboot the machine or dump memory. On a laptop in a locked office, physical
# access is already total, so this trades nothing real for a working
# instrument.
kernel.sysrq = 1

# Log tasks blocked in D state for 60s (default 120). Turns a silent wedge
# into a stack trace naming what is stuck.
kernel.hung_task_timeout_secs = 60

# An oops becomes a panic, and a panic reboots after 20s. Without these an
# oops can leave the machine half-dead and silent, which is indistinguishable
# from the power loss we are trying to rule out.
kernel.panic_on_oops = 1
kernel.panic = 20

# NOT ENABLED — these are the user's call, see the script output.
# They convert a wedge into a reboot WITH a trace, which is much better
# diagnostics, but they will reboot a machine that might have recovered.
#kernel.hung_task_panic = 1
#kernel.softlockup_panic = 1
EOF
echo "  written"

sysctl -q -p "$CONF"

# ---------------------------------------------------------------- watchdog
say "Hardware watchdog (iTCO_wdt)"
if [ -e /dev/watchdog ]; then
    echo "  /dev/watchdog already present"
elif modinfo iTCO_wdt >/dev/null 2>&1; then
    modprobe iTCO_wdt 2>/dev/null || true
    if [ -e /dev/watchdog ]; then
        echo "  loaded, /dev/watchdog now present"
    else
        echo "  module loaded but no /dev/watchdog — the firmware may not"
        echo "  expose the TCO timer. Not fatal; the sysctl instruments still work."
    fi
    echo "iTCO_wdt" > /etc/modules-load.d/finch-watchdog.conf
    echo "  persisted via /etc/modules-load.d/finch-watchdog.conf"
else
    echo "  iTCO_wdt not available in this kernel"
fi

if [ -e /dev/watchdog ]; then
    say "Handing the watchdog to systemd"
    # systemd pets the device continuously. If userspace or the kernel wedges
    # for longer than RuntimeWatchdogSec, the HARDWARE resets the machine --
    # no software involvement, which is the point.
    #
    # What this buys is discrimination, not uptime: once live, a machine that
    # comes back on its own was WEDGED, and one that stays down LOST POWER.
    # That is the distinction the journal structurally cannot make.
    mkdir -p /etc/systemd/system.conf.d
    cat > /etc/systemd/system.conf.d/99-finch-watchdog.conf <<'EOF'
[Manager]
RuntimeWatchdogSec=60
RebootWatchdogSec=10min
EOF
    echo "  /etc/systemd/system.conf.d/99-finch-watchdog.conf written"
    echo "  (takes effect on reboot)"
fi

# ---------------------------------------------------------------- verify
# Read the SYSTEM, never the file just written. The two mistakes this project
# has made in as many days -- a `check-ignore` predicate read backwards, and
# 50-default.conf overriding 10-magic-sysrq.conf -- were both "the file said
# one thing, the system did another".
say "Effective values (read from the system, not the file)"
fail=0
eff_sysrq=$(sysctl -n kernel.sysrq)
printf "  kernel.sysrq                  = %s\n" "$eff_sysrq"
printf "  kernel.panic                  = %s\n" "$(sysctl -n kernel.panic)"
printf "  kernel.panic_on_oops          = %s\n" "$(sysctl -n kernel.panic_on_oops)"
printf "  kernel.hung_task_timeout_secs = %s\n" "$(sysctl -n kernel.hung_task_timeout_secs)"
printf "  RuntimeWatchdogUSec (live)    = %s\n" "$(systemctl show -p RuntimeWatchdogUSec --value)"
printf "  /dev/watchdog                 = %s\n" "$([ -e /dev/watchdog ] && echo present || echo absent)"

if [ "$eff_sysrq" != "1" ]; then
    echo
    echo "  *** FAILED: kernel.sysrq is $eff_sysrq, expected 1."
    echo "      Something later in the sysctl.d order is still overriding it."
    echo "      Find it with:  systemd-analyze cat-config sysctl.d | grep -n sysrq"
    fail=1
fi

say "Which file actually wins for sysrq"
systemd-analyze cat-config sysctl.d 2>/dev/null | grep -n "sysrq" | tail -5 | sed 's/^/  /' || true

if [ "$fail" -ne 0 ]; then
    echo
    echo "Finished WITH ERRORS — see above." >&2
    exit 1
fi

cat <<'CLOSING'

=== ONE DECISION LEFT TO YOU ===

Two settings are written but commented out in
/etc/sysctl.d/99-finch-diagnostics.conf:

    kernel.hung_task_panic = 1
    kernel.softlockup_panic = 1

They turn a wedge into a reboot that leaves a trace, instead of a machine that
sits silent until somebody walks to it. The cost is that they will reboot a
machine that might have recovered on its own.

Given 7 of the last 10 boots ended abruptly anyway, there is not much recovery
being lost. Uncomment both and re-run this script if you want them.

=== REBOOT ===

The watchdog and the panic settings need one. sysrq is live already, so REISUB
works from now on regardless.

After rebooting, confirm the watchdog actually armed:

    systemctl show -p RuntimeWatchdogUSec     # expect 1min, not 0
    ls -l /dev/watchdog

From then on the machine tells you which failure it had: back on its own means
it was wedged, still down means it lost power.
CLOSING
