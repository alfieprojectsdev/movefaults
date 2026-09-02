#!/usr/bin/env bash
# Apply the 7 published bug fixes for BSW 5.4 release 2024-11-11, then rebuild.
#
# READ docs/bsw54_patch_plan.md FIRST. The three constraints that matter:
#
#   1. AIUB state the fixes are CUMULATIVE: "It may damage your installation if
#      you try to establish only selected bug-fixes." All 15 files or none.
#   2. This CHANGES RESULTS. B_33 alters the geomagnetic model used for
#      higher-order ionosphere corrections; B_38 touches TRPSTORE on the
#      GPSEST/ADDNEQ2 path. Everything produced before this point belongs to
#      the unpatched build and is not bit-comparable afterwards.
#   3. NEVER under a running BPE -- this replaces executables in place.
#
# Idempotent: a file already identical to its patch is skipped, so a re-run
# after a partial failure resumes rather than redoing.
#
# Usage:
#   scripts/bsw/apply_bsw54_patches.sh --check    # preconditions only, no writes
#   scripts/bsw/apply_bsw54_patches.sh --place    # copy files, no compile
#   scripts/bsw/apply_bsw54_patches.sh --all      # place + makemake + compile
set -uo pipefail

STAGE="${BSW_PATCH_STAGE:-$HOME/bsw-patches-2024-11-11}"
BASE="${BSW_PATCH_BASELINE:-$HOME/bsw-patch-baseline}"
MODE="${1:---check}"

# shellcheck disable=SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || { echo "FATAL: no LOADGPS"; exit 3; }
: "${LG:?}" "${FG:?}" "${PAN:?}" "${HLP:?}" "${C:?}" "${XG:?}"

