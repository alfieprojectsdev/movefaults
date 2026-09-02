#!/usr/bin/env bash
# stage_national_campaign.sh — stage the full PH network for a year, not one subnetwork.
#
# WHY THIS IS SEPARATE FROM stage_luzon_campaign.sh
# That script hard-codes the 25 LUZON stations, deliberately: the 2025 LUZON run
# had to stay comparable with 30 days already solved, so the network could not
# change. This one takes the opposite position -- every PH station with data for
# the year -- and the two must not be conflated. Running this against the LUZON
# campaign would silently enlarge that network and invalidate the comparison.
#
# THE BLOCKER THAT WASN'T
# "Station metadata for the other ~80 sites" was carried as a blocker for weeks.
# It is four files on the file server, fetched in one pass:
#
#   PHIVOLCS.STA   station information   119,760 B
#   PHIVOLCS.BLQ   ocean loading         113,350 B
#   PHIVOLCS.VEL   velocities             13,090 B
#   WK_2405.CRD    439-station a priori   30,489 B   <- the "439 catalogued"
#
# Together they cover 101/101 stations with 2025 data. The blocker was never
# the metadata's absence; it was that nobody had looked.
#
# Usage:
#   scripts/stage_national_campaign.sh --fetch-meta     # pull the 4 files over SMB
#   scripts/stage_national_campaign.sh --dry-run
#   scripts/stage_national_campaign.sh --apply
set -uo pipefail

NAT_YEAR="${NAT_YEAR:-2025}"
NAT_CAMPAIGN="${NAT_CAMPAIGN:-PHNAT}"
NAT_SRC="${NAT_SRC:-/srv/gnss-archive/datapool/PHIVOLCS}"
NAT_META="${NAT_META:-$HOME/phivolcs-meta}"
NAT_DOY_FROM="${NAT_DOY_FROM:-1}"
NAT_DOY_TO="${NAT_DOY_TO:-365}"
SMB_STA='\\192.168.48.99\Bernese\GPSDATA\CAMPAIGN52\PHIVOLCS\STA'

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }

MODE="${1:-}"
case "$MODE" in --fetch-meta|--dry-run|--apply) ;; *) die "usage: $0 --fetch-meta | --dry-run | --apply" ;; esac

_snap="$NAT_YEAR|$NAT_CAMPAIGN|$NAT_SRC|$NAT_META|$NAT_DOY_FROM|$NAT_DOY_TO"
# shellcheck disable=SC1090,SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || die "cannot source LOADGPS.setvar"
[ "$_snap" = "$NAT_YEAR|$NAT_CAMPAIGN|$NAT_SRC|$NAT_META|$NAT_DOY_FROM|$NAT_DOY_TO" ] \
    || die "LOADGPS clobbered a config variable -- use NAT_-prefixed names"
if [ -z "${P:-}" ] || [ -z "${D:-}" ] || [ -z "${U:-}" ]; then die "P/D/U unset"; fi

if [ "$MODE" = "--fetch-meta" ]; then
    mkdir -p "$NAT_META"
    uv run --quiet --with smbprotocol python - "$NAT_META" <<'PY'
import sys, pathlib
from smbclient import register_session, open_file
dest = pathlib.Path(sys.argv[1])
register_session("192.168.48.99", username="guest", password="", encrypt=False)
C = r"\\192.168.48.99\Bernese\GPSDATA\CAMPAIGN52\PHIVOLCS\STA"
for n in ("PHIVOLCS.STA", "PHIVOLCS.BLQ", "PHIVOLCS.VEL", "WK_2405.CRD", "IGS.STA"):
    try:
        with open_file(f"{C}\\{n}", mode="rb") as f:
            d = f.read()
        (dest / n).write_bytes(d)
        print(f"  {n}: {len(d):,} bytes")
    except Exception as exc:
        print(f"  {n}: FAILED {type(exc).__name__}: {exc}")
PY
    say ""
    say "fetched to $NAT_META. These are READ-ONLY copies of the file server's"
    say "authoritative metadata; the server remains the system of record."
    exit 0
fi

for f in PHIVOLCS.STA PHIVOLCS.BLQ WK_2405.CRD; do
    [ -s "$NAT_META/$f" ] || die "missing $NAT_META/$f -- run --fetch-meta first"
done

# The station list is DERIVED from the data, not hard-coded. That is the whole
# difference from the LUZON script: this campaign is defined as "everything with
# observations", so the list cannot drift from what is actually processable.
# EXCLUDED, and why. These five sit in the datapool but are IGS regional
# fiducials rather than PH network sites -- Bitung, Guam, Manila-PTAG,
# Shanghai, Taiwan -- and none has ocean-loading coefficients in any BLQ file
# we hold. Including them would either fail the metadata guard below or, worse,
# process them without tidal loading and quietly degrade their coordinates.
#
# The seven fiducials this pipeline actually uses come from
# scripts/fetch_fiducial_obs.sh and DO have coefficients. If these five are
# ever wanted, get their BLQ blocks from the Onsala service and merge with
# scripts/merge_blq.py -- do not simply delete this list.
NAT_EXCLUDE="${NAT_EXCLUDE:-BTNG GUUG PTAG SHAO TNML}"

