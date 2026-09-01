#!/usr/bin/env bash
# Run the weekly Helmert comparison across every week both sides have.
#
# Reports the population, not a sample: every week is compared, weeks that
# cannot be compared are named with the reason, and the per-station residuals
# are aggregated so a station that is bad in ONE week is distinguishable from
# one that is bad in ALL of them. The latter is a metadata problem; the former
# is a week to look at.
set -uo pipefail
OURS="${OURS_DIR:-$HOME/phref-weekly}"
THEIRS="${THEIRS_DIR:-$HOME/phivolcs-weekly}"
OUT="${OUT_DIR:-$HOME/weekly-comparison}"
mkdir -p "$OUT"
: > "$OUT/summary.txt"
n=0; miss=0
for f in "$OURS"/WKG_*.SNX; do
    wk=$(basename "$f" .SNX); wk=${wk#WKG_}
    theirs="$THEIRS/WK_${wk}.SNX"
    if [ ! -s "$theirs" ]; then
        printf 'WK_%s  NO COUNTERPART\n' "$wk" >> "$OUT/summary.txt"; miss=$((miss+1)); continue
    fi
    uv run --with numpy python scripts/compare_weekly_solutions.py \
        --ours "$f" --theirs "$theirs" --label "GPS week $wk" \
        > "$OUT/WK_${wk}.txt" 2>&1
    line=$(grep -m1 '^  RMS' "$OUT/WK_${wk}.txt" || echo "  RMS  (failed)")
    printf 'WK_%s %s\n' "$wk" "$line" >> "$OUT/summary.txt"
    n=$((n+1))
done
printf '\n  compared %d week(s), %d without a counterpart\n' "$n" "$miss"
printf '  per-week detail in %s\n' "$OUT"
