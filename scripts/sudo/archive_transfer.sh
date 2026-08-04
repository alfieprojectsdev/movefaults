#!/usr/bin/env bash
# archive_transfer.sh — copy the RECOVERED_* legacy archive from the DOSTB
# drive onto /srv/gnss-archive/legacy, then census both sides.
#
# This is the project's Tier 0 item: it takes the legacy GNSS archive from ONE
# copy, on a personal drive holding material rescued from three dead disks, to
# TWO copies on independent hardware.
#
# WHY IT GLOBS RECOVERED_* INSTEAD OF TAKING A LIST
# The handover document listed three directories by name and omitted a fourth,
# RECOVERED_SEAGATE_W2A0W9T2_DATA0 — which by subtraction against the
# continuity audit's measured 157 G is roughly 131 G, and most likely holds the
# 125 G of raw observations. The one directory left out of the plan was the
# largest and least reproducible. A typed list cannot notice what it omits; a
# glob can. If a fifth directory appears, this copies it and says so.
#
# WHY IT CENSUSES INSTEAD OF TRUSTING rsync
# rsync exits 0 having skipped files it could not read, and exits 23 on a run
# that copied 99.99% successfully. Neither number describes what landed. Files,
# symlinks, directories and bytes are counted independently on both sides.
#
# EXPECT ZERO SYMLINKS on the source: the drive is NTFS. That is a property of
# the source, not a transfer failure — do not chase it.
#
# Usage:
#   sudo scripts/sudo/archive_transfer.sh --dry-run   # plan + source census
#   sudo scripts/sudo/archive_transfer.sh --apply     # copy, then census both
set -uo pipefail

SRC="/mnt/dostb"
DEST="/srv/gnss-archive/legacy"
LOGDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/logs"
STAMP="$(date +%Y%m%d-%H%M%S)"
LOG="$LOGDIR/archive-transfer-$STAMP.log"
MODE="${1:-}"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "needs root — run with sudo"
case "$MODE" in
    --dry-run|--apply) ;;
    *) die "usage: $0 --dry-run | --apply" ;;
esac

mountpoint -q "$SRC"  || die "$SRC is not mounted — run scripts/sudo/mount_dostb.sh first"
mountpoint -q /srv/gnss-archive || die "/srv/gnss-archive is not a mountpoint — refusing to write to the root filesystem"

# A bulk transfer and a headless BPE must not run together: BPE hangs under
# concurrent heavy I/O. Match on the real binaries, and exclude this script's
# own command line — pgrep -f matches itself, which has produced false
# readings on this machine three times.
busy=$(pgrep -af 'rnx2snx|RUNBPE|startBPE|pagenet_pcs' 2>/dev/null | grep -v "$$" | grep -v archive_transfer || true)
if [ -n "$busy" ]; then
    echo "REFUSING — Bernese processing appears to be running:"
    printf '%s\n' "$busy"
    die "wait for it to finish; concurrent bulk I/O hangs a headless BPE"
fi

mkdir -p "$LOGDIR"

