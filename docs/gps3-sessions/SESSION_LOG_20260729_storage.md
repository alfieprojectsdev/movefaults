# gps3 Session Log — 2026-07-29: Storage Provisioning

**Session:** `dell-gps` (Claude Code running on gps3)
**Purpose:** carve the unallocated PERC volume into LVs, migrate GPSDATA, re-verify Bernese.
**Prior:** `~/HANDOVER.md` (updated 2026-07-29 by the T420 session)
**Outcome:** ✅ complete — new mounts in service, BPE numerical parity preserved.

---

## 1. Starting state (verified this session)

- Machine confirmed: `gps3` @ `192.168.48.98/24` on `eno4`.
- `sda`: 32.7 TB Dell PERC H750 Adp virtual disk. `sda3` LVM2_member.
- `ubuntu-vg`: **32.74 TiB total, 32.64 TiB free** (`vgs`, `vgdisplay`). Single LV `ubuntu-lv` 100 G ext4 at `/`.
- Root at **74% used, 25 G avail**.
- `~/GPSDATA`: 4.5 GB (365 M CAMPAIGN54, 4.1 G DATAPOOL, 46 M SAVEDISK).
- `~/GPSWORK`: empty.
- No `MegaRAID` CLI installed (`storcli`/`perccli`/`megacli` all absent). `sudo dmesg | grep megaraid` shows driver init but not the RAID level.

---

## 2. What was done

### 2.1 Storage provisioning (`gps3_storage_provision.sh --apply`)

Order followed the handover's Order of Operations. `sudo systemctl daemon-reload` run afterward to clear the systemd/fstab-out-of-sync warning.

| LV | Size | FS | Mount | fstab entry |
|---|---|---|---|---|
| `ubuntu-lv` | 100 G → **250 G** | ext4 (online resize) | `/` | pre-existing |
| `lv_gpsdata` | **4 T** | XFS | `/mnt/lv_gpsdata_staging` (staging) | *(not in fstab yet)* |
| `lv_archive` | **20 T** | XFS | `/srv/gnss-archive` | UUID, `defaults,noatime,nofail` |
| `lv_work` | **1 T** | XFS | `~/GPSWORK` | UUID, `defaults,noatime,nofail` |
| free extents | ~7.5 T | — | — | headroom |

fstab backup at `/etc/fstab.bak-20260729`.

Post-apply: root `/` now 246 G / 30% / 167 G free.

### 2.2 GPSDATA migration (`gps3_gpsdata_migrate.sh --sync` then `--swap`)

- `--sync`: rsync `-aHAX --info=progress2` from `~/GPSDATA/` to `/mnt/lv_gpsdata_staging/`. Three-way census matched exactly: **4262 files, 3 symlinks, 4,807,040,204 bytes**.
- `--swap`: unmounted staging, renamed `~/GPSDATA` → `~/GPSDATA.old-20260729`, added fstab entry (UUID `0d94836d-0d79-4db9-a681-bb93ffad9b36`, xfs, `defaults,noatime,nofail`), mounted `lv_gpsdata` at `~/GPSDATA`, re-verified through the new mount. Census matched. All 3 DATAPOOL/REF54 symlinks intact (`EXAMPLE.ABB → EXAMPLE.ABB_REF`, `.CRD`, `.VEL`).
- Rollback dir `~/GPSDATA.old-20260729` retained on root (4.5 G — root still at 30%).

### 2.3 BPE re-verify

- Launched detached: `setsid nohup perl $U/SCRIPT/rnx2snx_pcs.pl 2023 0100` with output to `~/bpe-reverify.log`, PID pinned in `~/bpe-reverify.pid`.
- Ran on the new storage: `$P` on `lv_gpsdata`, `$T` on `lv_work` (fresh XFS, empty at start). BPE created `BPE_RNX2SNX_37309_23_0100_201_000` under `~/GPSWORK` — confirms scratch mount is working.
- **Runtime:** 14:16:05 → 14:27:33 = **11 m 28 s** (matches the 11 m 23 s reference within seconds).
- SINEX comparison (`/tmp/sinex_diff.sh`, extracts 54 STAX/STAY/STAZ params from `SOLUTION/ESTIMATE`, subtracts, converts to mm):
  - params compared: 54
  - **max abs diff: 0.000020489 mm** at BRST STAX (20 nanometers)
  - rms diff: 0.000007519 mm (7.5 nanometers)
  - rounded to 4 dp: **0.0000 mm** — exact match with the handover's baseline.

---

## 3. Script patches applied

`gps3_gpsdata_migrate.sh`, lines ~102-107 (the "open files under GPSDATA" pre-flight check).

**Bug 1: `fuser -m` false positive on non-mount paths.** When `$SRC` (`~/GPSDATA`) is a plain directory rather than a mountpoint, `fuser -m` escalates to the containing mount (`/`) and matches every process on the system — kernel threads, systemd, etc. In `--sync` mode this was just a noisy warning; in `--swap` mode the script would die with "close them before swapping".

**Bug 2: `set -euo pipefail` silent exit.** My initial patch used `open_under=$(lsof +D "$SRC" 2>/dev/null | tail -n +2)`. `lsof +D` returns **exit 1 when the tree has no open files** (the safe case). Under `pipefail`, the command substitution inherited that non-zero exit, and `set -e` killed the script silently right after the last successful `ok` — the first `--swap` attempt exited with no output past "no BPE process running", and no changes made.

Final patched block replaces `fuser -m` with a properly-guarded `lsof +D`:

```bash
if command -v lsof >/dev/null 2>&1; then
    open_under=$(lsof +D "$SRC" 2>/dev/null | tail -n +2 || true)
    if [ -n "$open_under" ]; then
        warn "processes currently have files open under $SRC:"
        printf '%s\n' "$open_under" | head -10
        [ "$MODE" = "swap" ] && die "close them before swapping"
    fi
fi
```

---

## 4. Notable gotchas discovered

