#!/usr/bin/env bash
# run_luzon_year.sh — process a full year in parallel, in blocks.
#
# WHY BLOCKS RATHER THAN ONE CALL
# BSW's multi-session mode takes a first session and a count, and runs that
# many CONSECUTIVE sessions. It has no notion of "skip this day". Days that
# must not run therefore become block boundaries rather than a skip list.
#
# Two kinds of day are excluded, for different reasons:
#
#   already solved   121-138, 140-151 were processed 2026-08-06 under this
#                    same configuration and are being kept, not redone.
#   cannot be solved 058-061, 079, 139, 345 have fewer than three reference
#                    stations. Three is the minimum for a Helmert
#                    transformation, so there is no way to tie those days to
#                    the reference frame. BSW would still produce a file.
#
# PARALLELISM
# REPR_MODE gives each session a private campaign, which is what makes this
# safe -- the 2026-08-12 attempt with one shared campaign failed 4 of 5 at
# CCRNXO because sessions consumed each other's staged RINEX. Proven
# byte-identical against the sequential baseline over 5 sessions.
#
# MAXSESS defaults to 6. The proven figure is 5 and the box has 24 cores with
# an 11-job cap per session, so 5 was never obviously the ceiling -- but it is
# the only number measured. Six is a deliberate small step, not a guess at the
# optimum; watch the first block's rate before raising it. Oversubscription
# makes runs slower, not faster, and the failure is silent.
#
# CAMPAIGN CLEANUP
# The driver sets REPR_MODE_ON_SUCCESS=remove, unlike luzon_repr.pl which
# keeps campaigns for autopsy. luzon_repr.pl's own comment says to switch this
# for production "or the campaign area will grow without bound" -- at 365 days
# and ~283 MB each that is ~103 GB. Failed sessions are still KEPT, so
# anything worth diagnosing survives.
#
# Usage:
#   scripts/run_luzon_year.sh --plan     # print the blocks, run nothing
#   scripts/run_luzon_year.sh --run
set -uo pipefail

# NAMES ARE LUZON_-PREFIXED, and the defaults do NOT read the bare names.
# LOADGPS.setvar exports a large set of short uppercase variables -- P D U C T
# S SRC PCF PAN OPT and more. `PCF=LUZON_DLY` became $U/PCF that way in
# run_luzon_month.sh, and it happened again here: writing
# `PCF="${PCF:-LUZON_DLY}"` lets an already-polluted environment supply the
# value BEFORE the snapshot is taken, so the assertion below compares a bad
# value against itself and passes. The naming rule is the fix; an override
# spelled with the bare name reintroduces the bug it was meant to catch.
LUZON_YEAR="${LUZON_YEAR:-2025}"
LUZON_PCF="${LUZON_PCF:-LUZON_DLY}"
LUZON_MAXSESS="${LUZON_MAXSESS:-6}"
LOG_DIR="$HOME/luzon-year-logs"

# first:last, inclusive. Derived from the exclusions above.
BLOCKS="1:57 62:78 80:120 152:344 346:365"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

_snap="$LUZON_YEAR|$LUZON_PCF|$LUZON_MAXSESS|$BLOCKS|$LOG_DIR"
# shellcheck disable=SC1090,SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || die "cannot source LOADGPS.setvar"
[ "$_snap" = "$LUZON_YEAR|$LUZON_PCF|$LUZON_MAXSESS|$BLOCKS|$LOG_DIR" ] || die "LOADGPS clobbered a config variable"
if [ -z "${P:-}" ] || [ -z "${U:-}" ] || [ -z "${S:-}" ]; then die "P/U/S unset"; fi

DRV="$U/SCRIPT/luzon_year.pl"
[ -x "$DRV" ] || die "driver missing: $DRV"
[ -f "$U/PCF/$LUZON_PCF.PCF" ] || die "$U/PCF/$LUZON_PCF.PCF not found"

total=0
for b in $BLOCKS; do total=$(( total + ${b#*:} - ${b%:*} + 1 )); done

if [ "${1:-}" = "--plan" ]; then
    printf 'year %s   PCF %s   MAXSESS %s\n' "$LUZON_YEAR" "$LUZON_PCF" "$LUZON_MAXSESS"
    for b in $BLOCKS; do
        printf '  DOY %03d-%03d  (%d days)\n' "${b%:*}" "${b#*:}" \
               "$(( ${b#*:} - ${b%:*} + 1 ))"
    done
    printf '  total to process: %d days\n' "$total"
    printf '  already solved and kept: %d\n' \
      "$(find "$S/LUZON/$LUZON_YEAR/SOL" -name "FIN_${LUZON_YEAR}*.SNX.gz" 2>/dev/null | wc -l)"
    exit 0
fi
[ "${1:-}" = "--run" ] || die "usage: $0 --plan | --run"

mkdir -p "$LOG_DIR"
LOCK="$HOME/.run_luzon_year.lock"
mkdir "$LOCK" 2>/dev/null || die "another run holds $LOCK"
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

printf '=== LUZON %s, %d days in %d blocks, MAXSESS=%s ===\n' \
       "$LUZON_YEAR" "$total" "$(echo "$BLOCKS" | wc -w)" "$LUZON_MAXSESS"
printf 'started %s\n\n' "$(date '+%F %T')"
t_all=$(date +%s)

for b in $BLOCKS; do
    from="${b%:*}"; to="${b#*:}"
    n=$(( to - from + 1 ))
    sess=$(printf '%03d0' "$from")
    log="$LOG_DIR/block-$(printf '%03d-%03d' "$from" "$to").log"
    printf '  DOY %03d-%03d (%3d days)  start %s ... ' "$from" "$to" "$n" "$(date '+%H:%M:%S')"
    t0=$(date +%s)

    perl "$DRV" "$LUZON_YEAR" "$sess" "$LUZON_PCF" "$n" "$LUZON_MAXSESS" >"$log" 2>&1

    # Count solutions produced rather than trusting the exit code. A BPE that
    # reports success having written nothing has happened here before.
    made=0
    for d in $(seq "$from" "$to"); do
        ls "$S/LUZON/$LUZON_YEAR/SOL/FIN_${LUZON_YEAR}$(printf '%03d' "$d")0."* >/dev/null 2>&1 \
            && made=$((made + 1))
    done
    printf '%d/%d solved  (%d min)\n' "$made" "$n" "$(( ($(date +%s) - t0) / 60 ))"
done

printf '\nelapsed %s min\n' "$(( ($(date +%s) - t_all) / 60 ))"
printf 'solutions now in %s: %s\n' "$S/LUZON/$LUZON_YEAR/SOL" \
       "$(find "$S/LUZON/$LUZON_YEAR/SOL" -name "FIN_${LUZON_YEAR}*.SNX.gz" 2>/dev/null | wc -l)"
printf 'kept failed campaigns: %s\n' "$(find "$P" -maxdepth 1 -name 'LZY*' 2>/dev/null | wc -l)"
