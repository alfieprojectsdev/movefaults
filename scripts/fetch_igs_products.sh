#!/usr/bin/env bash
# fetch_igs_products.sh — download IGS long-name final products for a day range.
#
# WHY THIS EXISTS
# The 5.2 LUZON set ships orbit products in the OLD IGS legacy naming
# (`igs22364.sp3.Z` — GPS week + day-of-week). Bernese 5.4 reads the long-name
# convention (`IGS0OPSFIN_20251210000_01D_15M_ORB.SP3.gz`). The products were
# therefore "already local" and simultaneously unusable — presence is not
# usability, and the runbook's §1.1c claim that FTP_DWLD could be dropped was
# wrong for exactly that reason.
#
# WHY NOT packages/pogf-geodetic-suite igs_downloader.py
# That is a ProductDownloader for SP3/CLK by analysis centre and GPS week, built
# around the legacy filename builders. It has no notion of the long-name
# convention, of the weekly ERP, or of BKG paths. Extending it properly is
# deliverable 2.2 (IGS20 naming + mirror fallback); this is the narrow thing
# needed to run one campaign, kept separate rather than half-migrating that
# module under time pressure.
#
# SOURCE: BKG, anonymous over HTTPS. CDDIS holds the same products but requires
# an Earthdata login, so it is not usable unattended without credentials.
#
# ERP IS WEEKLY, not daily: `..._<startDOY>0000_07D_01D_ERP.ERP.gz`, covering
# seven days from a Sunday. Fetching "the ERP for DOY 121" means locating the
# week that contains it, not requesting DOY 121.
#
# Usage:
#   scripts/fetch_igs_products.sh 2025 121 123        # inclusive DOY range
#   scripts/fetch_igs_products.sh 2025 121 121 --dry-run
set -uo pipefail

BASE="https://igs.bkg.bund.de/root_ftp/IGS/products"
AC="IGS0OPSFIN"

# CODE products live in a SWITCH S3 bucket that www.aiub.unibe.ch redirects to.
# ftp.aiub.unibe.ch — the address in most documentation — is firewalled from
# this network and times out; the S3 host is not, and needs no credentials.
# Directory URLs 404 (object storage has no listings), so files are addressed
# individually. Bias products are NOT available from BKG: its IGS final set
# carries only CLK, SP3, ERP and SUM.
COD_BASE="https://zhw-b.s3.cloud.switch.ch/aiub/CODE"
YEAR="${1:?usage: $0 <year> <doy_from> <doy_to> [--dry-run]}"
FROM="${2:?doy_from required}"
TO="${3:?doy_to required}"
DRY="${4:-}"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# shellcheck disable=SC1090
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || die "cannot source LOADGPS.setvar"
DEST="$D/$AC"
mkdir -p "$DEST"

# GPS week for a given year/DOY. Week 0 began 1980-01-06.
gps_week() {
    local y="$1" d="$2" epoch days
    epoch=$(date -u -d "1980-01-06" +%s)
    days=$(date -u -d "${y}-01-01 +$((d - 1)) days" +%s)
    echo $(( (days - epoch) / 604800 ))
}

get() {  # $1 = gps week, $2 = filename
    local wk="$1" f="$2" url="$BASE/$1/$2"
    if [ -f "$DEST/$f" ]; then printf '    have  %s\n' "$f"; return 0; fi
    if [ "$DRY" = "--dry-run" ]; then printf '    fetch %s\n' "$f"; return 0; fi
    # --fail so a 404 is an error rather than an HTML error page written to disk
    # as if it were a product. -sS keeps it quiet but still reports failures.
    if curl -sS --fail -o "$DEST/$f.part" "$url" 2>/dev/null; then
        mv "$DEST/$f.part" "$DEST/$f"
        printf '    OK    %s (%s)\n' "$f" "$(du -h "$DEST/$f" | cut -f1)"
    else
        rm -f "$DEST/$f.part"
        printf '    FAIL  %s\n' "$f"
        return 1
    fi
}