- **Claude Code `!` prefix has no controlling tty.** `! sudo <cmd>` fails with *"a terminal is required to read the password"*. Workaround: run sudo commands in the user's own terminal, redirect output to a log file, have Claude Read it (e.g. `sudo ./script > ~/name.log 2>&1`). Applied throughout this session.
- **Monitor script's `pgrep` matched itself.** The `pgrep -f "MENU/menu "` in the completion-vs-crash detector kept matching the monitor's own bash shell (whose command line contained that pattern), so the crash branch never fired even after all real BPE processes were gone. Not a bug that mattered here — I detected completion via direct polling — but worth remembering when writing future monitors.
- **Launcher terminology.** The `rnx2snx_pcs.pl` launcher writes *"BPE finished at ..."* to its log, **not** *"Sessions finished: OK: 1 Error: 0"*. That "Sessions finished" phrasing in the handover came from a different wrapper (T420's `startBPE.pm` or similar). Use `"BPE finished"` for completion detection on gps3's setup.
- **`.gz_REF` really is gzipped.** `$S/RNX2SNX/2023/SOL/FIN_20230100.SNX.gz_REF` is a gzip stream (20 KB compressed, 63 880 B decompressed matching the produced size exactly). Compare against `gunzip -c`, not the raw file.
- **BPE self-timing preserved on XFS.** 11m28s vs the reference 11m23s — no measurable regression from moving `$P` and `$T` off ext4 onto XFS.

---

## 5. State after session

```
$ df -h / /home/gps3/GPSDATA /home/gps3/GPSWORK /srv/gnss-archive
Filesystem                          Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv   246G   69G  167G  30% /
/dev/mapper/ubuntu--vg-lv_gpsdata   4.0T   83G  4.0T   3% /home/gps3/GPSDATA
/dev/mapper/ubuntu--vg-lv_work      1.0T   20G 1004G   2% /home/gps3/GPSWORK
/dev/mapper/ubuntu--vg-lv_archive    20T  393G   20T   2% /srv/gnss-archive
```

XFS shows ~2% "used" out-of-the-box (metadata reservation), not real data.

VG free remaining: 7.5 TB.

fstab tail:
```
UUID=c707a41e-... /srv/gnss-archive xfs defaults,noatime,nofail 0 2
UUID=22ae67a5-... /home/gps3/GPSWORK xfs defaults,noatime,nofail 0 2
UUID=0d94836d-... /home/gps3/GPSDATA xfs defaults,noatime,nofail 0 2
```

---

## 6. Outstanding

| item | why deferred |
|---|---|
| Reclaim `~/GPSDATA.old-20260729` (4.5 G on `/`) | keep as rollback for a day or two |
| Verify PERC H750 RAID level | not needed for provisioning; only blocks treating gps3 as the archive's **only** copy |
| PAGENET transfer (~12.5 G RAW+SOL) | not blocking; ready when needed |
| Deploy orchestrator (`services/bernese-workflow/`) | "128 tests pass but has never driven a real BPE" — real next unknown per handover §7 |
| Legacy archive → `/srv/gnss-archive` (~150 G, single-copy) | wait for RAID level confirmation |
| `deploy_r740.sh` GPSUSER hazard (§4.1 of handover) | unchanged |
| Rotate leaked OAuth token at claude.ai | human action; unrelated to storage |

---

## 7. Files created/modified this session

- `/etc/fstab` — 3 new entries (2 by provision script, 1 by migrate --swap). Backup at `/etc/fstab.bak-20260729`.
- `/home/gps3/gps3_gpsdata_migrate.sh` — patched pre-flight check (`fuser -m` → `lsof +D` with `|| true`).
- `/home/gps3/GPSDATA.old-20260729/` — the pre-migration copy on root (rollback).
- `/home/gps3/{raid-vg,provision-dry,provision-apply,migrate-dry,migrate-sync,bpe-reverify}.log` — session logs from each sudo command.
- `/home/gps3/bpe-reverify.pid` — the launcher PID (227261).
- `/tmp/sinex_diff.sh` — the SINEX numerical comparison script.

## 8. Addendum — RAID member enumeration (same day, later)

The handover listed the PERC RAID level as **UNVERIFIED**, gating whether gps3 could
be the legacy archive's home. Resolved this session.

**Why the obvious routes failed:**
- `storcli`, `perccli`, `megacli` are **not in the Ubuntu repos** (all proprietary
  Broadcom/Dell binaries). The handover's suggested `apt install megacli` does not work.
- The backplane is **not exposed via SES** — no `/sys/class/enclosure`, and only 3
  `/dev/sg*` nodes (the VD, the DVD drive, the IDSDM). `sg_ses` had nothing to talk to.
- `/proc/scsi/scsi` shows only the virtual disk. The controller owns the members entirely.
- `sudo dmesg | grep megaraid` shows driver init but never the logical-drive config.

**What worked:** `smartctl -d megaraid,N /dev/sda` tunnels SMART through the
`megaraid_sas` driver to each physical member. `smartmontools` **is** in the official
Ubuntu archive (7.4-2build1). Script written to `/home/gps3/raid_enum.sh`, log at
`~/raid-enum.log`.

**Result — 16 members, all identical, all healthy:**

| | |
|---|---|
| model | Toshiba **AL15SEB24EQY** (2.4 TB, 10 000 RPM SAS) |
| count | **16** (device IDs 0–15, all on the `megaraid` transport) |
| raw total | 38.41 TB decimal |
| VD usable | 35.997 TB decimal (32.74 TiB) |
| health | all **OK**, zero reallocated / pending / uncorrectable sectors |

**Level inference:**

| candidate | would yield | delta vs VD |
|---|---|---|
| RAID 0 (16 data) | 38.410 TB | +6.703% |
| **RAID 5 (15 data)** | **36.009 TB** | **+0.034%** ← fits |
| RAID 6 (14 data) | 33.609 TB | −6.635% |
| RAID 10 (8 data) | 19.205 TB | −46.6% |
| RAID 0 ×15 + 1 spare | 36.009 TB | +0.034% ← also fits |
| RAID 5 ×15 + 1 spare | 33.609 TB | −6.635% |

Two configurations fit the arithmetic. The second — 15 drives in RAID 0 with a hot
spare — is not a real configuration: a hot spare cannot rebuild a RAID 0, and no
controller lets you assign one usefully. **Conclusion: 16-drive RAID 5.** The same
arithmetic also rules out any hot spare existing, since no sensible level fits
15 members at 36 TB.

**Non-confirming evidence, noted honestly:** the controller reports
`minimum_io_size=262144` (256 KB strip) and `optimal_io_size=1048576` (1 MB). That
ratio implies 4 data disks, not 15 — PERC firmware reports a generic
`optimal_io_size` rather than true stripe width, so this neither confirms nor
contradicts. Side effect: `mkfs.xfs` picked up `sunit=64 swidth=256` blocks from
these limits, aligning XFS for a 4-disk array rather than 15. A minor full-stripe
write inefficiency, irrelevant for GNSS's many-small-files workload. Not worth
reformatting over.

### Verdict on the gating question

**gps3 can host the legacy archive** — RAID 5 survives one drive failure, and all
16 members are currently clean.

**But it must not be the only copy.** 16-wide RAID 5 at 36 TB is the weakest
redundant layout in use:
- A rebuild must read **all 15 surviving drives** end to end. At 2.4 TB each on
  10K spindles that is a long window.
- A second drive failure *or a single unrecoverable read error* during that window
  loses the entire array.
- RAID protects against **drive** failure only — not controller failure, filesystem
  corruption, accidental `rm`, or fire.

### Follow-up this surfaced

- **`smartd` is enabled but monitoring nothing.** The package enabled the service,
  but the stock `/etc/smartd.conf` uses `DEVICESCAN`, which cannot see behind the
  controller. On a RAID 5 with no hot spare, early warning is the primary defense —
  it needs explicit `/dev/sda -d megaraid,N` lines for N=0..15.
- **Pending kernel upgrade.** Running `6.8.0-111-generic`, but `6.8.0-136-generic`
  is installed. The first reboot will exercise the new fstab; all three added
  entries use `nofail` and `findmnt --verify` passed clean, so it should be safe.

---

## 9. smartd configuration — **APPLIED 2026-07-30 07:49**, all 16 members monitored

> **Status: DONE.** `/etc/smartd.conf` now carries 16 explicit `-d megaraid,N`
> lines; `smartmontools` is active and enabled; the `20log` alert hook is
> installed and has been fired end to end. Verified independently of the setup
> script's own output (see §12). The original Ubuntu config is preserved at
> `/etc/smartd.conf.bak-20260730-074917`.
>
> The section below was written while the change was still only *prepared*; it
> is kept as-is for the reasoning. §12 records what actually happened, including
> a first run that failed.

The RAID enumeration surfaced that `smartd` was enabled by the `smartmontools`
install but is effectively inert:

- Stock config is a single `DEVICESCAN` line. It enumerates block devices the
  **kernel** can see — and the kernel sees only the virtual disk. The 16
  members are invisible to it, so smartd monitors nothing.
- There is **no MTA** on gps3, so the stock `10mail` run.d hook exits 1 and
  discards every alert silently.

On a 16-wide RAID 5 with **no hot spare**, early warning of a degrading drive
is the primary defense. Fixing this is worth doing before the archive lands.

**Prepared:** `/home/gps3/smartd_setup.sh` (executable, `bash -n` clean).

Run with:
```bash
sudo /home/gps3/smartd_setup.sh > ~/smartd-setup.log 2>&1; echo "exit=$?"
```

What it does, in order:
1. Re-probes all 16 members and **aborts if the count differs** — refuses to
   configure monitoring around a stale assumption about the array.
2. Installs `/etc/smartmontools/run.d/20log`, logging alerts to syslog and
   `/var/log/smartd-alerts.log`.
3. Generates 16 explicit `-d megaraid,N` lines replacing `DEVICESCAN`.
4. **Validates with `smartd -q onecheck` against a temp file before installing** —
   a malformed config cannot take out the running service.
5. Backs up the old config, restarts, and **auto-restores the backup** if the
   service fails to come up.
6. Confirms from the service journal that all 16 members registered.

Config decisions:

| choice | reasoning |
|---|---|
| short self-tests, staggered one drive per hour (drive N at hour N) | cheap (~2 min), and staggering avoids 16 simultaneous tests |
| **no** long self-tests | the PERC's own patrol read does surface scanning; 16 concurrent long tests would contend with it. Commented instructions included if patrol read is ever confirmed off. |
| `-W 4,50,60` | log 4 °C changes, warn 50 °C, critical 60 °C — standard enterprise SAS |
| `-a` | on SAS this resolves to health + error log + self-test log; the ATA-attribute portions of `-a` don't apply and are ignored |

### Bug caught during authoring

The first draft of the `20log` hook read the alert from **stdin**. That is wrong.
Reading `/usr/share/smartmontools/smartd-runner` shows it spools stdin to a temp
file and passes the **file path as `$1`**:

```bash
tmp=$(mktemp)
cat >$tmp
run-parts --report --lsbsysinit --arg=$tmp --arg="$1" ... -- /etc/smartmontools/run.d
```

The stock `10mail` confirms the contract (`input=$1; shift; mail "$@" < $input`).
Hook corrected to read `$1` as a file, and verified standalone against a
synthetic alert before shipping. Also verified `20log` satisfies
`run-parts --lsbsysinit` filename rules (matches the Debian cron namespace
`^[a-zA-Z0-9_-]+$`).

### Known cosmetic side effect

`10mail` will exit 1 on every alert (no `mail` binary), so `run-parts --report`
logs *"10mail exited with return code 1"* beside each genuine warning. Harmless.
Silence with `sudo chmod -x /etc/smartmontools/run.d/10mail`, or leave it so
alerts begin mailing if an MTA is ever installed.

---

## 10. State at end of session

**Applied and verified:**

```
Filesystem                         Size  Used Avail Use% Mounted on
/dev/mapper/ubuntu--vg-ubuntu--lv  246G   69G  167G  30% /
/dev/mapper/ubuntu--vg-lv_gpsdata  4.0T   83G  4.0T   3% /home/gps3/GPSDATA   ✓ mounted
/dev/mapper/ubuntu--vg-lv_work     1.0T   20G 1004G   2% /home/gps3/GPSWORK   ✓ mounted
/dev/mapper/ubuntu--vg-lv_archive   20T  393G   20T   2% /srv/gnss-archive    ✓ mounted
```

- RAID: 16 × 2.4 TB SAS, RAID 5, all members healthy.
- Rollback dir `~/GPSDATA.old-20260729` (4.5 G) still present on root.
- Nothing running; no background jobs outstanding.

**Prepared but NOT applied:**

- `smartd_setup.sh` — smartd still monitoring nothing until it is run.

**Carried forward:**

| item | note |
|---|---|
| Run `smartd_setup.sh` | the one immediately actionable item |
| Reboot | kernel 6.8.0-136 installed, running 6.8.0-111. First reboot exercises the new fstab (all `nofail`, `findmnt --verify` clean). |
| Reclaim `~/GPSDATA.old-20260729` | once satisfied with the migration |
| Legacy archive → `/srv/gnss-archive` | now unblocked by the RAID finding — but RAID 5 is not a backup, keep a second copy |
| Deploy orchestrator | `services/bernese-workflow/` — 128 tests pass, never driven a real BPE. The actual next unknown. |
| Revoke leaked OAuth token at claude.ai | human action, unrelated to storage |

### Useful gotcha for the next session

`findmnt` accepts only **one** target. `findmnt /a /b /c` silently prints
nothing, which reads exactly like "none of these are mounted." Use
`df -h /a /b /c` or loop `mountpoint -q` instead. This produced a false
"mounts missing" reading twice during this session.

---

## 11. Verified rollback path

If anything surfaces later, the swap is reversible while `GPSDATA.old-20260729` exists:

```bash
sudo umount /home/gps3/GPSDATA
sudo rmdir /home/gps3/GPSDATA
sudo mv /home/gps3/GPSDATA.old-20260729 /home/gps3/GPSDATA
sudo sed -i '/\/home\/gps3\/GPSDATA /d' /etc/fstab
sudo systemctl daemon-reload
```

---

## 12. smartd applied — 2026-07-30

### 12.1 The first run failed, and why that matters

`smartd_setup.sh` was run at 07:33 and **aborted at step 1 with "0 of 16 members
answered"** — on an array `raid_enum.sh` had enumerated cleanly 15 hours earlier.
It failed safe: no config installed, no backup written, no hook created.

Root cause, measured rather than assumed:

| construct | exit |
|---|---|
| `smartctl -i -d megaraid,0 /dev/sda 2>/dev/null \| grep -qiE '^(...\|Vendor):'` | **141** |
| identical pipeline, `set +o pipefail` | 0 |
| `o=$(smartctl ...)` then `printf '%s\n' "$o" \| grep -q ...` | 0 / 0 |

The chain: `grep -q` exits the instant it matches — `Vendor:` is **line 5** of
smartctl's output. smartctl is nowhere near finished; it continues issuing SCSI
inquiries for lines 6–26 (Rotation Rate, Form Factor, LU id, SMART support).
Its next write hits a pipe with no reader → **SIGPIPE, 141**. `set -o pipefail`
makes 141 the pipeline's status, so the `if` is false *even though grep matched*.

**Two false starts on the diagnosis, both worth recording:**

1. First explanation blamed smartctl's SMART **exit bitmask** (bit1 open failed,
   bit2 SMART cmd failed, bit6/7 error-log entries). Right mechanism —
   pipefail propagating a non-zero — wrong source. smartctl returns **0** here;
   the 141 came from SIGPIPE.
