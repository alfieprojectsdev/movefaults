#!/usr/bin/env bash
# gps3_no_suspend.sh -- stop this server suspending itself.
#
#   sudo bash /home/gps3/repos/movefaults_clean/scripts/sudo/gps3_no_suspend.sh
#
# WHAT HAPPENED
#
# On 2026-09-15 gps3 suspended at 15:52:21 and stayed suspended until 17:41:20
# -- one hour forty-nine minutes -- twenty-one minutes after coming back up
# from the MIS breaker replacement. From the journal of that boot:
#
#   15:52:20 systemd-logind[1385]: The system will suspend now!
#   15:52:21 kernel: PM: suspend entry (s2idle)
#   17:41:20 dbus-daemon[2831]: ... Activating service name='org.xfce.Xfconf'
#
# Nothing else is in between. The machine was not down and was not crashed; it
# was asleep, and invisible on the tailnet for the whole of it.
#
# That invisibility is what made it expensive. The operator could not see gps3
# on the tailnet, went to the machine, and power-cycled it -- resuming it at
# 17:41:20 and then hard-stopping it (that boot's journal ends at the resume
# with no shutdown sequence, which is what a held power button looks like).
# The suspend cost a physical trip and a forced reboot, and presented as a
# network or host fault rather than as a sleeping machine.
#
# WHY IT IS NOT logind's IDLE ACTION
#
#   $ loginctl show-session | grep -i idle
#   IdleAction=ignore
#   IdleActionUSec=30min
#
# IdleAction=ignore, so logind did not decide this on its own -- something asked
# it to. The desktop session is the candidate: this server runs an XFCE session,
# and xfce4-power-manager suspends an idle machine by asking logind to, which is
# exactly the call that was logged. That setting lives in the user's session, so
# changing it fixes one user on one login and not the machine.
#
# WHY IT MATTERS HERE RATHER THAN BEING COSMETIC
#
# This host is a witness and a long-run machine, and suspend breaks both roles
# silently:
#
#   * scripts/finch_watch.sh is the OUTSIDE witness for finch's crashes. A
#     suspended witness records no outage, and an absence of evidence from it
#     currently reads as "finch was fine". The 15:52-17:41 window has no finch
#     observations at all and nothing in the log says so.
#   * A Bernese BPE month is thirty sequential days at ~5m33s each, and the
#     datapool transfers run for hours. Either can be mid-write at the moment
#     the session decides the machine looks idle -- a long transfer that is
#     waiting on the network looks exactly like an idle desktop.
#   * Tailscale presence goes with it, so every remote route in -- Cockpit on
#     9090, SSH, the peer session -- fails in the way that looks like the
#     network rather than like the host.
#
# WHAT THIS DOES
#
# Masks the four sleep targets. Masking, not disabling: a masked unit cannot be
# started by anything, including a desktop session politely asking logind, which
# is the actual caller here. Every other approach fixes one requester.
#
# This is the standard treatment for a server and it is reversible -- the last
# section prints how.

set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "FATAL: run with sudo." >&2
    exit 1
fi

echo "== before =="
systemctl status sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null \
    | grep -E "^(●|\s+Loaded:)" || true
echo
echo "Most recent suspend entries in the journal:"
journalctl --no-pager -o short-iso | grep -c "PM: suspend entry" \
    | sed 's/^/  total suspend entries on record: /'
echo

echo "== masking =="
systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target

echo
echo "== after =="
# Verify rather than trust the exit code: a mask that did not take looks
# identical to one that did until the machine next goes quiet.
failed=0
for unit in sleep.target suspend.target hibernate.target hybrid-sleep.target; do
    state=$(systemctl is-enabled "${unit}" 2>&1 || true)
    if [[ "${state}" == "masked" ]]; then
        echo "  ${unit}: masked"
    else
        echo "  ${unit}: NOT MASKED (is-enabled says '${state}')" >&2
        failed=1
    fi
done

if [[ ${failed} -ne 0 ]]; then
    echo >&2
    echo "FATAL: at least one target is not masked. Nothing here should be" >&2
    echo "trusted until that is understood -- do not record this as done." >&2
    exit 1
fi

echo
echo "All four masked. This survives reboots."
echo
echo "Separately, and NOT fixed here: no UPS monitoring daemon is installed."
echo "apcupsd, NUT and powerpanel are all absent. If this server is on a UPS,"
echo "nothing here is listening to it, so a battery that runs down takes the"
echo "machine with no orderly shutdown -- mid-BPE or mid-transfer if that is"
echo "when it happens. Worth its own change if the UPS has a USB or serial link."
echo
echo "To undo:"
echo "  sudo systemctl unmask sleep.target suspend.target hibernate.target hybrid-sleep.target"
