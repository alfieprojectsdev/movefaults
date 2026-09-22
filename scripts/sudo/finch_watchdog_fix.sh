#!/usr/bin/env bash
# finch_watchdog_fix.sh — the watchdog did not survive the reboot. This fixes it.
#
# WHAT WENT WRONG
# finch_diagnostics_hardening.sh loaded iTCO_wdt with an explicit modprobe and
# persisted it via /etc/modules-load.d/finch-watchdog.conf. The modprobe
# worked; the persistence did not. After the 2026-09-08 10:22 reboot:
#
#     RuntimeWatchdogUSec = 1min      systemd wants to pet a watchdog
#     /dev/watchdog       = ABSENT    there is no watchdog to pet
#
# systemd-modules-load said exactly why, and then exited 0:
#
#     systemd-modules-load[325]: Module 'iTCO_wdt' is deny-listed (by kmod)
#     systemd[1]: Finished systemd-modules-load.service - Load Kernel Modules.
#
# iTCO_wdt is deny-listed by the distro in
# /usr/lib/modprobe.d/blacklist_linux-hwe-7.0_7.0.0-30-generic.conf line 26,
# along with every other watchdog driver. That is Ubuntu's default for laptops.
#
# WHY modules-load.d CANNOT WIN THIS
# A kmod deny-list cannot be un-set by a later modprobe.d file, and
# systemd-modules-load honours it even for a module named explicitly. An
# explicit `modprobe iTCO_wdt` from a shell DOES load it -- the deny-list
# governs kmod's own loading paths, not that command. Which is exactly why it
# worked when the script ran it by hand and failed at every boot since.
#
# So: a oneshot unit that runs modprobe directly, ordered before
# systemd-modules-load, rather than another config file asking kmod nicely.
#
# Usage:  sudo bash scripts/sudo/finch_watchdog_fix.sh
# Safe to re-run. No reboot needed to arm it now; the unit makes it survive.

set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run with sudo." >&2; exit 1; }

# NOTE ON `lsmod | grep -q`, WHICH THIS SCRIPT USED AND GOT WRONG
# Under `set -o pipefail` that idiom cannot report a loaded module. grep -q
# exits the instant it matches; lsmod is still writing 164 lines, takes SIGPIPE,
# and exits 141; pipefail promotes 141 to the pipeline's status, so `&& yes ||
# no` prints "no" BECAUSE the module was found. Unloaded gives status 1 and
# also prints "no" -- the check has no path to "yes". It reported `iTCO_wdt
# loaded : no` on 2026-09-09 in the same breath as `/dev/watchdog : present`
# and a kernel log line saying the driver had initialized.
# Reading /proc/modules directly has no pipe and therefore no SIGPIPE.

say() { printf '\n=== %s\n' "$*"; }

say "Before"
echo "  /dev/watchdog       : $([ -e /dev/watchdog ] && echo present || echo ABSENT)"
echo "  RuntimeWatchdogUSec : $(systemctl show -p RuntimeWatchdogUSec --value)"
echo "  iTCO_wdt loaded     : $(grep -qi '^iTCO_wdt ' /proc/modules && echo yes || echo no)"

say "Installing a oneshot unit that modprobes explicitly"
cat > /etc/systemd/system/finch-watchdog-module.service <<'EOF'
[Unit]
Description=Load iTCO_wdt despite the distro deny-list
# Ordered before systemd-modules-load purely for clarity; the point is that
# this runs /sbin/modprobe directly, which the kmod deny-list does not govern,
# rather than asking kmod to load a module it has been told to refuse.
DefaultDependencies=no
Before=systemd-modules-load.service sysinit.target
ConditionPathExists=!/dev/watchdog

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/sbin/modprobe iTCO_wdt
# Do not fail the boot if the hardware is absent -- this machine having a TCO
# timer is a fact about a 2011 QM67 chipset, not a guarantee.
SuccessExitStatus=0 1

[Install]
WantedBy=sysinit.target
EOF
systemctl daemon-reload
systemctl enable finch-watchdog-module.service >/dev/null 2>&1
echo "  finch-watchdog-module.service enabled"

# The stale config the previous script wrote. It is inert -- kmod refuses it --
# and leaving it would suggest the module is handled when it is not.
if [ -e /etc/modules-load.d/finch-watchdog.conf ]; then
    rm -f /etc/modules-load.d/finch-watchdog.conf
    echo "  removed the inert /etc/modules-load.d/finch-watchdog.conf"
fi

say "Loading it now, so the machine is protected before any reboot"
modprobe iTCO_wdt 2>/dev/null || true

say "Effective state — read from the system"
fail=0
wd=$([ -e /dev/watchdog ] && echo present || echo ABSENT)
echo "  /dev/watchdog       : $wd"
echo "  iTCO_wdt loaded     : $(grep -qi '^iTCO_wdt ' /proc/modules && echo yes || echo no)"
echo "  RuntimeWatchdogUSec : $(systemctl show -p RuntimeWatchdogUSec --value)"
journalctl -b -k --no-pager 2>/dev/null | grep -i "iTCO_wdt" | tail -2 | sed 's/^/  /'

if [ "$wd" != "present" ]; then
    echo
    echo "  *** FAILED: still no /dev/watchdog. The watchdog is NOT armed." >&2
    echo "      systemd will keep reporting RuntimeWatchdogUSec=1min while" >&2
    echo "      petting nothing, which is the state this script exists to end." >&2
    fail=1
fi

say "The wifi hook — checking, because it is still outstanding"
HOOK=/etc/NetworkManager/dispatcher.d/99-wifi-auto-toggle.sh
if [ -x "$HOOK" ]; then
    echo "  STILL ACTIVE. scripts/sudo/wifi_keep_both_networks.sh has not been run."
    echo "  It kills the wifi radio whenever ethernet comes up, which is why"
    echo "  wifi was down at login after the reboot."
    echo "  Run:  sudo bash /home/finch/wifi_fix.sh"
else
    echo "  already disabled"
fi

[ "$fail" -eq 0 ] || exit 1

cat <<'CLOSING'

=== VERIFY AFTER THE NEXT REBOOT ===

This is the check that was missed last time -- the watchdog was confirmed
working in the session that installed it, and not after a boot:

    ls -l /dev/watchdog                        # must exist
    systemctl show -p RuntimeWatchdogUSec      # 1min
    systemctl is-active finch-watchdog-module

Only then does the machine actually discriminate its own failures: back on its
own means WEDGED, still down means POWER.
CLOSING
