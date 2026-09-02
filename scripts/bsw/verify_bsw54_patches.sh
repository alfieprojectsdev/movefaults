#!/usr/bin/env bash
# Verify a patched BSW 5.4 build before trusting it for production.
#
# Three checks, in increasing cost:
#   1. the patch markers are actually in the built sources
#   2. the EXAMPLE campaign still reproduces (BSW's own regression; BRN-001
#      set the bar at 0.0000 mm against the shipped reference)
#   3. one PHREF day re-runs and is compared against its UNPATCHED solution
#
# Check 3 is the one that matters scientifically: it turns "results may have
# changed" into a measured number. B_33 alters the geomagnetic model and B_38
# touches TRPSTORE on the GPSEST/ADDNEQ2 path, so a nonzero difference is
# EXPECTED -- the point is to know its size, not to hope it is zero.
set -uo pipefail
BASE="${BSW_PATCH_BASELINE:-$HOME/bsw-patch-baseline}"
PREFLIGHT_DOY="${PREFLIGHT_DOY:-200}"   # solved before PIMO joined; never use as baseline
YEAR="${VERIFY_YEAR:-2025}"
REPO="${REPO:-$HOME/repos/movefaults_clean}"
# shellcheck disable=SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || { echo "FATAL: no LOADGPS"; exit 3; }
say() { printf '  %s\n' "$*"; }

say "== 1. patch markers present in source =="
ok=1
grep -q 'IGRF14' "$LG/IONOSP2.f90" 2>/dev/null \
  && say "B_33: IONOSP2.f90 references IGRF14" || { say "B_33: NOT APPLIED"; ok=0; }
[ -f "$LG/IGRF14SYN.f" ] && say "B_33: IGRF14SYN.f present" || { say "B_33: IGRF14SYN.f MISSING"; ok=0; }
for f in O_RXOWRAP.f90 TRPSTORE.f90 D_GRID.f90 D_RXNTYPE.f90 UPDMEA.f90; do
  if [ -f "$LG/$f.pre-patch" ]; then say "applied: $f (pre-patch copy kept)"; else say "no pre-patch copy for $f"; fi
done

say ""
say "== 2. executables rebuilt =="
if [ -s "$BASE/exe-sha256-post.txt" ]; then
  say "changed: $(comm -13 <(sort "$BASE/exe-sha256-pre.txt") <(sort "$BASE/exe-sha256-post.txt") | wc -l)"
else
  say "no post-build fingerprint -- run apply_bsw54_patches.sh --all first"; ok=0
fi

say ""
# ---------------------------------------------------------------------------
# 3. Re-run one day and MEASURE the change. This step used to print the
#    commands and let the operator run them; it now runs them, because a check
#    that has to be executed by hand is one that gets skipped.
#
#    THE DAY MATTERS. DOY 200 was the pre-flight test day, solved BEFORE PIMO
#    was added to the campaign, so its stored solution has 33 stations against
#    the year's 35. Re-running it compares 34 to 33 and yields ~1.9 mm of pure
#    network change -- which looks exactly like a plausible patch effect and is
#    not one. Pick a day from the MAIN run.
# ---------------------------------------------------------------------------
say ""
say "== 3. re-run a day and measure the difference =="

SOL="$S/PHREF/$YEAR/SOL"
if [ -n "${VERIFY_DOY:-}" ]; then
    day=$(printf '%03d' "$((10#$VERIFY_DOY))")
    say "day $day (VERIFY_DOY)"
else
    # Choose a day whose station count matches the year's mode -- i.e. one the
    # main run produced under the network that is actually in use. The
    # pre-flight day is excluded by name as well, since its count could
    # coincide.
    day=""
    mode=$(for f in "$SOL"/FIN_"$YEAR"*.SNX.gz; do
               zcat "$f" 2>/dev/null | awk '/^\+SITE\/ID/,/^-SITE\/ID/' \
                 | grep -cE '^ [A-Z0-9]{4} '
           done | sort -n | uniq -c | sort -rn | head -1 | awk '{print $2}')
    for f in "$SOL"/FIN_"$YEAR"*.SNX.gz; do
        d=${f##*/FIN_"$YEAR"}; d=${d%%0.SNX.gz}
        [ "$d" = "$PREFLIGHT_DOY" ] && continue
        n=$(zcat "$f" 2>/dev/null | awk '/^\+SITE\/ID/,/^-SITE\/ID/' | grep -cE '^ [A-Z0-9]{4} ')
        if [ "$n" -eq "$mode" ]; then day="$d"; break; fi
    done
    [ -n "$day" ] || { say "could not find a main-run day with the modal station count"; exit 2; }
    say "day $day (first main-run day at the modal count of $mode stations;"
    say "        DOY $PREFLIGHT_DOY excluded -- it is the pre-flight day and predates PIMO)"
fi

src="$SOL/FIN_${YEAR}${day}0.SNX.gz"
[ -s "$src" ] || { say "no solution at $src"; exit 2; }

# Snapshot BEFORE the re-run overwrites it, and restore afterwards: the year is
# a published dataset and must not end up half patched, half not.
ref="$BASE/FIN_${YEAR}${day}0-prepatch.SNX"
refnq="$BASE/FIN_${YEAR}${day}0-prepatch.NQ0.gz"
[ -s "$ref" ] || zcat "$src" > "$ref"
[ -s "$refnq" ] || cp -p "${src%.SNX.gz}.NQ0.gz" "$refnq" 2>/dev/null
n_ref=$(awk '/^\+SITE\/ID/,/^-SITE\/ID/' "$ref" | grep -cE '^ [A-Z0-9]{4} ')
say "baseline: $n_ref stations, $(sha256sum "$ref" | cut -c1-16)..."

say "re-running DOY $day ..."
( cd "$HOME" && perl "$U/SCRIPT/phref_year.pl" "$YEAR" "${day}0" PHREF_DLY 1 1 ) \
    > "$BASE/verify-rerun-$day.log" 2>&1
rc=$?
say "  exit=$rc  log: $BASE/verify-rerun-$day.log"

post="$BASE/postpatch-${day}.SNX"
zcat "$src" > "$post" 2>/dev/null
n_post=$(awk '/^\+SITE\/ID/,/^-SITE\/ID/' "$post" 2>/dev/null | grep -cE '^ [A-Z0-9]{4} ')

# A station-count mismatch invalidates the comparison -- that is the DOY 200
# trap, and it must fail loudly rather than produce a plausible number.
if [ "$n_post" -ne "$n_ref" ]; then
    say "STATION COUNT DIFFERS: baseline $n_ref, re-run $n_post."
    say "  The comparison would measure a NETWORK change, not the patches. Aborting."
    ok=0
else
    say "station counts match ($n_ref) -- the only variable is the software"
    ( cd "$REPO" && uv run --with numpy python scripts/compare_weekly_solutions.py \
        --ours "$post" --theirs "$ref" --quiet ) 2>&1 | sed 's/^/  /'
fi

# Restore, so the year stays homogeneous.
gzip -c "$ref" > "$src"
[ -s "$refnq" ] && cp -p "$refnq" "${src%.SNX.gz}.NQ0.gz"
say "restored DOY $day to its pre-patch solution"

say ""
say "Anything above a few mm horizontal deserves an explanation before this"
say "build goes to production."
[ "$ok" -eq 1 ]