say() { printf '  %s\n' "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 3; }

# --- preconditions -----------------------------------------------------------
say "== preconditions =="
running=$(ps -u "$(id -un)" -o comm --no-headers | grep -cE 'RUNBPE|GPSEST|ADDNEQ2|MAUPRP|CODSPP' || true)
[ "$running" -eq 0 ] || die "$running BSW process(es) running -- refusing to replace executables under a live BPE"
say "no BSW processes running"

for t in BERN54-SOURCE BERN54-SUPGUI BERN54-EXE_GNU; do
    ls "$HOME/$t"-pre-patch-*.tar.gz >/dev/null 2>&1 || die "no rollback snapshot $t-pre-patch-*.tar.gz"
done
say "rollback snapshots present"
[ -s "$BASE/exe-sha256-pre.txt" ] || die "no pre-patch executable fingerprint at $BASE"
say "pre-patch fingerprint present ($(wc -l < "$BASE/exe-sha256-pre.txt") executables)"

n=$(find "$STAGE" -type f 2>/dev/null | wc -l)
[ "$n" -eq 15 ] || die "expected 15 staged patch files under $STAGE, found $n"
say "15 patch files staged"

# THE CHECK THIS SCRIPT ORIGINALLY LACKED.
#
# On 2026-09-02 --check passed on a machine with no compiler. --all then placed
# the files, ran CBERN COMPLINK, and the link step DELETED ALL 88 EXECUTABLES
# before failing with "make: gfortran: No such file or directory". The install
# was left unable to run anything until the snapshot was restored.
#
# BSW was installed here from prebuilt AIUB binaries, so a toolchain was never
# required until the moment something needed rebuilding. The evidence had been
# visible for days -- pytest could not collect test_dc3d.py, reporting
# "No such file or directory: 'cc'" -- and was read as an unrelated nuisance.
#
# A precondition check that verifies everything except the one prerequisite the
# operation actually depends on is not a precondition check.
missing=""
for tool in gfortran gcc make perl; do
    command -v "$tool" >/dev/null 2>&1 || missing="$missing $tool"
done
[ -z "$missing" ] || die "no build toolchain --$missing not on PATH.
       CBERN COMPLINK removes every executable before rebuilding, so running
       without a compiler leaves the install unusable. Install with:
           sudo apt install gfortran gcc make
       Note this makes the install locally compiled rather than the AIUB
       prebuilt binaries BRN-001 verified at 0.0000 mm."
say "toolchain present ($(gfortran --version 2>/dev/null | head -1))"

# A compiler on PATH is not proof it can build. Compile one trivial unit.
_probe=$(mktemp -d)
printf 'program t\nend program t\n' > "$_probe/t.f90"
if gfortran -o "$_probe/t" "$_probe/t.f90" >"$_probe/log" 2>&1; then
    say "gfortran compiles a trivial program"
else
    rm -rf "$_probe"
    die "gfortran is on PATH but cannot compile: see the error above"
fi
rm -rf "$_probe"

declare -A DEST=( [LIB_FOR]="$LG" [PGM_FOR]="$FG" [SUPGUI_PAN]="$PAN" [SUPGUI_HLP]="$HLP" )

todo=0; already=0
for d in "${!DEST[@]}"; do
    for f in "$STAGE/$d"/*; do
        [ -f "$f" ] || continue
        if cmp -s "$f" "${DEST[$d]}/$(basename "$f")"; then already=$((already+1)); else todo=$((todo+1)); fi
    done
done
say "to apply: $todo    already identical: $already"
[ "$MODE" = "--check" ] && { say "check only -- nothing written"; exit 0; }
[ "$todo" -eq 0 ] && say "nothing to place (already applied)"

# --- place -------------------------------------------------------------------
say ""; say "== placing files =="
manifest="$BASE/applied-manifest-$(date +%Y%m%d-%H%M%S).txt"
: > "$manifest"
for d in "${!DEST[@]}"; do
    for f in "$STAGE/$d"/*; do
        [ -f "$f" ] || continue
        n=$(basename "$f"); t="${DEST[$d]}/$n"
        cmp -s "$f" "$t" && continue
        [ -f "$t" ] && cp -p "$t" "$t.pre-patch" 2>/dev/null
        cp -p "$f" "$t" || die "cannot write $t"
        printf '%s  %s  %s\n' "$(sha256sum "$t" | cut -d' ' -f1)" "$t" "$([ -f "$t.pre-patch" ] && echo replaced || echo new)" >> "$manifest"
        say "placed $n -> ${DEST[$d]}"
    done
done
say "manifest: $manifest"
[ "$MODE" = "--place" ] && { say "placed only -- NOT compiled. Run with --all to build."; exit 0; }

# --- build -------------------------------------------------------------------
# B_33 requires makemake.pl first; the others do not, but running it is
# harmless and the fixes are cumulative, so do it once for the whole set.
say ""; say "== makemake.pl -r \$C =="
perl "$C/SCRIPT/EXE/makemake.pl" -r "$C" > "$BASE/makemake.log" 2>&1
say "exit=$?  log: $BASE/makemake.log"

# Individual entries name CBERN RNXGRA / RXOBV3 / RXN2PRE / ALL. Once library
# sources have changed a per-program build is not sufficient, so do the full
# link -- slower, and the only consistent option.
say ""; say "== CBERN COMPLINK (full rebuild; expect this to take a while) =="
( cd "$C" && perl "$C/SCRIPT/EXE/cbern.pl" COMPLINK ) > "$BASE/compile.log" 2>&1
rc=$?
say "exit=$rc  log: $BASE/compile.log"
grep -icE '\berror\b' "$BASE/compile.log" | sed 's/^/  compile-log error lines: /'

# --- what actually changed ---------------------------------------------------
say ""; say "== executables changed by the rebuild =="
( cd "$XG" && sha256sum * 2>/dev/null | sort -k2 ) > "$BASE/exe-sha256-post.txt"
changed=$(comm -13 <(sort "$BASE/exe-sha256-pre.txt") <(sort "$BASE/exe-sha256-post.txt") | wc -l)
say "changed: $changed of $(wc -l < "$BASE/exe-sha256-post.txt")"
comm -13 <(sort "$BASE/exe-sha256-pre.txt") <(sort "$BASE/exe-sha256-post.txt") | awk '{print "    "$2}' | head -20
missing=$(comm -23 <(awk '{print $2}' "$BASE/exe-sha256-pre.txt" | sort) <(awk '{print $2}' "$BASE/exe-sha256-post.txt" | sort) | wc -l)
[ "$missing" -gt 0 ] && say "WARNING: $missing executable(s) present before and MISSING now -- build did not complete"

say ""
say "NEXT: verify before trusting this build --"
say "  scripts/bsw/verify_bsw54_patches.sh"
[ "$rc" -eq 0 ] && [ "$missing" -eq 0 ]
