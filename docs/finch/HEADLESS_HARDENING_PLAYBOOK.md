# Finch headless hardening playbook (ThinkPad T420)

**For:** the Claude Code session on finch, run while physically at the laptop.
**Written:** 2026-09-04 from gps3, which could not reach finch to check any of
this. Every command below is therefore *unverified against finch* — confirm
before trusting, and correct this file where it is wrong.

**Why it exists:** on 2026-09-04 finch was off the network entirely. A subnet
sweep from gps3 found 8 live hosts and none was a Linux ThinkPad — not merely
hung with a live kernel, which would still answer ICMP and keep `sshd`
listening. With the operator away from PHIVOLCS there was no remote path to it,
and stage-3 coordination had to route through GitHub instead.

The goal is not "never freeze". It is **"a freeze does not cost a trip to the
office"**.

---

## Order matters

Diagnose first. Every step after §1 changes the machine, and a changed machine
cannot tell you why the old one died.

---

## 1. Find out what actually happened — BEFORE changing anything

```bash
journalctl -b -1 -e            # end of the PREVIOUS boot
journalctl -b -1 -p err        # errors only, that boot
journalctl --list-boots | tail -5
```

Read the last lines of `-b -1`. They distinguish causes that need different
fixes:

| what you see | what it means | what fixes it |
|---|---|---|
| `Reached target Sleep`, `PM: suspend entry` | clean suspend — lid or idle | §3, lid switch |
| kernel panic / oops / `BUG:` | driver or hardware fault | §2 disk/RAM checks first |
| log simply stops mid-line | hard hang or power loss | thermal or hardware; §2 |
| `watchdog: BUG: soft lockup` | CPU stall | §2, then §5 watchdog |

**Record what you find in this file.** The next person to read it — including a
future session — needs the answer, not the checklist.

---

## 2. Cheap hardware checks (15 minutes, while you are there)

The machine is ~15 years old. These are the usual suspects and all are cheap to
rule out.

```bash
sudo smartctl -a /dev/sda | grep -iE 'result|reallocated|pending|offline_unc'
sudo apt install -y lm-sensors && sudo sensors-detect --auto && sensors
sudo dmesg -T | grep -iE 'mce|thermal|throttl|ata.*error|I/O error'
```

* **SMART** — anything but `PASSED`, or a nonzero reallocated/pending count,
  makes the disk the prime suspect and everything else secondary.
* **Temperature** — a T420 with dried thermal paste and a dusty fan throttles
  and then hangs. If idle core temps are already above ~70 °C, that is the
  answer.
* **RAM** — if the journal showed a panic with no disk errors, boot `memtest86+`
  before doing anything else. A bad DIMM will defeat every software fix here.

Physical, and worth more than any config change: **blow the dust out of the
fan.** It is the single most common cause of an old ThinkPad hanging.

---

## 3. Stop it suspending — the highest-value fix

`systemd-logind` handles the lid switch **with or without a desktop**, so going
headless does not address this on its own. If finch is docked with the lid
closed, this is almost certainly why it "drops off the network".

```bash
sudo tee /etc/systemd/logind.conf.d/99-headless.conf >/dev/null <<'CONF'
[Login]
HandleLidSwitch=ignore
HandleLidSwitchDocked=ignore
HandleLidSwitchExternalPower=ignore
IdleAction=ignore
CONF
sudo systemctl restart systemd-logind
```

A drop-in under `logind.conf.d/` rather than editing `logind.conf`, so a
package upgrade cannot silently revert it.

Also disable sleep targets outright, since a headless box has no reason to
suspend:

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

**Verify:** close the lid. It should stay up.

```bash
systemctl status systemd-logind | head -3
ping -c2 <gps3-address>          # from finch, lid shut
```

---

## 4. Boot to console

Reduces load and removes the Intel graphics stack — which matters only if §1
pointed at a GPU or compositor fault, but costs nothing either way.

```bash
sudo systemctl set-default multi-user.target
systemctl get-default            # expect: multi-user.target
```

Reversible: `sudo systemctl set-default graphical.target`.

### Parallel terminals: tmux

This is a solved problem and the operator already uses it — the gps3 session
runs in tmux `gps3-move`, up continuously since 24 Aug.

```bash
tmux new -s finch          # create
# ctrl-b c   new window     ctrl-b n / p   next / previous
# ctrl-b "   split          ctrl-b d       detach
tmux attach -t finch       # reattach, from anywhere, after any disconnect
```

Detaching leaves everything running. That is the property that makes a headless
box workable over an unreliable link.

**Do not run long jobs outside tmux.** A dropped SSH session kills them; inside
tmux it does not.

---

## 5. Make networking independent of a login session

A headless machine must come up on the network with nobody logged in.

```bash
systemctl is-enabled NetworkManager systemd-networkd 2>/dev/null
nmcli -t -f NAME,AUTOCONNECT connection show      # autoconnect must be yes
```

If the connection is a user-scoped NetworkManager profile it will **not** come
up before login. Make it system-wide:

```bash
sudo nmcli connection modify <name> connection.permissions ''
sudo nmcli connection modify <name> connection.autoconnect yes
```

---

## 6. The hardware watchdog — the piece that saves the trip

The T420 has one (`iTCO_wdt`). It does not prevent freezes; it ends them
without a human.

```bash
ls /dev/watchdog*                       # should exist
sudo tee /etc/systemd/system.conf.d/99-watchdog.conf >/dev/null <<'CONF'
[Manager]
RuntimeWatchdogSec=60
RebootWatchdogSec=10min
CONF
sudo systemctl daemon-reexec
systemctl show | grep -i watchdog       # RuntimeWatchdogUSec should be 1min
```

If the kernel stops petting the watchdog for 60 s, the hardware resets the
machine. Combined with §5, finch comes back on the network by itself.

**Caveat worth knowing:** a watchdog reboot is a hard reset. Filesystems should
be journalled (ext4/xfs are), but anything mid-write can still be lost. That is
the trade — an unattended reboot against an unattended machine staying dead.

---

## 7. Tailscale, so none of this needs the cubicle again

Install on finch while you are there. This is the step that makes every future
fix remote.

```bash
sudo apt install tailscale
sudo tailscale up                # prints a URL; authenticate in a browser
systemctl is-enabled tailscaled  # MUST be enabled, or a reboot loses the route
tailscale ip -4
```

**Do not pass `--ssh` yet.** It adds a second SSH server with its own auth
model alongside the working one. Prove plain `sshd` over the tailnet first;
one moving part at a time.

Then, from gps3 or a phone:

```bash
ssh finch                        # MagicDNS
```

---

## 8. Verification — reboot and confirm it comes back alone

Nothing above is proven until the machine has done it unattended.

```bash
sudo reboot
```

Then, **without touching the laptop**, from another machine:

```bash
ping -c3 finch
ssh finch 'systemctl get-default; systemctl is-enabled tailscaled; \
           systemctl is-active tailscaled; uptime'
```

All four must answer. If you have to touch finch to get it back, the setup has
not achieved its one goal and something above is wrong.

Close the lid and repeat the SSH check.

---

## What to write back

Append the answers to this file and commit:

* what §1 said the cause was
* SMART result and idle temperature
* whether the lid-close test passed
* whether the machine came back from §8 unattended

That turns a checklist into a record, which is what makes it worth having next
time.