2. An attempt to reproduce it locally with `echo`, `seq 1 200000` and a
   background subshell returned **0 every time**, which looked like proof the
   pipefail theory was wrong. It was not. A **fast** writer drains into the
   64 KB pipe buffer and exits before `grep -q` can close the read end, so there
   is no second write to fault on. Only a genuinely slow writer — smartctl
   round-tripping SCSI commands through the megaraid tunnel — faults, and it
   does so deterministically on all 16.

**Generalisable rule:** under `pipefail`, `slow_cmd | grep -q` is a landmine.
A clean local repro with a fast writer is not evidence the theory is wrong.
This is the second instance of this bug class in the same session — see §3's
`lsof +D` exit-1 bug — hence the memory note `feedback_pipefail_traps.md`.

**Fix:** step 1 now captures to a variable then greps (the shape `raid_enum.sh`
used all along), and prints per-member exit codes so a future failure names the
member instead of emitting a bare count.

**Second hardening while there:** step 4's validation previously only checked
for the *absence* of error strings, which would have happily installed a config
that registered nothing. It now counts distinct `megaraid_disk_NN` identifiers
smartd actually opened and refuses to install unless all 16 appear.

### 12.2 Applied state (verified independently of the script's own output)

Second run at 07:49: **exit 0**, all 16 members registered.

