#!/usr/bin/env bash
# gps3_storage_provision.sh — carve the unallocated PERC volume on gps3 into LVs
#
# Context: gps3 (Dell R740) has a ~32.7 TB PERC H750 hardware-RAID virtual disk,
# but the Ubuntu installer only claimed a 100 G root LV. Everything else sits as
# free extents in the volume group. This script allocates it.
#
# SAFE BY DESIGN — this script never touches existing data:
#   * grows the root LV/filesystem online (no unmount, no reboot)
#   * creates NEW logical volumes from free extents only
#   * mkfs runs WITHOUT -f, so it refuses any device that already has a
#     filesystem (a typo cannot wipe a populated volume)
#   * mounts lv_gpsdata at a STAGING path, never over the live ~/GPSDATA
#   * fstab entries use nofail, so a bad entry can never block boot
#
# Moving the existing GPSDATA onto the new volume is deliberately NOT done here.
# That is the only step that can lose data — see gps3_gpsdata_migrate.sh.
#
# Usage:
#   sudo ./gps3_storage_provision.sh              # DRY RUN (default) — prints, changes nothing
#   sudo ./gps3_storage_provision.sh --apply      # actually make the changes
#   ./gps3_storage_provision.sh --help
#
# Run it inside tmux, because an SSH drop mid-resize would otherwise SIGHUP it:
#   ssh -t gps3@192.168.48.98 'tmux new -As storage'

set -euo pipefail

# ── Tunables ──────────────────────────────────────────────────────────────────
VG="ubuntu-vg"
ROOT_LV="ubuntu-lv"
ROOT_TARGET="250G"          # grown from the installer's 100G; OS/packages only

# LVM -L sizes are binary (1T = 1TiB).
LV_GPSDATA_SIZE="4T"        # live campaigns, DATAPOOL, SAVEDISK  ($P/$D/$S)
LV_ARCHIVE_SIZE="20T"       # legacy GNSS data from the external drives
LV_WORK_SIZE="1T"           # BPE scratch ($T) — churns small files, kept apart

TARGET_USER="${SUDO_USER:-gps3}"
TARGET_HOME="/home/${TARGET_USER}"

GPSDATA_STAGING="/mnt/lv_gpsdata_staging"
ARCHIVE_MOUNT="/srv/gnss-archive"
WORK_MOUNT="${TARGET_HOME}/GPSWORK"

MOUNT_OPTS="defaults,noatime,nofail"

APPLY=0

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
    case "$1" in
        --apply) APPLY=1; shift ;;
        --dry-run) APPLY=0; shift ;;
        -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; echo "Try --help" >&2; exit 1 ;;
    esac
done

# ── Output helpers ────────────────────────────────────────────────────────────
step() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

# Print every command before running it; only execute under --apply.
run() {
    printf '  $ %s\n' "$*"
    if [ "$APPLY" -eq 1 ]; then
        "$@" || die "command failed: $*"
    fi
}

