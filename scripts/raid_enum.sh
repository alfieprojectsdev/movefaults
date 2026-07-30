#!/usr/bin/env bash
# raid_enum.sh — enumerate the physical members behind the PERC H750 on gps3
#
# The controller hides its physical disks: /proc/scsi/scsi shows only the
# virtual disk, and there is no /sys/class/enclosure (the backplane is not
# exposed via SES). smartctl's `-d megaraid,N` transport tunnels SMART
# commands through the megaraid_sas driver to each member drive, which is the
# only enumeration path available without a vendor CLI.
#
# READ-ONLY: this issues SMART inquiries. It does not touch the array,
# the VD, or any filesystem.
#
# Usage:  sudo ./raid_enum.sh > ~/raid-enum.log 2>&1
#
# NOTE: deliberately NOT using `set -e`. smartctl's exit status is a bitmask
# (bit1 = open failed, bit2 = SMART cmd failed, bit6/7 = error-log entries
# present), so it returns non-zero on perfectly healthy drives and on every
# absent device ID we probe. `set -e` would abort the scan on the first gap.
set -uo pipefail

VD_DEV="/dev/sda"
MAX_ID=63          # PERC device IDs are usually 0..N but can start high
CACHE="/tmp/raid_enum_cache"
mkdir -p "$CACHE"

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "must run as root: sudo $0" >&2; exit 1; }

# ── 0. Dependency ─────────────────────────────────────────────────────────────
step "0. smartmontools"
if command -v smartctl >/dev/null 2>&1; then
    ok "already installed: $(smartctl --version | head -1)"
else
    echo "  installing from the Ubuntu archive..."
    DEBIAN_FRONTEND=noninteractive apt-get install -y -q smartmontools \
        || { echo "apt install failed" >&2; exit 1; }
    ok "installed: $(smartctl --version | head -1)"
    # The package enables a smartd monitoring daemon by default. Harmless and
    # arguably useful on a server, but announce it rather than leave it silent.
    if systemctl is-enabled smartd >/dev/null 2>&1; then
        warn "smartd daemon was enabled by the package (disable with:"
        warn "  systemctl disable --now smartd )"
    fi
fi

# ── 1. Virtual disk, for the arithmetic later ─────────────────────────────────
step "1. Virtual disk"
VD_SECTORS=$(cat /sys/block/"$(basename "$VD_DEV")"/size)
VD_BYTES=$(( VD_SECTORS * 512 ))
printf '  %s : %s sectors = %s bytes\n' "$VD_DEV" "$VD_SECTORS" "$VD_BYTES"
printf '  %.2f TB (decimal)   %.2f TiB (binary)\n' \
    "$(echo "$VD_BYTES/1000000000000" | bc -l)" \
    "$(echo "$VD_BYTES/1099511627776" | bc -l)"

# ── 2. Probe every device ID ──────────────────────────────────────────────────
step "2. Probing megaraid device IDs 0..${MAX_ID}"
echo "  (absent IDs are silent; each hit prints one line)"
echo

printf '  %-4s %-10s %-22s %-18s %-10s %-8s %s\n' \
    "ID" "BUS" "MODEL" "SERIAL" "CAPACITY" "RPM" "HEALTH"
printf '  %s\n' "------------------------------------------------------------------------------------------------"

FOUND=0
TOTAL_BYTES=0
: > "$CACHE/sizes"
: > "$CACHE/concerns"

for id in $(seq 0 "$MAX_ID"); do
    out=""
    bus=""
    # SAS/SCSI members answer to megaraid,N; SATA members need the sat+ layer.
    for transport in "megaraid,$id" "sat+megaraid,$id"; do
        o=$(smartctl -i -H "-d" "$transport" "$VD_DEV" 2>/dev/null)
        if echo "$o" | grep -qiE '^(Device Model|Model Number|Product|Vendor):'; then
            out="$o"; bus="${transport%%,*}"
            break
        fi
    done
    [ -z "$out" ] && continue

    FOUND=$((FOUND + 1))

    model=$(echo "$out"  | grep -iE '^(Device Model|Model Number|Product):' | head -1 | cut -d: -f2- | xargs)
    vendor=$(echo "$out" | grep -iE '^Vendor:'                              | head -1 | cut -d: -f2- | xargs)
    serial=$(echo "$out" | grep -iE '^Serial [Nn]umber:'                    | head -1 | cut -d: -f2- | xargs)
    rpm=$(echo "$out"    | grep -iE '^Rotation Rate:'                       | head -1 | cut -d: -f2- | xargs)
    health=$(echo "$out" | grep -iE 'SMART overall-health|SMART Health Status' | head -1 | cut -d: -f2- | xargs)

    # "User Capacity: 4,000,787,030,016 bytes [4.00 TB]"
    capline=$(echo "$out" | grep -iE '^User Capacity:|^Total NVM Capacity:' | head -1)
    capbytes=$(echo "$capline" | sed 's/,//g' | grep -oE '[0-9]{6,}' | head -1)
    caphuman=$(echo "$capline" | grep -oE '\[[^]]+\]' | tr -d '[]' | head -1)

    [ -z "$model" ] && model="$vendor"
    [ -z "$rpm" ] && rpm="?"
    [ -z "$health" ] && health="?"
    [ -z "$caphuman" ] && caphuman="?"

    if [ -n "$capbytes" ]; then
        TOTAL_BYTES=$(( TOTAL_BYTES + capbytes ))
        echo "$capbytes" >> "$CACHE/sizes"
    fi

    printf '  %-4s %-10s %-22s %-18s %-10s %-8s %s\n' \
        "$id" "$bus" "${model:0:22}" "${serial:0:18}" "$caphuman" "${rpm%% *}" "$health"

    # Flag anything that is not a clean PASSED/OK
    if ! echo "$health" | grep -qiE '^(PASSED|OK)$'; then
        echo "id=$id model=$model serial=$serial health=$health" >> "$CACHE/concerns"
    fi

    # Reallocated / pending / uncorrectable sectors — the failure mode that
    # motivated this whole check.
    att=$(smartctl -A "-d" "${bus},${id}" "$VD_DEV" 2>/dev/null \
          | grep -iE 'Reallocated_Sector|Current_Pending_Sector|Offline_Uncorrectable|Reallocated_Event' \
          | awk '$10 != 0 {print "      " $2 " = " $10}')
    if [ -n "$att" ]; then
        echo "$att"
        echo "id=$id model=$model serial=$serial bad-sectors:" >> "$CACHE/concerns"
        echo "$att" >> "$CACHE/concerns"
    fi