```
/etc/smartd.conf                      16 × "/dev/sda -d megaraid,N -a -W 4,50,60 -s S/../.././NN"
/etc/smartd.conf.bak-20260730-074917  original Ubuntu config (6136 B), preserved
/etc/smartmontools/run.d/20log        installed, mode 755
/var/log/smartd-alerts.log            mode 640
smartmontools                         active, enabled
journal                               zero warn/error/unable/cannot since restart
```

### 12.3 Alert path tested end to end

`/var/log/smartd-alerts.log` was 0 bytes, so the hook had never actually run —
an untested alert path is an assumption, not a defense. Fired one synthetic
alert through `20log` directly:

```
hook exit = 0
/var/log/smartd-alerts.log:
  === 2026-07-30T08:04:15+08:00 ===
  device   : /dev/sda megaraid,0
  failtype : TEST
syslog:
  Jul 30 08:04:15 gps3 smartd-alert[292956]: SMART ALERT on /dev/sda megaraid,0: TEST
```

Landed in **both** sinks, as `COORDINATION.md` §7 required. The synthetic entry
should be truncated so no future reader mistakes it for a real warning:
`sudo truncate -s 0 /var/log/smartd-alerts.log`.

### 12.4 Divergences from COORDINATION.md §7 — read before assuming compliance

| §7 requirement | status |
|---|---|
| 16 explicit `-d megaraid,N` lines | ✅ |
| non-mail sink, tested in journald **and** flat file | ✅ but implemented differently — see below |
| **stagger the long self-tests** | ❌ **no long tests are scheduled at all** |
| `smartd -q onecheck` reports 16, not 0 | ✅ 16 of 16 |
| alert path tested end to end | ✅ §12.3 |

**On `-m root`:** §7 said do not use it. The installed lines do use
`-m root -M exec /usr/share/smartmontools/smartd-runner`. This is not the
failure mode §7 was guarding against: `-M exec` *replaces* mailing, and
`smartd-runner` run-parts `/etc/smartmontools/run.d/`, where `20log` writes both
sinks. `10mail` will exit 1 on every alert (no MTA) and run-parts logs that
alongside the real warning — noise, not loss. This is also the distro-idiomatic
form; Ubuntu's own stock `DEVICESCAN` line uses exactly these flags. The
substance of the requirement — an externally observable, non-mail sink, proven
to work — is met and evidenced above. A standalone `/usr/local/sbin/smartd-alert`
would be equivalent, not safer.

**On long self-tests — this is a real gap, not a variance.** The config
schedules a **short** test per drive daily, staggered one member per hour
(`-s S/../.././NN`), and deliberately no long tests. The stated reasoning was
that the PERC's own **patrol read** performs surface scanning and 16 concurrent
long tests would contend with it.

**That reasoning is unverified.** Whether patrol read is actually enabled on
this controller was never checked, and there is no vendor CLI on the box to
check it with (`storcli`/`perccli`/`megacli` are not in the Ubuntu repos, and
the backplane is not exposed via SES). If patrol read is disabled, then
**nothing is doing a full-surface read of these 16 drives** — and an unread bad
sector that only surfaces during a rebuild is precisely the failure mode that
kills 16-wide RAID 5. §2 of `COORDINATION.md` puts URE risk per rebuild at
~3.1% for enterprise SAS at 1e-16; that figure assumes latent defects are being
found *before* the rebuild, which is what a surface scan is for.

**Action needed (requires iDRAC, cannot be done from the OS):** confirm patrol
read is enabled and note its period. If it is disabled, either enable it, or
append staggered long tests to the `-s` expressions:
`-s (S/../.././NN|L/../../6/NN)`.

> **RESOLVED 2026-08-03 — see §13.2. Do not act on the paragraph above.**
> The premise was wrong in a way worth noticing: it assumed surface scanning
> could only come from the controller, so an unreachable iDRAC meant an
> unanswerable question. It came instead from **BMS, the drive firmware's own
> Background Media Scan**, which runs below the controller and is fully visible
> from the OS. Full-surface reads are happening roughly daily on all 16
> members. Long self-tests were considered and **rejected** — they would
> duplicate existing coverage. Whether PERC patrol read is enabled remains
> unknown and no longer matters.

---

## 13. Mirror, surface-scan resolution, and archive prep — 2026-07-30 to 08-03

Covers the tail of the 07-30 session, a four-day unattended gap, and the
08-03 resumption. §1–12 stand as written except where noted above.

### 13.1 Git mirror onto agency hardware

The repository's only durable copy lived on a personal GitHub account —
identified in `COORDINATION.md` as the project's top continuity risk, since
nobody at PHIVOLCS can grant or recover access to it. There is now a bare
mirror on agency-owned storage:

