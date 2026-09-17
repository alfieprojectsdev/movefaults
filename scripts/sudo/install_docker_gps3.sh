#!/usr/bin/env bash
# install_docker_gps3.sh -- Docker on gps3, with the database off the root LV.
#
#   sudo bash /home/gps3/repos/movefaults_clean/scripts/sudo/install_docker_gps3.sh
#
# WHY gps3 AND WHY NOW
#
# `docker-compose.yml` defines the TimescaleDB/PostGIS the pipeline has been
# waiting on: CLAUDE.md's steps 2 and 3 are aspirational precisely because
# nothing writes to it, and field-ops' `promote` -- the one write field-ops
# makes to `public.stations` -- cannot be tested without it. Two integration
# tests have skipped since fo007 for want of this.
#
# It goes here rather than on the T420 because the T420 is currently running a
# power experiment with its battery removed, and adding a database to the
# machine under test confounds the result it exists to produce. gps3 has 24
# cores and 57 GiB free; the database is not a burden here.
#
# WHAT THIS DOES DIFFERENTLY FROM `apt install docker.io`
#
# It puts Docker's data-root on a dedicated LV BEFORE the daemon ever stores
# anything. By default everything -- images, containers and named volumes --
# lands in /var/lib/docker on the 250 GB root LV. A database there fills the
# root filesystem and takes the OS down with it, and moving it afterwards means
# moving a live database. The VG has ~7.3 TB free; there is no reason to use
# root.
#
# 500G, not more: LVM extends online and XFS grows online, so the cheap move is
# to start small and `lvextend -r` when it is actually needed. The sizing driver
# is eventually VADASE at 1 Hz across ~35 stations -- roughly 3M rows a day --
# not the solutions or the logsheets, which are negligible.
#
# WHAT THIS DOES NOT DO, AND YOU MUST NOT SKIP IT
#
# Docker publishes ports by writing its own iptables chain AHEAD of ufw's, so
# `-p 5433:5432` is reachable on every interface -- including the tailnet --
# past the firewall that is active on this host. With the committed default
# credentials that is a database anyone on the tailnet can open.
#
# The fix is in the repository, not here: bind the published ports to
# 127.0.0.1 in docker-compose.yml. Every consumer is local. Do that before the
# first `docker compose up`.

set -euo pipefail

VG=ubuntu-vg
LV=lv_dbdata
LV_SIZE=500G
MOUNT=/srv/dbdata
DOCKER_ROOT="${MOUNT}/docker"

if [[ ${EUID} -ne 0 ]]; then
    echo "FATAL: run with sudo." >&2
    exit 1
fi

say() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
say "1/6  the logical volume"
# ---------------------------------------------------------------------------
if lvs "${VG}/${LV}" >/dev/null 2>&1; then
    echo "  ${VG}/${LV} already exists -- leaving it alone"
else
    echo "  free space before:"
    vgs --noheadings -o vg_name,vg_free "${VG}" | sed 's/^/    /'
    lvcreate -L "${LV_SIZE}" -n "${LV}" "${VG}"
    # XFS to match lv_archive, lv_gpsdata, lv_work and lv_eildata. Consistency
    # is the point: one filesystem to know the quirks of, not two.
    mkfs.xfs "/dev/${VG}/${LV}"
fi

# ---------------------------------------------------------------------------
say "2/6  the mount point"
# ---------------------------------------------------------------------------
# HANDOVER.md section 4: never mount over a non-empty directory. A mount that
# hides existing data looks exactly like a mount that did not happen.
mkdir -p "${MOUNT}"
if [[ -n "$(ls -A "${MOUNT}" 2>/dev/null)" ]] && ! mountpoint -q "${MOUNT}"; then
    echo "FATAL: ${MOUNT} is not empty and nothing is mounted there." >&2
    echo "Refusing to mount over it. Inspect it first." >&2
    exit 1
fi

UUID=$(blkid -s UUID -o value "/dev/${VG}/${LV}")
[[ -n "${UUID}" ]] || { echo "FATAL: no UUID for /dev/${VG}/${LV}" >&2; exit 1; }

if grep -q "^UUID=${UUID} " /etc/fstab; then
    echo "  fstab already has this UUID"
else
    cp /etc/fstab "/etc/fstab.bak-$(date +%Y%m%d%H%M%S)"
    # Same options as every other data LV on this host. `nofail` matters: a
    # server that will not boot because one data volume is missing is worse
    # than a server that boots without it.
    printf 'UUID=%s %s xfs defaults,noatime,nofail 0 2\n' "${UUID}" "${MOUNT}" >> /etc/fstab
    echo "  appended to /etc/fstab (backup taken)"
fi

mountpoint -q "${MOUNT}" || mount "${MOUNT}"
mountpoint -q "${MOUNT}" || { echo "FATAL: ${MOUNT} did not mount" >&2; exit 1; }
df -h --output=target,size,avail "${MOUNT}" | sed 's/^/  /'

# ---------------------------------------------------------------------------
say "3/6  packages"
# ---------------------------------------------------------------------------
# Ubuntu's own packages, not Docker's repository: 24.04 ships docker.io 29.x
# and docker-compose-v2 2.40.x, which is compose v2 and is what this project's
# `docker compose` invocations expect. One less third-party apt source to own.
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2

