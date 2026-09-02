#!/usr/bin/env bash
# Stack PHREF daily normal equations into GPS-weekly solutions with ADDNEQ2.
#
# WHY: PHIVOLCS retains no 2025 daily solutions -- only 53 weeklies and 12
# monthlies -- so a comparison against production has to happen at weekly
# cadence. See docs/phref_vs_production_comparison_plan.md.
#
# Runs ADDNEQ2 standalone (no BPE). Notes that cost time to establish:
#   * the panel path is read from STDIN, not argv, in this build
#   * multi-value keys are "KEY <n>" alone on the line, then one indented
#     quoted value per line; putting the first value on the count line makes
#     the parser run off the end of the list into the next key
#   * ${VAR} in a panel resolves from an ENVIRONMENT key INSIDE the panel, not
#     from the shell, and the values need inner quotes because a bare '/'
#     terminates a Fortran list-directed read
#   * TRP_ELIM and GRD_ELIM must both be BEFORE_STACKING to get a
#     coordinates-only weekly comparable with the production one
#
# MAXPAR here is set high deliberately and is NOT the daily value: stacking
# several days needs several times a single day's parameters. This does not
# touch $U/OPT/R2S_FIN/ADDNEQ2.INP, which produced the 360 daily solutions.
set -uo pipefail
YEAR="${STACK_YEAR:-2025}"
CAMP="${STACK_CAMP:-PHRWK}"
TEMPLATE="${STACK_TEMPLATE:?set STACK_TEMPLATE to the ADDNEQ2 panel template}"
OUTDIR="${STACK_OUTDIR:-$HOME/phref-weekly}"
FIRST="${1:-2347}"; LAST="${2:-2399}"

# shellcheck disable=SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || { echo "no LOADGPS"; exit 3; }
# NOT named SRC: LOADGPS.setvar exports SRC=$C/SOURCE, so "${SRC:-default}"
# silently keeps Bernese's value and every week then reports "0 days
# available" -- a misconfiguration that looks exactly like missing data.
NQ_SRC="${STACK_SRC:-$S/PHREF/$YEAR/SOL}"

# Fail loudly rather than reporting an empty result 53 times over.
n_avail=$(ls "$NQ_SRC"/FIN_"$YEAR"*.NQ0.gz 2>/dev/null | wc -l)
if [ "$n_avail" -eq 0 ]; then
    echo "FATAL: no FIN_${YEAR}*.NQ0.gz under $NQ_SRC" >&2
    echo "       (set STACK_SRC if the solutions live elsewhere)" >&2
    exit 3
fi
echo "  source: $NQ_SRC  ($n_avail daily NEQ)"
W="$P/$CAMP"
mkdir -p "$W"/{SOL,OUT,STA} "$OUTDIR"

ok=0; skip=0; fail=0; nodata=0
for wk in $(seq "$FIRST" "$LAST"); do
    out="$OUTDIR/WKG_${wk}.SNX"
    if [ -s "$out" ]; then skip=$((skip+1)); continue; fi

    # GPS week -> the days of $YEAR it contains
    mapfile -t doys < <(python3 -c "
import datetime,sys
ep=datetime.date(1980,1,6); w=int(sys.argv[1]); y=int(sys.argv[2])
s=ep+datetime.timedelta(days=w*7)
for i in range(7):
    d=s+datetime.timedelta(days=i)
    if d.year==y: print(f'{d.timetuple().tm_yday:03d}')
" "$wk" "$YEAR")

    inputs=()
    for d in "${doys[@]}"; do
        gz="$NQ_SRC/FIN_${YEAR}${d}0.NQ0.gz"
        [ -f "$gz" ] || continue
        [ -s "$W/SOL/FIN_${YEAR}${d}0.NQ0" ] || zcat "$gz" > "$W/SOL/FIN_${YEAR}${d}0.NQ0"
        inputs+=("$W/SOL/FIN_${YEAR}${d}0.NQ0")
    done

    # A weekly from one or two days is not a weekly. Partial weeks at the year
    # boundary are expected; they are reported, not silently averaged in.
    if [ "${#inputs[@]}" -lt 3 ]; then
        printf '  WK_%s  SKIP — only %d day(s) of %s available\n' "$wk" "${#inputs[@]}" "$YEAR"
        nodata=$((nodata+1)); continue
    fi

    panel="$W/ADDNEQ2_${wk}.INP"
    python3 - "$TEMPLATE" "$panel" "$W" "$wk" "${inputs[@]}" <<'PY'
import sys, pathlib, re
tpl, dst, W, wk, *inp = sys.argv[1:]
s = pathlib.Path(tpl).read_text()
blk = "INPFILE %d\n" % len(inp) + "".join('  "%s"\n' % f for f in inp)
s = re.sub(r'^INPFILE \d+.*\n(?:\s+"[^"]*"\n)*', blk, s, count=1, flags=re.M)
setk = lambda t,k,v: re.sub(rf'^{k} \d+ +"[^"]*"', f'{k} 1  "{v}"', t, count=1, flags=re.M)
s = setk(s, "SYSOUT",  f"{W}/OUT/WKG_{wk}.OUT")
s = setk(s, "NEQOUT",  f"{W}/SOL/WKG_{wk}.NQ0")
s = setk(s, "SINEXRS", f"{W}/SOL/WKG_{wk}.SNX")
s = setk(s, "COORDRS", f"{W}/STA/WKG_{wk}.CRD")
pathlib.Path(dst).write_text(s)
PY

    echo "$panel" | "$XG/ADDNEQ2" >/dev/null 2>&1
    rc=$?
    if [ "$rc" -eq 0 ] && [ -s "$W/SOL/WKG_${wk}.SNX" ]; then
        cp -p "$W/SOL/WKG_${wk}.SNX" "$out"
        printf '  WK_%s  ok  (%d days)\n' "$wk" "${#inputs[@]}"
        ok=$((ok+1))
    else
        printf '  WK_%s  FAIL rc=%s: %s\n' "$wk" "$rc" \
          "$(grep -m1 -A2 '\*\*\* ' "$W/OUT/WKG_${wk}.OUT" 2>/dev/null | tr '\n' ' ' | cut -c1-100)"
        fail=$((fail+1))
    fi
done
printf '\n  stacked %d, skipped %d already present, %d too few days, %d FAILED\n' \
       "$ok" "$skip" "$nodata" "$fail"
[ "$fail" -eq 0 ]
