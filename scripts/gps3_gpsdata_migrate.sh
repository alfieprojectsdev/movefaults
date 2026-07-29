#!/usr/bin/env bash
# gps3_gpsdata_migrate.sh — move gps3's existing GPSDATA onto lv_gpsdata
#
# Run gps3_storage_provision.sh FIRST — this expects lv_gpsdata to exist and be
# mounted at the staging path.
#
# This is the only step in the storage work that can lose data, so it is split
# into two explicitly-separate phases:
#
#   --sync   copy GPSDATA → staging volume, then verify counts and bytes.
#            Safe, idempotent and resumable: rsync skips what already matches,
#            and the live GPSDATA is only ever read. Re-run as often as needed.
#
#   --swap   the cutover: rename the old directory aside, then mount the new
#            volume in its place. Requires --sync to have verified clean.
#
# The old copy is NEVER deleted automatically. It is renamed to
# GPSDATA.old-<date> and left on the root filesystem for you to remove by hand
# once you are satisfied — that is what makes this reversible.
#
# Usage:
#   sudo ./gps3_gpsdata_migrate.sh             # dry run — show the plan
#   sudo ./gps3_gpsdata_migrate.sh --sync      # copy + verify (repeatable)
#   sudo ./gps3_gpsdata_migrate.sh --swap      # cut over
#
# Run inside tmux so an SSH drop cannot interrupt a long rsync:
#   ssh -t gps3@192.168.48.98 'tmux new -As storage'

set -euo pipefail

VG="ubuntu-vg"
LV="lv_gpsdata"
TARGET_USER="${SUDO_USER:-gps3}"
TARGET_HOME="/home/${TARGET_USER}"

SRC="${TARGET_HOME}/GPSDATA"
STAGING="/mnt/lv_gpsdata_staging"
DEV="/dev/${VG}/${LV}"
MOUNT_OPTS="defaults,noatime,nofail"
STAMP="$(date +%Y%m%d)"
OLD="${SRC}.old-${STAMP}"

MODE="dryrun"

while [ $# -gt 0 ]; do
    case "$1" in
        --sync) MODE="sync"; shift ;;
        --swap) MODE="swap"; shift ;;
        --dry-run) MODE="dryrun"; shift ;;
        -h|--help) sed -n '2,28p' "$0"; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; echo "Try --help" >&2; exit 1 ;;
    esac
done

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$*"; }
die()  { printf '\n\033[31mERROR:\033[0m %s\n' "$*" >&2; exit 1; }

run() {
    printf '  $ %s\n' "$*"
    if [ "$MODE" != "dryrun" ]; then
        "$@" || die "command failed: $*"
    fi
}

# Count regular files, symlinks and total file bytes. Comparing all three
# catches a truncated copy that a bare file count would miss, and symlinks
# matter because the FAT32 thumb-drive hop silently destroyed them once
# already (see DATAPOOL/REF54 in RESUME_NEXT.md).
census() {
    local d="$1" f l b
    f=$(find "$d" -type f 2>/dev/null | wc -l)
    l=$(find "$d" -type l 2>/dev/null | wc -l)
    b=$(find "$d" -type f -printf '%s\n' 2>/dev/null | awk '{s+=$1} END {print s+0}')
    echo "$f $l $b"
}

# ── Pre-flight ────────────────────────────────────────────────────────────────
step "Pre-flight checks"

[ "$(id -u)" -eq 0 ] || die "must run as root (use: sudo $0)"
[ -d "$SRC" ] || die "source '$SRC' not found (wrong TARGET_USER?)"

lvs --noheadings -o lv_name "${VG}/${LV}" >/dev/null 2>&1 \
    || die "$LV does not exist — run gps3_storage_provision.sh first"
ok "$LV exists"

mountpoint -q "$STAGING" \
    || die "$STAGING is not mounted.
Run gps3_storage_provision.sh, or mount it manually:
    sudo mount -o defaults,noatime $DEV $STAGING"
