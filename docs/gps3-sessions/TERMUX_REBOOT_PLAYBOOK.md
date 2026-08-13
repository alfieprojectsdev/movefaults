# Reboot + resume playbook (Termux / phone)

**For:** rebooting gps3 and picking the working session back up from a phone.
**Written:** 2026-08-13, while kernel `6.8.0-137` sat installed and
`6.8.0-111` was still running.

Written for a phone screen: short commands, one job per step, and the
verification *before* the celebration. Everything here is copy-pasteable.

---

## Why this needs a playbook at all

**Every data volume on this machine is mounted `nofail`.**

```
UUID=… /srv/gnss-archive  xfs  defaults,noatime,nofail 0 2
UUID=… /home/gps3/GPSWORK xfs  defaults,noatime,nofail 0 2
UUID=… /home/gps3/GPSDATA xfs  defaults,noatime,nofail 0 2
UUID=… /srv/eil-data      xfs  defaults,noatime,nofail 0 2
```

`nofail` means a volume that fails to mount **does not stop the boot**. The
machine comes up clean, you log in, everything looks normal — and the data is
simply not there. That is the right setting for a headless server (you never
want a bad disk to strand you at an emergency prompt), but it converts a loud
failure into a silent one.

**This reboot is the first real test of the July fstab changes.** Step 3 is
therefore not optional.

---

## 0. Before you reboot

```bash
tmux ls                 # note which sessions exist
uptime                  # note load; wait for background jobs to finish
pgrep -af 'verify_archive|transfer_phivolcs|luzon_|RUNBPE'
```

**If that last command prints anything, wait.** A BPE run or a manifest job
killed mid-flight is not corruption, but it is wasted hours. As of writing,
nothing is in flight: the datapool transfer, all three fixity manifests, and
the parallel-session test have completed.

Commit and push anything uncommitted — a reboot is a fine time to discover you
had 400 lines only on disk:

```bash
cd ~/repos/movefaults_clean && git status --short
```

---

## 1. Reboot

You said you want to be on premises for this, which is right: if a volume does
not come back, the fix may need console access.

```bash
sudo reboot
```

Expect ~2–4 minutes. The PERC controller takes its time.

---

## 2. Reconnect from Termux

```bash
ssh gps3@192.168.48.98
```

`gps3` is **not** resolvable as a hostname — use the IP. (The `gps3@gps3:~$`
in older notes is a shell prompt, not an address.)

---

## 3. Verify the mounts — DO THIS FIRST

```bash
df -h | grep -E 'gnss-archive|GPSDATA|GPSWORK|eil-data'
```

**You must see four lines.** Expected sizes:

| Mount | Size | Holds |
|---|---|---|
| `/srv/gnss-archive` | 20T | legacy archive, 476 GiB datapool, fixity manifests |
| `/home/gps3/GPSDATA` | 4.0T | DATAPOOL, CAMPAIGN54, SAVEDISK — all Bernese work |
| `/home/gps3/GPSWORK` | 1.0T | scratch |
| `/srv/eil-data` | — | separate project |

**Fewer than four lines means a volume did not mount.** Do not start work.
Diagnose:

```bash
findmnt --verify --verbose        # fstab sanity
sudo dmesg | grep -iE 'xfs|mount|I/O error' | tail -20
lsblk -o NAME,SIZE,FSTYPE,UUID,MOUNTPOINT
```

A missing volume with a healthy disk is usually a UUID mismatch — compare
`lsblk` UUIDs against `/etc/fstab`. A missing volume with I/O errors in
`dmesg` is a hardware problem: **stop and check the array before mounting
anything read-write.**

## 4. Verify the kernel actually changed

```bash
uname -r          # expect 6.8.0-137-generic
```

If it still says `6.8.0-111-generic`, the new kernel did not take. The machine
is fine — you simply rebooted into the old one. Check `sudo dmesg | head -5`
and the GRUB default before trying again.

## 5. Verify the array is still being watched

```bash
sudo systemctl status smartd --no-pager | head -5
sudo smartctl --scan | wc -l          # expect 16 devices behind the PERC
```

`smartd` running is not sufficient — a stock `DEVICESCAN` config sees **zero**
drives behind a PERC controller while reporting itself perfectly healthy. If
the device count is 0, the monitoring is decorative.

## 6. Verify Bernese comes back

```bash
source ~/BERN54/LOADGPS.setvar
echo "$P" "$D" "$S" "$U"
ls "$S"/LUZON/2025/SOL/FIN_2025*.SNX.gz | wc -l      # expect 30
```

`LOADGPS.setvar` is sourced by `~/.bashrc` **for interactive shells only** — a
non-interactive `ssh gps3 '<cmd>'` will not have `$P`/`$D`/`$U` set. Source it
explicitly in scripts.

## 7. Spot-check fixity (optional, ~1 minute)

Cheap reassurance that the array survived:

```bash
cd /srv/gnss-archive/legacy
zcat ~/repos/movefaults_clean/docs/archive-manifests/legacy-sha256-*.txt.gz \
  | shuf -n 20 | sha256sum -c
```

Twenty random files out of 162,328. All `OK` is a good sign; any `FAILED` is
worth stopping for.

---

## 8. Restart the working session

tmux does **not** survive a reboot — the sessions are gone and that is normal.

```bash
tmux new -s claude
cd ~/repos/movefaults_clean
git pull --rebase
claude --resume 35d41bfc-e010-46a4-814e-a3fb35603c1a
```

Detach with **Ctrl-b** then **d**. Reattach later, from anywhere:

```bash
tmux attach -t claude
```

This survives closing Termux, losing signal, and leaving the building — the
session keeps running on the server. It has been driven from a home network
outside the PHIVOLCS LAN.

Other sessions that existed before the reboot (`archive`, `hasadmin`) were
separate working contexts; recreate them only if you need them.

---

## 9. Tell the session where things stand

Once Claude Code is back, paste something like:

> Rebooted onto 6.8.0-137. All four volumes mounted, 30 LUZON solutions
> present, smartd sees 16 drives. Resume from the outstanding list.

The conversation is restored, but **the machine state is not** — background
jobs are gone, and it has no way to know the reboot succeeded unless told.

---

## Quick reference

| | |
|---|---|
| Host | `ssh gps3@192.168.48.98` (IP, not hostname) |
| Session ID | `35d41bfc-e010-46a4-814e-a3fb35603c1a` |
| Repo | `~/repos/movefaults_clean` |
| Bernese env | `source ~/BERN54/LOADGPS.setvar` |
| File server | `\\192.168.48.99` — guest SMB, read-only |
| teqc | `/home/gps3/teqc/teqc` (not on `PATH`) |
| gfzrnx | `/home/gps3/gfzrnx/gfzrnx_2.2.0_lx64` (not on `PATH`) |
| Detach tmux | `Ctrl-b` then `d` |

## Things a reboot will NOT break

Worth knowing so they are not re-verified every time:

- **The archives.** 493,082 files fingerprinted and committed to git, so
  corruption is now *detectable* rather than merely unlikely.
- **The 30-day LUZON baseline**, preserved at
  `$S/LUZON_BASELINE_20260806`.
- **Bernese itself.** `$U/GPSUSER` and `BERN54` are on the root volume, which
  mounts or the machine does not boot.
- **Anything committed and pushed.** The repo is also mirrored to
  `/srv/gnss-archive/git/`.
