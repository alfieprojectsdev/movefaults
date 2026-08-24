#!/usr/bin/env bash
# fetch_fiducial_obs.sh — download RINEX 3 daily observations for the fiducial
# stations that realise the datum.
#
# WHY THIS EXISTS
# `fetch_igs_products.sh` gets orbits, clocks, ERP and biases. Nothing in this
# repository fetched the fiducial *observations* — `igs_downloader.py` is a
# ProductDownloader and reads `/gnss/products/`, not `/gnss/data/`. The 31-day
# LUZON run did not need one because Abegail's copied set happened to include
# 32 days of RINEX 3. Extending to a full year exposed the gap: without these,
# every day outside that window has no datum to constrain it.
#
# WHAT THE DATUM ACTUALLY DEPENDS ON
# The daily REF_*.FIX files name five to six of these as the constrained set --
# ALIC, DAEJ, DARW, MCIL, PIMO, sometimes PNGM. They are what ties the network
# to ITRF. A day missing them is not a slightly worse day, it is a day whose
# coordinates are not in the reference frame the rest of the series uses.
#
# BASC AND CLAV ARE NOT HERE, DELIBERATELY
# Both are PHIVOLCS-operated RINEX 3 sites and return 404 from IGS. They are
# ordinary network stations, not part of the constrained set, so their absence
# outside the 31-day window costs coverage rather than datum. They come from
# the file server (192.168.48.99) if wanted; do not "fix" this by dropping
# them into an IGS fetch that cannot serve them.
#
# MIRROR
# BKG over HTTPS, the same host `fetch_igs_products.sh` already uses for IGS
# products and which is known to work through the PHIVOLCS firewall. CDDIS
# needs an Earthdata login; AIUB's FTP is firewalled.
#
# IDEMPOTENT: a file already present with non-zero size is skipped, so a run
# interrupted anywhere resumes rather than restarting.
#
# PARALLELISM: measured, not guessed. One stream off this link runs at ~190
# KB/s; four concurrent streams reach ~425 KB/s aggregate, so the limit is
# per-connection latency rather than bandwidth. Four is where the measurement
# was taken and is polite to a public mirror -- this is ~2,500 files and BKG is
# a courtesy, not a contract. Raising it further was not tested and should be
# measured before being assumed to help.
#
# Usage:
#   scripts/fetch_fiducial_obs.sh <year> <doy_from> <doy_to> [--dry-run]
#   scripts/fetch_fiducial_obs.sh 2025 1 365
set -uo pipefail

YEAR="${1:?usage: $0 <year> <doy_from> <doy_to> [--dry-run]}"
FROM="${2:?usage: $0 <year> <doy_from> <doy_to> [--dry-run]}"
TO="${3:?usage: $0 <year> <doy_from> <doy_to> [--dry-run]}"
DRY="${4:-}"

# The nine-character IGS station IDs used by the LUZON campaign. AIRA is
# included because the staged set carries it, even though the daily REF_*.FIX
# files have not selected it as a constraint.
STATIONS="AIRA00JPN ALIC00AUS DAEJ00KOR DARW00AUS MCIL00JPN PIMO00PHL PNGM00PNG"
BASE="https://igs.bkg.bund.de/root_ftp/IGS/obs"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# shellcheck disable=SC1090,SC1091
source "$HOME/BERN54/LOADGPS.setvar" >/dev/null 2>&1 || die "cannot source LOADGPS.setvar"
[ -n "${D:-}" ] || die "D unset after LOADGPS"

DEST="$D/RINEX3"
mkdir -p "$DEST" || die "cannot create $DEST"

printf '=== fiducial RINEX 3 observations: %s DOY %s-%s ===\n' "$YEAR" "$FROM" "$TO"
printf 'mirror : %s\n' "$BASE"
printf 'dest   : %s\n' "$DEST"
printf 'sites  : %s\n\n' "$STATIONS"

PARALLEL="${PARALLEL:-4}"
STATE=$(mktemp -d) || die "cannot make a temp dir"
trap 'rm -rf "$STATE"' EXIT