# ---------------------------------------------------------------------------
say "4/6  point the daemon at ${DOCKER_ROOT}"
# ---------------------------------------------------------------------------
# Stop first. Installing started the daemon against the default root, and
# rewriting data-root under a running daemon leaves images in one place and
# the configuration pointing at another.
systemctl stop docker.socket docker.service 2>/dev/null || true

mkdir -p "${DOCKER_ROOT}" /etc/docker

if [[ -f /etc/docker/daemon.json ]] && grep -q '"data-root"' /etc/docker/daemon.json; then
    echo "  daemon.json already sets data-root -- leaving it alone:"
    sed 's/^/    /' /etc/docker/daemon.json
else
    [[ -f /etc/docker/daemon.json ]] && \
        cp /etc/docker/daemon.json "/etc/docker/daemon.json.bak-$(date +%Y%m%d%H%M%S)"
    cat > /etc/docker/daemon.json <<JSON
{
  "data-root": "${DOCKER_ROOT}"
}
JSON
    echo "  wrote /etc/docker/daemon.json"
fi

# The default tree is minutes old and holds nothing worth keeping, but it is
# moved rather than deleted -- this project does not delete things it did not
# create in order to tidy up.
if [[ -d /var/lib/docker ]] && [[ -n "$(ls -A /var/lib/docker 2>/dev/null)" ]]; then
    stash="/var/lib/docker.preinstall-$(date +%Y%m%d%H%M%S)"
    mv /var/lib/docker "${stash}"
    echo "  moved the default tree aside: ${stash}"
fi

# ENABLED, deliberately, and this is what makes `restart: always` bite.
#
# A compose `restart: always` only operates while the daemon is running, so on
# a host where docker.service is DISABLED a reboot ends the load and nothing
# brings it back. That is the T420's configuration and it is why the container
# load there was self-limiting.
#
# gps3 is the opposite and should be: this is a server, the database is meant
# to survive a reboot, and a database that needs someone to log in and start it
# is a database that is down every time nobody notices. But it means every
# service in docker-compose.yml with `restart: always` comes back on every
# boot, unattended -- which is the right behaviour for `db` and a decision you
# should make on purpose for `redis` and `grafana`. Bring up `db` alone.
systemctl enable --now docker
sleep 3

# ---------------------------------------------------------------------------
say "5/6  verify -- not the exit codes, the facts"
# ---------------------------------------------------------------------------
fail=0

active=$(systemctl is-active docker || true)
[[ "${active}" == "active" ]] && echo "  docker.service: active" \
    || { echo "  docker.service: ${active}  <- NOT RUNNING" >&2; fail=1; }

root_dir=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "unavailable")
if [[ "${root_dir}" == "${DOCKER_ROOT}" ]]; then
    echo "  data-root: ${root_dir}"
else
    echo "  data-root: ${root_dir}  <- EXPECTED ${DOCKER_ROOT}" >&2
    fail=1
fi

# The check that actually matters: is the root on the new LV, or still on /?
# `docker info` reporting the right path is not the same as the path being on
# the right filesystem, and a stale bind or a failed mount looks identical.
on=$(df --output=source "${root_dir}" 2>/dev/null | tail -1)
want="/dev/mapper/${VG//-/--}-${LV//-/--}"
if [[ "${on}" == "${want}" ]]; then
    echo "  and it lives on: ${on}"
else
    echo "  data-root is on ${on}, expected ${want}  <- STILL ON THE WRONG LV" >&2
    fail=1
fi

if getent group docker | grep -qw gps3; then
    echo "  gps3 is in the docker group"
else
    usermod -aG docker gps3
    echo "  added gps3 to the docker group"
fi

if [[ ${fail} -ne 0 ]]; then
    echo >&2
    echo "FATAL: verification failed above. Do not run 'docker compose up'" >&2
    echo "until this is understood -- a database created now would land in" >&2
    echo "the wrong place and moving it later means moving a live database." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
say "6/6  what is still yours to do"
# ---------------------------------------------------------------------------
cat <<'NEXT'
  1. Log out and back in, or run `newgrp docker`. Group membership is read at
     login; until then `docker` needs sudo.

  2. DO NOT `docker compose up` until the port bindings are merged.
     Docker writes its iptables chain ahead of ufw's, so a published port is
     reachable on every interface -- the tailnet included -- past the firewall
     that is active on this host. The committed defaults are pogf_password,
     redis_password and admin. Bind to 127.0.0.1 first.

  3. Bring up the database alone, not the whole file:
         docker compose up -d db
     Redis and Grafana also carry `restart: always` and would run permanently
     from every boot. Start them when something actually needs them.

  4. The volume must mount at /home/postgres/pgdata/data, not
     /var/lib/postgresql/data. The compose file explains why at length: the
     timescaledb-ha image sets PGDATA to the former, and at the wrong path the
     whole database lives in the container's writable layer while
     `docker compose ps` reports healthy.

  To undo everything here:
     sudo systemctl disable --now docker
     sudo umount /srv/dbdata && sudo lvremove ubuntu-vg/lv_dbdata
     then remove the /srv/dbdata line from /etc/fstab
NEXT
exit 0
