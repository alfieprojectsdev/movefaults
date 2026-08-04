#!/usr/bin/env bash
# processed_transfer.sh — copy the Bernese 5.2 LUZON processed set from the
# DOSTB drive to /srv/gnss-archive/processed/, then census both sides.
#
# WHAT THIS IS
# `processing_files/` (~22 GB) is a complete processed run of the LUZON network
# from Abegail, produced under Bernese 5.2. It is one of exactly two paths on
# that personal drive which are in scope — see README_FOR_GPS3_CLAUDE.md §0.
#
# WHY IT MATTERS MORE THAN ITS SIZE SUGGESTS
# 21.6 GB of the 22 GB is one month of intermediates: DOY 121-151 of 2025, 25
# stations, plus OBS/ORB/ATM/OUT. The remaining 406 MB is
# GPSDATA/CAMPAIGN/LUZON/SOL/, and that directory holds **725 weekly and 166
# monthly combined solutions spanning 2010-02-28 to 2026-04-12** — sixteen years
# of results. The raw data those were computed from is NOT on this drive, so
# they cannot be regenerated here: reproducing them needs ~15 years of RINEX
# that lives on staff machines. The smallest directory in the tree is the
# irreplaceable one.
#
# WHY IT DOES NOT GO IN legacy/
# /srv/gnss-archive/legacy/ holds material rescued from dead hardware. This is a
# current, working product from a live staff machine. Mixing the two would make
# "where did this come from" unanswerable later, which is the failure the
# continuity audit is about.
#
# DIFFERENCE FROM archive_transfer.sh
# That script tees everything, including rsync's --info=progress2 output, which
# emits a carriage-return update per file. On the 157 GB run it produced an
# 11.2 MB log in which the structured results were buried. Here rsync writes
# progress to the terminal only; the log gets structured lines. Same censusing,
# readable output.
#
# Usage:
#   sudo scripts/sudo/processed_transfer.sh --dry-run
#   sudo scripts/sudo/processed_transfer.sh --apply
set -uo pipefail

SRC="/mnt/dostb/processing_files"
DEST="/srv/gnss-archive/processed/luzon-bern52"
LOGDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/processed-transfer-$STAMP.log"
MODE="${1:-}"

# The scientifically densest subtree — copied first, so an interrupted run still
# secures the 16-year solution series.
PRIORITY_REL="GPSDATA/CAMPAIGN/LUZON/SOL"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Structured output goes to BOTH terminal and log. rsync's progress goes to the
# terminal alone — that is the whole point of not wrapping this in a pipeline.
log() { printf '%s\n' "$*" | tee -a "$LOG"; }

[ "$(id -u)" -eq 0 ] || die "needs root — run with sudo"
case "$MODE" in
    --dry-run|--apply) ;;
    *) die "usage: $0 --dry-run | --apply" ;;
esac

mountpoint -q /mnt/dostb || die "/mnt/dostb is not mounted — run scripts/sudo/mount_dostb.sh first"
[ -d "$SRC" ]            || die "$SRC does not exist — wrong drive?"
mountpoint -q /srv/gnss-archive || die "/srv/gnss-archive is not a mountpoint — refusing to write to the root filesystem"

# Confirm the source really is read-only. This drive is single-copy for material
# rescued from dead hardware; a writable mount is a standing hazard even when
# this script itself only reads.
opts=$(findmnt -n -o OPTIONS --target /mnt/dostb 2>/dev/null)
case "$opts" in
    ro|ro,*|*,ro|*,ro,*) ;;
    *) die "/mnt/dostb is NOT mounted read-only (options: $opts) — remount before proceeding" ;;
esac

# Bulk I/O and a headless BPE must not overlap; BPE hangs. Exclude this script's
# own command line, since pgrep -f matches itself — that has produced false
# readings on this machine three times.
busy=$(pgrep -af 'rnx2snx|RUNBPE|startBPE|pagenet_pcs' 2>/dev/null | grep -v "$$" | grep -v processed_transfer || true)
[ -z "$busy" ] || { printf '%s\n' "$busy"; die "Bernese processing is running — wait for it"; }

mkdir -p "$LOGDIR"

