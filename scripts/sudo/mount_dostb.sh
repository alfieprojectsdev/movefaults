#!/usr/bin/env bash
# mount_dostb.sh — mount the DOSTB20150918 archive drive READ-ONLY.
#
# WHY READ-ONLY, in order of seriousness:
#
#   1. It is currently the ONLY complete copy of the legacy GNSS archive.
#      /srv/gnss-archive/legacy on this machine is still empty. Until a second
#      copy exists, a write error here is unrecoverable data loss for the
#      project.
#   2. The RECOVERED_* directories were rescued from dead or dying hardware.
#      There is nothing left to re-rescue from.
#   3. NTFS-3G write support works, but a read-only mount removes the entire
#      class of accident rather than relying on nobody making one.
#
# WHY THIS RESOLVES THE DEVICE BY LABEL, NOT BY /dev/sdX:
# sdX assignment is not stable across reboots or other USB devices, and this
# project has a documented history of it shifting between sessions. Mounting
# the wrong device read-only is harmless; running a 157 GB rsync FROM the wrong
# device is a wasted window on a drive that will not stay attached. The label
# is stable, so we use it and print what it resolved to for confirmation.
#
# Usage:  sudo scripts/sudo/mount_dostb.sh          # mount
#         sudo scripts/sudo/mount_dostb.sh --umount # unmount cleanly
set -uo pipefail

LABEL="DOSTB20150918"
MNT="/mnt/dostb"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: needs root — run with sudo." >&2
    exit 1
fi

if [ "${1:-}" = "--umount" ]; then
    if mountpoint -q "$MNT"; then
        # Refuse while anything is reading it: yanking the mount out from under
        # a running rsync produces a partial copy that still exits 0.
        if command -v lsof >/dev/null 2>&1; then
            open=$(lsof +D "$MNT" 2>/dev/null | tail -n +2 || true)
            if [ -n "$open" ]; then
                echo "REFUSING to unmount — files are open under $MNT:"
                printf '%s\n' "$open" | head -10
                exit 1
            fi
        fi
        sync
        umount "$MNT" && echo "unmounted $MNT"
    else
        echo "$MNT is not mounted — nothing to do"
    fi
    exit 0
fi

echo "=== block devices ==="
lsblk -o NAME,SIZE,FSTYPE,LABEL,MOUNTPOINT | grep -vE '^loop'

DEV=$(blkid -L "$LABEL" 2>/dev/null)
if [ -z "$DEV" ]; then
    echo
    echo "ERROR: no device with label '$LABEL' found." >&2
    echo "  Is the drive plugged in and spun up? Check the listing above." >&2
    echo "  If the label differs, mount by hand:" >&2
    echo "     sudo mount -o ro,noatime /dev/sdX1 $MNT" >&2
    exit 1
fi

echo
echo "label '$LABEL' resolves to: $DEV"

if mountpoint -q "$MNT"; then
    src=$(findmnt -n -o SOURCE --target "$MNT")
    opts=$(findmnt -n -o OPTIONS --target "$MNT")
    echo "$MNT is already mounted from $src"
    case "$opts" in
        ro,*|*,ro,*|*,ro) echo "  options: $opts  — read-only, good" ;;
        *) echo "  WARNING: options are '$opts' — NOT read-only. Unmount and re-run." >&2; exit 1 ;;
    esac
else
    mkdir -p "$MNT"
    if ! mount -o ro,noatime "$DEV" "$MNT"; then
        echo "ERROR: mount failed. If NTFS is dirty from an unclean Windows" >&2
        echo "  eject, ntfs-3g may refuse. Do NOT force with 'remove_hiberfile'" >&2
        echo "  or run ntfsfix — both WRITE to the drive." >&2
        exit 1
    fi
    echo "mounted $DEV -> $MNT (ro,noatime)"
fi

# Prove read-only rather than trusting the option string.
if touch "$MNT/.write_probe" 2>/dev/null; then
    rm -f "$MNT/.write_probe"
    echo "CRITICAL: the mount accepted a write. Unmount immediately." >&2
    exit 1
fi
echo "verified: writes are rejected"

echo
echo "=== RECOVERED_* directories present (globbed, not assumed) ==="
shopt -s nullglob
found=("$MNT"/RECOVERED_*)
if [ ${#found[@]} -eq 0 ]; then
    echo "  NONE FOUND — wrong drive, or the layout differs from the handover."
else
    for d in "${found[@]}"; do
        printf '  %-52s %s\n' "$(basename "$d")" "$(du -sh "$d" 2>/dev/null | cut -f1)"
    done
    echo
    printf '  %-52s %s\n' "TOTAL" "$(du -sch "${found[@]}" 2>/dev/null | tail -1 | cut -f1)"
fi
echo
echo "The handover's table listed three directories and missed one."
echo "Whatever is listed above is the truth; the table is not."
