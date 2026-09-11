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
# Below this, an outage is a link flap rather than the machine going away.
# 2026-09-11: 164 outages in 17 h, median 10 s (one probe interval), mean
# 11.6 s, while finch had 1d17h uptime and no reboots throughout -- PHIVOLCS
# wifi, not finch. Unclassified, a real crash is one line among ~200 daily
# false positives: the instrument working and unreadable.
#
# 30 s sits against finch's ~37 s boot cycle so the classes do not overlap --
# but the longest flap observed was 37 s, exactly at that boundary. Duration
# separates 163 of 164 and is ambiguous for the one case that matters, so it
# errs toward DOWN. The boot-id probe removes that ambiguity; this manages it.
FLAP_MAX=30
LOG="${FINCH_WATCH_LOG:-$HOME/finch-watch.log}"

now() { date '+%Y-%m-%dT%H:%M:%S%z'; }
log() { printf '%s  %s\n' "$(now)" "$*" >> "$LOG"; }

probe() { ping -c1 -W2 -n "$1" >/dev/null 2>&1 && echo ok || echo fail; }

# WHAT ACTUALLY SEPARATES A FLAP FROM A CRASH.
#
# Duration cannot. The longest flap observed was 37 s and finch's boot cycle is
# ~37 s, so FLAP_MAX sits on the boundary of the thing it is meant to detect --
# and because a cycle costs ~4 s of ping timeouts per unreachable address, a
# nominal 30 s threshold is a real 35-45 s during an outage. The classes touch.
#
# `boot_id` does not change while a machine is up and always changes across a
# reboot. Same id after an outage means finch never went away and the network
# did; a different id means it really rebooted, however brief the gap looked.
# It is evidence about the machine rather than about the path to it.
#
# Read over plain sshd on the LAN address with a `command=` restricted key that
# can return only these two values -- no shell, no forwarding. NOT over
# Tailscale SSH, which is in `check` mode here: it wants periodic browser
# re-auth that an unattended watcher cannot do, and the failure would be silent
# and indistinguishable from finch being down. That failure mode inside the
# instrument built to detect it is the thing this whole exercise is about.
#
# Bounded and allowed to fail. It runs only on an UP transition, never in the
# steady state, so it does not lengthen the sampling period the way the pings
# do. On failure it returns `unknown` and the caller falls back to duration --
# it must never guess, because "probe failed" and "same machine" are different
# facts and conflating them is how a crash gets filed as a flap.
FINCH_SSH=finch@192.168.48.124
boot_id() {
    timeout 8 ssh -n -o BatchMode=yes -o ConnectTimeout=4 \
        -o StrictHostKeyChecking=accept-new "$FINCH_SSH" true 2>/dev/null \
        | head -1 | tr -d '[:space:]'
}

# A gap in the watcher is NOT a gap in finch, and conflating the two would be
# precisely the failure this exists to avoid. Say so on every start, so nobody
# later reads a silent stretch as finch having been up.
# The instrument must report whether it is armed. These timestamps are only
# usable for correlating against finch's journal if this clock is right, and on
# 2026-09-10 it was 250 s out -- 25 probe intervals, against lines that state
# `resolution=10s`.
#
# It MEASURES the offset rather than asking systemd whether NTP synced.
# `NTPSynchronized` is permanently `no` on this host by design: UDP/123 is
# blocked here, so the clock is kept by scripts/sudo/fix_gps3_clock.sh over
# HTTP instead. A check reading that flag would report UNSYNCED forever,
# including when the clock is correct -- a permanent alarm, which is an ignored
# alarm. One HTTP HEAD answers the question actually being asked.
#
# Called at start, hourly, and on DOWN -- not every probe. It is a network
# call, and a DOWN event is exactly when the network may be the problem, so it
# is bounded and allowed to fail.
clock_state() {
    local d r off
    d=$(curl -sS -I --max-time 6 https://www.cloudflare.com 2>/dev/null \
        | grep -i '^date:' | head -1 | cut -d' ' -f2-) || true
    [ -n "${d:-}" ] || { echo "offset=unknown"; return; }
    r=$(date -d "$d" +%s 2>/dev/null) || { echo "offset=unknown"; return; }
    off=$(( $(date +%s) - r ))
    if [ "${off#-}" -le 5 ]; then echo "offset=${off}s"
    else echo "offset=${off}s-TIMESTAMPS-SUSPECT"; fi
}

log "WATCH-START pid=$$ interval=${INTERVAL}s lan=$LAN ts=$TS clock_$(clock_state)"
log "WATCH-NOTE  any gap before this line is UNOBSERVED, not finch being up"
trap 'log "WATCH-STOP  pid=$$ -- from here finch is UNOBSERVED"; exit 0' TERM INT

