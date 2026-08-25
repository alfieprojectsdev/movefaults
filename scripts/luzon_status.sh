#!/usr/bin/env bash
# luzon_status.sh — one-screen status of the LUZON reprocessing run.
#
# INDEPENDENT OF ANY ASSISTANT SESSION. Plain bash and cron. Run it over SSH,
# put it in crontab, or both:
#
#   ssh gps3 repos/movefaults_clean/scripts/luzon_status.sh
#   watch -n 300 'ssh gps3 repos/movefaults_clean/scripts/luzon_status.sh'
#
# EXIT CODE carries the headline, so it can drive other things:
#   0  running normally
#   1  finished (no driver, nothing left to do)
#   2  STALLED  -- driver alive but no new solution for --stall-min
#   3  driver is gone with work outstanding
#
# EMAIL is optional and off unless a config file exists. See --email below.
set -uo pipefail

YEAR="${LUZON_STATUS_YEAR:-2025}"
TARGET_NEW=328          # days this run is meant to produce
KEPT=30                 # solved 2026-08-06 and deliberately retained
STALL_MIN="${LUZON_STALL_MIN:-45}"
STATE="$HOME/.luzon_status_state"
MAILRC="$HOME/.luzon_mail.conf"

EMAIL=no
[ "${1:-}" = "--email" ] && EMAIL=yes

# shellcheck disable=SC1090,SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || {
    echo "ERROR: cannot source LOADGPS.setvar" >&2; exit 3; }

SOL="$S/LUZON/$YEAR/SOL"
LOG="$HOME/luzon-year.log"

tot=$(find "$SOL" -name "FIN_${YEAR}*.SNX.gz" 2>/dev/null | wc -l)
new=$(( tot - KEPT ))
[ "$new" -lt 0 ] && new=0
pct=$(( new * 100 / TARGET_NEW ))
# `pgrep -c` PRINTS 0 and EXITS NON-ZERO when nothing matches, so the obvious
# `|| echo 0` appends a second zero and yields "0\n0". Every integer test on
# that then fails with "integer expression expected" -- and the driver-gone
# branch never fires, so a FINISHED run reports RUNNING forever. Count lines
# instead: no output means no matches, and `wc -l` says 0 without an exit-code
# trick.
driver=$(pgrep -f 'run_luzon_yea[r]\.sh' 2>/dev/null | wc -l)
jobs=$(pgrep -f 'RUNBP[E]|GPSES[T]|MAUPR[P]' 2>/dev/null | wc -l)
camps=$(find "$P" -maxdepth 1 -name 'LZY*' 2>/dev/null | wc -l)
block=$(grep -oE 'DOY [0-9]{3}-[0-9]{3}' "$LOG" 2>/dev/null | tail -1)
load=$(cut -d' ' -f1-3 /proc/loadavg)
disk=$(df -h "$S" | awk 'NR==2{print $4" free ("$5" used)"}')

# Stall detection needs memory between runs: compare against the count and
# timestamp recorded last time. Without this, "no progress" and "slow day" are
# indistinguishable from a single sample.
now=$(date +%s); prev_n=-1; prev_t=$now
if [ -r "$STATE" ]; then
    read -r _n _t < "$STATE" 2>/dev/null
    # Both fields must be integers or the file is ignored. An empty or
    # truncated state file otherwise leaves these unset, and the arithmetic
    # below then treats "" as 0 -- which dates the last progress to 1970 and
    # reports STALLED on a perfectly healthy run. A false alarm at 3am is
    # worse than no alarm, because it is the one that gets the alerting
    # switched off.
    case "${_n:-}${_t:-}" in
        *[!0-9]*|"") : ;;                       # non-numeric or empty: ignore
        *) prev_n="$_n"; prev_t="$_t" ;;
    esac
fi
if [ "$new" -gt "$prev_n" ]; then
    printf '%s %s\n' "$new" "$now" > "$STATE"
    since=0
else
    since=$(( (now - prev_t) / 60 ))
fi

status="RUNNING"; code=0
if [ "$driver" -eq 0 ]; then
    if [ "$new" -ge "$TARGET_NEW" ]; then status="FINISHED"; code=1
    else status="DRIVER GONE — $(( TARGET_NEW - new )) days outstanding"; code=3; fi
elif [ "$since" -ge "$STALL_MIN" ]; then
    status="STALLED — no new solution in ${since} min"; code=2
fi

bar_w=32; filled=$(( pct * bar_w / 100 ))
bar=$(printf '%*s' "$filled" '' | tr ' ' '#')$(printf '%*s' "$(( bar_w - filled ))" '')

read -r -d '' REPORT <<EOF
LUZON ${YEAR} reprocessing — $(date '+%F %H:%M:%S %Z')
$(printf '%.0s-' {1..58})
  status     ${status}
  progress   [${bar}] ${pct}%
  solutions  ${new} / ${TARGET_NEW} new   (${tot} on disk, incl. ${KEPT} kept)
  block      ${block:-unknown}
  sessions   ${camps} campaigns, ${jobs} BPE jobs
  load       ${load}
  disk       ${disk}

$(grep -E "solved  \(" "$LOG" 2>/dev/null | tail -6 | sed 's/^ */  /')
EOF

printf '%s\n' "$REPORT"

if [ "$EMAIL" = yes ]; then
    if [ ! -r "$MAILRC" ]; then
        echo "  (email requested but $MAILRC not found — see scripts/README-status-email.md)" >&2
    else
        # shellcheck disable=SC1090
        . "$MAILRC"
        subj="LUZON ${YEAR}: ${new}/${TARGET_NEW} — ${status%% *}"
        {
            printf 'From: %s\nTo: %s\nSubject: %s\n\n' "$MAIL_FROM" "$MAIL_TO" "$subj"
            printf '%s\n' "$REPORT"
        } | curl -sS --ssl-reqd --url "$MAIL_URL" \
                 --mail-from "$MAIL_FROM" --mail-rcpt "$MAIL_TO" \
                 --user "$MAIL_USER:$MAIL_PASS" --upload-file - \
            && echo "  (emailed $MAIL_TO)" \
            || echo "  (email FAILED — run remains unaffected)" >&2
    fi
fi

exit "$code"