# One file. Runs in a subshell under `&`, so it reports by writing a line to
# $STATE rather than by setting a variable the parent could never see.
fetch_one() {
    local f="$1" url="$2" out="$DEST/$1"
    if [ -s "$out" ]; then echo "skip" >> "$STATE/log"; return; fi
    rm -f "$out" "$out.part"
    local code
    code=$(curl -sS -o "$out.part" -w '%{http_code}' --max-time 300 \
                --retry 2 --retry-delay 3 "$url" 2>/dev/null)
    case "$code" in
        200)
            # A mirror can return 200 with an error page. Gzip magic is the
            # cheap check that this is the file and not an apology for it.
            if [ -s "$out.part" ] && \
               [ "$(head -c2 "$out.part" | od -An -tx1 | tr -d ' \n')" = "1f8b" ]; then
                mv -f "$out.part" "$out"; echo "ok" >> "$STATE/log"
            else
                rm -f "$out.part"; echo "fail $f not-gzip" >> "$STATE/log"
            fi
            ;;
        404)
            # Routine: stations go offline. Recorded, not treated as an error.
            rm -f "$out.part"; echo "miss $f" >> "$STATE/log"
            ;;
        *)
            rm -f "$out.part"; echo "fail $f HTTP-$code" >> "$STATE/log"
            ;;
    esac
}

: > "$STATE/log"
running=0
for doy in $(seq "$FROM" "$TO"); do
    d3=$(printf '%03d' "$doy")
    for s in $STATIONS; do
        f="${s}_R_${YEAR}${d3}0000_01D_30S_MO.crx.gz"
        if [ "$DRY" = "--dry-run" ]; then
            [ -s "$DEST/$f" ] || printf '  would fetch %s\n' "$f"
            continue
        fi
        fetch_one "$f" "$BASE/$YEAR/$d3/$f" &
        running=$((running + 1))
        if [ "$running" -ge "$PARALLEL" ]; then wait -n 2>/dev/null || wait; running=$((running - 1)); fi
    done
    if [ $((doy % 20)) -eq 0 ] || [ "$doy" = "$TO" ]; then
        printf '  DOY %s  ok=%d skip=%d missing=%d fail=%d  (%s)\n' "$d3" \
          "$(grep -c '^ok'   "$STATE/log")" "$(grep -c '^skip' "$STATE/log")" \
          "$(grep -c '^miss' "$STATE/log")" "$(grep -c '^fail' "$STATE/log")" \
          "$(date '+%H:%M:%S')"
    fi
done
wait

if [ "$DRY" = "--dry-run" ]; then
    printf '\nDry run — nothing written.\n'; exit 0
fi

ok=$(grep -c '^ok'   "$STATE/log")
skip=$(grep -c '^skip' "$STATE/log")
miss=$(grep -c '^miss' "$STATE/log")
fail=$(grep -c '^fail' "$STATE/log")
missing_list=$(awk '/^miss/ {split($2,a,"_"); split($2,b,"00"); printf "%s:%s ", b[1], substr(a[3],5,3)}' "$STATE/log")
grep '^fail' "$STATE/log" | head -10 | sed 's/^/  !! /' 

printf '\n%s\n' "----------------------------------------------------------"
printf 'downloaded %d   already present %d   absent upstream %d   failed %d\n' \
       "$ok" "$skip" "$miss" "$fail"

if [ "$miss" -gt 0 ]; then
    printf '\nAbsent upstream (station:doy) — these are station outages, not errors,\n'
    printf 'but a day short of constrained sites is a day whose datum is weaker.\n'
    printf 'Check per-day coverage before trusting those solutions:\n'
    printf '%s\n' "$missing_list" | tr ' ' '\n' | grep -v '^$' | \
        awk -F: '{c[$1]++} END {for (s in c) printf "  %-6s %d day(s)\n", s, c[s]}'
fi

[ "$fail" -eq 0 ] || { printf '\n%d download(s) FAILED — re-run to resume.\n' "$fail" >&2; exit 1; }