# Baseline, so the first recovery has something to compare against. If finch
# is unreachable at start this is empty and the first UP reports `unknown`,
# which is correct: we genuinely do not know what it was before.
last_boot=$(boot_id)
log "WATCH-BASE  finch boot_id=${last_boot:-unknown}"

state=init
since=$(date +%s)
last_ok=$(date +%s)
last_beat=0
flaps=0
down_at=0
down_reported=yes

while :; do
    probe_start=$(date +%s)
    l=$(probe "$LAN"); t=$(probe "$TS")
    if [ "$l" = ok ] || [ "$t" = ok ]; then new=UP; else new=DOWN; fi
    n=$(date +%s)
    # The REAL sampling period, not the nominal one. Each probe waits up to
    # -W2 per address, so when finch is unreachable a cycle costs ~4 s of
    # timeouts plus the sleep -- the interval degrades during exactly the
    # event it is measuring. Reporting INTERVAL would understate the window
    # the death actually falls in, on the one line somebody correlates.
    [ "${prev_probe:-0}" -gt 0 ] && actual_gap=$(( probe_start - prev_probe )) || actual_gap=$INTERVAL
    prev_probe=$probe_start

    if [ "$new" != "$state" ]; then
        if [ "$new" = DOWN ]; then
            # The DOWN line is DEFERRED, not suppressed. An outage's duration
            # is not knowable when the link drops, and writing one line per
            # flap is what made this log unreadable. It is emitted below as
            # soon as the outage outlives FLAP_MAX, so a real crash is still
            # recorded within 30 s even if this watcher is killed next.
            down_at=$n
            down_reported=no
        else
            d=$(( n - since ))
            [ "$state" = init ] && d=0
            # Ask the machine what it is before classifying. boot_id decides
            # when it answers; duration is the fallback when it does not.
            b=$(boot_id)
            if [ -z "$b" ]; then
                verdict="boot_id=unavailable -- classified by duration only"
                if [ "$state" = DOWN ] && [ "$d" -le "$FLAP_MAX" ]; then
                    flaps=$(( flaps + 1 ))
                    log "FLAP? lan=$l ts=$t  down_for=${d}s  $verdict"
                else
                    log "UP    lan=$l ts=$t  down_for=${d}s  $verdict"
                fi
            elif [ -n "$last_boot" ] && [ "$b" = "$last_boot" ]; then
                # Same boot. finch never went away, whatever the duration said.
                flaps=$(( flaps + 1 ))
                log "FLAP  lan=$l ts=$t  down_for=${d}s  boot_id=unchanged (the network dropped, finch did not)"
            elif [ -n "$last_boot" ]; then
                # Different boot. A REBOOT, even if the gap looked like a flap
                # -- which is the case duration can never catch and the whole
                # reason this probe exists.
                log "CRASH lan=$l ts=$t  down_for=${d}s  boot_id=CHANGED  was=${last_boot:0:8} now=${b:0:8}  <- finch actually rebooted"
                last_boot=$b
            else
                log "UP    lan=$l ts=$t  down_for=${d}s  boot_id=${b:0:8} (no baseline to compare)"
                last_boot=$b
            fi
        fi
        state=$new
        since=$n
    fi

    # Promote a sustained outage to DOWN once it is no longer a plausible flap.
    # last_ok is the newest moment finch is KNOWN alive; the true death is in
    # (last_ok, now] and the interval is the resolution. clock_ is on this line
    # specifically -- it is the timestamp somebody correlates against finch's
    # journal, and a wrong clock makes that correlation wrong by far more than
    # the stated resolution.
    if [ "$state" = DOWN ] && [ "${down_reported:-yes}" = no ] \
       && [ $(( n - down_at )) -gt "$FLAP_MAX" ]; then
        log "DOWN  lan=$l ts=$t  last_seen=$(date -d "@$last_ok" '+%H:%M:%S')  resolution=${actual_gap}s(nominal_${INTERVAL}s)  exceeded_flap_max=${FLAP_MAX}s  clock_$(clock_state)"
        down_reported=yes
    fi
    [ "$new" = UP ] && last_ok=$n

    if [ $(( n - last_beat )) -ge 3600 ]; then
        # flaps/hour is the health of the LINK and a finding in its own right:
        # ~200/day is plausibly why the user could not reach finch from home.
        log "beat  state=$state lan=$l ts=$t  since=$(date -d "@$since" '+%Y-%m-%dT%H:%M:%S')  flaps_last_hour=${flaps}  clock_$(clock_state)"
        flaps=0
        last_beat=$n
    fi
    sleep "$INTERVAL"
done
