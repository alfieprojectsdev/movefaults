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
echo "  restoring SOURCE and SUPGUI ..."
tar xzf "$HOME/BERN54-SOURCE-pre-patch-$STAMP.tar.gz" -C /home/gps3
tar xzf "$HOME/BERN54-SUPGUI-pre-patch-$STAMP.tar.gz" -C /home/gps3
echo "  restoring executables ..."
tar xzf "$HOME/BERN54-EXE_GNU-pre-patch-$STAMP.tar.gz" -C "$C/SOURCE/PGM"
echo "  executables now: $(ls "$XG" | wc -l)"
echo "  verify against the pre-patch fingerprint:"
echo "    cd $XG && sha256sum * | sort -k2 | diff - $HOME/bsw-patch-baseline/exe-sha256-pre.txt && echo IDENTICAL"
