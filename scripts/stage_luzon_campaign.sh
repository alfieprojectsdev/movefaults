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
# DRY RUN BY DEFAULT.
set -uo pipefail

# NOT named SRC: LOADGPS.setvar exports its own $SRC (=$C/SOURCE) and would
# silently overwrite it, making every source path resolve under the Bernese
# tree. The first dry run did exactly that -- every file reported "MISSING FROM
# SOURCE" and every count came back 0, which reads as an empty source rather
# than as a clobbered variable. Bernese exports a large, undocumented set of
# short names (P D U C T SRC XG XQ ...); do not use bare short names here.
LUZON_SRC="/srv/gnss-archive/processed/luzon-bern52"
CAMPAIGN="LUZON"
YEAR=2025
DOY_FROM=121
DOY_TO=151
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
# addresses them through V_RNXDIR and V_RX3DIR respectively. Only the 31-day
# window is staged — copying all 741+281 files would pull in days the run does
# not process and make any station-day count meaningless.
say "--- observations for $YEAR DOY $DOY_FROM-$DOY_TO ---"
n2=0; n3=0
run mkdir -p "$D/$CAMPAIGN" "$D/RINEX3"
for doy in $(seq "$DOY_FROM" "$DOY_TO"); do
    for f in "$LUZON_SRC/GPSDATA/DATAPOOL/LUZON/"????"${doy}"0.*; do
        [ -e "$f" ] || continue
        n2=$((n2 + 1))
        [ "$MODE" = "--apply" ] && cp -pn "$f" "$D/$CAMPAIGN/"
    done
    for f in "$LUZON_SRC/GPSDATA/DATAPOOL/RINEX3/"*"_${YEAR}${doy}0000_"*; do
        [ -e "$f" ] || continue
        n3=$((n3 + 1))
        [ "$MODE" = "--apply" ] && cp -pn "$f" "$D/RINEX3/"
    done
done
say "    RINEX 2 (-> \$D/$CAMPAIGN): $n2 files"
say "    RINEX 3 (-> \$D/RINEX3)   : $n3 files"
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
