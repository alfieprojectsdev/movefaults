#!/usr/bin/env bash
# run_luzon_month.sh — process 2025 DOY 121-151 through the LUZON_DLY PCF.
#
# Follows the pattern proven by run_pagenet_week.sh: idempotent, resumable,
# one log per day, safe to re-run after an interruption.
#
# ⚠ WHAT THIS RUN IS AND IS NOT
# It runs under **I20**, not the I14 configuration Abegail used. That is a
# deliberate choice, not an oversight: I14's satellite tables end in 2023 and
# AIUB no longer publishes them, and the I14 ANTEX fails 5.4's SVN/PRN
# consistency check (runbook §4b.6). So:
#
#   * This IS a pipeline test — does the chain execute end to end, unattended,
#     over a month of real data. That is BRN-001 acceptance evidence.
#   * This is NOT a comparison with her results. The coordinates carry an
#     I14→I20 frame and antenna-model difference of centimetre scale,
#     concentrated in the Up component (runbook §1.4). Do not difference these
#     against F1_25*.SNX and report the residual as a Bernese-version effect.
#
# IDEMPOTENCE: a day whose FIN_2025<doy>0.NQ0 already exists in SAVEDISK is
# skipped. Re-running after a crash resumes rather than redoing.
#
# CONTINUE ON ERROR: a failed day is recorded and the run moves on. For a first
# month-long pass, collecting 30 good days plus one diagnosable failure beats
# halting at hour two and learning nothing about the rest.
set -uo pipefail

YEAR=2025
DOY_FROM=121
DOY_TO=151
PCF=LUZON_DLY

# Days excluded for want of data, NOT for convenience. Each needs a reason.
#
#   139 — our copy of her DATAPOOL holds ONE RINEX2 station for this day
#         (TGDN) where every neighbouring day holds 25. She did solve it
#         (F1_251390.SNX exists), so the observations existed at processing
#         time and our copy of that day is incomplete. Running it anyway
#         would yield a solution from the nine fiducials alone — TGDN is one
#         of the two stations the DOY 121 run dropped — and that file would
#         sit in SOL/ beside thirty proper ones, indistinguishable without
#         opening it. A missing day is honest; a degenerate one is a trap.
SKIP_DOYS="139"
LOG_DIR="$HOME/luzon-month-logs"
SUMMARY="$LOG_DIR/summary.txt"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# shellcheck disable=SC1090
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || die "cannot source LOADGPS.setvar"
if [ -z "${P:-}" ] || [ -z "${U:-}" ] || [ -z "${S:-}" ]; then
    die "P/U/S unset after LOADGPS"
fi
[ -f "$U/PCF/$PCF.PCF" ]      || die "$U/PCF/$PCF.PCF not found"
[ -x "$U/SCRIPT/luzon_pcs.pl" ] || die "driver missing: $U/SCRIPT/luzon_pcs.pl"

mkdir -p "$LOG_DIR"

# One instance only. A second concurrent BPE on the same campaign would corrupt
# the working directories both are using.
LOCK="$HOME/.run_luzon_month.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
    die "another run holds $LOCK — remove it if no BPE is running"
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
    echo "=== LUZON month run: $YEAR DOY $DOY_FROM-$DOY_TO ==="
    echo "started : $(date '+%F %T')"
    echo "PCF     : $PCF   (V_PCV=$(grep -oE '^V_PCV *= *\S+' "$U/PCF/$PCF.PCF" | awk '{print $3}' | tr -d ';'))"
    echo "campaign: $P/LUZON"
    echo
} | tee "$SUMMARY"

ok=0; failed=0; skipped=0; excluded=0; failed_days=""
start_all=$(date +%s)

for doy in $(seq "$DOY_FROM" "$DOY_TO"); do
    d3=$(printf '%03d' "$doy")
    sess="${d3}0"
    log="$LOG_DIR/luzon-$YEAR$sess.log"

    case " $SKIP_DOYS " in
        *" $doy "*)
            printf '  DOY %s  EXCLUDED (insufficient observations — see SKIP_DOYS)\n' \
              "$d3" | tee -a "$SUMMARY"
            excluded=$((excluded + 1))
            continue
            ;;
    esac

    # Idempotence: SAVEDISK is where R2S_SAV archives the final solution, so a
    # completed day is evident there even after R2S_DEL cleans the campaign.
    # Archived name is FIN_<yyyy><ddd>0.SNX.gz — four-digit year, and gzipped
    # by R2S_SAV. An earlier version looked for a two-digit year in a directory
    # that does not exist, so every day would have re-run.
    if ls "$S/LUZON/$YEAR/SOL/FIN_${YEAR}${sess}."* >/dev/null 2>&1; then
        printf '  DOY %s  SKIP (already done)\n' "$d3" | tee -a "$SUMMARY"
        skipped=$((skipped + 1))
        continue
    fi

    t0=$(date +%s)
    printf '  DOY %s  start %s ... ' "$d3" "$(date '+%H:%M:%S')" | tee -a "$SUMMARY"

    echo "start: $(date '+%F %T')" > "$log"
    perl "$U/SCRIPT/luzon_pcs.pl" "$YEAR" "$sess" "$PCF" >> "$log" 2>&1
    rc=$?
    echo "BPE_EXIT=$rc end: $(date '+%F %T')" >> "$log"
    dt=$(( $(date +%s) - t0 ))

    # The BPE's own summary decides, not the exit code — consistent with how
    # every other check in this project treats exit statuses.
    if grep -qE 'Sessions finished: *OK: *1 +Error: *0' "$P/LUZON/BPE/$PCF.OUT" 2>/dev/null; then
        printf 'OK   (%02d:%02d)\n' $((dt / 60)) $((dt % 60)) | tee -a "$SUMMARY"
        ok=$((ok + 1))
    else
        err=$(grep -oE '[0-9]{3}_[0-9]{3} +\S+' "$P/LUZON/BPE/$PCF.OUT" 2>/dev/null \
              | tail -1 | awk '{print $2}')
        printf 'FAIL (%02d:%02d) at %s — see %s\n' \
          $((dt / 60)) $((dt % 60)) "${err:-unknown}" "$(basename "$log")" | tee -a "$SUMMARY"
        failed=$((failed + 1)); failed_days="$failed_days $d3"
    fi
done

{
    total=$(( $(date +%s) - start_all ))
    echo
    echo "=== finished $(date '+%F %T') ==="
    printf '  OK %s   FAILED %s   SKIPPED %s   EXCLUDED %s   elapsed %02d:%02d:%02d\n' \
      "$ok" "$failed" "$skipped" "$excluded" \
      $((total/3600)) $(((total%3600)/60)) $((total%60))
    if [ -n "$failed_days" ]; then echo "  failed days:$failed_days"; fi
    if [ "$excluded" -gt 0 ]; then
        echo "  excluded days: $SKIP_DOYS (data gaps, not failures — see script header)"
    fi
    echo
    echo "  Solutions: \$S/LUZON/$YEAR/SOL/ (archived by R2S_SAV)"
    echo
    echo "  REMINDER: this ran under I20. The coordinates are NOT comparable"
    echo "  with Abegail's I14 solutions — see runbook §1.4 and §4b.6."
} | tee -a "$SUMMARY"

exit "$failed"