```
/srv/gnss-archive/git/movefaults.git        bare, ~14 MB, 50 branches at creation
/srv/gnss-archive/git/mirror-update.sh      refresh script
cron: 37 22 * * *                           nightly
```

The design goal is **preservation, not synchronisation**, and the difference is
the whole point:

| Setting | Value | Why |
|---|---|---|
| `--prune` on fetch | **omitted, deliberately** | A mirror that prunes faithfully reproduces upstream deletions. A force-push or branch deletion on GitHub would erase the same history here — the mirror would dutifully destroy the thing it exists to protect. |
| `core.logAllRefUpdates` | `true` | Bare repos default this **off**. With it on, every ref movement is recorded in the reflog, so a clobbered ref is still recoverable locally. |
| `gc.pruneExpire` | `never` | Unreachable objects are never garbage-collected. Anything that ever arrived stays. |
| `git fsck` | every run | Fixity check. Catches silent corruption on the array itself. |

The combined effect is an **append-only** copy: upstream can add history to it,
but cannot take history away. The cost is that genuinely dead branches
accumulate, which is a trivial price.

Two smaller guards, both from bugs this project has already paid for:

- **Mount guard.** The script refuses to run unless `/srv/gnss-archive` is a
  real mountpoint. Without it, an unmounted array means the mirror silently
  writes into the empty directory on the root filesystem — appearing to work
  while backing up nothing to the wrong disk.
- **`BatchMode=yes`, `GIT_TERMINAL_PROMPT=0`.** Under cron there is no tty; a
  credential prompt would hang the job indefinitely instead of failing. Fail
  fast and loudly beats hang quietly.

The script is committed as `scripts/gnss_mirror_update.sh`. **The deployed copy
at `/srv/gnss-archive/git/` is the one cron runs** — edits to the repo copy do
not take effect until copied across.

**Verified 2026-08-03 after four unattended days:** fired all four nights,
`fsck clean` every run, branches 50 → 54. It works without supervision, which
was the requirement.

### 13.2 Surface scanning: the §12.4 gap closed, from an unexpected direction

§12.4 left a genuine hole. smartd schedules only short self-tests; long tests
were omitted on the assumption that PERC patrol read handles surface scanning;
that assumption was never checked, and appeared uncheckable — no vendor CLI
exists in the Ubuntu repos and iDRAC has no IP (§13.4).

**The question was answerable after all, because the assumption about where
scanning comes from was too narrow.** SAS drives run their own **Background
Media Scan (BMS)** in firmware, below the RAID controller, and both the scan
log and the lifetime byte counters are readable through the megaraid
pass-through. Measured 2026-08-03 via `/home/gps3/patrol_check.sh`:

```
Status: waiting until BMS interval timer expires
Accumulated power on time, hours:minutes 10142:56
Number of background scans performed: 424

read:  0  228  228  228  3929  1025339.394  0
                             GB processed ^      ^ uncorrected
```

| Measure | Value |
|---|---|
| Lifetime read, per drive | ~1,025,300 GB ≈ **1.03 PB** |
| Total uncorrected read errors | **0** on all 16 |
| Background scans performed | **424** |
| Power-on hours | 10,142 (≈423 days) |
| Implied scan interval | **≈ one full pass per 24 h** |

**The cross-check that makes this a conclusion rather than a guess.** Scan
count and bytes-read are separate firmware counters kept for unrelated
purposes. 424 scans × 2.4 TB = 1,017.6 TB, against a measured 1,025.3 TB —
agreement within 0.8%. Two independent counters converge on the same fact, so
the conclusion does not rest on trusting either number's label. `patrol_check.sh`
now computes this ratio directly and prints it as the `SWEEPS` column.

**Direct evidence the mechanism has already earned its keep.** Across all 16
members BMS has found and repaired **~112 physical sectors** (895 logical
entries), every one logged `[1,18,7]  Recovered via rewrite in-place` —
RECOVERED ERROR, data retrieved via ECC and retries, then rewritten. **Zero
reassignments, zero failures, zero uncorrected errors array-wide.** These are
exactly the latent defects that destroy a 16-wide RAID 5 rebuild, caught during
routine scanning while every member was healthy and full parity was available.
The ~3.1% per-rebuild URE risk from §2 of `COORDINATION.md` is being actively
worked down, not merely assumed away.

**Read this column in physical sectors, not log entries.** These are 512e
drives — one 4096-byte physical sector reports as **eight** consecutive
512-byte logical entries. The distribution looked alarming at first:

| Member | Logical entries | Physical sectors |
|---|---|---|
| **6** | 671 | ~84 |
| 1 | 96 | 12 |
| 8, 9 | 40 each | 5 each |
| 15 | 24 | 3 |
| 7 | 16 | 2 |
| 5 | 8 | 1 |
| 0, 2–4, 10–14 | 0 | 0 |

Member 6 at seven times its nearest peer was investigated as a probable early
failure (`scripts/sudo/inspect_member6.sh`). **It is healthy.** All 671 entries
are rewrite-in-place; nothing was reassigned, so no spare sectors were consumed
and the grown defect list is not growing. The defects span power-on hours 121
to 10,127 — the drive's *entire* life at a steady ~1 physical sector every five
days — rather than clustering recently, which is what degradation looks like.
And 671/8 ≈ 84 matches that drive's own corrected-read-error counter of exactly
84, an independent confirmation of the unit factor. **No replacement needed.**

The instructive part is that the ranking is misleading in both directions.
Member 0 — zero BMS entries, the apparent control — carries **228** corrected
read errors and **3,929** correction-algorithm invocations, against member 6's
84 and 85. Member 0 works considerably harder to read its own data; it simply
never needed a rewrite. **Ranking drives by defect count alone selects the
wrong suspect.** What actually indicates a failing drive is a `reassign_status`
other than rewrite-in-place, defects concentrated in recent power-on hours, or
any non-zero uncorrected count. Member 6 has none of the three.

**Decision: do not add SMART long tests.** The `-s (S/../.././NN|L/../../6/NN)`
change contemplated in §12.4 is **rejected** — it would duplicate a daily
full-surface scan and add contention for no additional coverage. The smartd
config in §9 stands unchanged.

**What remains genuinely unknown:** whether PERC patrol read is enabled. BMS
says nothing about it either way. It no longer blocks anything, since both
defend the same failure mode and one of them is confirmed running.

### 13.3 A fourth inverted-value bug, in the tool built to find the third

Worth recording because of where it happened. The first run of
`patrol_check.sh` reported **0.00 TB read and ~1,025,339 uncorrected errors per
drive** — a fleet of unscanned, catastrophically failing disks. Both figures
were wrong, and they were the same two numbers with their columns transposed:

```
read:  0  228  228  228  3929  1025339.394  0
                               ^ $(NF-1)    ^ $(NF)
                               GB processed   uncorrected errors
```

The script read `$(NF)` as gigabytes and `$(NF-1)` as uncorrected errors.

