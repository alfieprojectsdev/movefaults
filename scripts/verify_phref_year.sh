#!/usr/bin/env bash
# Full-population verification of a completed PHREF/LUZON year.
#
# WHY: "N solutions on disk" is a count, not a check. This project has four
# recorded instances of a sample being reported as a population, so this
# examines EVERY expected day and reports what is missing, not what is present.
#
# Usage: scripts/verify_phref_year.sh [CAMPAIGN] [YEAR]
set -uo pipefail
CAMPAIGN="${1:-PHREF}"; YEAR="${2:-2025}"
# shellcheck disable=SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || { echo "no LOADGPS"; exit 3; }
SOL="$S/$CAMPAIGN/$YEAR/SOL"
[ -d "$SOL" ] || { echo "no such solution dir: $SOL"; exit 3; }

EXCL="${PHREF_EXCLUDE:-058 059 060 061 345}"
printf '%s %s verification — %s\n' "$CAMPAIGN" "$YEAR" "$(date '+%F %H:%M:%S %Z')"
printf -- '----------------------------------------------------------\n'

missing=""; present=0; excluded=0
for i in $(seq 1 365); do
    d=$(printf '%03d' "$i")
    case " $EXCL " in *" $d "*) excluded=$((excluded+1)); continue;; esac
    if [ -f "$SOL/FIN_${YEAR}${d}0.SNX.gz" ]; then
        present=$((present+1))
    else
        missing="$missing $d"
    fi
done
printf '  expected   %d  (365 less %d excluded)\n' "$((365-excluded))" "$excluded"
printf '  present    %d\n' "$present"
printf '  MISSING   %s\n' "${missing:- none}"

# A truncated or empty solution has the right name and the wrong size.
printf -- '\n  size distribution (a truncated solution shows here):\n'
ls -l "$SOL"/FIN_"${YEAR}"*.SNX.gz 2>/dev/null | awk '{print $5}' | sort -n | awk '
  {a[NR]=$1; s+=$1}
  END {if(NR) printf "    min %d   p05 %d   median %d   max %d   n=%d\n",
       a[1], a[int(NR*0.05)+1], a[int(NR/2)+1], a[NR], NR}'
small=$(find "$SOL" -name "FIN_${YEAR}*.SNX.gz" -size -20k | wc -l)
printf '    suspiciously small (<20k): %s\n' "$small"

# Station count per solution, every day, not a sample.
printf -- '\n  stations per solution (all days):\n'
for f in "$SOL"/FIN_"${YEAR}"*.SNX.gz; do
    zcat "$f" 2>/dev/null | awk '/^\+SITE\/ID/,/^-SITE\/ID/' | grep -cE '^ [A-Z0-9]{4} '
done | sort -n | uniq -c | awk '{printf "    %3d stations : %3d day(s)\n", $2, $1}'

printf -- '\n  NQ0 normal equations (input for weekly stacking): %s\n' \
    "$(ls "$SOL"/FIN_"${YEAR}"*.NQ0.gz 2>/dev/null | wc -l)"
printf '  disk: %s\n' "$(du -sh "$SOL" | cut -f1)"
[ -z "$missing" ] && [ "$small" -eq 0 ] && { printf '\n  VERDICT: complete and no degraded solutions.\n'; exit 0; }
printf '\n  VERDICT: INCOMPLETE — see MISSING / small above.\n'; exit 1
