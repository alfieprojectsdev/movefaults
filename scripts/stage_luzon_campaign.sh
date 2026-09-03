#!/usr/bin/env bash
# stage_luzon_campaign.sh — set up a Bernese 5.4 LUZON campaign from the
# copied 5.2 production set, per docs/bernese54_luzon_reprocessing_runbook.md §4.
#
# Runs as gps3 — everything it writes is under $P, $D and $U, all user-owned.
# No sudo. Sourcing LOADGPS.setvar is required for $P/$D/$U/$C.
#
# WHAT IT DOES NOT DO
# It does not adapt the PCF (§4.1 script renames and PID drops) and it does not
# run anything. Staging is mechanical and reversible; those two involve
# decisions and are done separately.
#
# RUN THE PREFLIGHT FIRST
# `rinex-completeness` reports, from the datapool alone, which days have too
# few reference stations to be tied to the frame -- and therefore cannot be
# processed no matter how cleanly they stage:
#
#     uv run rinex-completeness /srv/gnss-archive/datapool/PHIVOLCS \
#         --year 2025 --from 1 --to 365
#
# Exit 1 means at least one day is short; the report names them. The 2025 run
# lost DOY 058-061, 079 and 345 exactly this way, and each was discovered by
# failing a BPE run rather than by looking. This is not wired into staging on
# purpose -- a short day is sometimes staged deliberately, and a preflight that
# blocks the operator is a preflight the operator learns to skip.
#
# DRY RUN BY DEFAULT.
set -uo pipefail

# NOT named SRC: LOADGPS.setvar exports its own $SRC (=$C/SOURCE) and would
# silently overwrite it, making every source path resolve under the Bernese
# tree. The first dry run did exactly that -- every file reported "MISSING FROM
# SOURCE" and every count came back 0, which reads as an empty source rather
# than as a clobbered variable. Bernese exports a large, undocumented set of
# short names (P D U C T SRC XG XQ ...); do not use bare short names here.
LUZON_SRC="/srv/gnss-archive/processed/luzon-bern52"

# WHERE THE RINEX 2 OBSERVATIONS COME FROM (changed 2026-08-24, approved)
# Abegail's copied set holds only DOY 121-151. A full year has to come from the
# national datapool transferred off the file server in August, which carries
# 2010 to present for every PHIVOLCS site.
#
# Verified before switching, because changing the source of a year of
# observations is not a free move. For DOY 121, which both sources hold, the
# same 25 stations were compared record by record:
#
#   10 of 15 checked  byte-identical after the header
#    5 of 15          differ in 2-4 observation lines out of ~100,000 (0.002%)
#
# Every difference is one unit in the last decimal of a carrier phase --
# 0.001 cycles, about 0.19 mm on L1 -- from the files having been converted by
# different teqc builds (the header COMMENT shows Linux 2.4 vs 2.6 and
# different operator initials). The observations are the same measurements;
# the last digit rounds differently. That is far below the 3 mm daily
# repeatability and cannot affect a solution.
#
# Set LUZON_RNX2_SRC to override, e.g. back to Abegail's set for a comparison.
LUZON_RNX2_SRC="${LUZON_RNX2_SRC:-/srv/gnss-archive/datapool/PHIVOLCS}"

# The 25 stations that DEFINE the LUZON subnetwork, taken from Abegail's staged
# set -- the authoritative statement of which sites this campaign processes.
# The national datapool holds hundreds of sites; staging it unfiltered would
# silently change the network and make every solution incomparable with the
# thirty days already computed.
LUZON_STATIONS="ALAB ANTP AURA BALA BASC BLN2 BRGC CAC2 CLAV ELNA GUMA GUNG \
IBAZ INFA LGYE MAUB MLPA PAGP POLI PTBN S01R SAPN TANY TGDN VIGN"

CAMPAIGN="LUZON"
YEAR="${YEAR:-2025}"
YY="${YEAR: -2}"          # RINEX 2 two-digit year, derived so it cannot drift
DOY_FROM="${DOY_FROM:-1}"
DOY_TO="${DOY_TO:-365}"
MODE="${1:-}"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }

case "$MODE" in
    --dry-run|--apply) ;;
    *) die "usage: $0 --dry-run | --apply" ;;
esac

# shellcheck disable=SC1090
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || die "cannot source LOADGPS.setvar"
if [ -z "${P:-}" ] || [ -z "${D:-}" ] || [ -z "${U:-}" ]; then
    die "P/D/U unset after LOADGPS"
fi
[ -d "$LUZON_SRC" ] || die "$LUZON_SRC not found — is the processed set copied?"

run() {
    if [ "$MODE" = "--apply" ]; then "$@"; else say "    would: $*"; fi
}

