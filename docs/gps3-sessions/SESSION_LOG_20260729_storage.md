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
