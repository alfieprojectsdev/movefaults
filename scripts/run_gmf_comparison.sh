#!/usr/bin/env bash
# run_gmf_comparison.sh — settle GEO-002 by measurement instead of argument.
#
# THE QUESTION
# Six GPSEST panels carry three mapping functions. The float and final solves
# use one thing; the three ambiguity-resolution steps use WET_NIELL:
#
#     R2S_AMB (MW)        COSZ         <- correct for Melbourne-Wubbena, not at issue
#     R2S_EDT (float)     WET_GMF3
#     R2S_FIN (final)     WET_GMF3
#     R2S_QIF/L53/L12     WET_NIELL    <- the subject
#
# GEO-002 calls the split "unintentional". Before baking it into a year of
# national data, measure whether it matters: make the ambiguity panels agree
# with the final panel, reprocess the same 30 days, and diff the solutions.
#
# WHAT THE ANSWER MEANS
#   identical / sub-mm  -> the split is cosmetic. Resolve it on style grounds,
#                          whenever, and launch 2025 now.
#   millimetres         -> it is a real choice. Cass decides BEFORE the year
#                          runs, because fixing it afterwards means a partial
#                          reprocess, and a partially reprocessed series
#                          carries a step at the boundary with no physical
#                          cause (provenance_record_design.md, amendment).
#
# A CORRECTION THIS SCRIPT ENCODES
# GEO-002 and pcf_context.LUZON_TROPOSPHERE both record the float/final panels
# as WET_GMF. The LIVE 5.4 tree says WET_GMF3 -- a different card, and the one
# that actually ran. The declared table is measured against the repo's *5.2*
# config (config/bernese/gpsuser52-luzon/OPT), which is not what executes.
# So the variant here targets WET_GMF3: matching what the final solve does,
# not what the table says it does.
#
# ISOLATION
# Nothing touches the baseline. Variant OPT dirs, a variant PCF, a variant
# campaign, a variant SAVEDISK subtree. The baseline 30 days in
# $S/LUZON/2025/SOL stay exactly as they are and are the comparison target.
#
# Usage:
#   scripts/run_gmf_comparison.sh --setup     # build variant config, verify, stop
#   scripts/run_gmf_comparison.sh --run       # process the days (long)
#   scripts/run_gmf_comparison.sh --compare   # diff against the baseline
#   scripts/run_gmf_comparison.sh --teardown  # remove variant config + campaign
set -uo pipefail

VARIANT_MAPPNG="${VARIANT_MAPPNG:-WET_GMF3}"
VARIANT_PANELS="R2S_QIF R2S_L53 R2S_L12"
VARIANT_TAG="GMF3AMB"
VARIANT_PCF="LZGMF_DLY"
VARIANT_CAMPAIGN="LZGMF"
YEAR=2025
# A subset, not all 30. Enough to see a systematic difference; a day is ~5m33s
# and the answer does not improve with repetition. Spread across the month so a
# single bad day cannot carry the conclusion.
DOYS="${DOYS:-121 126 131 136 141 146 151}"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }

_snap="$VARIANT_PCF|$VARIANT_CAMPAIGN|$YEAR|$DOYS|$VARIANT_MAPPNG"
# shellcheck disable=SC1090,SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || die "cannot source LOADGPS.setvar"
[ "$_snap" = "$VARIANT_PCF|$VARIANT_CAMPAIGN|$YEAR|$DOYS|$VARIANT_MAPPNG" ] \
    || die "LOADGPS.setvar clobbered a config variable -- rename it"
if [ -z "${P:-}" ] || [ -z "${U:-}" ] || [ -z "${S:-}" ]; then
    die "P/U/S unset after LOADGPS"
fi

BASE_SOL="$S/LUZON/$YEAR/SOL"
VAR_SOL="$S/$VARIANT_CAMPAIGN/$YEAR/SOL"

