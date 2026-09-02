#!/usr/bin/env bash
# Restore the pre-patch BSW 5.4 install from the snapshots.
#
# Use when the patched build fails its verification. Restores SOURCE, SUPGUI
# and the built executables together -- AIUB: "Keep your source code,
# executables, and supporting files consistent at all times."
set -uo pipefail
# shellcheck disable=SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || { echo "FATAL: no LOADGPS"; exit 3; }
STAMP="${1:-}"
[ -n "$STAMP" ] || { echo "usage: $0 <YYYYMMDD>   (the snapshot date)"; ls "$HOME"/BERN54-*-pre-patch-*.tar.gz 2>/dev/null | sed 's|.*/|  |'; exit 2; }
for t in SOURCE SUPGUI EXE_GNU; do
  f="$HOME/BERN54-$t-pre-patch-$STAMP.tar.gz"
  [ -s "$f" ] || { echo "FATAL: missing $f"; exit 3; }
done
running=$(ps -u "$(id -un)" -o comm --no-headers | grep -cE 'RUNBPE|GPSEST|ADDNEQ2|MAUPRP' || true)
[ "$running" -eq 0 ] || { echo "FATAL: $running BSW process(es) running"; exit 3; }
# The tarballs hold "BERN54/SOURCE/..." relative to the PARENT of $C, so that
# is the extraction target. Deriving it beats hardcoding /home/gps3: this repo
# is shared with finch and reese, where that path does not exist, and a
# rollback script that only works on one machine is not a safety net.
BERN_PARENT=$(dirname "$C")
[ -d "$BERN_PARENT" ] || { echo "FATAL: $BERN_PARENT does not exist"; exit 3; }
echo "  restoring SOURCE and SUPGUI into $BERN_PARENT ..."
tar xzf "$HOME/BERN54-SOURCE-pre-patch-$STAMP.tar.gz" -C "$BERN_PARENT"
tar xzf "$HOME/BERN54-SUPGUI-pre-patch-$STAMP.tar.gz" -C "$BERN_PARENT"
echo "  restoring executables ..."
tar xzf "$HOME/BERN54-EXE_GNU-pre-patch-$STAMP.tar.gz" -C "$C/SOURCE/PGM"
echo "  executables now: $(ls "$XG" | wc -l)"
# Verify here rather than telling the operator how to. A rollback that reports
# success without checking is the same failure the rollback exists to undo.
FP="${BSW_PATCH_BASELINE:-$HOME/bsw-patch-baseline}/exe-sha256-pre.txt"
if [ -s "$FP" ]; then
    if ( cd "$XG" && sha256sum * 2>/dev/null | sort -k2 ) | diff -q - "$FP" >/dev/null; then
        echo "  VERIFIED: all $(wc -l < "$FP") executables bit-for-bit identical to pre-patch"
    else
        echo "  MISMATCH against $FP -- the restore did NOT reproduce the pre-patch state" >&2
        exit 1
    fi
else
    echo "  WARNING: no fingerprint at $FP, cannot verify the restore" >&2
fi

# A new file added by the patches is not removed by restoring an older tarball.
for extra in "$LG/IGRF14SYN.f"; do
    [ -e "$extra" ] && { rm -f "$extra"; echo "  removed patch-added file: ${extra##*/}"; }
done
n_pp=$(find "$LG" "$FG" "${PAN:-}" "${HLP:-}" -name '*.pre-patch' 2>/dev/null | wc -l)
if [ "$n_pp" -gt 0 ]; then
    find "$LG" "$FG" "${PAN:-}" "${HLP:-}" -name '*.pre-patch' -delete 2>/dev/null
    echo "  cleaned $n_pp .pre-patch copies"
fi
