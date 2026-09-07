# Why finch went down — 2026-09-04 01:20:56

Written 2026-09-07 from `journalctl -b -1`. Raw evidence preserved at
`~/finch_lastboot.log` (12,099 lines) and `~/finch_boot_minus2.log` (17,324),
so it survives future reboots shifting the boot index.

## A note on these files

The two journals committed alongside this are **redacted**. Two local account
names, the wifi SSID and seven MAC addresses were replaced (`user-a`,
`user-b`, `WIFI-SSID-REDACTED`, `MAC:REDACTED`) because this repository is
public and the accounts belong to family members, not to the project.

Line counts are unchanged (12,099 and 17,324) and nothing else was touched.
The redaction costs no forensic value: the evidence here is *timestamps* and
the absence of a shutdown sequence, not which account a per-minute timer
happened to serve. The unredacted originals stay on finch at
`~/finch_lastboot.log` and `~/finch_boot_minus2.log` for as long as that
machine survives.

## The finding

**Abrupt power loss or a hard hang, with no preceding error logged.**

That is the whole honest answer. It is not a guess between hypotheses — the
discriminating evidence is present and it rules out the software-initiated
case cleanly, while offering nothing that separates the remaining ones.

## What the log actually shows

Boot -1 ran 2026-09-03 12:34:50 → 2026-09-04 01:20:56 (12h46m), then stops
**mid-normal-activity**:

```
Sep 04 01:20:01 CRON[226089]: (finch) CMD (/home/finch/scripts/monitor_memory.sh)
Sep 04 01:20:56 systemd[1]: Starting kid-time.service ...
Sep 04 01:20:56 systemd[1]: Finished user-time-limit@user-b.service ...
<end of log>
```

Those last services are per-minute timers. They fire, complete normally, and
then there is nothing. No `Stopping ...`, no `Reached target Shutdown`, no
`systemd-shutdown`. The three `Reached target shutdown.target` lines in this
boot are **user-session** managers (`systemd[1503]`, `[20703]`, `[105116]`)
exiting hours earlier — not the system going down.

`last -x` agrees independently: the Sep 3 sessions are recorded as `crash`.

## What it rules out

| hypothesis | evidence |
|---|---|
| clean/software shutdown | **ruled out** — no shutdown sequence at all |
| thermal | **ruled out** — all 17 `thermal` lines are boot-time driver registration; THM0 read 54 °C at boot; no critical-temperature event |
| OOM | **ruled out** — `earlyoom` logged 76.5% memory free and 100% swap free at 00:35, 45 min before |
| kernel panic / MCE / hardware error | **not present** — zero matches for `mce`, `Machine Check`, `Hardware Error`, `kernel panic`, `watchdog: BUG` |
| USB/disk bus wedge | **no direct evidence** — zero USB disconnects, ATA resets, or I/O errors |

## What it does not establish

**Which of power loss, PSU/battery failure, or a wedged kernel it was.** All
three produce exactly this signature: a log that simply stops. Nothing in the
journal separates them, and inventing a cause here would be worse than saying
so.

## It is recurrent, and that is the more useful finding

Boot -2 ends the same way — same per-minute timers, same absence of any
shutdown sequence. Across the last nine completed boots:

```
boot -9   up 13h30m   ABRUPT
boot -8   up  2h09m   clean shutdown
boot -7   up  0h17m   clean shutdown
boot -6   up 29h20m   ABRUPT
boot -5   up  0h27m   clean shutdown
boot -4   up 65h33m   ABRUPT
boot -3   up  1h19m   ABRUPT
boot -2   up 20h04m   ABRUPT
boot -1   up 12h46m   ABRUPT
```

**Six of nine ended abruptly.** The three clean ones are the three shortest
(17 m, 27 m, 2 h) — deliberate reboots. Every long unattended run has died.
`wtmp` carries 156 `crash` records in total.

So this is not a one-off to be explained away. finch does not stay up
unattended, and has not for some time.

## One observation, explicitly not a conclusion

`udisksd` logged a SMART housekeeping failure every ~10 minutes for the whole
boot — 77 times — against
`WDC_WD10EARS_003BB1_WD_WCAV5M032380`, which is the **GPS_1TB_2 drive**:

```
Error updating SMART data: Error sending ATA command CHECK POWER MODE:
Unexpected sense data returned
```

Tempting, and probably not the cause: the errors run from 12:41 to 01:15 at a
steady cadence with no change approaching the failure, and there are **no** USB
disconnects, ATA resets or I/O errors anywhere in the boot. This reads as a USB
bridge that does not pass ATA passthrough — a normal, noisy limitation of that
enclosure. Worth remembering only if a future crash correlates with that drive
being attached.

## What would actually settle it

The journal cannot, because the machine dies before it can write. What would:

- **a watchdog** (PR #170's playbook) — turns a wedged kernel into an automatic
  reboot, and its absence into evidence: if the watchdog fires, it was a hang;
  if the machine dies without firing, it was power.
- **`netconsole` or a serial console** — gets the last kernel messages off the
  box before it stops writing to disk.
- **an attached UPS or a PSU swap** — for the 2011 hardware hypotheses.

## Bearing on PR #170

Nothing here contradicts the playbook; it strengthens the case for it. The
watchdog is the higher-value fix, for the reason gps3 gave: remote access only
helps while the box is still answering. It should be read as the primary
remedy, with Tailscale as the observability that tells you when it did not work.