done

# ── 3. Summary and RAID-level inference ───────────────────────────────────────
step "3. Summary"

if [ "$FOUND" -eq 0 ]; then
    warn "no physical members answered on any device ID 0..${MAX_ID}."
    warn "The megaraid SMART tunnel may be blocked by this firmware."
    warn "Fall back to the iDRAC web UI, or install Broadcom storcli / Dell perccli."
    exit 2
fi

ok "$FOUND physical members enumerated"
printf '  raw total : %.2f TB (decimal)\n' "$(echo "$TOTAL_BYTES/1000000000000" | bc -l)"
printf '  VD usable : %.2f TB (decimal)\n' "$(echo "$VD_BYTES/1000000000000" | bc -l)"

# Distinct member capacities — a mixed-size array changes the arithmetic.
distinct=$(sort -u "$CACHE/sizes" | wc -l)
if [ "$distinct" -gt 1 ]; then
    warn "members are NOT all the same size ($distinct distinct capacities) —"
    warn "the inference below assumes a uniform array; treat it as a hint only."
fi

step "4. RAID level inference"
echo "  Comparing the VD's usable capacity against what each level would yield"
echo "  from $FOUND members. The matching row is the array's level."
echo

C=$(sort -u "$CACHE/sizes" | head -1)   # per-member capacity
N=$FOUND
if [ -n "$C" ] && [ "$N" -gt 0 ]; then
    printf '  %-10s %-16s %s\n' "LEVEL" "WOULD YIELD" "MATCH?"
    printf '  %s\n' "-------------------------------------------------"
    check() {
        local label="$1" expect_b="$2"
        local tb pct
        tb=$(echo "$expect_b/1000000000000" | bc -l)
        # within 3% tolerance: controller metadata + rounding
        pct=$(echo "define abs(x){if(x<0)return -x;return x} abs($expect_b - $VD_BYTES)/$VD_BYTES*100" | bc -l)
        if [ "$(echo "$pct < 3" | bc -l)" -eq 1 ]; then
            printf '  %-10s %-16s \033[1;32m<<< MATCH\033[0m\n' "$label" "$(printf '%.2f TB' "$tb")"
            echo "$label" >> "$CACHE/match"
        else
            printf '  %-10s %-16s\n' "$label" "$(printf '%.2f TB' "$tb")"
        fi
    }
    : > "$CACHE/match"
    check "RAID 0"  "$(( C * N ))"
    [ "$N" -ge 3 ] && check "RAID 5"  "$(( C * (N - 1) ))"
    [ "$N" -ge 4 ] && check "RAID 6"  "$(( C * (N - 2) ))"
    [ "$N" -ge 4 ] && [ $((N % 2)) -eq 0 ] && check "RAID 10" "$(( C * N / 2 ))"
    [ "$N" -eq 2 ] && check "RAID 1"  "$C"

    echo
    if [ -s "$CACHE/match" ]; then
        m=$(tr '\n' ' ' < "$CACHE/match")
        if [ "$(wc -l < "$CACHE/match")" -gt 1 ]; then
            warn "ambiguous — more than one level fits: $m"
            warn "Confirm via iDRAC or storcli before relying on redundancy."
        else
            ok "inferred level: $m"
            case "$m" in
                *"RAID 0"*)
                    echo
                    printf '  \033[1;31mNO REDUNDANCY.\033[0m A single drive failure destroys the whole array.\n'
                    printf '  gps3 must NOT be the only copy of the legacy GNSS archive.\n'
                    ;;
                *)
                    echo
                    ok "redundant — gps3 can host the archive (still keep a second copy offsite)"
                    ;;
            esac
        fi
    else
        warn "no level matched within 3%. Members may be mixed-size, the array may"
        warn "span multiple VDs, or spares/foreign drives are inflating the count."
    fi
fi

# ── 5. Health concerns ────────────────────────────────────────────────────────
step "5. Drive health"
if [ -s "$CACHE/concerns" ]; then
    printf '  \033[1;31mISSUES FOUND:\033[0m\n'
    sed 's/^/    /' "$CACHE/concerns"
else
    ok "all members report PASSED/OK with zero reallocated, pending or"
    ok "uncorrectable sectors"
fi

step "Done"
echo "  Read-only: no array, VD or filesystem state was modified."
