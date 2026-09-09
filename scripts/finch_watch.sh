#!/usr/bin/env bash
# finch_watch.sh -- an outside witness to finch's death.
#
# WHY THIS RUNS ON gps3 AND NOT ON finch
#
# finch has crashed six times with full instrumentation armed, and every
# kernel-visible cause is eliminated: softlockup_panic never fired, pstore is
# empty under root, the watchdog's bootstatus is 0, thermals sat at 42-46 C
# against a 98 C critical. What remains is below the OS.
#
# The machine cannot witness its own death. finch's journal ends mid-line by
# definition, so its last entry is the last thing it MANAGED TO WRITE, not the
# moment it died -- and both 2026-09-09 crashes happened with nobody present.
# A box reporting its own health is the failure mode, not the test.
#
# WHAT IT ANSWERS, AND WHAT IT DOES NOT
#
# It gives an independent death timestamp, the outage duration, and whether
# finch degrades before dying or vanishes between one probe and the next.
# `down_for` is the discriminator:
#
#     ~90 s      instant loss + BIOS restore-on-AC-power
#     ~97 s+     a watchdog cycle (60 s timeout + ~37 s boot)
#     minutes    something else entirely
#
# It will NOT say why. It is a witness, not a diagnosis -- and no witness has
# existed for any of the six.
#
# WHY BOTH ADDRESSES
#
# They fail differently, and the pair separates "dead" from "off the network":
#   LAN down + tailnet up   impossible if the box is off
#   LAN up   + tailnet down a tailscaled problem, not a power one
#
# WHY TRANSITIONS ONLY
#
# Every probe would be 8,640 lines a day of `UP`, which buries the signal and
# eventually the disk. Transitions plus an hourly heartbeat keeps the log
# readable and still proves the watcher was alive.
set -uo pipefail

LAN=192.168.48.124
TS=100.111.100.73
INTERVAL=10
LOG="${FINCH_WATCH_LOG:-$HOME/finch-watch.log}"

now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '%s  %s\n' "$(now)" "$*" >> "$LOG"; }

probe() { ping -c1 -W2 -n "$1" >/dev/null 2>&1 && echo ok || echo fail; }

# A gap in the watcher is NOT a gap in finch, and conflating the two would be
# precisely the failure this exists to avoid. Say so on every start, so nobody
# later reads a silent stretch as finch having been up.
# The instrument must report whether it is armed. These timestamps are only
# usable for correlating against finch's journal if this clock is right, and on
# 2026-09-10 it was 250 s out -- 25 probe intervals, against lines that state
# `resolution=10s`. NTP cannot fix it here: UDP/123 is blocked on this network,
# the same restriction that makes every off-subnet Tailscale path DERP-relayed.
# See scripts/sudo/fix_gps3_clock.sh.
clock_state() {
    local sync
    sync=$(timedatectl show -p NTPSynchronized --value 2>/dev/null || echo unknown)
    if [ "$sync" = yes ]; then echo "synced"; else echo "UNSYNCED-timestamps-suspect"; fi
}

log "WATCH-START pid=$$ interval=${INTERVAL}s lan=$LAN ts=$TS clock=$(clock_state)"
log "WATCH-NOTE  any gap before this line is UNOBSERVED, not finch being up"
trap 'log "WATCH-STOP  pid=$$ -- from here finch is UNOBSERVED"; exit 0' TERM INT

state=init
since=$(date +%s)
last_ok=$(date +%s)
last_beat=0

while :; do
    l=$(probe "$LAN"); t=$(probe "$TS")
    if [ "$l" = ok ] || [ "$t" = ok ]; then new=UP; else new=DOWN; fi
    n=$(date +%s)

    if [ "$new" != "$state" ]; then
        if [ "$new" = DOWN ]; then
            # last_ok is the newest moment finch is KNOWN to have been alive.
            # The true death is somewhere in (last_ok, now]; the interval is
            # the resolution, and saying so keeps the number honest.
            # clock= on the DOWN line specifically: this is the timestamp
            # somebody will correlate against finch's journal, and an unsynced
            # clock makes that correlation wrong by an unknown amount that is
            # far larger than the stated resolution.
            log "DOWN  lan=$l ts=$t  last_seen=$(date -d "@$last_ok" '+%H:%M:%S')  resolution=${INTERVAL}s  clock=$(clock_state)"
        else
            d=$(( n - since ))
            [ "$state" = init ] && d=0
            log "UP    lan=$l ts=$t  down_for=${d}s"
        fi
        state=$new
        since=$n
    fi
    [ "$new" = UP ] && last_ok=$n

    if [ $(( n - last_beat )) -ge 3600 ]; then
        log "beat  state=$state lan=$l ts=$t  since=$(date -d "@$since" '+%Y-%m-%dT%H:%M:%S')  clock=$(clock_state)"
        last_beat=$n
    fi
    sleep "$INTERVAL"
done