Three things make this worth more than a one-line fix:

1. **The output was individually plausible.** A near-zero read total is what an
   unscanned array looks like. A huge error count is what a dying drive looks
   like. Nothing was obviously malformed — only the *magnitude* of the error
   count (a million errors on a drive still answering queries) gave it away.
2. **It reached the exactly-opposite conclusion.** Not a degraded or partial
   answer: a confident, precisely inverted one, on the specific question the
   tool existed to settle.
3. **This script was written to close out the third instance of this bug
   class** (the SIGPIPE/pipefail bug in §12.1), and its header comment warns
   about that bug — while committing a fresh variant of the same family
   fourteen lines below the warning.

The family: **a value taken from the wrong place, then trusted because it
looked reasonable.** SIGPIPE 141 read as failure; `lsof +D` exit 1 read as
"files open"; a trailing `[ cond ] && echo` read as the script's verdict; and
now `$(NF)` read as gigabytes. Knowing the pattern did not prevent it.

What did catch it: **going back to the raw tool output instead of iterating on
the parsed summary.** The fix is now pinned in the script by a comment carrying
the literal column header, so the next reader can check the field positions
without re-deriving them.

**A second misreading, same session, same shape.** With the parse fixed, the
recovered-sector column was read in the wrong *units* — raw 512-byte log
entries rather than 4K physical sectors — making member 6 look seven times
worse than its peers and very nearly justifying a proactive drive replacement
(§13.2). Not a code bug this time: the script reported exactly what it
measured. The error was in interpretation, and it produced the same outcome as
the parse bug — a confident conclusion, drawn from a real number, pointing the
wrong way.

What broke both: **going back to the raw per-drive output instead of iterating
on the summary.** Worth generalising, since it is now the operating lesson of
this whole section — *a derived number is only as good as the last time someone
checked it against the thing it was derived from.* Both fixes are pinned in the
script by comments carrying the literal evidence (the column header; the
671 ÷ 8 = 84 cross-check), so the next reader can verify without re-deriving.

`patrol_check.sh` was corrected to report scan count, recovered sectors in
physical units, and the sweeps ratio, and is now in the repo at
`scripts/patrol_check.sh`. Root-requiring run-scripts live in `scripts/sudo/`
(`verify_patrol_check.sh`, `inspect_member6.sh`), with their logs gitignored
and the scripts themselves committed as the record of what was run.

### 13.4 iDRAC is not reachable

```
sudo ipmitool lan print 1   ->  IP Address 0.0.0.0, IP Address Source: DHCP
                                MAC b0:7b:25:fe:2c:38
```

`/dev/ipmi0` exists and the drivers are loaded, so the BMC is alive — it simply
has no address. **There is no out-of-band management on this machine today:** no
remote console, no remote power cycle, no hardware event log access, no
controller configuration. If gps3 fails to boot, it needs someone physically in
front of it.

`sudo ipmitool delloem lan get` will report whether the BMC is on the dedicated
port or shares an onboard NIC, which determines what needs cabling.

**Before it is put on the network, change the password.** Dell ships iDRAC with
factory credentials `root`/`calvin`, and an iDRAC is a full remote console with
power control — reachable regardless of the OS state.

### 13.5 Branching policy adopted

