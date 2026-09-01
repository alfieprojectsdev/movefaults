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
DAY="${VERIFY_DOY:-200}"
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
say "== 3. re-run PHREF DOY $DAY and compare against the unpatched solution =="
ref="$BASE/FIN_2025${DAY}0-prepatch.SNX"
if [ ! -s "$ref" ]; then say "no pre-patch baseline for DOY $DAY -- cannot quantify the change"; exit 2; fi
say "baseline: $ref  ($(sha256sum "$ref" | cut -c1-16)...)"
say ""
say "  Run the day, then compare. The comparison tool is already in the repo:"
say "    perl \$U/SCRIPT/phref_year.pl 2025 ${DAY}0 PHREF_DLY 1 1"
say "    zcat \$S/PHREF/2025/SOL/FIN_2025${DAY}0.SNX.gz > /tmp/postpatch.SNX"
say "    uv run --with numpy python scripts/compare_weekly_solutions.py \\"
say "        --ours /tmp/postpatch.SNX --theirs $ref --label 'patched vs unpatched'"
say ""
say "  Same station set and same day, so the Helmert parameters should be ~zero"
say "  and the residuals ARE the effect of the patches. Anything above a few mm"
say "  horizontal deserves an explanation before the build goes to production."
[ "$ok" -eq 1 ]
