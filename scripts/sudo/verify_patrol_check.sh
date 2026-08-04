#!/usr/bin/env bash
# verify_patrol_check.sh — re-run patrol_check.sh after the 2026-08-03 column
# fix and confirm the corrected parse produces sane numbers.
#
# WHAT THIS IS CHECKING. The first version of patrol_check.sh read the SCSI
# error-counter columns one position off, reporting 0.00 TB read and ~1,025,339
# uncorrected errors per drive — an array that looked simultaneously unscanned
# and dying, when it is neither. Both figures were the same two numbers with
# their columns transposed. This run confirms the fix.
#
# EXPECTED (from raw smartctl output verified 2026-08-03):
#   READ       ~1025 TB per drive
#   UNCORR     0 on all 16          <- anything non-zero is a real problem
#   SCANS      424
#   SWEEPS     ~1.00x               <- the load-bearing number
#   RECOVERED  16 on member 7, 0 on member 0
#
# If SWEEPS prints "-" or is far from 1.00x, the User Capacity parse is wrong
# and the conclusion in session log §13.2 needs re-checking before it is
# trusted.
#
# READ-ONLY. Issues 48 smartctl queries; takes about a minute.
set -uo pipefail

# The REPO copy — the one this PR fixes. Pointing at ~/patrol_check.sh (the
# original location) meant the "confirm the fix" run could exercise a stale
# pre-fix copy and cheerfully report the old, wrong numbers.
TARGET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/patrol_check.sh"
LOGDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/logs"
LOG="$LOGDIR/patrol-check-$(date +%Y%m%d-%H%M%S).log"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: needs root — run with sudo." >&2
    exit 1
fi
[ -x "$TARGET" ] || { echo "ERROR: $TARGET missing or not executable" >&2; exit 1; }

mkdir -p "$LOGDIR"

# tee, not redirect: the operator watches it live in their terminal AND it is
# captured for the session to read afterwards. A plain '>' means one or the
# other, and this project has already lost time to output that went to only
# one place.
"$TARGET" 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}

echo
echo "-------------------------------------------------------------"
echo "patrol_check.sh exit: $rc"
echo "log: $LOG"
echo
echo "Check before trusting the result:"
echo "  UNCORR must be 0 on all 16 members."
echo "  SWEEPS should be ~1.00x — that is the evidence of full-surface reads."
exit "$rc"