say "=== staging $CAMPAIGN into the 5.4 environment ==="
say "  P = $P"
say "  D = $D"
say "  U = $U"
say "  mode = $MODE"
say ""

# --- 1. campaign skeleton --------------------------------------------------
# Bernese expects these subdirectories to exist. RAW holds the RINEX that
# RNX_COP stages; ORX/GRD stay empty for this workflow.
say "--- campaign directories ---"
for sub in ATM BPE GRD OBS ORB ORX OUT RAW SOL STA; do
    if [ -d "$P/$CAMPAIGN/$sub" ]; then
        say "    exists: $CAMPAIGN/$sub"
    else
        run mkdir -p "$P/$CAMPAIGN/$sub"
    fi
done
say ""

# --- 2. reference frame files ----------------------------------------------
# THE ONE REAL GAP (runbook §4.2). PHIVOL_REL wants V_REFINF=IGS14 and
# V_REFPSD=IGS14; 5.4 ships IGS20 only. Without these the run either fails or
# silently falls back to IGS20 — the I14/I20 confound the whole exercise exists
# to avoid, arriving without announcing itself.
say "--- IGS14 reference frame files -> \$D/REF54 ---"
for f in IGS14.FIX IGS14.PSD IGS14.SIG IGS14_R.CRD IGS14_R.VEL; do
    if [ -f "$D/REF54/$f" ]; then
        say "    exists: REF54/$f"
    elif [ -f "$LUZON_SRC/DATAPOOL_REF52/$f" ]; then
        run cp -p "$LUZON_SRC/DATAPOOL_REF52/$f" "$D/REF54/$f"
    else
        say "    MISSING FROM SOURCE: $f"
    fi
done
say ""

# --- 3. antenna model -------------------------------------------------------
# ANTENNA_I14.PCV already ships with 5.4, so only the ATX is staged. V_PCVINF
# must be ANTENNA (not the 5.2 value PCV) for {V_PCVINF}_{V_PCV} to resolve —
# that is a PCF edit, not a staging step. See runbook §4.3 item 0.
say "--- antenna model ---"
if [ -f "$D/REF54/ANTENNA_I14.PCV" ]; then
    say "    exists: REF54/ANTENNA_I14.PCV  (ships with 5.4)"
else
    say "    WARNING: ANTENNA_I14.PCV absent — V_PCV=I14 will not resolve"
fi
if [ -f "$D/REF54/I14.ATX" ]; then
    say "    exists: REF54/I14.ATX"
else
    run cp -p "$LUZON_SRC/BERN52/GPS/GEN/I14.ATX" "$D/REF54/I14.ATX"
fi
say ""

# --- 4. station information -------------------------------------------------
say "--- LUZON station files -> \$D/REF54 ---"
for ext in STA CRD VEL ABB CLU BLQ ATL PLD; do
    src=""
    for cand in "$LUZON_SRC/DATAPOOL_REF52/$CAMPAIGN.$ext" \
                "$LUZON_SRC/GPSDATA/CAMPAIGN/$CAMPAIGN/STA/$CAMPAIGN.$ext"; do
        [ -f "$cand" ] && { src="$cand"; break; }
    done
    if [ -f "$D/REF54/$CAMPAIGN.$ext" ]; then say "    exists: REF54/$CAMPAIGN.$ext"
    elif [ -n "$src" ];                  then run cp -p "$src" "$D/REF54/$CAMPAIGN.$ext"
    else say "    MISSING FROM SOURCE: $CAMPAIGN.$ext"; fi
done
say ""