ok "staging volume mounted at $STAGING"

# Moving campaign data out from under a running BPE would corrupt the run.
if pgrep -f "rnx2snx_pcs.pl|startBPE|BPE_" >/dev/null 2>&1; then
    die "a Bernese BPE process appears to be running — let it finish first"
fi
ok "no BPE process running"

# Anything holding files open under GPSDATA will silently keep the old inodes
# alive after the swap, so callers would keep reading stale data.
#
# Do NOT use `fuser -m "$SRC"` here. `-m` takes a path and reports every
# process using the FILESYSTEM that path lives on. Before the swap $SRC is a
# plain directory on /, so fuser escalates to / and matches essentially every
# process on the box — the check fired unconditionally and `--swap` always
# died with "close them before swapping". Found on gps3 2026-07-29.
#
# `lsof +D` walks the directory tree itself, which is the actual question.
# Two traps it carries:
#   * it exits 1 when the tree has NO open files (the safe case), so under
#     `set -euo pipefail` the command substitution must end in `|| true` or
#     the script dies silently right here;
#   * it self-matches if this script's cwd or an open fd is under $SRC — run
#     the script from outside the tree (it is invoked from $HOME).
if command -v lsof >/dev/null 2>&1; then
    open_under=$(lsof +D "$SRC" 2>/dev/null | tail -n +2 || true)
    if [ -n "$open_under" ]; then
        warn "processes currently have files open under $SRC:"
        printf '%s\n' "$open_under" | head -10
        [ "$MODE" = "swap" ] && die "close them before swapping"
    fi
fi

read -r SF SL SB <<<"$(census "$SRC")"
SRC_H=$(numfmt --to=iec --suffix=B "$SB")
AVAIL_B=$(df -B1 --output=avail "$STAGING" | tail -1 | tr -d ' ')

printf '  source : %s — %s files, %s symlinks, %s\n' "$SRC" "$SF" "$SL" "$SRC_H"
printf '  target : %s — %s free\n' "$STAGING" "$(numfmt --to=iec --suffix=B "$AVAIL_B")"

[ "$SB" -lt "$AVAIL_B" ] || die "not enough space on $LV for $SRC_H"
ok "target has room"

# ── Sync ──────────────────────────────────────────────────────────────────────
if [ "$MODE" = "dryrun" ] || [ "$MODE" = "sync" ]; then
    step "Phase 1: copy → staging"
    echo "  -aHAX preserves symlinks, hardlinks, ACLs and xattrs."
    echo "  Repeatable: rsync skips files that already match."

    if [ "$MODE" = "dryrun" ]; then
        printf '  $ rsync -aHAX --info=progress2 %s/ %s/\n' "$SRC" "$STAGING"
        echo
        ok "dry run — nothing copied. Re-run with --sync to perform the copy."
        exit 0
    fi

    run rsync -aHAX --info=progress2 "${SRC}/" "${STAGING}/"

    step "Verify"
    read -r DF DL DB <<<"$(census "$STAGING")"
    printf '  source : %s files, %s symlinks, %s bytes\n' "$SF" "$SL" "$SB"
    printf '  target : %s files, %s symlinks, %s bytes\n' "$DF" "$DL" "$DB"

    # rsync exiting 0 does not by itself prove a complete copy — that lesson
    # cost a whole session once (see backup_plus_health_crisis memory).
    if [ "$SF" != "$DF" ] || [ "$SL" != "$DL" ] || [ "$SB" != "$DB" ]; then
        die "census MISMATCH — do NOT swap. Re-run --sync and investigate."
    fi
    ok "census matches exactly"

    run chown -R "${TARGET_USER}:${TARGET_USER}" "$STAGING"
    echo
    ok "sync complete and verified"
    echo "  NEXT: sudo $0 --swap"
    exit 0
fi

# ── Swap ──────────────────────────────────────────────────────────────────────
step "Phase 2: cutover"