Merged to `main` 2026-07-30 (PR #58) and now in `CLAUDE.md`: all substantive
work reaches `main` through a PR; branches live at most one week; `git pull
--rebase` before every push; never redirect a gated git/gh operation to
`/dev/null`; verify after every merge and retarget.

Rule 2's one-week limit came from `docs/bernese-training-notes` drifting 27 days
until neither it nor `main` held the whole project, taking a full session (PR
#57) to reconcile. The diagnosis worth keeping: the failure was not the branch,
it was the branch **outliving its purpose and quietly becoming a second trunk**.

Commits `6c7709c` and `23d4b29` predate the policy, went directly to `main`, and
still carry AI-attribution trailers the policy now forbids. Left alone
deliberately — rewriting `main` to tidy history is a worse act than the
inconsistency it would fix.

### 13.6 Archive: receiving side ready, still empty

`/srv/gnss-archive/legacy` is prepared and **verified empty (0 entries)** as of
2026-08-03. The ~157 GB legacy archive still exists in exactly one place: a
personal external drive with a pending sector. **This remains the single
largest data-loss risk in the project.** Blocked on the push from the T420's
DOSTB mount.

`/srv/gnss-archive/verify_archive.sh` is staged for afterwards, in two modes:

- **`census`** — counts files, symlinks, directories and bytes separately, to
  be compared against the same census on the source. Separate counts because
  this archive once lost every symlink to a FAT32 hop, silently: a file count
  alone would not have noticed, since the symlinks were still present as
  regular files.
- **`manifest`** — sha256 over the destination, written to
  `/srv/gnss-archive/manifests/` and gzipped for committing to git.

**Why a census and not `rsync --stats`:** rsync exits 0 having skipped files it
could not read, and exits 23 on a run that copied 99.99% successfully. Neither
number describes what actually landed. Hashing is destination-only on purpose —
the source is failing media being rescued, rsync already verifies each file in
flight, and the manifest's real job is detecting silent corruption on the array
years from now, which nothing currently defends against.

**Commit the manifest `.gz` to git.** Fingerprints stored only beside the data
cannot prove anything if that disk is what went wrong.

Note the third exit-status bug of the set was found here, in this script, by
running it against the empty destination before handover: a trailing
`[ "$other" -gt 0 ] && echo …` made a *clean* census exit 1.

### 13.7 Four unattended days, and the gh token

The 07-30 session ended with the laptop leaving the network. Nothing was in
flight. Verified on return 2026-08-03: mirror cron fired all four nights,
`smartd` still active, no alerts, uptime 11 days.

**Lesson recorded:** that session ran outside `tmux`, so disconnecting ended it.
Nothing was lost because nothing was running — but the archive transfer will be
hours of rsync from failing media, and must run inside `tmux` on both ends.
Start `tmux` *first*, then the work inside it; a running process cannot be
moved in afterwards.

`gh`'s stored token had gone invalid over the gap (`HTTP 401: Bad credentials`).
Git itself was unaffected — it uses SSH — so the failure surfaced only when a
PR wrapper was called. Re-authenticated via device flow. Note that `gh` stores
the new token **in plain text** in `~/.config/gh/hosts.yml`; that is normal `gh`
behaviour, not a misconfiguration, but it is a second static credential on this
box alongside `R740_PASS` in `scripts/deploy_r740.secrets` (still `gps3`, the
same as the username, on a LAN-reachable host with sudo — should be changed).

### 13.8 State at 2026-08-03

| Item | State |
|---|---|
| smartd | Active, 16 members, staggered short tests, alert path proven |
| Surface scanning | **Confirmed** — BMS, ~daily full pass, SWEEPS 1.01x on all 16 |
| Drive health | 0 uncorrected errors array-wide; ~112 sectors repaired in place, none reassigned; member 6 investigated and cleared |
| Git mirror | Nightly, 4/4 runs clean unattended, append-only by design |
| `/srv/gnss-archive/legacy` | **Empty** — transfer not started |
| iDRAC | No IP; no out-of-band management exists |
| PERC patrol read | Unknown; no longer blocking |
| Kernel | 6.8.0-136 installed, **6.8.0-111 running** — reboot pending |
| `~/GPSDATA.old-20260729` | 4.5 GB retained; this *is* the migration rollback |

Outstanding, in priority order: **deploy the `bernese-workflow` orchestrator**
(§14 — now the active work, under time pressure); **populate the archive**
(Tier 0) and manifest it; reboot deliberately with someone watching, which also
first exercises the new `fstab`; configure iDRAC networking with a changed
password.

---

## 14. Bernese orchestrator deployment — 2026-08-03

Working against §5 of `docs/project_documentation/bernese_orchestrator_r740_readiness.md`.

### 14.1 Where the deployment actually stands

**Step 1 (install + verify) is done** — `BERN54` present, EXAMPLE campaign
verified at 0.0000 mm on 07-29. Everything needed for the acceptance test is
already on the box, which was not obvious before checking:

| Asset | State |
|---|---|
| PAGENET RINEX | **677 files, DOY 081–090** in `$D/PGN` — wider than the 084–086 training week |
| `PGN.*` reference set | STA, CRD, ABB, CLU, BLQ, ATL, PLD, VEL — all in `REF54/` |
| Orchestrator P0 tasks A–E | All have code; **128 tests pass** |
| DATAPOOL migration (07-29) | **Verified complete** — 0 diff lines old vs new, 4.1 G both |
| `GPSDATA` volume | Own 4 TB LV, 4.5 G used — DL-012 disk pressure is **not** a near-term constraint |

**Correction (made later the same day, §14.5).** An earlier reading of this
recorded that `PLG2` — the station that hard-aborted DOY 086 on the T420 — was
"absent from this DATAPOOL entirely (0 files)". That was wrong, and wrong in an
instructive way: `ls | grep -i plg2` at the top level finds nothing because the
files are **hand-quarantined in a hidden subdirectory**,
`.excluded_plg2/plg20860.26o.gz` and `plg20880.26o.gz`. They came across in the
migration intact. PLG2 is still **missing from `PGN.STA`**, so the underlying
defect is unfixed; it is merely hidden behind a manual workaround applied
during the training week.

The reference files also disagree with each other — `PGN.STA` 74 records,
`PGN.CRD` 72, `PGN.ABB` 71, against 71–72 stations per session in the RINEX.
A `.STA` carrying more stations than any one day's data is normal and benign;
validation against all seven sessions now passes clean (§14.5).

### 14.2 maxjobs was 2 — the R740 was using 2 of its 12 cores

`USER.CPU` carried the **T420's** `maxjobs 2` across with the config. The 502
GPSCLU_P bottleneck (readiness §2.4, ~40 min of every ~2 h run) was therefore
being served by a box configured as if it were the laptop.

Corrected via the repo's own `cpu_config.compute_maxjobs()` rather than by hand,
so the change is the one the orchestrator will make in production:

```
physical cores=12  ram=62.0G  reserve=1  -> maxjobs=11
"localhost" "…" "FAST" "11" "0" "0"      (was "2")
```

Backup at `PAN/USER.CPU.bak-<timestamp>`.

**The readiness doc's core count was wrong by 2×** — it assumed 24 physical from
the gaps memory. `lscpu`: Xeon Silver 4214R, 1 socket, **12 physical**, 2
threads/core = 24 logical. Since maxjobs tracks physical cores (sub-solves are
FPU-bound and gain nothing from hyperthreads sharing an FPU), setting 24 would
have oversubscribed by 2× and plausibly run *slower* than a correct 12. Doc
corrected in place. Also settled: the CPU carries AVX-512 (Cascade Lake), so the
x86-64 ISA `objcopy` patch that section flagged as uncertain is **not needed**.

`V_CLUFIN` clustering (P2-K) is still untuned and remains the other half of the
502 fix.

### 14.3 The validator cannot see the real DATAPOOL — new P0 blocker

Pointing `validate_rinex_headers()` at the actual gps3 DATAPOOL:

```
ERROR No RINEX observation files found in /home/gps3/GPSDATA/DATAPOOL/PGN
      for session 2026/0860 — refusing to pass validation vacuously
```

`_is_rinex_obs()` matches on `path.suffix` against `.rnx`, `.obs`, `.rxo`,
`.<yy>o`. **Every file here is gzipped**, so the suffix is `.gz`. Decompressing
would not save it: PAGENET files are Hatanaka `.26d` and the IGS fiducials
`.crx`, neither of which is accepted. The real names are `PZAM0860.26d.gz`,
`pbay0860.26o.gz`, `CUSV00THA_R_20260860000_01D_30S_MO.crx.gz`.

**Why this is worse than an ordinary bug.** It surfaced loudly only because the
call passed `require_stations=True`. Under the **default** `require_stations=False`
the function returns a **passing** report — approving every session while having
examined nothing, with the first symptom being RXOBV3 hard-aborting mid-BPE.
That is the "vacuous pass" the docstring itself warns about, reached through a
door nobody anticipated.

And **the 128 tests pass**, because the fixtures use uncompressed `.YYo`/`.rnx`
names. The gap is invisible to the suite and appears only against real data —
which is readiness §6's thesis, demonstrated on the first contact with the
production DATAPOOL.

Filed as task **C2**. Fix: strip `.gz`/`.Z` before matching, accept `.<yy>d` and
`.crx`, decompress (or header-read) via `gzip` + `CRX2RNX`, and add fixtures in
the real naming scheme so the suite can catch this class.

This is also a fifth instance of the session's running theme — see §13.3. A
check that reports success without having inspected anything is the same defect
as an exit status that reports success without having run anything.

### 14.5 C2 fixed — the validator now sees the real DATAPOOL

**Result: all seven PAGENET sessions (DOY 084–090) validate clean**, from a
starting point of zero files visible. 179 tests pass, up from 128.

**The fix was much smaller than expected, because of one property of CRINEX.**
A Hatanaka file stores the original RINEX header **verbatim** after two
`CRINEX VERS`/`CRINEX PROG` lines; only the observation records *below*
`END OF HEADER` are compacted. Since this validator reads nothing past the
header, `crx2rnx` never has to run. No RNXCMP build, no `hatanaka` package, no
Hatanaka decoding anywhere in validation — **decompression alone is enough.**
(RNXCMP is still needed for actual processing; canonical source is GSI's RNXCMP
page, currently 4.1.0, plain C with no dependencies.)

**Compression had to handle two formats, not one.** IGS convention is `.Z`
(UNIX compress / LZW), not `.gz`. Python's `gzip` module cannot read it —
`BadGzipFile: Not a gzipped file (b'\x1f\x9d')`, LZW magic `1f 9d` against
gzip's `1f 8b`. On this box: 3,010 `.gz` against 20 `.Z`, including four real
Hatanaka-plus-LZW files at `GRCC/RINEX/GFCN0100.23D.Z`. Resolution: Python
`gzip` for `.gz` (keeping the 3,010-file path subprocess-free), GNU `gzip -dc`
for `.Z`. No new dependency.

Extension stripping loops right-to-left rather than using one regex, because
every real name stacks two extensions and both orders occur: `PZAM0860.26d.gz`,
`GFCN0100.23D.Z`, `CUSV..._MO.crx.gz`, `..._MO.rnx.gz`.

**Two further defects surfaced only once the validator could see data at all.**
Both would have blocked the acceptance test, and neither was visible before:

1. **Descriptive marker names shadowed the station code.** PAGENET CORS write
   `MARKER NAME = "BOGO CITY"` with the code in `MARKER NUMBER = "PBOG"`; IGS
   fiducials do the reverse (`MARKER NAME = "CUSV"`, `MARKER NUMBER` = a 9-char
   DOMES). Taking `MARKER NAME[:4]` yielded `BOGO`, absent from `PGN.STA`, so
   **9 of 72 real stations were reported missing on data that processes
   correctly**. Two naming conventions in one campaign — readiness §2.6 again.
   `_resolve_station_code()` now prefers a bare 4-char `MARKER NUMBER`, then a
   bare 4-char `MARKER NAME`, then the filename, and logs disagreements.
   *A validator that fails on good data gets switched off, which costs more
   than the check was ever worth.*

2. **`rglob` descended into the hidden quarantine directory.** It picked up
   `.excluded_plg2/`, reporting PLG2 missing from `PGN.STA` on exactly DOY 086
   and 088 — which, pleasingly, reproduces readiness §2.2's empirical finding
   ("present only DOY 086 + 088") from an entirely independent direction. But
   RNX_COP globs the source directory *without* recursing, so those files will
   never be staged. **The validator must model what will actually be
   processed**; flagging files that cannot reach the run is the mirror image of
   the vacuous pass, and just as effective at getting the check ignored.
   Dot-directories are now skipped, with the reasoning recorded in the code.

**PLG2 remains genuinely missing from `PGN.STA`.** The quarantine is a manual
workaround from the training week, not a fix, and task A is meant to replace it
with automatic per-session detection and quarantine. Skipping dot-directories
suppresses the *symptom* in validation; it does not resolve the defect.

Test coverage now spans the production filename space — the reason the previous
128 could not see any of this. Added: parametrised recognition across all real
encodings and their negative cases (nav/met/product files), round-trip reads for
plain/`.gz`/`.Z`, a from-scratch LZW encoder so `.Z` is testable with no
external compressor (nothing on stock Ubuntu can *write* `.Z`), an early-exit
test asserting that SIGPIPE from the cut-off `gzip` is not treated as failure,
and an integration test against the real gps3 DATAPOOL that skips off-host.

### 14.6 Provisioning `$U` — mechanism built, one asset still missing

§5 step 2 says "provision `$U` from repo gold-standard PCFs/panels/scripts".
**The gold standard did not exist.** Checking first was worth it:

- `$U/OPT`, `$U/PCF`, `$U/SCRIPT`, `$U/PAN` on gps3 are **byte-identical to the
  `$C/USER` template** shipped with Bernese 5.4 — zero files differing. Nothing
  PHIVOLCS-specific had ever been deployed here.
- The repo held only `scripts/pagenet_pcs.pl` and one Jinja template. P1-H's
  "gold-standard panels versioned in repo" was aspirational.

**Built the mechanism** (`config/bernese/gpsuser/` + `scripts/provision_gpsuser.py`),
because it is the thing readiness §4 actually requires: after a MIS reset, a
working environment must be recoverable by re-running provisioning rather than
by re-debugging panels by hand.

Three file classes, handled deliberately differently:

| Class | Treatment | Why |
|---|---|---|
| `OPT/**/*.INP` | Separator-sanitized; `ADDNEQ2.INP` MAXPAR sized from station count | Windows `\` are literal chars on Linux (gap #8, readiness §2.5) |
| `SCRIPT/*` | Copied **verbatim** | A backslash in Perl is an escape, not a path separator — converting corrupts the driver |
| `PCF/*.PCF` | Checked for dangling `WAIT`, refused if any | A WAIT on an undefined PID makes the BPE block **forever**, silently |

`PAN/USER.CPU` is **generated, never versioned.** `maxjobs` must track the
host's physical cores, so a committed copy would carry one machine's core count
onto another — which is precisely the bug found earlier today (§14.2). The
provisioner detects cores and RAM itself and independently arrived at
`maxjobs=11`, matching the hand-set value.

Dry-run by default; `--apply` to write. Strict: a panel with an unresolvable
hazard aborts the whole run *before* anything is written, so `$U` is never left
half-updated.

**Applied.** `pagenet_pcs.pl` is now at `$U/SCRIPT/`, byte-identical to the gold
copy, and a second run reports no changes.

**Still blocked: `PAGENET_DLY.PCF`.** It exists only on the T420, where it drove
the full training week. **It must be captured, not re-derived.** It is described
as RNX2SNX modules 1–14 (PID 001→514), but that is not a truncation anyone can
safely perform by eye: `599 DUMMY` waits on `512 514 522`, so dropping the
R2S_RED branch (521/522) leaves 599 waiting on a PID that never runs — the exact
dangling-WAIT hang the provisioner now refuses. The `9xx` save/cleanup tail
needs deliberate decisions too. A re-derived PCF would be a *different* PCF from
the validated one, and the acceptance test would then be exercising something
nobody has ever run.

To hand it over, from the T420:

```bash
cp "$U/PCF/PAGENET_DLY.PCF" <repo>/config/bernese/gpsuser/PCF/
cp -r "$U/OPT/PGN_WK"       <repo>/config/bernese/gpsuser/OPT/   # if present
```

Expect the provisioner to **reject `PGN_WK/ADDNEQ2.INP` on first attempt** —
readiness §2.5 records it carrying Windows separators, a dangling `WAIT=522`,
and hardcoded sessions (`20261030/40/50`, the instructor's demo week). That
rejection is the tool working, not a malfunction: remap the hardcoded literals,
then re-run.

### 14.7 Still to do for BRN-001

1. **Capture `PAGENET_DLY.PCF` from the T420** into
   `config/bernese/gpsuser/PCF/` — the only thing between here and an acceptance
   test.
2. **Add PLG2 to `PGN.STA`** (or implement task A's automatic quarantine) and
   retire `.excluded_plg2/`.
3. **Tune `V_CLUFIN`** (P2-K) — empirical, needs a real run to measure.
4. **Acceptance test**: one PAGENET session end-to-end on gps3, then the week.
   It must clear the station/MAXPAR/panel problems *automatically*, not by hand.
