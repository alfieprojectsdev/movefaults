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

# NAMES ARE PREFIXED because LOADGPS.setvar exports a large set of short
# uppercase variables -- P D U C T S SRC XG XQ PCF PAN OPT SCR and more -- and
# it is sourced BELOW this block, so anything sharing a name is silently
# overwritten before first use. `PCF=LUZON_DLY` became `$U/PCF` that way and the
# first launch died looking for
# `/home/gps3/GPSUSER/PCF//home/gps3/BERN54/USER/PCF.PCF`. That was the fourth
# such collision in this campaign ($SRC, $S, $P before it), so the fix is the
# naming rule, not another rename. The assertion after the source enforces it.
LUZON_YEAR="${LUZON_YEAR:-2025}"
LUZON_DOY_FROM="${LUZON_DOY_FROM:-121}"
LUZON_DOY_TO="${LUZON_DOY_TO:-151}"
LUZON_PCF="${LUZON_PCF:-LUZON_DLY}"

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
#   058 059 060 061 079 345 — fewer than three reference stations available
#         (2026-08-24 survey of $D/RINEX3). Three is the minimum for a Helmert
#         transformation, so these days cannot be tied to the reference frame
#         at all. A solution would still be produced and would still look like
#         a solution. Same reasoning as 139: a missing day is honest, a
#         degenerate one is a trap.
LUZON_SKIP_DOYS="${LUZON_SKIP_DOYS:-139 58 59 60 61 79 345}"
LUZON_LOG_DIR="$HOME/luzon-month-logs"
LUZON_SUMMARY="$LUZON_LOG_DIR/summary.txt"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Snapshot the config so the source below cannot change it unnoticed. This
# catches the whole collision class rather than the one name that bit us.
_snap="$LUZON_YEAR|$LUZON_DOY_FROM|$LUZON_DOY_TO|$LUZON_PCF|$LUZON_SKIP_DOYS|$LUZON_LOG_DIR"

# shellcheck disable=SC1090
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || die "cannot source LOADGPS.setvar"

if [ "$_snap" != "$LUZON_YEAR|$LUZON_DOY_FROM|$LUZON_DOY_TO|$LUZON_PCF|$LUZON_SKIP_DOYS|$LUZON_LOG_DIR" ]; then
    die "LOADGPS.setvar overwrote a config variable — rename it with a LUZON_ prefix"
fi
if [ -z "${P:-}" ] || [ -z "${U:-}" ] || [ -z "${S:-}" ]; then
    die "P/U/S unset after LOADGPS"
fi
[ -f "$U/PCF/$LUZON_PCF.PCF" ]      || die "$U/PCF/$LUZON_PCF.PCF not found"
[ -x "$U/SCRIPT/luzon_pcs.pl" ] || die "driver missing: $U/SCRIPT/luzon_pcs.pl"

mkdir -p "$LUZON_LOG_DIR"

# One instance only. A second concurrent BPE on the same campaign would corrupt
# the working directories both are using.
LOCK="$HOME/.run_luzon_month.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
    die "another run holds $LOCK — remove it if no BPE is running"
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

{
    echo "=== LUZON month run: $LUZON_YEAR DOY $LUZON_DOY_FROM-$LUZON_DOY_TO ==="
    echo "started : $(date '+%F %T')"
    echo "PCF     : $LUZON_PCF   (V_PCV=$(grep -oE '^V_PCV *= *\S+' "$U/PCF/$LUZON_PCF.PCF" | awk '{print $3}' | tr -d ';'))"
    echo "campaign: $P/LUZON"
    echo
} | tee "$LUZON_SUMMARY"

ok=0; failed=0; skipped=0; excluded=0; failed_days=""
start_all=$(date +%s)

