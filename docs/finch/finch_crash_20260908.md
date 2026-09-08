# finch crash, 2026-09-07 20:03:37 — and why REISUB proved nothing

Companion to [`finch_shutdown_diagnosis.md`](finch_shutdown_diagnosis.md),
which covers the 2026-09-04 outage. **This is a different, later event.** Only
what is new is recorded here.

Raw evidence: `finch_crash_20260908.log.gz` (6,133 lines, redacted — see the
note in the earlier diagnosis for what and why).

## The headline: REISUB could not have worked

The user found finch unresponsive and reported that Alt+SysRq **R-E-I-S-U-B**
produced no response before rebooting at ~08:00.

That is tempting evidence — SysRq is handled in the kernel, well below
userspace, so a machine that ignores it while still powered looks like a hard
lockup. It would have been the first positive characterisation of this failure
rather than a description by absence.

**It proves nothing here, because two of the six keys are disabled.**

```
kernel.sysrq = 438 = 0x1B6

  0x001  OFF  console log level control
  0x002  ON   keyboard control (SAK, unraw)      <- R
  0x004  ON   debugging dumps
  0x008  OFF  sync command                       <- S
  0x010  ON   remount read-only                  <- U
  0x020  ON   signalling processes (term/kill)   <- E, I
  0x040  OFF  reboot/poweroff                    <- B
  0x080  ON   nicing RT tasks
  0x100  ON   (extended)
```

`S` (sync) and **`B` (reboot)** are both masked off. `B` is the only key whose
effect the user could have observed, and it never had permission to fire. A
perfectly healthy kernel would have produced exactly the same silence.

### Why the mask is 438 and not what /etc asks for

```
/etc/sysctl.d/10-magic-sysrq.conf : kernel.sysrq = 176
/usr/lib/sysctl.d/50-default.conf : kernel.sysrq = 0x01b6   (438)
live                              : 438
```

`systemd-sysctl` applies files in lexical order by filename across all
directories; `/etc` overrides `/usr/lib` only for the *same* filename. These
differ, so `50-default.conf` is applied after `10-magic-sysrq.conf` and wins.
The administrator-intent file in `/etc` is silently overridden by a vendor
default.

Not that it would have helped: 176 = 0xB0 clears `R`, `S` **and** `B`. REISUB
fails under either value.

Note the value was read *after* the reboot, so it reflects boot-time
configuration. Nothing sets it at runtime — it appears in no unit, cron job or
dispatcher script — so it was almost certainly 438 during the hang too, but
that is inference, not observation.

## This boot's evidence

Boot ran 2026-09-07 15:58:55 → 20:03:37 (4 h 04 m) and ends the same way as
every other: mid-activity, on the per-minute timers, with **zero** PID-1
shutdown lines.

Checked for what a lockup leaves and a power cut does not:

| signature | result |
|---|---|
| `hung_task` | none |
| soft / hard lockup | none |
| `Call Trace`, `Oops` | none |
| `rcu_sched` stall | none |
| `i8042` / `atkbd` failure | none — only normal boot-time device registration |

**Nine apparent matches were all `kerneloops.service`** — a service *name*
containing "oops", not an oops. The same false-positive class as the
`password` matches that turned out to be systemd unit names in the earlier
diagnosis. Grep the string, read the line.

Absence of a trace does **not** disprove a lockup: the machine may not have
survived long enough to write one. Recorded as absence.

The last minutes carry a NetworkManager `sd-event` assertion failure at
20:01:07 and routine tailscaled reconnect churn through 20:03:32. Neither is
obviously causal and neither is being claimed as such.

## What remains open

Unchanged from the earlier diagnosis: **power loss, PSU failure and a wedged
kernel are still not separable.** The REISUB observation, which looked like the
discriminator, is void. A dead input path would also produce silence, so even
with sysrq fully enabled a negative result would have needed care.

## The tally, updated — 7 of 10

```
boot -10  13h30m  ABRUPT     boot -5  65h33m  ABRUPT
boot  -9   2h09m  clean      boot -4   1h19m  ABRUPT
boot  -8   0h17m  clean      boot -3  20h04m  ABRUPT
boot  -7  29h20m  ABRUPT     boot -2  12h46m  ABRUPT
boot  -6   0h27m  clean      boot -1   4h04m  ABRUPT
```

The shape holds and strengthens. All three clean shutdowns remain the three
**shortest** sessions — 17 m, 27 m, 2 h 09 m, i.e. deliberate reboots. This
crash ended a 4 h 04 m run, longer than any of them.

## What this argues for

Exactly what the earlier diagnosis argued, now with a concrete missed case:

1. **Enable sysrq properly**, so the next hang is diagnosable by the one
   instrument that reaches below userspace.
2. **The watchdog** from the headless-hardening playbook — it discriminates
   hang from power loss without needing anyone at the keyboard.
3. `kernel.hung_task_timeout_secs` and `nmi_watchdog`, so a lockup leaves a
   trace *before* the machine goes.

The first is cheap and was the difference between an answer and this document.