# ── Predicates (all safe to call when the object does not exist) ──────────────
lv_exists()  { lvs --noheadings -o lv_name "${VG}/$1" >/dev/null 2>&1; }
has_fs()     { [ -n "$(lsblk -no FSTYPE "$1" 2>/dev/null | head -1)" ]; }
is_mnt()     { mountpoint -q "$1" 2>/dev/null; }
in_fstab()   { grep -qsF " $1 " /etc/fstab; }
lv_dev()     { echo "/dev/${VG}/$1"; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
step "Pre-flight checks"

[ "$(id -u)" -eq 0 ] || die "must run as root (use: sudo $0)"

if [ "$APPLY" -eq 1 ]; then
    warn "APPLY MODE — changes will be written"
else
    ok "DRY RUN — nothing will be modified (re-run with --apply to commit)"
fi

for c in lvs vgs lvextend lvcreate mkfs.xfs resize2fs findmnt blkid; do
    command -v "$c" >/dev/null || die "missing required command: $c"
done
ok "required tools present"

vgs --noheadings -o vg_name "$VG" >/dev/null 2>&1 || die "volume group '$VG' not found"
ok "volume group '$VG' found"

[ -d "$TARGET_HOME" ] || die "target home '$TARGET_HOME' does not exist (wrong TARGET_USER?)"
ok "target user: ${TARGET_USER} (${TARGET_HOME})"

# Confirm the free space really exists rather than trusting an lsblk inference.
VG_FREE_B=$(vgs --noheadings --nosuffix --units b -o vg_free "$VG" | tr -d ' ')
ROOT_CUR_B=$(lvs --noheadings --nosuffix --units b -o lv_size "${VG}/${ROOT_LV}" | tr -d ' ')

# numfmt --from=iec takes bare binary suffixes (250G = 250 GiB), matching how
# LVM interprets -L. "250GiB" is NOT valid input and errors out — do not add
# an "|| echo 0" fallback here: a zero target would silently skip the root
# extend while still reporting success.
to_bytes() { numfmt --from=iec "$1" || die "cannot parse size '$1' (use forms like 250G, 4T)"; }

ROOT_TARGET_B=$(to_bytes "$ROOT_TARGET")

root_growth_b=0
if [ "$ROOT_TARGET_B" -gt "$ROOT_CUR_B" ]; then
    root_growth_b=$(( ROOT_TARGET_B - ROOT_CUR_B ))
fi

need_b=$root_growth_b
for s in "$LV_GPSDATA_SIZE" "$LV_ARCHIVE_SIZE" "$LV_WORK_SIZE"; do
    need_b=$(( need_b + $(to_bytes "$s") ))
done

printf '  VG free      : %s\n' "$(numfmt --to=iec --suffix=B "$VG_FREE_B")"
printf '  root now     : %s  → target %s\n' \
    "$(numfmt --to=iec --suffix=B "$ROOT_CUR_B")" "$ROOT_TARGET"
printf '  total needed : %s\n' "$(numfmt --to=iec --suffix=B "$need_b")"

if [ "$need_b" -gt "$VG_FREE_B" ]; then
    die "not enough free space in $VG: need $(numfmt --to=iec --suffix=B "$need_b"), have $(numfmt --to=iec --suffix=B "$VG_FREE_B")

Reduce the LV_*_SIZE values at the top of this script and re-run."
fi
ok "sufficient free space"

# A BPE run writing into GPSDATA/GPSWORK while we reshape storage is asking for
# trouble; the campaign dirs are not moved here, but scratch is remounted.
if pgrep -f "rnx2snx_pcs.pl|startBPE|BPE_" >/dev/null 2>&1; then
    die "a Bernese BPE process appears to be running — let it finish first"
fi
ok "no BPE process running"

# ── 1. Grow the root filesystem ───────────────────────────────────────────────
step "1. Root LV → ${ROOT_TARGET}"

if [ "$ROOT_CUR_B" -ge "$ROOT_TARGET_B" ]; then
    ok "root LV already ≥ ${ROOT_TARGET} — skipping extend"
else
    run lvextend -L "$ROOT_TARGET" "/dev/${VG}/${ROOT_LV}"
fi
# resize2fs is a no-op when the filesystem already fills the LV.
run resize2fs "/dev/${VG}/${ROOT_LV}"

# ── 2. Create the new logical volumes ─────────────────────────────────────────
step "2. Create logical volumes"

create_lv() {
    local name="$1" size="$2"
    if lv_exists "$name"; then
        ok "${name} already exists — skipping create"
    else
        run lvcreate -L "$size" -n "$name" "$VG"
    fi
}

create_lv lv_gpsdata "$LV_GPSDATA_SIZE"
create_lv lv_archive "$LV_ARCHIVE_SIZE"
create_lv lv_work    "$LV_WORK_SIZE"

# ── 3. Make filesystems ───────────────────────────────────────────────────────
step "3. Create XFS filesystems"
echo "  XFS: dynamic inode allocation (archives are millions of small files),"
echo "  good multi-TB throughput. Note XFS can grow but NEVER shrink."

make_fs() {
    local name="$1" label="$2" dev
    dev="$(lv_dev "$name")"

    if ! lv_exists "$name"; then
        printf '  (dry-run) would: mkfs.xfs -L %s %s\n' "$label" "$dev"
        return
    fi
    if is_mnt "$dev"; then
        die "$dev is mounted — refusing to mkfs"
    fi
    if has_fs "$dev"; then
        ok "${name} already has a filesystem ($(lsblk -no FSTYPE "$dev" | head -1)) — skipping mkfs"
        return
    fi
    # Deliberately no -f: mkfs.xfs will refuse a device that already holds a
    # filesystem. That guard is the difference between a typo and a disaster.
    run mkfs.xfs -L "$label" "$dev"
}

make_fs lv_gpsdata gpsdata
make_fs lv_archive gnssarch
make_fs lv_work    gpswork

# ── 4. Mount points ───────────────────────────────────────────────────────────
step "4. Mount points"

run mkdir -p "$GPSDATA_STAGING" "$ARCHIVE_MOUNT"

# GPSWORK ($T) was created by configure.pm option 3. Mounting over a non-empty
# directory hides its contents, so refuse rather than silently shadow.
if [ -d "$WORK_MOUNT" ] && [ -n "$(ls -A "$WORK_MOUNT" 2>/dev/null)" ] && ! is_mnt "$WORK_MOUNT"; then
    die "$WORK_MOUNT is not empty and is not a mountpoint.
Mounting over it would hide its contents. Inspect and clear it first:
    ls -la $WORK_MOUNT"
fi
run mkdir -p "$WORK_MOUNT"
ok "mount points ready"

# ── 5. fstab ──────────────────────────────────────────────────────────────────
step "5. fstab entries (nofail — a bad entry can never block boot)"

add_fstab() {
    local name="$1" mnt="$2" uuid dev
    dev="$(lv_dev "$name")"

    if in_fstab "$mnt"; then
        ok "fstab already has an entry for ${mnt} — skipping"
        return
    fi
    if ! lv_exists "$name"; then
        printf '  (dry-run) would add fstab entry: UUID=<%s> %s xfs %s 0 2\n' \
            "$name" "$mnt" "$MOUNT_OPTS"
        return
    fi
    uuid="$(blkid -s UUID -o value "$dev" 2>/dev/null || true)"
    [ -n "$uuid" ] || die "could not read UUID of $dev (was mkfs run?)"

    printf '  $ echo "UUID=%s %s xfs %s 0 2" >> /etc/fstab\n' "$uuid" "$mnt" "$MOUNT_OPTS"
    if [ "$APPLY" -eq 1 ]; then
        cp -n /etc/fstab "/etc/fstab.bak-$(date +%Y%m%d)" 2>/dev/null || true
        printf 'UUID=%s %s xfs %s 0 2\n' "$uuid" "$mnt" "$MOUNT_OPTS" >> /etc/fstab
    fi
}

# Only the two volumes with no pre-existing data get persistent entries now.
# lv_gpsdata stays staging-only until its data has actually been migrated.
add_fstab lv_archive "$ARCHIVE_MOUNT"
add_fstab lv_work    "$WORK_MOUNT"

# ── 6. Mount and validate ─────────────────────────────────────────────────────
step "6. Mount and validate"

if [ "$APPLY" -eq 1 ]; then
    # Catches a malformed fstab BEFORE a reboot can act on it.
    run findmnt --verify --verbose
    run mount -a
else
    echo "  (dry-run) would: findmnt --verify --verbose && mount -a"
fi

# Staging mount is intentionally transient — not in fstab.
if lv_exists lv_gpsdata && ! is_mnt "$GPSDATA_STAGING"; then
    run mount -o "defaults,noatime" "$(lv_dev lv_gpsdata)" "$GPSDATA_STAGING"
elif ! lv_exists lv_gpsdata; then
    printf '  (dry-run) would: mount %s %s\n' "$(lv_dev lv_gpsdata)" "$GPSDATA_STAGING"
else
    ok "staging already mounted"
fi

run chown "${TARGET_USER}:${TARGET_USER}" "$ARCHIVE_MOUNT" "$WORK_MOUNT" "$GPSDATA_STAGING"

# ── Summary ───────────────────────────────────────────────────────────────────
step "Result"

if [ "$APPLY" -eq 1 ]; then
    lvs "$VG" 2>/dev/null || true
    echo
    df -h "$ARCHIVE_MOUNT" "$WORK_MOUNT" "$GPSDATA_STAGING" 2>/dev/null || true
    echo
    printf '  VG free remaining: %s\n' \
        "$(numfmt --to=iec --suffix=B "$(vgs --noheadings --nosuffix --units b -o vg_free "$VG" | tr -d ' ')")"
    echo
    ok "provisioning complete"
    echo
    echo "  Left unallocated on purpose: LVM grows online in seconds, XFS can"
    echo "  never shrink. Free extents cost nothing and cover a wrong guess."
    echo
    echo "  NEXT: migrate the existing GPSDATA onto lv_gpsdata:"
    echo "      sudo ./gps3_gpsdata_migrate.sh              # dry run"
    echo "      sudo ./gps3_gpsdata_migrate.sh --apply"
else
    echo
    ok "dry run complete — no changes made"
    echo "  Re-run with --apply to execute."
fi