# --- 5. observations --------------------------------------------------------
# RINEX 2 locals and RINEX 3 fiducials go to SEPARATE directories; the PCF
# addresses them through V_RNXDIR and V_RX3DIR respectively.
#
# Only the 25 LUZON stations are staged, by name. The national datapool holds
# every PHIVOLCS site, and taking whatever matches a day pattern would quietly
# enlarge the network -- which changes the datum, changes every coordinate, and
# makes the result incomparable with the days already solved.
say "--- observations for $YEAR DOY $DOY_FROM-$DOY_TO ---"
say "    RINEX 2 source: $LUZON_RNX2_SRC"
n2=0; n3=0; missing_days=0
run mkdir -p "$D/$CAMPAIGN" "$D/RINEX3"
for doy in $(seq "$DOY_FROM" "$DOY_TO"); do
    d3=$(printf '%03d' "$doy")
    found_today=0
    for st in $LUZON_STATIONS; do
        # The two-digit year must be MATCHED, not wildcarded. An earlier version
        # used `??[oOdD]`, which accepts any year: staging a 2025 campaign
        # copied 8,668 files from 2024 and 2026 as well. Harmless to the results
        # -- RNX_COP globs on ${yy}=25 and ignored them -- but it wasted ~52 GB
        # and left a directory that misrepresents its own contents to the next
        # reader. Found 2026-08-27 while investigating a different question.
        for f in "$LUZON_RNX2_SRC/${st}${d3}0.${YY}"[oOdD] "$LUZON_RNX2_SRC/${st}${d3}0.${YY}"[dD].gz; do
            [ -e "$f" ] || continue
            n2=$((n2 + 1)); found_today=$((found_today + 1))
            [ "$MODE" = "--apply" ] && cp -pn "$f" "$D/$CAMPAIGN/"
        done
    done
    # A day with almost nothing is worth naming now rather than as a puzzling
    # BPE failure later. Three is arbitrary but well under the ~25 a normal
    # day carries, and the 31-day run showed a one-station day does exist.
    if [ "$found_today" -lt 3 ]; then
        missing_days=$((missing_days + 1))
        say "    !! DOY $d3: only $found_today station file(s)"
    fi

    # RINEX 3 fiducials must land in the SAME directory as the RINEX 2 files.
    #
    # This is not tidiness, it is what the pipeline requires. The PCF sets
    # V_RNXDIR = ${D}/LUZON and RNX_COP globs that one directory for both
    # conventions -- `????SSSS.YY[DdOo]*` for RINEX 2 and
    # `?????????_?_YYYYDDD*_01[dD]*O.{rnx,crx}*` for RINEX 3. A fiducial left
    # in $D/RINEX3 is invisible to the run.
    #
    # An earlier version of this block counted these files instead of copying
    # them, on the mistaken belief that fetch_fiducial_obs.sh had already put
    # them in place. It puts them in $D/RINEX3, which is a staging area, not
    # the directory the BPE reads. DOY 001 then ran with zero fiducials and
    # died in RNXGRA on a header-only file that CCRNXO had produced from no
    # input -- a failure four steps downstream of the actual cause.
    for f in "$D/RINEX3/"*"_${YEAR}${d3}0000_"*; do
        [ -e "$f" ] || continue
        n3=$((n3 + 1))
        [ "$MODE" = "--apply" ] && cp -pn "$f" "$D/$CAMPAIGN/"
    done
done
say "    RINEX 2 (-> \$D/$CAMPAIGN): $n2 files"
say "    RINEX 3 (-> \$D/RINEX3)   : $n3 files"
[ "$missing_days" -gt 0 ] && say "    !! $missing_days day(s) with fewer than 3 stations — review before running those"
say ""

# --- 6. products ------------------------------------------------------------
# GPS weeks 2364-2368 span DOY 121-151 of 2025. ION files are GPS-week named
# (COD2364*), which is why a year-DOY search finds nothing — runbook §1.5.
say "--- orbit / ERP / clock / ION / DCB products ---"
np=0
run mkdir -p "$D/IGS" "$D/BSW52" "$D/COD"
for w in 2364 2365 2366 2367 2368; do
    for f in "$LUZON_SRC/GPSDATA/DATAPOOL/IGS/"*"$w"*; do
        [ -e "$f" ] || continue; np=$((np + 1))
        [ "$MODE" = "--apply" ] && cp -pn "$f" "$D/IGS/"
    done
    for f in "$LUZON_SRC/DATAPOOL_BSW52/"*"$w"*; do
        [ -e "$f" ] || continue; np=$((np + 1))
        [ "$MODE" = "--apply" ] && cp -pn "$f" "$D/BSW52/"
    done
done
say "    products staged: $np files"
say ""

# --- 7. what remains, deliberately not automated ----------------------------
cat <<'EOF'
===================================================================
Staging complete. NOT done here, and each needs a decision:

  1. Adapt the PCF (runbook §4.1). Copy PHIVOL_REL.PCF to LUZON_DLY.PCF and:
       POLUPDH -> POLUPD      ORBGENH  -> ORBGEN
       RXOBV3_H -> RXOBV3     RNXSMT_H -> RNXSMT_P
       PRETAB  -> ORBMRG      (5.4 chains ORBMRG then ORBGEN)
       drop PIDs 000 (FTP_DWLD), 530 (ADD_WK), 531 (ADD_MON), 515-999
  2. Set V_PCVINF = ANTENNA   (5.2 value PCV does not resolve in 5.4)
     Set V_REFDIR = ${D}/REF54
     Confirm V_PCV = I14
  3. Register the campaign in $U/PAN/MENU_CMP.INP
  4. Decide BASC/CLAV convention — both staged, RINEX 3 recommended
  5. Pre-flight: station-days per convention, duplicates, PNGM's 5 short days

Then run ONE day (DOY 121) before the other 30.
===================================================================
EOF