# Codes are UPPERCASED, and the -o branches are grouped. Some IGS sites are
# stored with lowercase filenames (shao0890.25d.gz), so a raw cut yields
# "shao", which then fails a case-sensitive grep against .STA and looks like a
# missing station. Bernese station codes are uppercase; the filename case is
# only a convention of whoever downloaded them.
mapfile -t STATIONS < <(find "$NAT_SRC" -maxdepth 1 \
    \( -name "*.${NAT_YEAR: -2}[oOdD]" -o -name "*.${NAT_YEAR: -2}[dD].gz" \) 2>/dev/null \
    | sed 's|.*/||' | cut -c1-4 | tr '[:lower:]' '[:upper:]' | sort -u \
    | grep -vxF -e "$(echo "$NAT_EXCLUDE" | tr ' ' '\n')")
[ "${#STATIONS[@]}" -gt 0 ] || die "no $NAT_YEAR observations under $NAT_SRC"

say "=== national campaign $NAT_CAMPAIGN, $NAT_YEAR DOY $NAT_DOY_FROM-$NAT_DOY_TO ==="
say "  stations with data : ${#STATIONS[@]}  (excluding: $NAT_EXCLUDE)"

# Refuse to proceed on a station the metadata cannot describe -- a station
# present in the observations but absent from .STA/.BLQ/.CRD does not fail
# loudly, it produces a solution quietly missing that site.
missing=0
for s in "${STATIONS[@]}"; do
    for f in PHIVOLCS.STA PHIVOLCS.BLQ WK_2405.CRD; do
        grep -q "\b$s\b" "$NAT_META/$f" || { say "  !! $s absent from $f"; missing=$((missing+1)); }
    done
done
[ "$missing" -eq 0 ] || die "$missing station/metadata gap(s) -- resolve before staging"
say "  metadata coverage  : ${#STATIONS[@]}/${#STATIONS[@]} across .STA .BLQ .CRD"

if [ "$MODE" = "--dry-run" ]; then
    n=0
    for doy in $(seq "$NAT_DOY_FROM" "$NAT_DOY_TO"); do
        d3=$(printf '%03d' "$doy")
        for s in "${STATIONS[@]}"; do
            for f in "$NAT_SRC/${s}${d3}0.${NAT_YEAR: -2}"[oOdD] "$NAT_SRC/${s}${d3}0.${NAT_YEAR: -2}"[dD].gz; do
                [ -e "$f" ] && n=$((n+1))
            done
        done
    done
    say "  would stage        : $n station-day files"
    say ""
    say "Dry run -- nothing written."
    exit 0
fi

say "  staging into       : \$P/$NAT_CAMPAIGN and \$D/$NAT_CAMPAIGN"
for sub in ATM BPE GRD OBS ORB ORX OUT RAW SOL STA; do
    mkdir -p "$P/$NAT_CAMPAIGN/$sub"
done
mkdir -p "$D/$NAT_CAMPAIGN"

cp -f "$NAT_META/PHIVOLCS.STA" "$P/$NAT_CAMPAIGN/STA/$NAT_CAMPAIGN.STA"
cp -f "$NAT_META/PHIVOLCS.BLQ" "$P/$NAT_CAMPAIGN/STA/$NAT_CAMPAIGN.BLQ"
cp -f "$NAT_META/WK_2405.CRD"  "$P/$NAT_CAMPAIGN/STA/$NAT_CAMPAIGN.CRD"
[ -s "$NAT_META/PHIVOLCS.VEL" ] && cp -f "$NAT_META/PHIVOLCS.VEL" "$P/$NAT_CAMPAIGN/STA/$NAT_CAMPAIGN.VEL"
say "  station files      : installed as $NAT_CAMPAIGN.{STA,BLQ,CRD,VEL}"

n=0; thin=0
for doy in $(seq "$NAT_DOY_FROM" "$NAT_DOY_TO"); do
    d3=$(printf '%03d' "$doy"); today=0
    for s in "${STATIONS[@]}"; do
        for f in "$NAT_SRC/${s}${d3}0.${NAT_YEAR: -2}"[oOdD] "$NAT_SRC/${s}${d3}0.${NAT_YEAR: -2}"[dD].gz; do
            [ -e "$f" ] || continue
            cp -n "$f" "$D/$NAT_CAMPAIGN/" 2>/dev/null
            n=$((n+1)); today=$((today+1))
        done
    done
    # Named at staging time rather than surfacing as a confusing BPE failure
    # hours later. Three is well under a normal day and is the threshold the
    # LUZON script settled on.
    [ "$today" -lt 3 ] && { say "    !! DOY $d3: only $today file(s)"; thin=$((thin+1)); }
done

say "  staged             : $n station-day files"
[ "$thin" -gt 0 ] && say "  !! $thin day(s) with fewer than 3 stations -- review before running those"
say ""
say "NOT done here, deliberately: the fiducial RINEX 3 observations."
say "Run scripts/fetch_fiducial_obs.sh, then copy them into \$D/$NAT_CAMPAIGN --"
say "RNX_COP globs ONE directory for both conventions, and fiducials left in"
say "\$D/RINEX3 are invisible to the run. That cost a failed DOY 001 once."
