#!/usr/bin/env bash
# verify_archive.sh — census + fixity for the legacy GNSS archive on gps3.
#
# Run AFTER the transfer from the T420 completes.
#
# WHY A CENSUS AND NOT `rsync --stats`: this project has already lost a session
# to trusting rsync's exit code. rsync exits 0 having skipped files it could not
# read, and exits 23 ("partial transfer due to error") on a run that copied
# 99.99% successfully. Neither number tells you what actually landed. Counting
# files, symlinks and bytes independently does.
#
# WHY SYMLINKS ARE COUNTED SEPARATELY: this archive previously lost its symlinks
# entirely to a FAT32 thumb-drive hop, silently. A file count alone would not
# have caught it, because the symlinks were still there as regular files.
#
# WHY sha256 IS COMPUTED ON THE DESTINATION ONLY: the source drive has a
# pending sector and is the thing we are rescuing. Hashing the source would
# mean a second full read of failing media for no safety gain — rsync already
# verifies each file's checksum as it transfers. The manifest here exists for
# FUTURE fixity: detecting silent corruption on the array years from now, which
# is the thing that currently has no defence at all.
#
# Usage:
#   sudo -u gps3 /srv/gnss-archive/verify_archive.sh census     # fast, minutes
#   sudo -u gps3 /srv/gnss-archive/verify_archive.sh manifest   # slow, hours
#
#   ARCHIVE=/srv/gnss-archive/processed \
#     /srv/gnss-archive/verify_archive.sh manifest              # any target
set -uo pipefail

# Target is now selectable. It was hardcoded to legacy/ until 2026-08-12, which
# meant `processed/` -- Abegail's sixteen-year SOL series, equally
# irreplaceable -- had no fixity path at all and nobody noticed. Anything under
# /srv/gnss-archive can be addressed now; the mountpoint check below still
# refuses to run against a path that is not on the array.
ARCHIVE="${ARCHIVE:-/srv/gnss-archive/legacy}"
MANIDIR="/srv/gnss-archive/manifests"
STAMP="$(date +%Y%m%d-%H%M%S)"
MODE="${1:-census}"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

[ -d "$ARCHIVE" ] || die "$ARCHIVE does not exist"
mountpoint -q /srv/gnss-archive || die "/srv/gnss-archive is not a mountpoint — refusing to run"

case "$MODE" in
census)
    echo "=== census of $ARCHIVE ==="
    # -xdev: never cross into another filesystem. Without it a stray mount or
    # symlinked mountpoint inside the tree silently inflates every number.
    files=$(find "$ARCHIVE" -xdev -type f | wc -l)
    links=$(find "$ARCHIVE" -xdev -type l | wc -l)
    dirs=$(find "$ARCHIVE" -xdev -type d | wc -l)
    other=$(find "$ARCHIVE" -xdev ! -type f ! -type l ! -type d | wc -l)
    # Apparent size, not disk usage: XFS block rounding would otherwise make
    # the byte count differ from the source for reasons that are not data loss.
    bytes=$(find "$ARCHIVE" -xdev -type f -printf '%s\n' | awk '{s+=$1} END {print s+0}')

    printf '  regular files : %s\n' "$files"
    printf '  symlinks      : %s\n' "$links"
    printf '  directories   : %s\n' "$dirs"
    printf '  other         : %s\n' "$other"
    printf '  total bytes   : %s  (%.2f GiB)\n' "$bytes" "$(awk -v b="$bytes" 'BEGIN{print b/1073741824}')"
    echo
    echo "  Compare all five against the SAME census run on the T420 source."
    echo "  Data loss shows up as FEWER files or FEWER bytes. More is normal only"
    echo "  if something wrote to the archive after the copy."
    # `[ cond ] && echo` as the LAST statement makes a false condition the
    # script's exit status — a clean census would report failure to any caller
    # checking $?. Third instance of a swallowed/inverted exit status in this
    # project (see the SIGPIPE and `lsof +D` writeups). Use a full if-block.
    if [ "$other" -gt 0 ]; then
        echo "  NOTE: 'other' > 0 — sockets/fifos/devices present; inspect before trusting."
    fi
    ;;
manifest)
    OUT="$MANIDIR/$(basename "$ARCHIVE")-sha256-$STAMP.txt"
    echo "=== sha256 manifest of $ARCHIVE ==="
    echo "  This reads every byte. Expect hours for ~157 GB."
    echo "  Writing: $OUT"
    echo
    # cd so paths are recorded relative to the archive root — an absolute-path
    # manifest is useless after the archive is ever moved or restored elsewhere.
    ( cd "$ARCHIVE" && find . -xdev -type f -print0 | sort -z | xargs -0 -r sha256sum ) > "$OUT"
    rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "  WARNING: sha256sum returned $rc — some files may be unreadable."
        echo "  The manifest is still written; check it for gaps before trusting it."
    fi
    lines=$(wc -l < "$OUT")
    gzip -9 -k -f "$OUT" && echo "  compressed: ${OUT}.gz ($(du -h "${OUT}.gz" | cut -f1))"
    printf '  %s files hashed\n' "$lines"
    echo
    echo "  Verify at any future date with:"
    echo "      cd $ARCHIVE && sha256sum -c ${OUT}"
    echo "  Commit the .gz to git so the fingerprints live somewhere other than"
    echo "  the disk they describe. A manifest stored only beside the data cannot"
    echo "  prove anything if that disk is what went wrong."
    ;;
*)
    die "unknown mode '$MODE' (use: census | manifest)"
    ;;
esac
exit 0
