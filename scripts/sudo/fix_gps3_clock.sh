#!/usr/bin/env bash
# fix_gps3_clock.sh -- set gps3's clock, and keep it set, without NTP.
#
#   sudo bash /home/gps3/repos/movefaults_clean/scripts/sudo/fix_gps3_clock.sh
#
# WHY NOT NTP
#
# This network blocks outbound UDP. `tailscale netcheck` reports `UDP: false`,
# which is why every Tailscale path off this subnet is DERP-relayed -- and NTP
# is UDP/123. Measured 2026-09-10: ntp.ubuntu.com, time.cloudflare.com and
# pool.ntp.org all hang. systemd-timesyncd cannot work here, and enabling it
# would produce a service that looks healthy and never syncs, which is the
# failure this project keeps cataloguing.
#
# WHY IT MATTERS
#
# gps3 measured +250 s against three independent HTTPS sources on 2026-09-10;
# finch's clock is correct to ~2 s. gps3 is the offender.
#
# scripts/finch_watch.sh timestamps finch's outages in gps3's frame. Correlating
# a DOWN line against finch's journal -- the first thing anyone will do -- was
# therefore misaligned by 250 s, which is 25 probe intervals against a log line
# that states `resolution=10s`. A number precise about its sampling and silent
# about a frame error two orders larger.
#
# HOW
#
# TCP/443 is open, and an HTTP `Date:` header is a time source of roughly
# one-second accuracy -- far short of NTP, and four hundred times better than
# being 250 s out. Good enough to correlate two logs; NOT good enough for
# anything that needs sub-second time, and nothing here does.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "FATAL: run with sudo." >&2; exit 1; }

SOURCES=(https://www.cloudflare.com https://github.com https://www.google.com)

read_remote() {
    local d
    d=$(curl -sS -I --max-time 10 "$1" 2>/dev/null | grep -i '^date:' | head -1 | cut -d' ' -f2-) || return 1
    [ -n "$d" ] || return 1
    date -d "$d" +%s 2>/dev/null || return 1
}

echo "=== sampling ==="
declare -a got
for u in "${SOURCES[@]}"; do
    if t=$(read_remote "$u"); then
        printf '  %-28s %s  (gps3 %+ds)\n' "$u" "$(date -d "@$t" '+%H:%M:%S')" "$(( $(date +%s) - t ))"
        got+=("$t")
    else
        printf '  %-28s unreachable\n' "$u"
    fi
done
[ "${#got[@]}" -ge 2 ] || { echo "FATAL: need >=2 sources to agree; got ${#got[@]}." >&2; exit 3; }

# Median, so one lying source cannot move the clock on its own.
IFS=$'\n' sorted=($(sort -n <<<"${got[*]}")); unset IFS
target=${sorted[$(( ${#sorted[@]} / 2 ))]}
spread=$(( sorted[-1] - sorted[0] ))
echo "  median=$(date -d "@$target" '+%F %T')  spread_between_sources=${spread}s"
[ "$spread" -le 5 ] || { echo "FATAL: sources disagree by ${spread}s; refusing." >&2; exit 4; }

before=$(date +%s)
timedatectl set-ntp false >/dev/null 2>&1 || true
date -s "@$target" >/dev/null

# Write the RTC too, or the correction is lost at the next boot: the kernel
# seeds the system clock from the RTC, so gps3 would come back with the old
# wrong time and stay wrong until the timer fires at OnBootSec=2min. Bounded,
# but the window lands exactly where a post-crash correlation would be read.
#
# hwclock lives in util-linux-extra, which is NOT installed by default on
# Ubuntu 24.04 -- the first version of this script assumed it was present and
# printed a warning nobody would have acted on.
if ! command -v hwclock >/dev/null 2>&1; then
    echo "  hwclock absent (util-linux-extra); installing"
    apt-get install -y util-linux-extra >/dev/null 2>&1 || true
fi
if command -v hwclock >/dev/null 2>&1; then
    hwclock --systohc && echo "  RTC written"
else
    echo "  WARNING: no hwclock -- the RTC keeps the OLD time and a reboot"
    echo "           returns gps3 ~4 min fast until the timer runs at +2min."
    echo "           Timestamps in that window are not correlatable."
fi
echo "=== set ==="
printf '  was %s -> now %s   (moved %+ds)\n' \
    "$(date -d "@$before" '+%F %T')" "$(date '+%F %T')" "$(( target - before ))"

# Keep it set. A one-shot fix drifts back, and the drift is silent.
cat > /usr/local/sbin/http-timesync <<'INNER'
#!/usr/bin/env bash
set -euo pipefail
declare -a got
for u in https://www.cloudflare.com https://github.com https://www.google.com; do
    d=$(curl -sS -I --max-time 10 "$u" 2>/dev/null | grep -i '^date:' | head -1 | cut -d' ' -f2-) || continue
    [ -n "$d" ] || continue
    t=$(date -d "$d" +%s 2>/dev/null) || continue
    got+=("$t")
done
[ "${#got[@]}" -ge 2 ] || { logger -t http-timesync "only ${#got[@]} source(s); not adjusting"; exit 0; }
IFS=$'\n' s=($(sort -n <<<"${got[*]}")); unset IFS
target=${s[$(( ${#s[@]} / 2 ))]}
[ $(( s[-1] - s[0] )) -le 5 ] || { logger -t http-timesync "sources disagree; not adjusting"; exit 0; }
off=$(( $(date +%s) - target ))
[ "${off#-}" -ge 2 ] || exit 0
date -s "@$target" >/dev/null
command -v hwclock >/dev/null 2>&1 && hwclock --systohc 2>/dev/null || true
logger -t http-timesync "adjusted ${off}s"
INNER
chmod +x /usr/local/sbin/http-timesync

cat > /etc/systemd/system/http-timesync.service <<'UNIT'
[Unit]
Description=Set the clock from HTTP Date headers (UDP/123 is blocked on this network)
After=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/local/sbin/http-timesync
UNIT
cat > /etc/systemd/system/http-timesync.timer <<'UNIT'
[Unit]
Description=Hourly HTTP-based clock correction
[Timer]
OnBootSec=2min
OnUnitActiveSec=1h
Persistent=true
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now http-timesync.timer
echo
echo "=== verify from the OUTCOME, not from the unit ==="
echo "  date; journalctl -t http-timesync -n 5 --no-pager"
echo "  systemctl is-active reporting a timer says nothing about whether the"
echo "  clock is right -- that is the whole reason this script exists."