census() {
    # $1 = root. Counts each type separately: this archive once lost every
    # symlink to a FAT32 hop, silently, and a file count alone did not notice
    # because the symlinks were still present as regular files.
    local root="$1"
    local f l d o b
    f=$(find "$root" -xdev -type f 2>/dev/null | wc -l)
    l=$(find "$root" -xdev -type l 2>/dev/null | wc -l)
    d=$(find "$root" -xdev -type d 2>/dev/null | wc -l)
    o=$(find "$root" -xdev ! -type f ! -type l ! -type d 2>/dev/null | wc -l)
    b=$(find "$root" -xdev -type f -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {print s+0}')
    printf '%s %s %s %s %s' "$f" "$l" "$d" "$o" "$b"
}

show_census() {
    # $1 = "files symlinks dirs other bytes" as emitted by census()
    local -a c
    read -r -a c <<<"$1"
    printf '    files %-10s symlinks %-6s dirs %-8s other %-4s bytes %s (%.2f GiB)\n' \
      "${c[0]}" "${c[1]}" "${c[2]}" "${c[3]}" "${c[4]}" \
      "$(awk -v x="${c[4]}" 'BEGIN{print x/1073741824}')"
}

{
echo "=== archive transfer $STAMP  (mode: $MODE) ==="
echo "src : $SRC"
echo "dest: $DEST"
echo

shopt -s nullglob
dirs=("$SRC"/RECOVERED_*)
[ ${#dirs[@]} -gt 0 ] || die "no RECOVERED_* directories under $SRC — wrong drive?"

echo "Found ${#dirs[@]} RECOVERED_* directories (globbed):"
for d in "${dirs[@]}"; do
    printf '  %-52s %s\n' "$(basename "$d")" "$(du -sh "$d" 2>/dev/null | cut -f1)"
done
echo
echo "Destination free space: $(df -h "$DEST" | tail -1 | awk '{print $4}')"
echo

if [ "$MODE" = "--dry-run" ]; then
    echo "--- source census (per directory) ---"
    for d in "${dirs[@]}"; do
        echo "  $(basename "$d"):"
        show_census "$(census "$d")"
    done
    echo
    echo "Dry run — nothing copied. Re-run with --apply."
    exit 0
fi

mkdir -p "$DEST"
rc_worst=0
for d in "${dirs[@]}"; do
    name=$(basename "$d")
    echo "--- copying $name ---"
    # -aHAX preserves hardlinks/ACLs/xattrs where the destination supports them.
    # --partial so an interrupted multi-GB file resumes rather than restarting.
    rsync -aHAX --partial --info=progress2 "$d/" "$DEST/$name/"
    rc=$?
    echo "  rsync exit: $rc"
    # 24 = "source vanished during transfer", benign here. Anything else is worth
    # flagging — but the census, not this code, decides whether it worked.
    [ "$rc" -ne 0 ] && [ "$rc" -ne 24 ] && rc_worst=$rc
    echo
done

echo "=== census: source vs destination ==="
for d in "${dirs[@]}"; do
    name=$(basename "$d")
    # NB: not named `cd` — that shadows the builtin. The destination fields
    # were previously read into `df dl dd do db`, where `do` is a bash keyword.
    # SC1010 caught it; `bash -n` had accepted it happily.
    # (A comment line must not begin with the linter's own name, or it is
    #  parsed as a directive — which is how the first fix attempt failed.)
    src_c=$(census "$d")
    dst_c=$(census "$DEST/$name")
    echo "  $name"
    echo "    SRC :"; show_census "$src_c"
    echo "    DEST:"; show_census "$dst_c"

    local_s=(); local_d=()
    read -r -a local_s <<<"$src_c"
    read -r -a local_d <<<"$dst_c"
    # [0] = file count, [4] = total bytes. Symlinks are reported but not
    # compared: the source is NTFS and legitimately has none.
    if [ "${local_s[0]}" -eq "${local_d[0]}" ] && [ "${local_s[4]}" -eq "${local_d[4]}" ]; then
        echo "    MATCH on files and bytes"
    else
        echo "    *** MISMATCH: files ${local_s[0]} vs ${local_d[0]}," \
             "bytes ${local_s[4]} vs ${local_d[4]} ***"
        rc_worst=1
    fi
    echo
done

echo "==================================================================="
if [ "$rc_worst" -eq 0 ]; then
    echo "All directories match on file count and byte total."
    echo
    echo "This is NOT yet 'the archive is backed up'. Next:"
    echo "  1. sha256 manifest:  /srv/gnss-archive/verify_archive.sh manifest"
    echo "  2. commit the manifest .gz to git — fingerprints stored only beside"
    echo "     the data cannot prove anything if that disk is what failed."
    echo "  3. report what was copied BY DIRECTORY, not as a single claim."
else
    echo "SOMETHING DID NOT MATCH. Do not report success."
    echo "Report exactly which directories matched and which did not."
fi
echo "==================================================================="

# Exit from INSIDE the block so the status is the pipeline's first element.
# Everything above runs in a subshell (the `{ } | tee` pipeline), so assigning
# rc_worst here never reached the parent: the old `exit "${rc_worst:-0}"` after
# the pipeline read an unset variable and returned 0 for every run, including
# one that had just printed "*** MISMATCH ***". Caught by SC2030/SC2031,
# not by testing — and it is the seventh instance in this
# project of a swallowed exit status reporting success, this time in the script
# written to stop trusting exit statuses.
exit "$rc_worst"
} 2>&1 | tee "$LOG"
rc=${PIPESTATUS[0]}

echo
echo "log: $LOG"
echo "exit: $rc"
exit "$rc"