read -r DF DL DB <<<"$(census "$STAGING")"
if [ "$SF" != "$DF" ] || [ "$SL" != "$DL" ] || [ "$SB" != "$DB" ]; then
    die "staging does not match source — run --sync first.
    source: $SF files / $SL links / $SB bytes
    target: $DF files / $DL links / $DB bytes"
fi
ok "staging verified against source"

cat <<PLAN

  This will:
    1. unmount            $STAGING
    2. rename             $SRC
             ->           $OLD
    3. create             $SRC  (empty mount point)
    4. add fstab entry (nofail) and mount $LV at $SRC
    5. re-verify the census through the new mount

  The old copy is KEPT at $OLD — nothing is deleted.
  It still occupies root-filesystem space until you remove it by hand.

PLAN

if [ -t 0 ]; then
    printf '  Type EXACTLY "swap" to proceed: '
    read -r reply
    [ "$reply" = "swap" ] || die "aborted (got '$reply')"
else
    die "refusing to swap non-interactively — run this in a terminal"
fi

[ -e "$OLD" ] && die "$OLD already exists — resolve it before re-running"

run umount "$STAGING"
run mv "$SRC" "$OLD"
run mkdir -p "$SRC"

if grep -qsF " $SRC " /etc/fstab; then
    ok "fstab already has an entry for $SRC"
else
    UUID="$(blkid -s UUID -o value "$DEV")"
    [ -n "$UUID" ] || die "could not read UUID of $DEV"
    printf '  $ echo "UUID=%s %s xfs %s 0 2" >> /etc/fstab\n' "$UUID" "$SRC" "$MOUNT_OPTS"
    cp -n /etc/fstab "/etc/fstab.bak-${STAMP}" 2>/dev/null || true
    printf 'UUID=%s %s xfs %s 0 2\n' "$UUID" "$SRC" "$MOUNT_OPTS" >> /etc/fstab
fi

# Validate fstab BEFORE anything reboots and acts on it.
run findmnt --verify --verbose
run mount "$SRC"
run chown "${TARGET_USER}:${TARGET_USER}" "$SRC"

step "Post-swap verification"

mountpoint -q "$SRC" || die "$SRC is not a mountpoint after swap"
ok "$SRC is now a mount of $LV"

read -r NF NL NB <<<"$(census "$SRC")"
printf '  expected : %s files, %s symlinks, %s bytes\n' "$SF" "$SL" "$SB"
printf '  actual   : %s files, %s symlinks, %s bytes\n' "$NF" "$NL" "$NB"
if [ "$SF" != "$NF" ] || [ "$SL" != "$NL" ] || [ "$SB" != "$NB" ]; then
    die "census mismatch after swap. The old data is intact at $OLD.
To roll back:  umount $SRC && rmdir $SRC && mv $OLD $SRC
Then remove the $SRC line from /etc/fstab."
fi
ok "census matches through the new mount"

# The Bernese variables must still resolve, or BPE breaks in confusing ways.
for sub in CAMPAIGN54 DATAPOOL SAVEDISK; do
    if [ -d "${SRC}/${sub}" ]; then ok "\$-path present: ${SRC}/${sub}"
    else warn "missing: ${SRC}/${sub}"; fi
done

step "Done"
df -h "$SRC"
echo
cat <<DONE
  Old copy retained at:
      $OLD

  Verify Bernese still works before reclaiming that space:
      sudo -u $TARGET_USER bash -ic 'echo \$P; ls \$P'
      sudo -u $TARGET_USER bash -ic 'perl \$U/SCRIPT/rnx2snx_pcs.pl 2023 0100'

  ONLY once satisfied, reclaim the root-filesystem space:
      sudo rm -rf $OLD

  Rollback while the old copy still exists:
      sudo umount $SRC && sudo rmdir $SRC && sudo mv $OLD $SRC
      # then delete the $SRC line from /etc/fstab
DONE