census() {
    # Files, symlinks, dirs, other, bytes — counted independently. rsync's exit
    # code describes neither completeness nor correctness: it exits 0 having
    # skipped unreadable files and 23 on a run that copied 99.99%.
    local root="$1" f l d o b
    f=$(find "$root" -xdev -type f 2>/dev/null | wc -l)
    l=$(find "$root" -xdev -type l 2>/dev/null | wc -l)
    d=$(find "$root" -xdev -type d 2>/dev/null | wc -l)
    o=$(find "$root" -xdev ! -type f ! -type l ! -type d 2>/dev/null | wc -l)
    b=$(find "$root" -xdev -type f -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {print s+0}')
    printf '%s %s %s %s %s' "$f" "$l" "$d" "$o" "$b"
}

show_census() {
    local -a c
    read -r -a c <<<"$1"
    log "$(printf '    files %-9s symlinks %-5s dirs %-7s other %-4s bytes %s (%.2f GiB)' \
      "${c[0]}" "${c[1]}" "${c[2]}" "${c[3]}" "${c[4]}" \
      "$(awk -v x="${c[4]}" 'BEGIN{print x/1073741824}')")"
}

log "=== processed-set transfer $STAMP  (mode: $MODE) ==="
log "src : $SRC"
log "dest: $DEST"
log ""
log "Source subtrees:"
for d in "$SRC"/*/; do
    log "$(printf '  %-24s %s' "$(basename "$d")" "$(du -sh "$d" 2>/dev/null | cut -f1)")"
done
log ""
log "Destination free: $(df -h /srv/gnss-archive | tail -1 | awk '{print $4}')"
log ""

SRC_CENSUS=$(census "$SRC")
log "Source census (whole tree):"
show_census "$SRC_CENSUS"
log ""
log "Priority subtree $PRIORITY_REL — 16 years of weekly/monthly solutions:"
show_census "$(census "$SRC/$PRIORITY_REL")"
log ""

if [ "$MODE" = "--dry-run" ]; then
    log "Dry run — nothing copied. Re-run with --apply."
    log "log: $LOG"
    exit 0
fi

mkdir -p "$DEST"

# --- pass 1: the irreplaceable subtree, first and alone --------------------
log "--- copying PRIORITY subtree first: $PRIORITY_REL ---"
mkdir -p "$DEST/$PRIORITY_REL"
rsync -aHAX --partial --info=progress2 "$SRC/$PRIORITY_REL/" "$DEST/$PRIORITY_REL/"
rc_prio=$?
log "  rsync exit: $rc_prio"
log ""

# --- pass 2: everything else ----------------------------------------------
log "--- copying the full tree ---"
rsync -aHAX --partial --info=progress2 "$SRC/" "$DEST/"
rc_full=$?
log "  rsync exit: $rc_full"
log ""

# --- census both sides -----------------------------------------------------
log "=== census: source vs destination ==="
DST_CENSUS=$(census "$DEST")
log "  WHOLE TREE"
log "    SRC :"; show_census "$SRC_CENSUS"
log "    DEST:"; show_census "$DST_CENSUS"

read -r -a s <<<"$SRC_CENSUS"
read -r -a t <<<"$DST_CENSUS"
rc_worst=0
if [ "${s[0]}" -eq "${t[0]}" ] && [ "${s[4]}" -eq "${t[4]}" ]; then
    log "    MATCH on files and bytes"
else
    log "    *** MISMATCH: files ${s[0]} vs ${t[0]}, bytes ${s[4]} vs ${t[4]} ***"
    rc_worst=1
fi
log ""

log "  PRIORITY SUBTREE ($PRIORITY_REL)"
ps_src=$(census "$SRC/$PRIORITY_REL"); ps_dst=$(census "$DEST/$PRIORITY_REL")
log "    SRC :"; show_census "$ps_src"
log "    DEST:"; show_census "$ps_dst"
read -r -a ps <<<"$ps_src"
read -r -a pt <<<"$ps_dst"
if [ "${ps[0]}" -eq "${pt[0]}" ] && [ "${ps[4]}" -eq "${pt[4]}" ]; then
    log "    MATCH — the 16-year solution series is secured"
else
    log "    *** MISMATCH IN THE PRIORITY SUBTREE — this is the irreplaceable one ***"
    rc_worst=1
fi
log ""

# --- provenance stamp, written beside the data -----------------------------
if [ "$rc_worst" -eq 0 ]; then
    cat > "$DEST/PROVENANCE.txt" <<EOF
Bernese 5.2 LUZON processed set
===============================
Copied     : $STAMP
From       : DOSTB20150918 (NTFS, mounted read-only at /mnt/dostb)
Source path: processing_files/
Origin     : PHIVOLCS staff machine (Abegail's LUZON processing, Bernese 5.2)

Census at copy time (source and destination matched):
  whole tree : $SRC_CENSUS   (files symlinks dirs other bytes)
  SOL subtree: $ps_src

Contents of note:
  GPSDATA/DATAPOOL/LUZON/          741 RINEX obs, DOY 121-151 of 2025, 25 stations
  GPSDATA/CAMPAIGN/LUZON/SOL/      725 weekly + 166 monthly combined solutions,
                                   GPS weeks 1573-2414 = 2010-02-28 to 2026-04-12

The SOL series cannot be regenerated from this tree: the raw observations for
all but one month of those sixteen years are not here. They are on staff
machines and have not been captured.

NOT YET FIXED: no checksum manifest. Run
  /srv/gnss-archive/verify_archive.sh manifest
and commit the result to git.
EOF
    log "wrote $DEST/PROVENANCE.txt"
fi

log "==================================================================="
if [ "$rc_worst" -eq 0 ]; then
    log "Whole tree and priority subtree both match on files and bytes."
    log ""
    log "This is NOT yet 'the processed set is backed up'. Next:"
    log "  1. sha256 manifest, then commit the .gz to git."
    log "  2. Report what landed BY SUBTREE, not as one claim."
    log ""
    log "Note for planning: this is ONE MONTH of raw input against SIXTEEN YEARS"
    log "of solutions. The rest of the raw archive is on staff computers and is"
    log "not covered by this or any other copy."
else
    log "SOMETHING DID NOT MATCH. Do not report success."
fi
log "==================================================================="
log "log: $LOG"

exit "$rc_worst"
