#!/usr/bin/env bash
# inspect_member6.sh — investigate the recovered-sector outlier found 2026-08-03.
#
# WHY. patrol_check.sh reported BMS recovered-sector counts across the 16 PERC
# members: nine drives at 0, most of the rest in single or double digits, and
# member 6 at 671 — roughly 75% of the array's 895 total, seven times the
# next-worst drive (member 1 at 96).
#
# That asymmetry is the point. A drive finding and repairing occasional bad
# sectors is a healthy scanning setup doing its job. One drive out of sixteen,
# on identical hardware, of identical age (all ~10,145 power-on hours), with
# an order of magnitude more defects than its cohort, is a drive whose media is
# degrading faster than its peers. In a 16-wide RAID 5 there is exactly one
# drive's worth of redundancy, so the question "which member is most likely to
# fail first" has real consequences.
#
# WHAT TO LOOK FOR in the output:
#
#   reassign_status — the load-bearing field.
#     "Recovered via rewrite in-place"  ECC recovered the data, rewrote it,
#                                       sector still in use. Benign.
#     "Reassigned"                      Sector retired, spare consumed. Real
#                                       media loss; watch the spare count.
#     "Reassign failed" / "Failed"      Data was NOT recovered. Escalate.
#
#   Clustering of the lba(hex) values. Contiguous runs (as seen on member 7)
#   usually mean one localised media defect — a scratch or particle. Values
#   scattered across the whole address space suggest general degradation,
#   which is the worse diagnosis.
#
#   Timestamps (power-on hours). Defects spread evenly over 10,000 hours is
#   slow wear. Hundreds clustered into a narrow recent window means something
#   changed, and the trend matters more than the total.
#
#   "Elements in grown defect list" from -a: sectors permanently reassigned.
#   Compare against member 0 (a clean drive) printed below for contrast.
#
# READ-ONLY. Nothing here writes to the drive or the controller.
set -uo pipefail

VD=/dev/sda
SUSPECT=6
CONTROL=0
LOGDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/logs"
LOG="$LOGDIR/member6-inspect-$(date +%Y%m%d-%H%M%S).log"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: needs root — run with sudo." >&2
    exit 1
fi
mkdir -p "$LOGDIR"

{
    for id in "$SUSPECT" "$CONTROL"; do
        echo "==================================================================="
        if [ "$id" -eq "$SUSPECT" ]; then
            echo "  MEMBER $id  — THE OUTLIER (671 recovered sectors)"
        else
            echo "  MEMBER $id  — CONTROL (0 recovered sectors, same age)"
        fi
        echo "==================================================================="

        echo "--- identity, health, grown defect list ---"
        smartctl -i -H -d "megaraid,$id" "$VD" 2>&1 \
          | grep -iE 'Model|Serial|Firmware|Capacity|health|SMART|defect' || true

        echo
        echo "--- error counters (GB processed is 2nd-from-last; uncorrected is last) ---"
        smartctl -l error -d "megaraid,$id" "$VD" 2>&1 \
          | grep -iE '^read:|^write:|^verify:|Non-medium' || true

        echo
        echo "--- reassign_status tally (the key question) ---"
        smartctl -l background -d "megaraid,$id" "$VD" 2>&1 \
          | grep -oE '\[[0-9]+,[0-9]+,[0-9]+\][[:space:]]+.*$' \
          | sed -E 's/^\[[0-9,]+\][[:space:]]+//' \
          | sort | uniq -c | sort -rn || true

        echo
        echo "--- defect timeline: power-on hour -> count (are they recent?) ---"
        smartctl -l background -d "megaraid,$id" "$VD" 2>&1 \
          | grep -E '\[[0-9]+,[0-9]+,[0-9]+\]' \
          | awk '{print $2}' | cut -d: -f1 | sort -n | uniq -c \
          | awk '{printf "    %8s h : %s entries\n", $2, $1}' || true

        echo
        echo "--- first and last 5 entries (check LBA clustering) ---"
        smartctl -l background -d "megaraid,$id" "$VD" 2>&1 \
          | grep -E '\[[0-9]+,[0-9]+,[0-9]+\]' > /tmp/.m$id.entries || true
        head -5 /tmp/.m$id.entries 2>/dev/null || true
        echo "      ..."
        tail -5 /tmp/.m$id.entries 2>/dev/null || true
        rm -f /tmp/.m$id.entries
        echo
    done

    echo "==================================================================="
    echo "VERDICT GUIDE"
    echo "  All 'Recovered via rewrite in-place', spread over 10,000 h,"
    echo "  clustered LBAs, UNCORR still 0"
    echo "      -> localised media defect, contained. Monitor, no action."
    echo
    echo "  Any 'Reassign failed', OR a growing grown-defect list, OR defects"
    echo "  concentrated in recent hours, OR scattered LBAs"
    echo "      -> member 6 is the likely first failure in a 16-wide RAID 5"
    echo "         with one drive of redundancy. Plan a proactive replacement"
    echo "         BEFORE populating the archive, not after."
    echo "==================================================================="
} 2>&1 | tee "$LOG"

echo
echo "log: $LOG"
