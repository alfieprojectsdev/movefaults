#!/usr/bin/env bash
# finch_enable_softlockup_panic.sh — turn on ONE of the two panic settings.
#
# softlockup_panic YES, hung_task_panic NO. They look like a pair and are not.
#
#   softlockup_panic  fires when a CPU is stuck in kernel mode ~20s without
#                     scheduling. Nothing legitimate does that, so the
#                     false-positive rate is near zero.
#
#   hung_task_panic   fires when a task is blocked 60s in UNINTERRUPTIBLE
#                     sleep. That is ordinary for slow or failing I/O. finch
#                     has legacy drives docked through a USB bridge that logs
#                     SMART housekeeping failures every ten minutes; a stalled
#                     read there would panic a healthy machine mid-transfer.
#                     The drives are attached right now, so this is a live
#                     risk, not a retrospective one.
#
# A stalled USB read blocks a task in D-state; it does not leave a CPU spinning
# in kernel mode. So softlockup_panic does not fire on it, which is exactly why
# only one of the two goes in.
#
# Usage:  sudo bash scripts/sudo/finch_enable_softlockup_panic.sh
# Safe to re-run. No reboot needed -- sysctl values apply immediately.

set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run with sudo." >&2; exit 1; }

CONF=/etc/sysctl.d/99-finch-diagnostics.conf
[ -f "$CONF" ] || { echo "ERROR: $CONF not found — run finch_diagnostics_hardening.sh first." >&2; exit 1; }

printf '\n=== Before\n'
printf '  kernel.softlockup_panic = %s\n' "$(sysctl -n kernel.softlockup_panic 2>/dev/null || echo '<unset>')"
printf '  kernel.hung_task_panic  = %s\n' "$(sysctl -n kernel.hung_task_panic 2>/dev/null || echo '<unset>')"

printf '\n=== Rewriting the panic block in %s\n' "$CONF"
python3 - "$CONF" <<'PY'
import re, sys, pathlib
p = pathlib.Path(sys.argv[1])
s = p.read_text()
block = """# --- panic-on-wedge -------------------------------------------------------
# ENABLED. A CPU stuck in kernel mode ~20s without scheduling is never
# legitimate, so this has a near-zero false-positive rate. It converts a silent
# wedge into a panic that leaves a call stack, which is the thing three crashes
# so far have not produced.
kernel.softlockup_panic = 1

# NOT ENABLED, deliberately -- and this is not an oversight to be tidied up.
#
# hung_task_panic fires on a task blocked 60s in UNINTERRUPTIBLE sleep, which
# is ordinary behaviour for slow or failing I/O rather than a fault. finch has
# legacy GNSS drives docked through a USB bridge that logs SMART housekeeping
# failures every ten minutes; a stalled read there would panic a perfectly
# healthy machine in the middle of a transfer. The drives are attached now, so
# that is a present risk.
#
# Note also that hung_task_timeout_secs is set to 60 above, against a kernel
# default of 120. That is aggressive on purpose for LOGGING, and it would be
# reckless for PANICKING.
#
# Revisit only if the watchdog starts firing without leaving a trace -- that
# would mean wedges the softlockup detector is not catching, which is the case
# this setting exists for.
#kernel.hung_task_panic = 1
"""
# drop any previous panic lines/comments for these two keys
s = re.sub(r'\n?#?\s*kernel\.(softlockup_panic|hung_task_panic)\s*=.*\n', '\n', s)
s = re.sub(r'\n# NOT ENABLED[^\n]*\n(#[^\n]*\n)*', '\n', s)
s = s.rstrip('\n') + '\n\n' + block
p.write_text(s)
print("  rewritten")
PY

sysctl --system >/dev/null 2>&1 || sysctl -p "$CONF" >/dev/null

printf '\n=== Effective values, read from the SYSTEM not the file\n'
sp=$(sysctl -n kernel.softlockup_panic 2>/dev/null || echo unset)
hp=$(sysctl -n kernel.hung_task_panic 2>/dev/null || echo unset)
printf '  kernel.softlockup_panic = %s   (want 1)\n' "$sp"
printf '  kernel.hung_task_panic  = %s   (want 0)\n' "$hp"
printf '  kernel.hung_task_timeout_secs = %s\n' "$(sysctl -n kernel.hung_task_timeout_secs)"

fail=0
[ "$sp" = "1" ] || { echo "  *** FAILED: softlockup_panic is $sp, expected 1" >&2; fail=1; }
[ "$hp" = "0" ] || { echo "  *** FAILED: hung_task_panic is $hp, expected 0 — a USB stall could now panic the box" >&2; fail=1; }

printf '\n=== Which file wins\n'
systemd-analyze cat-config sysctl.d 2>/dev/null | grep -n "softlockup_panic" | tail -3 | sed 's/^/  /' || true

[ "$fail" -eq 0 ] || exit 1
printf '\nDone. No reboot needed.\n'