for doy in $(seq "$LUZON_DOY_FROM" "$LUZON_DOY_TO"); do
    d3=$(printf '%03d' "$doy")
    sess="${d3}0"
    log="$LUZON_LOG_DIR/luzon-$LUZON_YEAR$sess.log"

    case " $LUZON_SKIP_DOYS " in
        *" $doy "*)
            printf '  DOY %s  EXCLUDED (insufficient observations — see SKIP_DOYS)\n' \
              "$d3" | tee -a "$LUZON_SUMMARY"
            excluded=$((excluded + 1))
            continue
            ;;
    esac

    # Idempotence: SAVEDISK is where R2S_SAV archives the final solution, so a
    # completed day is evident there even after R2S_DEL cleans the campaign.
    # Archived name is FIN_<yyyy><ddd>0.SNX.gz — four-digit year, and gzipped
    # by R2S_SAV. An earlier version looked for a two-digit year in a directory
    # that does not exist, so every day would have re-run.
    if ls "$S/LUZON/$LUZON_YEAR/SOL/FIN_${LUZON_YEAR}${sess}."* >/dev/null 2>&1; then
        printf '  DOY %s  SKIP (already done)\n' "$d3" | tee -a "$LUZON_SUMMARY"
        skipped=$((skipped + 1))
        continue
    fi

    t0=$(date +%s)
    printf '  DOY %s  start %s ... ' "$d3" "$(date '+%H:%M:%S')" | tee -a "$LUZON_SUMMARY"

    echo "start: $(date '+%F %T')" > "$log"
    perl "$U/SCRIPT/luzon_pcs.pl" "$LUZON_YEAR" "$sess" "$LUZON_PCF" >> "$log" 2>&1
    rc=$?
    echo "BPE_EXIT=$rc end: $(date '+%F %T')" >> "$log"
    dt=$(( $(date +%s) - t0 ))

    # The BPE's own summary decides, not the exit code — consistent with how
    # every other check in this project treats exit statuses.
    #
    # But the summary must be THIS day's. LUZON_DLY.OUT is rewritten in place
    # each run, so a day whose BPE never started leaves the PREVIOUS day's file
    # sitting there saying "OK: 1 Error: 0" — and the day is scored OK having
    # verified nothing. A dry run of this loop scored all thirty days OK from
    # one stale file. So: the file must be at least as new as this day's start.
    out="$P/LUZON/BPE/$LUZON_PCF.OUT"
    fresh=no
    if [ -f "$out" ] && [ "$(stat -c %Y "$out")" -ge "$t0" ]; then
        fresh=yes
    fi

    if [ "$fresh" = no ]; then
        printf 'FAIL (%02d:%02d) — BPE produced no summary (exit %s); see %s\n' \
          $((dt / 60)) $((dt % 60)) "$rc" "$(basename "$log")" | tee -a "$LUZON_SUMMARY"
        failed=$((failed + 1)); failed_days="$failed_days $d3"
    elif grep -qE 'Sessions finished: *OK: *1 +Error: *0' "$out" 2>/dev/null; then
        printf 'OK   (%02d:%02d)\n' $((dt / 60)) $((dt % 60)) | tee -a "$LUZON_SUMMARY"
        ok=$((ok + 1))
    else
        err=$(grep -oE "[0-9]{3}_[0-9]{3} +\S+" "$out" 2>/dev/null \
              | tail -1 | awk '{print $2}')
        printf 'FAIL (%02d:%02d) at %s — see %s\n' \
          $((dt / 60)) $((dt % 60)) "${err:-unknown}" "$(basename "$log")" | tee -a "$LUZON_SUMMARY"
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
        echo "  excluded days: $LUZON_SKIP_DOYS (data gaps, not failures — see script header)"
    fi
    echo
    echo "  Solutions: \$S/LUZON/$LUZON_YEAR/SOL/ (archived by R2S_SAV)"
    echo
    echo "  REMINDER: this ran under I20. The coordinates are NOT comparable"
    echo "  with Abegail's I14 solutions — see runbook §1.4 and §4b.6."
} | tee -a "$LUZON_SUMMARY"

exit "$failed"
