#!/usr/bin/env bash
# ============================================================================
# run_pagenet_week.sh — finish the PAGENET 7-day weekly BPE run, unattended.
#
# Processes daily sessions 084..090 through the PAGENET_DLY PCF (modules 1-14,
# PID 001->514) headless via Bernese startBPE. Idempotent: skips any day whose
# final normal-equation file (FIN_2026<doy>0.NQ0) already exists, so it safely
# resumes wherever a previous run stopped.
#
# USAGE
#   ./run_pagenet_week.sh                 # foreground (watch it run)
#   ./run_pagenet_week.sh --detach        # background, survives logout/SSH drop
#   ./run_pagenet_week.sh 087 088 089 090 # only these days (default: 084..090)
#   ./run_pagenet_week.sh --detach 087 088 089 090
#   tail -f ~/run_pagenet_week.log        # follow progress when detached
#
# After all 7 dailies exist -> Phase B (fix PGN_WK panel) + Phase C (ADD_WK
# weekly combine). See ~/RESUME_pagenet_week.md.
# ============================================================================
set -u

# ---- config -----------------------------------------------------------------
LOADGPS="$HOME/BERN54/LOADGPS.setvar"
PCF="PAGENET_DLY"
YEAR="2026"
DEFAULT_DAYS="084 085 086 087 088 089 090"
LOG="$HOME/run_pagenet_week.log"
LOCK="$HOME/.run_pagenet_week.lock"

# ---- arg parse --------------------------------------------------------------
DETACH=0
DAYS=""
for a in "$@"; do
  case "$a" in
    --detach) DETACH=1 ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) DAYS="$DAYS $a" ;;
  esac
done
DAYS="${DAYS:-$DEFAULT_DAYS}"

# ---- re-exec detached if requested ------------------------------------------
if [ "$DETACH" = "1" ]; then
  # strip --detach, relaunch in own session, no controlling terminal.
  # $DAYS intentionally unquoted: each day must become a separate argument.
  # shellcheck disable=SC2086
  setsid nohup "$0" $DAYS > "$LOG" 2>&1 < /dev/null &
  echo "detached (PID $!). follow: tail -f $LOG"
  exit 0
fi

# ---- environment ------------------------------------------------------------
# shellcheck disable=SC1090
source "$LOADGPS" >/dev/null 2>&1 || { echo "FATAL: cannot source $LOADGPS"; exit 1; }
DRIVER="$U/SCRIPT/pagenet_pcs.pl"
SOL="$P/PAGENET/SOL"
[ -f "$DRIVER" ] || { echo "FATAL: driver not found: $DRIVER"; exit 1; }
[ -f "$U/PCF/${PCF}.PCF" ] || { echo "FATAL: PCF not found: $U/PCF/${PCF}.PCF"; exit 1; }

log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }

# ---- single-instance lock ---------------------------------------------------
if [ -e "$LOCK" ]; then
  oldpid=$(cat "$LOCK" 2>/dev/null)
  if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
    log "ABORT: another run is active (PID $oldpid). Lock: $LOCK"
    exit 1
  fi
  log "stale lock (PID ${oldpid:-?} dead) — removing"
fi
echo $$ > "$LOCK"
trap 'rm -f "$LOCK"' EXIT

# ---- wait for any in-flight BPE to clear ------------------------------------
if pgrep -x RUNBPE >/dev/null 2>&1; then
  log "in-flight BPE detected — waiting for it to finish before starting..."
  while pgrep -x RUNBPE >/dev/null 2>&1; do sleep 30; done
fi

# ---- main loop --------------------------------------------------------------
log "=== PAGENET week run. days:$DAYS ==="
done_cnt=0; skip_cnt=0; fail=0
for doy in $DAYS; do
  sess="${doy}0"
  nq="$SOL/FIN_${YEAR}${sess}.NQ0"
  if [ -f "$nq" ]; then
    log "SKIP $sess — already done ($(basename "$nq") exists)"
    skip_cnt=$((skip_cnt+1))
    continue
  fi
  log "--- START $sess ---"
  start=$(date +%s)
  perl "$DRIVER" "$YEAR" "$sess" "$PCF" >> "$LOG" 2>&1
  rc=$?
  el=$(( $(date +%s) - start ))
  if [ "$rc" -ne 0 ] || [ ! -f "$nq" ]; then
    log "FAIL $sess (rc=$rc) after $((el/60))m$((el%60))s — FIN NQ $([ -f "$nq" ] && echo OK || echo MISSING)"
    # diagnostic: which PID/program errored + likely station
    errline=$(grep -iE "Script finished  ERROR" "$P/PAGENET/BPE/${PCF}.OUT" 2>/dev/null | tail -1)
    [ -n "$errline" ] && log "  errored step: $errline"
    logglob="$P/PAGENET/BPE/RS${YEAR}${sess}"
    badsta=$(grep -hiE "RINEX station name not listed|Station name +:" "${logglob}"_*.LOG 2>/dev/null | tail -3)
    [ -n "$badsta" ] && log "  station hint: $badsta"
    log "  -> fix, then re-run: ~/run_pagenet_week.sh $doy $(echo "$DAYS" | tr ' ' '\n' | sed -n "/^$doy\$/,\$p" | tail -n +2 | tr '\n' ' ')"
    fail=1
    break
  fi
  log "DONE $sess in $((el/60))m$((el%60))s -> $(basename "$nq")"
  done_cnt=$((done_cnt+1))
done

# ---- summary ----------------------------------------------------------------
log "=== run ended. new:$done_cnt skipped:$skip_cnt $([ "$fail" = 1 ] && echo 'HALTED-ON-ERROR' || echo 'all requested days present') ==="
log "FIN NQ inventory:"
present=0
for d in 0840 0850 0860 0870 0880 0890 0900; do
  f="$SOL/FIN_${YEAR}${d}.NQ0"
  if [ -f "$f" ]; then
    log "  FIN_${YEAR}${d}.NQ0  $(stat -c%y "$f" | cut -d. -f1)"
    present=$((present+1))
  else
    log "  FIN_${YEAR}${d}.NQ0  --"
  fi
done
if [ "$fail" = 0 ] && [ "$present" -ge 7 ]; then
  log "ALL 7 DAILIES PRESENT -> next: Phase B (fix PGN_WK panel) + Phase C (ADD_WK weekly). See ~/RESUME_pagenet_week.md"
fi
exit "$fail"
