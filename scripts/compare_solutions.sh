#!/usr/bin/env bash
# compare_solutions.sh — bit-for-bit diff of two Bernese solution sets.
#
# WHY THIS EXISTS
# Verifying that a configuration change did not alter results requires comparing
# the OUTPUT, not trusting that the change was innocuous. This was written to
# check whether BSW's parallel multi-session mode (SUPERBPE=1, DOCU52 §22.9)
# produces the same solutions as sequential processing — the manual warns that
# running many sessions in one campaign requires "all scripts and filenames
# (including all temporary files) [to] be fully sessions-independent", and the
# only way to know whether our derived PCF satisfies that is to look.
#
# WHY NOT JUST `diff` THE .gz FILES
# Two reasons they differ byte-wise even when the science is identical:
#   1. gzip embeds an mtime, so the container differs on every run.
#   2. SINEX carries a creation timestamp in its header line and in
#      FILE/REFERENCE, plus the run's own agency/time fields.
# So the comparison decompresses, strips the known-volatile header lines, and
# diffs the rest — which includes every coordinate, every covariance, and the
# station list.
#
# Usage:  scripts/compare_solutions.sh <dirA> <dirB> [glob]
#         scripts/compare_solutions.sh $S/LUZON_BASELINE/2025/SOL $S/LUZON/2025/SOL
set -uo pipefail

A="${1:?usage: $0 <dirA> <dirB> [glob]}"
B="${2:?usage: $0 <dirA> <dirB> [glob]}"
GLOB="${3:-FIN_*.SNX.gz}"

[ -d "$A" ] || { echo "ERROR: not a directory: $A" >&2; exit 1; }
[ -d "$B" ] || { echo "ERROR: not a directory: $B" >&2; exit 1; }

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

# Lines that legitimately differ between two runs of identical input.
# %=SNX  : header carries creation time
# +FILE/REFERENCE ... CREATED / the SNX time fields
# The DD-MMM-YY HH:MM pattern was added 2026-08-24. Without it, two runs made
# on different DAYS always differ on the program-header line
#     *RNX2SNX_20251210: NEQ reduction and SINEX generation   13-AUG-26 09:01
# and the tool reports DIFFERS for solutions that are otherwise bit-identical.
# That is the normal case for this script -- a baseline and a variant are
# rarely produced the same afternoon -- so the omission made it report a
# spurious difference exactly when it was most likely to be trusted.
strip() {
    grep -vE '^%=SNX|CREATED|^\*?[[:space:]]*(CREATION|FILE/REFERENCE)|[0-9]{2}:[0-9]{3}:[0-9]{5}|[0-9]{2}-[A-Z]{3}-[0-9]{2}[[:space:]]+[0-9]{2}:[0-9]{2}'
}

same=0; differ=0; onlyA=0; onlyB=0
differing_files=""

shopt -s nullglob
for fa in "$A"/$GLOB; do
    n=$(basename "$fa")
    fb="$B/$n"
    if [ ! -f "$fb" ]; then
        onlyA=$((onlyA + 1)); continue
    fi
    zcat "$fa" 2>/dev/null | strip > "$TMP/a.txt"
    zcat "$fb" 2>/dev/null | strip > "$TMP/b.txt"
    if cmp -s "$TMP/a.txt" "$TMP/b.txt"; then
        same=$((same + 1))
    else
        differ=$((differ + 1))
        differing_files="$differing_files $n"
        # Show the first few differing lines -- a coordinate change is
        # immediately obvious, a metadata change is immediately dismissible.
        echo "  DIFFERS: $n"
        diff "$TMP/a.txt" "$TMP/b.txt" | head -6 | sed 's/^/      /'
    fi
done
for fb in "$B"/$GLOB; do
    [ -f "$A/$(basename "$fb")" ] || onlyB=$((onlyB + 1))
done

echo
echo "identical: $same   differing: $differ   only in A: $onlyA   only in B: $onlyB"
if [ "$differ" -gt 0 ]; then
    echo "differing files:$differing_files"
    exit 1
fi
if [ "$same" -eq 0 ]; then
    echo "NOTHING COMPARED — check the glob and the directories." >&2
    exit 1
fi
echo "All compared solutions are identical after stripping run timestamps."
