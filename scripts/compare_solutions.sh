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
# WHAT IT COULD NOT SEE UNTIL 2026-10-27 (found by the PHREF parity run)
#   * Plain files: `zcat f 2>/dev/null` fails on an uncompressed file and
#     prints nothing, so both sides were empty and "identical". FIN_*.CRD
#     differing by up to 16 mm was reported identical: 30. Files are now read
#     with `gzip -cdf` (plain or compressed), and a file that cannot be read,
#     or two that strip to nothing, are not counted as identical.
#   * Coordinates: the run-timestamp pattern YY:DDD:SSSSS was applied to every
#     line, and every SOLUTION/ESTIMATE line carries its reference epoch in
#     that form, so the estimates were deleted before the diff (10,983 of
#     11,331 lines of a real SINEX). Only the covariance matrix and statistics
#     were compared. That pattern now applies only to the %=SNX header and
#     the INPUT/HISTORY lines, where the creation epoch lives.
#   * Binary files (*.NQ0): grep reduced both sides to "binary file matches",
#     so they compared equal. They are now reported BINARY and not compared.
#   Verdicts this script gave before the fix said nothing about coordinates.
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
# INPUT/HISTORY lines (" +SNX ..." / " =SNX ...") repeat the creation epoch.
strip() {
    grep -vE '^%=SNX|^ [+=]SNX |CREATED|^\*?[[:space:]]*(CREATION|FILE/REFERENCE)|[0-9]{2}-[A-Z]{3}-[0-9]{2}[[:space:]]+[0-9]{2}:[0-9]{2}'
}

# Decompress if compressed, pass through if not. Returns 1 if unreadable and
# 3 if binary: a NEQ (*.NQ0) cannot be text-stripped, and grep on it prints
# "binary file matches" and keeps nothing. Compare the SNX instead.
read_stripped() {
    gzip -cdf -- "$1" > "$TMP/raw" || return 1
    if [ -s "$TMP/raw" ] && ! grep -qI . "$TMP/raw"; then
        return 3
    fi
    strip < "$TMP/raw"
    return 0
}

same=0; differ=0; onlyA=0; onlyB=0; unreadable=0; binary=0
differing_files=""

shopt -s nullglob
for fa in "$A"/$GLOB; do
    n=$(basename "$fa")
    fb="$B/$n"
    if [ ! -f "$fb" ]; then
        onlyA=$((onlyA + 1)); continue
    fi
    read_stripped "$fa" > "$TMP/a.txt"; ra=$?
    read_stripped "$fb" > "$TMP/b.txt"; rb=$?
    if [ "$ra" -eq 3 ] || [ "$rb" -eq 3 ]; then
        binary=$((binary + 1))
        echo "  BINARY: $n (not comparable by this script; compare the SNX)"
        continue
    fi
    if [ "$ra" -ne 0 ] || [ "$rb" -ne 0 ]; then
        unreadable=$((unreadable + 1))
        echo "  UNREADABLE: $n"
        continue
    fi
    if [ ! -s "$TMP/a.txt" ] && [ ! -s "$TMP/b.txt" ]; then
        # Nothing left on either side is not agreement.
        unreadable=$((unreadable + 1))
        echo "  EMPTY: $n (nothing to compare after stripping)"
        continue
    fi
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
echo "identical: $same   differing: $differ   unreadable or empty: $unreadable   binary: $binary   only in A: $onlyA   only in B: $onlyB"
if [ "$differ" -gt 0 ]; then
    echo "differing files:$differing_files"
    exit 1
fi
if [ "$unreadable" -gt 0 ] || [ "$binary" -gt 0 ]; then
    echo "NOT COMPARED: $unreadable unreadable or empty, $binary binary." >&2
    exit 2
fi
if [ "$same" -eq 0 ]; then
    echo "NOTHING COMPARED — check the glob and the directories." >&2
    exit 1
fi
echo "All compared solutions are identical after stripping run timestamps."