get_cod() {  # $1 = year, $2 = filename, $3 = destination dir
    local y="$1" f="$2" dest="$3" url="$COD_BASE/$1/$2"
    mkdir -p "$dest"
    if [ -f "$dest/$f" ]; then printf '    have  %s\n' "$f"; return 0; fi
    if [ "$DRY" = "--dry-run" ]; then printf '    fetch %s (CODE)\n' "$f"; return 0; fi
    if curl -sS --fail -o "$dest/$f.part" "$url" 2>/dev/null; then
        mv "$dest/$f.part" "$dest/$f"
        printf '    OK    %s (%s)\n' "$f" "$(du -h "$dest/$f" | cut -f1)"
    else
        rm -f "$dest/$f.part"
        printf '    FAIL  %s (CODE)\n' "$f"
        return 1
    fi
}

echo "=== IGS long-name products, $YEAR DOY $FROM-$TO -> $DEST ==="
[ "$DRY" = "--dry-run" ] && echo "  (dry run)"
echo

rc=0
weeks_seen=""
for doy in $(seq "$FROM" "$TO"); do
    d3=$(printf '%03d' "$doy")
    wk=$(gps_week "$YEAR" "$doy")
    echo "  DOY $d3  (GPS week $wk)"
    # CODE is the PRIMARY set, not IGS. R2S_COP derives the bias filename from
    # V_ORB, so orbits, clocks, ERP and biases must all come from one analysis
    # centre or the names do not line up. Only CODE publishes the bias, and 5.4
    # ships defaulting to COD0OPSFIN for exactly that reason. This is also the
    # product set the working EXAMPLE campaign uses.
    get_cod "$YEAR" "COD0OPSFIN_${YEAR}${d3}0000_01D_05M_ORB.SP3.gz" "$D/COD0OPSFIN" || rc=1
    get_cod "$YEAR" "COD0OPSFIN_${YEAR}${d3}0000_01D_30S_CLK.CLK.gz" "$D/COD0OPSFIN" || rc=1
    get_cod "$YEAR" "COD0OPSFIN_${YEAR}${d3}0000_01D_01D_ERP.ERP.gz" "$D/COD0OPSFIN" || rc=1
    # The bias: R2S_COP runs BIA2OSB over this to produce the IAR_*.OSB it
    # treats as MANDATORY. Without it the very first BPE process fails. 5.4 uses
    # observable-specific biases where 5.2 used DCBs, so this is a 5.4
    # requirement, not one inherited from the 5.2 workflow.
    get_cod "$YEAR" "COD0OPSFIN_${YEAR}${d3}0000_01D_01D_OSB.BIA.gz" "$D/COD0OPSFIN" || rc=1
    get_cod "$YEAR" "COD0OPSFIN_${YEAR}${d3}0000_01D_01H_GIM.ION.gz" "$D/BSW54" || true

    # IGS equivalents, kept as a cross-check. CODE's ERP is daily; IGS's is
    # weekly, which is why the IGS branch below needs the week-start lookup.
    get "$wk" "${AC}_${YEAR}${d3}0000_01D_15M_ORB.SP3.gz" || true
    get "$wk" "${AC}_${YEAR}${d3}0000_01D_30S_CLK.CLK.gz" || true

    # The weekly ERP: find the Sunday of this GPS week and request that DOY.
    case " $weeks_seen " in
        *" $wk "*) ;;
        *)
            weeks_seen="$weeks_seen $wk"
            sunday=$(date -u -d "1980-01-06 +$((wk * 7)) days" +%j)
            syear=$(date -u -d "1980-01-06 +$((wk * 7)) days" +%Y)
            echo "    weekly ERP for week $wk (starts $syear DOY $sunday)"
            get "$wk" "${AC}_${syear}${sunday}0000_07D_01D_ERP.ERP.gz" || true
            ;;
    esac
done

echo
echo "  files now in $DEST: $(ls "$DEST" 2>/dev/null | wc -l)"
[ "$rc" -ne 0 ] && echo "  SOME DOWNLOADS FAILED — do not treat this as complete."
exit "$rc"