setup() {
    say "=== building variant configuration ($VARIANT_MAPPNG in the ambiguity panels) ==="

    # Show what the live tree actually uses, so the premise is on the record
    # rather than taken from a document.
    say "live panel mapping functions BEFORE any change:"
    for p in R2S_AMB R2S_EDT R2S_FIN R2S_QIF R2S_L53 R2S_L12; do
        printf '    %-9s %s\n' "$p" \
          "$(grep -m1 'MAPPNG' "$U/OPT/$p/GPSEST.INP" 2>/dev/null \
             | grep -oE '"[A-Z0-9_]+"' | tr -d '"')"
    done

    local final_mf
    final_mf=$(grep -m1 'MAPPNG' "$U/OPT/R2S_FIN/GPSEST.INP" \
               | grep -oE '"[A-Z0-9_]+"' | tr -d '"')
    if [ "$final_mf" != "$VARIANT_MAPPNG" ]; then
        say ""
        say "  NOTE: R2S_FIN uses '$final_mf' but the variant targets '$VARIANT_MAPPNG'."
        say "        The point of this test is to make the ambiguity panels match the"
        say "        FINAL panel. Set VARIANT_MAPPNG=$final_mf unless you mean otherwise."
    fi

    for p in $VARIANT_PANELS; do
        local src="$U/OPT/$p" dst="$U/OPT/${p}_${VARIANT_TAG}"
        [ -d "$src" ] || die "missing live panel dir: $src"
        rm -rf "$dst"
        cp -a "$src" "$dst" || die "cannot copy $src"
        # Rewrite only the MAPPNG value, preserving the fixed-column layout that
        # the surrounding quotes define. Anchored to line start so MSG_MAPPNG
        # and the commented `## cards =` list are untouched.
        sed -i -E "s/^(MAPPNG[[:space:]]+1[[:space:]]+)\"[A-Z0-9_]+\"/\1\"$VARIANT_MAPPNG\"/" \
            "$dst/GPSEST.INP" || die "sed failed on $dst"
        local got
        got=$(grep -m1 '^MAPPNG' "$dst/GPSEST.INP" | grep -oE '"[A-Z0-9_]+"' | tr -d '"')
        [ "$got" = "$VARIANT_MAPPNG" ] || die "$dst still says '$got'"
        # The cards list must contain the value or GPSEST will reject the panel.
        grep -q "$VARIANT_MAPPNG" "$dst/GPSEST.INP" || die "$VARIANT_MAPPNG not a valid card here"
        say "  $p -> ${p}_${VARIANT_TAG}  MAPPNG=$got"
    done

    # Variant PCF: identical but for the three OPT directory names.
    local src_pcf="$U/PCF/LUZON_DLY.PCF" dst_pcf="$U/PCF/$VARIANT_PCF.PCF"
    [ -f "$src_pcf" ] || die "missing $src_pcf"
    cp -f "$src_pcf" "$dst_pcf"
    for p in $VARIANT_PANELS; do
        sed -i -E "s/\b${p}\b/${p}_${VARIANT_TAG}/g" "$dst_pcf"
    done

    # THE SAFETY FIX THIS SCRIPT TURNS ON.
    # V_RESULT is where R2S_SAV archives the solution, and the baseline PCF
    # points it at ${S}/LUZON/$Y -- the very directory holding the 30 days we
    # are comparing against. Copying the PCF unchanged would have had the
    # variant overwrite the baseline, silently, and the comparison would then
    # have diffed the variant against itself and reported "identical".
    # Redirect it before anything can run.
    sed -i -E "s#^(V_RESULT = )\\\$\{S\}/LUZON/#\1\\\$\{S\}/${VARIANT_CAMPAIGN}/#" "$dst_pcf"
    local res
    res=$(grep -m1 '^V_RESULT' "$dst_pcf")
    case "$res" in
        *"/${VARIANT_CAMPAIGN}/"*) say "  V_RESULT redirected: $(echo "$res" | tr -s ' ')" ;;
        *) die "V_RESULT still points at the baseline: $res" ;;
    esac
    grep -q "LUZON" <<<"$(grep '^V_RESULT' "$dst_pcf")" \
        && die "V_RESULT still names LUZON -- refusing to risk the baseline"

    # Every OPT directory the variant PCF names must exist, or BPE hangs on a
    # missing panel rather than failing -- the same class as a dangling WAIT.
    local missing=0
    while read -r d; do
        [ -d "$U/OPT/$d" ] || { say "  MISSING OPT dir: $d"; missing=$((missing+1)); }
    done < <(awk '$1 ~ /^[0-9]+$/ {print $3}' "$dst_pcf" | sort -u)
    [ "$missing" -eq 0 ] || die "$missing OPT directory(ies) named but absent"

    # Dangling WAIT check: every WAIT target must be a PID in this file.
    local pids waits dangling
    pids=$(awk '$1 ~ /^[0-9]+$/ {print $1}' "$dst_pcf" | sort -u)
    waits=$(grep -oE 'WAIT=[0-9]+' "$dst_pcf" | cut -d= -f2 | sort -u)
    dangling=$(comm -13 <(echo "$pids") <(echo "$waits"))
    [ -z "$dangling" ] || die "dangling WAIT target(s): $(echo "$dangling" | tr '\n' ' ')"

    say ""
    say "variant PCF : $dst_pcf"
    say "  steps=$(awk '$1 ~ /^[0-9]+$/' "$dst_pcf" | wc -l)  dangling WAITs=0"
    say "  diff vs baseline PCF:"
    diff "$src_pcf" "$dst_pcf" | grep -E '^[<>]' | head -8 | sed 's/^/    /'
    # Variant driver: same as luzon_pcs.pl but pointed at the variant campaign.
    local src_drv="$U/SCRIPT/luzon_pcs.pl" dst_drv="$U/SCRIPT/${VARIANT_PCF}_pcs.pl"
    [ -f "$src_drv" ] || die "missing $src_drv"
    sed -E -e "s#'\\\$\{P\}/LUZON'#'\\\$\{P\}/${VARIANT_CAMPAIGN}'#" \
           -e "s/\"LUZON_DLY\"/\"${VARIANT_PCF}\"/" "$src_drv" > "$dst_drv"
    chmod +x "$dst_drv"
    grep -q "\${P}/${VARIANT_CAMPAIGN}" "$dst_drv" \
        || die "variant driver still points at the baseline campaign"
    say "  driver: $dst_drv -> campaign \${P}/${VARIANT_CAMPAIGN}"

    # The variant campaign must exist and hold the same staged inputs. Copy the
    # baseline campaign rather than re-staging: identical inputs are the whole
    # point of a controlled comparison, and re-staging could differ.
    if [ ! -d "$P/$VARIANT_CAMPAIGN" ]; then
        say "  staging $P/$VARIANT_CAMPAIGN from the baseline campaign (~7 GB)..."
        cp -a "$P/LUZON" "$P/$VARIANT_CAMPAIGN" || die "cannot copy campaign"
        rm -rf "${P:?}/$VARIANT_CAMPAIGN/BPE"/*.OUT "${P:?}/$VARIANT_CAMPAIGN/BPE"/*.RUN
        say "  staged: $(du -sh "$P/$VARIANT_CAMPAIGN" | cut -f1)"
    else
        say "  campaign $P/$VARIANT_CAMPAIGN already present"
    fi
    # Register the campaign with BSW or startBPE refuses it.
    if [ -f "$P/../MENU_CMP.INP" ] || [ -f "$U/PAN/MENU_CMP.INP" ]; then
        local mc="$U/PAN/MENU_CMP.INP"
        [ -f "$mc" ] && ! grep -q "$VARIANT_CAMPAIGN" "$mc" && \
            say "  NOTE: $VARIANT_CAMPAIGN is not listed in MENU_CMP.INP;" && \
            say "        startBPE may refuse it. Add it if the run fails at once."
    fi

    say ""
    say "baseline solutions to compare against: $(find "$BASE_SOL" -name "FIN_${YEAR}*.SNX.gz" 2>/dev/null | wc -l) in $BASE_SOL"
    say "setup complete. Nothing has been processed. Next: --run"
}

run_days() {
    [ -f "$U/PCF/$VARIANT_PCF.PCF" ] || die "run --setup first"
    # luzon_pcs.pl HARDCODES BPE_CAMPAIGN = '${P}/LUZON' and accepts at most
    # three arguments -- passing a campaign name as a fourth is silently
    # ignored, so the variant would execute inside the baseline campaign and
    # scribble on its working directories. Use a driver of our own instead.
    local drv="$U/SCRIPT/${VARIANT_PCF}_pcs.pl"
    [ -x "$drv" ] || die "driver missing: $drv -- run --setup first"

    local log_dir="$HOME/gmf-comparison-logs"
    mkdir -p "$log_dir"
    # Not `local`: the EXIT trap fires after this function returns, and a
    # function-scoped name is unbound by then -- under `set -u` the trap itself
    # then errors on the way out.
    LOCK_DIR="$HOME/.run_gmf_comparison.lock"
    mkdir "$LOCK_DIR" 2>/dev/null || die "another run holds $LOCK_DIR"
    trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

    local ok=0 bad=0 bad_days="" t_all
    t_all=$(date +%s)
    for doy in $DOYS; do
        local d3 sess log t0 out fresh
        d3=$(printf '%03d' "$doy"); sess="${d3}0"
        log="$log_dir/gmf-$YEAR$sess.log"
        if ls "$VAR_SOL/FIN_${YEAR}${sess}."* >/dev/null 2>&1; then
            say "  DOY $d3  SKIP (variant solution exists)"
            continue
        fi
        t0=$(date +%s)
        printf '  DOY %s  start %s ... ' "$d3" "$(date '+%H:%M:%S')"
        # Three arguments only: the campaign is baked into the variant driver,
        # not passed. luzon_pcs.pl rejects a fourth and prints usage.
        perl "$drv" "$YEAR" "$sess" "$VARIANT_PCF" >"$log" 2>&1
        # Do not trust the exit code alone: check for a solution produced in
        # THIS invocation. A stale .OUT once scored 30 days OK with nothing run.
        out="$P/$VARIANT_CAMPAIGN/BPE/$VARIANT_PCF.OUT"
        fresh=no
        [ -f "$out" ] && [ "$(stat -c %Y "$out")" -ge "$t0" ] && fresh=yes
        if [ "$fresh" = yes ] && ls "$VAR_SOL/FIN_${YEAR}${sess}."* >/dev/null 2>&1; then
            printf 'OK (%ds)\n' "$(( $(date +%s) - t0 ))"
            ok=$((ok+1))
        else
            printf 'FAILED (%ds)  see %s\n' "$(( $(date +%s) - t0 ))" "$log"
            bad=$((bad+1)); bad_days="$bad_days $d3"
        fi
    done
    say ""
    say "variant run: ok=$ok failed=$bad$([ -n "$bad_days" ] && echo "  failed:$bad_days")"
    say "elapsed: $(( ($(date +%s) - t_all) / 60 )) min"
    [ "$ok" -gt 0 ] || die "no variant solution produced -- nothing to compare"
    say "next: --compare"
}

compare() {
    [ -d "$VAR_SOL" ] || die "no variant solutions at $VAR_SOL -- run --run first"
    say "=== baseline vs variant ($VARIANT_MAPPNG in ambiguity panels) ==="
    say "baseline: $BASE_SOL"
    say "variant : $VAR_SOL"
    say ""
    # SINEX text diff first: identical means the question is closed outright.
    scripts/compare_solutions.sh "$BASE_SOL" "$VAR_SOL" 'FIN_*.SNX.gz'
    local rc=$?
    say ""
    if [ "$rc" -eq 0 ]; then
        say "VERDICT: solutions are identical. The GMF/Niell split does not affect"
        say "         the result at all. Resolve GEO-002 on style grounds and launch 2025."
    else
        say "The solutions differ, so the magnitude decides. Per-station coordinate"
        say "differences follow -- read these in mm, against a ~3 mm daily"
        say "repeatability and the ~40 mm/yr signal the velocities carry."
        say ""
        scripts/compare_coords.py "$BASE_SOL" "$VAR_SOL" 2>/dev/null \
            || say "  (no compare_coords.py yet -- inspect the SINEX diff above)"
    fi
    return 0
}

teardown() {
    say "=== removing variant configuration ==="
    for p in $VARIANT_PANELS; do
        rm -rf "$U/OPT/${p}_${VARIANT_TAG}" && say "  removed OPT/${p}_${VARIANT_TAG}"
    done
    rm -f "$U/PCF/$VARIANT_PCF.PCF" && say "  removed PCF/$VARIANT_PCF.PCF"
    say ""
    say "NOT removed (delete by hand once the answer is recorded):"
    say "  campaign  $P/$VARIANT_CAMPAIGN"
    say "  solutions $S/$VARIANT_CAMPAIGN"
    say "The baseline was never touched."
}

case "${1:-}" in
    --setup)    setup ;;
    --run)      run_days ;;
    --compare)  compare ;;
    --teardown) teardown ;;
    *) die "usage: $0 --setup | --run | --compare | --teardown" ;;
esac
