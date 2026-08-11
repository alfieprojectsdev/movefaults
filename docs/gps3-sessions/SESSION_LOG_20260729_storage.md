# gps3 Session Log — 2026-07-29 to 08-03

**Session:** `dell-gps` (Claude Code running on gps3, the Dell R740)
**Started as:** carve the unallocated PERC volume into LVs, migrate GPSDATA,
re-verify Bernese. **Grew into:** drive-health monitoring, an agency-side git
mirror, and the Bernese orchestrator's first contact with real data.

**Prior:** `~/HANDOVER.md` (updated 2026-07-29 by the T420 session)

## Where to start reading

This log is long because it is the succession record, not a changelog. If you
are new, read these three and skip the rest until you need it:

| If you want | Read |
|---|---|
| What state the machine is in now | **§15** — end-of-session state and the one open blocker |
| Why the RAID is considered safe | **§13.2** — surface scanning, settled by measurement |
| Why the orchestrator could not read real data | **§14.3–14.5** |
| The mistake this project keeps making | **§15.5** — five instances, one shape |

Sections are chronological and append-only. Where a later finding overturns an
earlier one, the earlier section carries a correction pointing forward rather
than being rewritten — the wrong turns are part of the record.

**Outcome (2026-08-03):** storage in service with BPE numerical parity
preserved; all 16 RAID members monitored and confirmed surface-scanned; git
mirrored onto agency hardware; the Bernese orchestrator validating all seven
PAGENET sessions against the real DATAPOOL. Outstanding: the legacy archive is
still single-copy on failing media, and `PAGENET_DLY.PCF` is still only on the
T420.

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

## 10. State at end of session — 2026-07-29

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

### 13.8 Infrastructure state

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

The Bernese work that followed on the same day is §14; the consolidated
end-of-session state and handover is §15.

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

**Correction (made later the same day, §14.4).** An earlier reading of this
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
validation against all seven sessions now passes clean (§14.4).

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

### 14.4 C2 fixed — the validator now sees the real DATAPOOL

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

### 14.5 Provisioning `$U` — mechanism built, one asset still missing

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
as RNX2SNX modules 1–14 (PID 001→514). In stock `RNX2SNX.PCF`, `599 DUMMY` waits
on `512 514 522`, so naively dropping the R2S_RED branch (521/522) would leave
599 waiting on a PID that never runs.

> **Corrected 2026-08-04, having now seen the real file (PR #65).** That was a
> prediction about what a careless truncation *would* do, and the actual
> `PAGENET_DLY.PCF` does not have the problem: its `599 DUMMY` waits on
> `512 514`, and 521/522 are simply absent. `find_dangling_waits()` reports
> **zero**. Whoever produced it performed the reduction properly rather than
> cutting the file short.
>
> The advice to capture rather than re-derive still stands, but the honest
> reason is weaker than the one originally given: not "a truncation leaves a
> dangling WAIT" — this one demonstrably does not — but that the captured file
> is the one actually validated during the training week, and the `9xx`
> save/cleanup tail involves choices a reconstruction would have to guess at.
> A stated hazard that turns out not to apply is worth less than it appears,
> and worth correcting at the point it was claimed.

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

### 14.6 Still to do for BRN-001

1. **Capture `PAGENET_DLY.PCF` from the T420** into
   `config/bernese/gpsuser/PCF/` — the only thing between here and an acceptance
   test.
2. **Add PLG2 to `PGN.STA`** (or implement task A's automatic quarantine) and
   retire `.excluded_plg2/`.
3. **Tune `V_CLUFIN`** (P2-K) — empirical, needs a real run to measure.
4. **Acceptance test**: one PAGENET session end-to-end on gps3, then the week.
   It must clear the station/MAXPAR/panel problems *automatically*, not by hand.

---

## 15. End of session — 2026-08-03

### 15.1 What changed on the machine

Everything below is applied and verified, not merely written down:

| Change | Verification |
|---|---|
| `USER.CPU` maxjobs **2 → 11** | Set via `cpu_config.compute_maxjobs()`; backup at `PAN/USER.CPU.bak-*` |
| `pagenet_pcs.pl` deployed to `$U/SCRIPT/` | `cmp` byte-identical to gold copy; re-run reports no change |
| `patrol_check.sh` corrected, moved into repo | Re-run: SWEEPS 1.01x, UNCORR 0 on all 16 |
| `scripts/sudo/` convention established | Two scripts used in anger this session |
| `.gitignore` — `scripts/sudo/logs/` | Logs excluded, scripts committed |

**Nothing was changed on the array, the mirror, or the archive.** The storage
side was read-only this session.

### 15.2 Questions that were open this morning and are now closed

- **Does anything scan the RAID surface?** Yes — BMS, ~daily, all 16 members,
  confirmed by two independent counters. Long self-tests explicitly rejected.
  (§13.2)
- **Is member 6 failing?** No. The 671 figure was 512-byte logical entries;
  ~84 physical sectors, flat rate across the drive's whole life, nothing
  reassigned. (§13.2)
- **Did the 07-29 GPSDATA migration lose anything?** No — 0 diff lines between
  old and new DATAPOOL. (§14.1)
- **How many cores does the R740 actually have?** 12 physical / 24 logical. The
  readiness doc's 24 was the logical count. (§14.2)
- **Is the objcopy ISA patch needed?** No — AVX-512 present. (§14.2)
- **Can the orchestrator read real GNSS data?** It could not; now it can.
  All seven PAGENET sessions validate clean. (§14.4)
- **Does a repo gold standard for `$U` exist?** It did not; it does now. (§14.5)

### 15.3 The one thing blocking progress

**`PAGENET_DLY.PCF` exists only on the T420.** Until it is committed to
`config/bernese/gpsuser/PCF/`, no acceptance test can run on gps3 — the
orchestrator is otherwise ready, `$U` is provisioned, `maxjobs` is correct and
the validator works against real data. Two `cp` commands on the other machine
close it (§14.5).

Do **not** re-derive it. §14.5 explains why, and the provisioner will now refuse
a truncation that leaves a dangling WAIT.

### 15.4 Delivered

> **Correction 2026-08-04.** The sentence below originally read "All work
> reached `main`". It had not, and still has not. Everything is on the branch in
> an **open** PR; at the time of writing `origin/main` was at `1d1082e`
> (PR #60). **It merged later the same day** — see below. Rule 5 exists
> for exactly this — *verify `origin/main` actually advanced*, do not infer it
> from having pushed successfully. Caught by the T420 session, not by me, in a
> section I wrote to be the authoritative end-of-session state.

All work reached `main` via [PR #64](https://github.com/alfieprojectsdev/movefaults/pull/64),
**merged 2026-08-04 as `9623395`** — verified by confirming `origin/main` advanced
and that each commit is an ancestor of it, not by the merge command's exit status,
which returned 0 while printing nothing at all. Branch retired after merge.
branch `docs/gps3-session-20260803`, three commits:

| Commit | Contents |
|---|---|
| `a82be79` | §13, tmux runbook, `patrol_check.sh`, `scripts/sudo/` |
| `ad2401c` | C2 — validator blind to real DATAPOOL; +51 tests |
| `3f51cd7` | `$U` gold standard and provisioner; +10 tests |

Test count 128 → 189, `ruff check` clean on everything touched.

Also written this session: `docs/gps3_tmux_claude_runbook.md`, a from-scratch
tmux guide for gps3 aimed at someone who has never used it — including the rule
that costs the most when broken (**start tmux first; a running process cannot be
moved into it afterwards**) and the fact that a reboot destroys every session
while cron and smartd carry on regardless.

Three T420 PRs (#61, #62, #63) were open and unmerged at session end. They are
the other machine's to land.

### 15.5 The running theme, for whoever reads this next

This session found the same defect shape five times, and it is worth naming
because it will recur:

> **A check that reports success without having inspected anything.**

- `smartd`'s `DEVICESCAN` — a green service monitoring **zero** drives (§9)
- `slow_cmd | grep -q` under `pipefail` — success inverted to 141 by SIGPIPE (§12.1)
- `patrol_check.sh` — columns transposed, reporting an unscanned, dying array
  that was neither (§13.3)
- The same script read in the wrong **units**, nearly condemning a healthy drive (§13.3)
- `validate_rinex_headers()` — a **passing** report having read no files at all (§14.3)

In every case the output was individually plausible, and in four of the five a
passing test suite or a zero exit status actively concealed it. What broke each
one was the same move: **go back to the raw output of the underlying tool
instead of iterating on the summary.** The `smartctl` column header, the
measured exit codes, `671 ÷ 8 = 84`, the actual DATAPOOL filenames.

The corollary for the test suite is sharper still. The 128 tests passed
throughout because their fixtures described a filename space that does not
exist in production. **A suite that never sees real data cannot fail on a
misreading of real data**, no matter how many assertions it contains.

---

## 16. The archive transfers — 2026-08-04

The DOSTB20150918 drive was carried from the T420 and attached to the R740's
USB bus, which removed the 6 MB/s wifi bottleneck that had kept
`/srv/gnss-archive/legacy` empty since §13.6. Both in-scope paths were copied
and verified the same day.

### 16.1 What landed

| Set | Files | Bytes | Result |
|---|---|---|---|
| `RECOVERED_*` (4 directories) | 162,328 | 155.71 GiB | **MATCH** |
| `processing_files/` | 67,553 | 21.55 GiB | **MATCH** |
| └ `GPSDATA/CAMPAIGN/LUZON/SOL/` | 1,944 | 0.39 GiB | **MATCH** |
| **Total** | **229,881** | **177.26 GiB** | |

Files, symlinks, directories and bytes were counted independently on both sides
for every directory. Zero symlinks throughout — the source is NTFS, and that is
a property of the source rather than a transfer fault. All rsync invocations
exited 0, but the censuses are what decided the outcome; rsync exits 0 having
skipped unreadable files and 23 on a run that copied 99.99%.

**The legacy archive now exists in two places on independent hardware.** That
was the project's Tier 0 item and it is closed.

### 16.2 The handover's directory table was missing 131 GB

`README_FOR_GPS3_CLAUDE.md` listed **three** `RECOVERED_*` directories totalling
26 GB and stated this was "not the ~157 GB the continuity audit refers to". The
user identified a fourth, `RECOVERED_SEAGATE_W2A0W9T2_DATA0`. Measured on
mounting: **131 G**, bringing the total to exactly the 157 G the audit records,
and holding 139,509 of the 162,328 files — **86% of the archive**.

The omission happened because three directory names were written out by hand.
Both transfer scripts glob `RECOVERED_*` and report what they find, so a fifth
directory would be copied rather than silently skipped. The measured 162,328
files also corroborates the audit's independent "~155k files" figure.

*A typed list cannot notice what it omits.*

### 16.3 The LUZON solution series is older than its documentation implied

§3 of the handover describes `GPSDATA/CAMPAIGN/LUZON/SOL/` as "the comparison
target — `F1_*` dailies, `WK_2413`/`WK_2414`", naming two recent weeks. Measured:

- **725 weekly** combines, GPS weeks **1573 → 2414** = **2010-02-28 to 2026-04-12**
- **166 monthly** combines
- **421 MB** total

Sixteen years of results in 0.39 GiB, against **one month** of raw input
(DOY 121–151 of 2025, 25 stations). **The SOL series cannot be regenerated from
this tree** — the observations for fifteen of those sixteen years are on staff
machines and remain uncaptured. `processed_transfer.sh` therefore copies that
subtree first and alone, so an interrupted run still secures it.

Rough sizing for the uncaptured remainder: 22 GB bought one month of full
campaign data, so ~192 months ≈ **4 TB**. `/srv/gnss-archive` has 20 T with
177 GiB used, so capacity is not the constraint — logistics and provenance are.

### 16.4 Still not "backed up"

Both scripts refuse to print that phrase, and the reason stands: **there is no
fixity.** No checksum manifest exists for either copy, so silent corruption on
the array is undetectable. Continuity-audit item 4, and cheap now that the data
is local:

```bash
/srv/gnss-archive/verify_archive.sh manifest
```

It reads every byte of 177 GiB. The resulting `.gz` belongs in git — fingerprints
stored only beside the data cannot prove anything if that disk is what failed.

### 16.5 A defect in the first script, found by using it

`archive_transfer.sh` wrapped everything in `{ … } | tee`, including rsync's
`--info=progress2` output, which emits a carriage-return update per file. The
157 GB run produced an **11.2 MB log** with the structured results buried in
progress spam. `processed_transfer.sh` sends progress to the terminal and
structured lines to the log; `archive_transfer.sh` should be brought into line
before its next use.

Separately, shellcheck on `archive_transfer.sh` before that run caught the bug
that would have mattered: `rc_worst` was assigned inside the `| tee` subshell,
so `exit "${rc_worst:-0}"` read an unset variable and returned 0 for every run —
including one that had just printed `*** MISMATCH ***`. Seventh instance of the
pattern in §15.5, in the script written because rsync's exit code cannot be
trusted.

---

## 17. Two-machine corrections and the first 5.4 run attempts — 2026-08-05

### 17.1 The T420 exchange, and two datasets that were never missing

Three relay documents arrived (`T420_REPLY_20260804.md`,
`T420_REPLY_20260805.md`, `T420_NOTE_20260805c.md`, all committed). Two of them
overturned conclusions this machine had reached, both verified here before being
accepted.

**The LUZON reference solutions exist.** §14 recorded that no daily solutions
covered the raw RINEX window (2025 DOY 121–151), concluding the comparison could
not be run against that data. Wrong: `SAVEDISK/2025/SOL/` holds **all 365 daily
finals for 2025**, gzipped — 730 files, 31 of 31 days in the window.
`CAMPAIGN/LUZON/SOL/` looked empty of them because `PHIVOL_REL.PCF` archives via
`902 R2S_SAV` then cleans the campaign with `903 R2S_DEL`. A campaign holding
only recent days is normal operation.

**The seven "missing" fiducials exist.** Having found the solutions, this machine
then reported that AIRA, ALIC, BASC, DAEJ, DARW, MCIL and PNGM had no local
RINEX, and advised requesting BASC from PHIVOLCS as "a Philippine station absent
from every archive". Wrong again: all nine are in `GPSDATA/DATAPOOL/RINEX3/` as
RINEX 3 long-name Hatanaka. `DATAPOOL/` has **fourteen** subdirectories and both
sessions had searched only `LUZON/`.

The decisive check, once framed correctly, took one command:

```
she used, we lack:        (none)
we have, she did not use: PIMO TGDN
```

**Both errors are the same shape**, and it is now the week's dominant one:
*searching with one convention and reading zero results as absence.* Five
instances by §1.5's count, seven by the end of the day. The remedy never varied:
look at actual filenames before writing the pattern.

The T420's framing of the first is worth keeping: the question that
short-circuits it is not *"what is in this directory?"* but ***"where does this
software put finished solutions?"*** — answerable from `PHIVOL_REL.PCF`, which
both sessions had already read while checking something else.

### 17.2 A commit was nearly lost to a merge race

`6399c9a` (T420) was authored 08-05 08:10 on the **pre-correction** PR #65 head,
after that PR had merged the previous evening and its branch was deleted. The
T420 recreated the branch and pushed there, leaving two divergent corrections to
one file: `main` had the hazard-count fix without the overlap fix, the recreated
branch had the reverse.

Recovered by cherry-pick; they merge cleanly and both are present. Authorship
preserved, AI co-author trailer dropped per `CLAUDE.md`.

**Per Alfie's decision, `config/bernese/gpsuser52-luzon/PROVENANCE.md` is now
single-writer on the gps3 side.** Two writers on one file cost more than the
corrections were worth.

### 17.3 PRs #64 and #65 merged

`main` moved `1d1082e` → `9623395` → `19c68cf`. Both verified at the git level
rather than from the wrapper's exit status: `scripts/merge_pr.sh` returned **0
while printing nothing at all** on both merges, and `gh pr view --json` came back
empty on the same PR immediately after. Confirmed instead with
`git merge-base --is-ancestor` per commit. Branches deleted after verifying
content, not after assuming redundancy.

### 17.4 Bernese 5.4: five run attempts, one file short

Full detail in `docs/bernese54_luzon_reprocessing_runbook.md` §4b. Summary:

| Attempt | Failure |
|---|---|
| 1 | `BPE_CAMPAIGN="LUZON"` — bare names resolve **relative to CWD** |
| 2 | `"${P}/LUZON"` in double quotes — Perl interpolated a variable that does not exist |
| 3 | Four broken WAIT lists — `001` still waiting on the dropped `000` |
| 4 | **Segmentation fault** — the 5.2 PCF format is unreadable by 5.4 |
| 5 | Reached **PID 001**; one mandatory bias file missing |

**The premise was wrong, not the details.** The PCF *file format* changed between
5.2 and 5.4 — fixed-column with a ruler line versus free-form `KEY=VALUE;` — and
5.4 responds to a 5.2 PCF with a segfault rather than a parse error, so four
attempts went by before the incompatibility surfaced. Script renames and WAIT
repairs cannot bridge a format change. `scripts/derive_luzon_pcf.py` now starts
from 5.4's own `RNX2SNX.PCF` and refuses to write any process row lacking `CPU=`.

**§14's `FTP_DWLD` conclusion was also wrong.** It said every product was local
so the download step could be dropped. The products are local **in 5.2-era legacy
naming**; 5.4 reads long-name. Present and unusable simultaneously — presence had
been verified, usability had not.

**Where it stands:** attempt 5 copied the station files, confirmed
`ANTENNA_I14.PCV` in use, and copied orbit and ERP into the campaign before
stopping on `IAR23644.OSB`. `R2S_COP` generates that from a bias SINEX, and the
input `IGS0OPSFIN_2025121*_OSB.BIA` is not at BKG — whose IGS final set carries
only CLK, SP3, ERP and SUM. AIUB is unreachable from this machine; CDDIS holds
them behind an Earthdata login. Her 5.2 run used **DCB**, so the OSB requirement
is a 5.4-ism, not inherited.

One credential or one file unblocks it. Everything else is staged and verified.

### 17.5 Three tool defects, found by using the tools

| Defect | Consequence |
|---|---|
| `find_dangling_waits()` knew only the `WAIT=` dialect | On a 5.2 PCF it parsed **zero** PIDs and zero WAITs, reported "0 dangling", and signed off a file with four broken WAIT lists |
| `REWAIT` regex captured 4 fields where the row has 3 | Old dependency survived; replacement appended after it |
| `BPE_CAMPAIGN` as a bare name | `startBPE` tests it with `-d` relative to CWD — the stock Bernese drivers are silently directory-dependent |

The first is the eighth instance of §15.5's pattern, in the function written to
prevent it. All three fixed; **198 tests pass**, up from 128 at the week's start.

Two smaller ones worth the same note: a `find` piped through `head -8` reported
zero orbit products where there were 76, and `LOADGPS.setvar` exports its own
`$SRC`, which silently clobbered the staging script's source path and made every
file report as missing.

### 17.6 State at end of 2026-08-05

| Item | State |
|---|---|
| Legacy archive | **Two copies** — 177.26 GiB, censused, matched |
| Fixity | **Still none.** No sha256 manifest on either copy |
| DOSTB drive | Still mounted read-only; unmount before unplugging |
| `main` | `19c68cf`; PRs #61–#63 still open (T420's) |
| LUZON campaign | Staged, registered, PCF derived, driver fixed |
| First 5.4 run | **Blocked on one OSB bias product** |

---

## 18. First Bernese 5.4 run attempts — 2026-08-05 evening

Nine attempts at DOY 121 of 2025. No solution yet, but the failures were
informative and three of them were defects in this project's own tooling. Full
detail in `docs/bernese54_luzon_reprocessing_runbook.md` §4b.

### 18.1 How far it gets

RINEX import, orbit preparation and observation conversion all succeed — **92
observation files in about 100 seconds** — before stopping at PID 232 `CODSPP`.

### 18.2 The premise was wrong, not the details

The plan was to adapt her 5.2 `PHIVOL_REL.PCF` by renaming scripts and repairing
WAIT lists. **The PCF file format changed between 5.2 and 5.4** — fixed-column
with a ruler line versus free-form `KEY=VALUE;` — and 5.4 answers a 5.2 PCF with
a **segmentation fault**, not a parse error. Four attempts passed before that
surfaced. `scripts/derive_luzon_pcf.py` now derives from 5.4's own
`RNX2SNX.PCF` and refuses to write a file whose process rows lack `CPU=`.

### 18.3 Products: present and unusable

§14 concluded `FTP_DWLD` could be dropped because every product was local. They
are local **in 5.2-era legacy naming** (`igs22364.sp3.Z`); 5.4 reads long-name.
Presence had been verified, usability had not.

Two further gaps, both fetched from AIUB: the **CODE satellite-bias product**,
without which `R2S_COP` cannot generate the `IAR_*.OSB` it treats as mandatory,
and **`SAT_2025.CRX`** — the installed set stopped at 2019, so any 2025
processing would have hit it. This is readiness **gap #6** arriving as predicted.

**A correction worth recording:** these were reported here as needing
credentials. They do not. `ftp.aiub.unibe.ch` is firewalled from gps3 and times
out; `www.aiub.unibe.ch` redirects to a SWITCH S3 bucket that serves everything
anonymously. A timeout was taken as proof of inaccessibility rather than as a
reason to look for another route. The user's own research corrected it.

### 18.4 `V_SATSYS` — the most instructive error

The override set copied `V_GNSSAR = ALL` from her PCF, reasoning that she
resolved ambiguities across all constellations. **That reads the variable
backwards.** `V_GNSSAR` selects which of the *already-selected* systems get
ambiguity resolution; **`V_SATSYS` selects the systems**, and hers reads `GPS`
where 5.4 ships `GRE`.

The run therefore attempted GLONASS and died on **GLONASS-M 861** — launched
after I14's epoch and absent from every I14 table. **It presented as a missing
file and was a constellation-selection error.** Had it been "fixed" by switching
to I20, the comparison would have silently acquired the I14/I20 confound the
whole exercise exists to isolate, and the numbers would have looked plausible.

Processing GPS-only is not a workaround. It is what she did, and it is why I14
is usable against 2025 data at all.

### 18.5 The blocker is model retirement, not configuration

Her retained log (`R2S251210.PRC`, 56,781 lines) settles it: **26,172 warnings
and 3 errors — and it produced `F1_251210.SNX` regardless.** `###` is a warning
in Bernese and `***` an error; she had all three errors and the run finished. The
version difference is one of **tolerance**, not capability.

Two independent blockers follow:

- **Satellite tables end in 2023.** Hers 2023-01-31, 5.4's I14 2023-08-10, I20
  2024-09-17. **AIUB no longer publishes `SATELLIT_I14.SAT`** (404 for I14, 200
  for I20). CODSPP stops on `BLOCK IIR-A 044` — a satellite that *is* in the
  antenna file; what fails is PRN→SVN resolution against a stale table.
- **The I14 ANTEX fails 5.4's consistency check.** `*** ATX2PCV: Given SVN and
  PRN inconsistent … PRN 22, SVN G041`. All three variants in her tree fail. A
  file 5.2 consumed without complaint is invalid to 5.4.

**Reproducing her I14 numbers on 5.4 is therefore not a configuration problem.**
The recommendation is to run I20 first, explicitly as a *pipeline test* rather
than a comparison — that is BRN-001 acceptance evidence in its own right — and
to put the I14 finding to Abegail, since it bears on how the LUZON series can be
continued at all.

### 18.6 Three tooling defects, found by use

| Defect | Consequence |
|---|---|
| `find_dangling_waits()` knew only the `WAIT=` dialect | On a 5.2 PCF it parsed **zero** PIDs and zero WAITs, reported "0 dangling", and signed off a file with four broken WAIT lists |
| `REWAIT` regex captured 4 fields where the row has 3 | Old dependency survived, replacement appended after it |
| `BPE_CAMPAIGN` as a bare name | `startBPE` tests it with `-d` **relative to CWD** — the stock Bernese drivers are silently directory-dependent |

The first is the eighth instance of §15.5's pattern, in the function written to
prevent it. All fixed; **198 tests pass**.

Three Bernese environment variables also collided with script variables this
session — `$SRC`, `$S` and `$P` are all exported by `LOADGPS.setvar`, and two of
them silently clobbered locals, making every source file report as missing.
**Do not use bare short names in scripts that source LOADGPS.**

### 18.7 A process note

One commit (`c4bc867`) was pushed **directly to `main`**, breaking Rule 1. After
the PR #66 merge the branch had been deleted and work continued on `main`
without creating a new one. The commit is sound; the route was not.

---

## 19. Ocean loading closed, the month launched — 2026-08-06

### 19.1 What ran

Ocean-loading coefficients for the nine fiducials arrived from the
Chalmers/Onsala service and were merged into `LUZON.BLQ`. **DOY 121 then
completed cleanly** — `Sessions finished: OK: 1 Error: 0`, 5m36s, 30 stations in
`FIN_20251210.SNX`, the same count Abegail's run produced, with `HELMCHK` and
`COMPARF` both passing. `scripts/run_luzon_month.sh` was launched over DOY
121–151 at 14:40 and is running at roughly 5m30s per day.

The run is under **I20** and is a pipeline test, not a comparison. §18.5 stands:
I14 cannot run on 5.4 at this epoch.

### 19.2 The BLQ merge took four attempts, each a different wrong assumption

`scripts/merge_blq.py` was written once and corrected four times, and the
corrections are more instructive than the script:

1. The station-name parser matched the **documented** single-token form and
   found **zero** stations in a file holding 135. The service does not emit what
   its documentation shows.
2. Rewritten to require two equal tokens — which held for all 135 local stations
   and rejected **every fiducial**, because IGS sites carry a DOMES number in
   that column instead of a repeated name. A rule generalised from the only
   examples available.
3. New blocks were appended at end-of-file, i.e. **after `$$ END TABLE`**, where
   Bernese never reads them. The file looked correct, the station was plainly
   there on inspection, and `GTOCNL` still reported the coefficients missing.
4. Padding to position the key line was inserted **after** it rather than before,
   so `GTOCNL`'s `FORMAT(//,2X,A10)` — where `//` skips *two* records — landed on
   a blank comment.

Every one of these produced a file that looked right. Three of them produced a
file that was silently wrong at read time rather than loudly wrong at parse time.

### 19.3 The month driver scored thirty days OK without running anything

Two defects in `run_luzon_month.sh`, **both found by dry-running the loop with
the BPE call stubbed out**, neither by reading it.

`LOADGPS.setvar` exports `PCF`, and the script set `PCF=LUZON_DLY` *above* the
source, so the source clobbered it. The first launch died looking for
`$U/PCF/$U/PCF.PCF`. That is the **fourth** such collision after `$SRC`, `$S` and
`$P` (§18.6), so the fix is now the naming rule and not another rename: config
names carry a `LUZON_` prefix and an assertion across the source fails loudly if
a future one is added without it.

The serious one: `LUZON_DLY.OUT` is rewritten in place each run, and the success
test grepped it **without checking whose run wrote it**. A day whose BPE never
started would be scored against the previous day's summary and counted OK. The
stubbed dry run reported **all thirty days OK from the single file DOY 121 left
behind** — a full month of green with nothing executed. The summary must now be
at least as new as the day's start; with the guard the same dry run reports 30
FAILED, 1 EXCLUDED.

This is the same defect the session has produced repeatedly and now for the
ninth time: **a check that reports success without having inspected anything.**
It would have been invisible in production — thirty OK lines and an empty `SOL/`
nobody opened until much later.

Worth noting separately: `shellcheck` passed clean on a version of this script
that referenced three unset variables under `set -u`. A grep caught them.

### 19.4 Two findings for Abegail, both about limits rather than bugs

**The series cannot be continued under its original model.** I14's satellite
tables end in 2023, AIUB no longer publishes `SATELLIT_I14.SAT`, and the I14
ANTEX fails 5.4's SVN/PRN consistency check (§18.5).

**The series cannot be rebuilt from what we hold.** §7 of the runbook asserted
that only DOY 121–151 of 2025 has raw observations; that claim came from the
transfer handover and had never been checked. It is now verified by census
across both the array and the live tree — exactly those 31 days, nothing else,
against **365 solved days in 2025 alone**. The reproducible fraction is 8.5% of
that year and well under 1% of the sixteen-year series.

The boundary falls there because her `DATAPOOL/LUZON` is a **rolling staging
area** holding about a month; the transfer captured a snapshot of it. The missing
observations were therefore probably never on the DOSTB drive, so re-transferring
will not recover them. Locating raw RINEX on staff machines is the only path, and
it is a much larger piece of work than this run.

Within the window, **DOY 139 holds one RINEX2 station where its neighbours hold
25**, though she solved it — so our copy of that day is short and the
reproducible month is 30 days, not 31. It is excluded from the run rather than
processed into a fiducials-only solution that would sit in `SOL/` looking
legitimate.

### 19.5 State at end of 2026-08-06

- Commits on `docs/luzon-i14-investigation` (PR #67): `f42a69d`, `69a16b4`,
  `35fbc56`, `4b2a133`, `b6dfffa` — all pushed and verified on `origin`.
- Results land in `${S}/LUZON/$Y+0`, moved off the stock `${S}/RNX2SNX/$Y+0`
  which every RNX2SNX-derived campaign shares.
- **Still open:** DOSTB unmount before unplugging
  (`sudo scripts/sudo/mount_dostb.sh --umount`); no sha256 fixity on either
  archive copy; T420 PRs #61–#63 now past the Rule 2 one-week limit; the leaked
  `sk-ant-oat01-` token still needs revoking by a human at claude.ai; reboot
  pending for kernel 6.8.0-136; iDRAC networking unconfigured.

### 19.6 The month completed — 30 days, zero failures

Finished 17:28, **2h47m** wall, **OK 30, FAILED 0, EXCLUDED 1**. Verified against
the filesystem rather than the summary: 30 `FIN_*.SNX.gz` and 30 `.NQ0.gz`, every
one readable under `gzip -t`, every one carrying ≥25 stations, no day missing
from the 121–151 range bar the excluded 139.

**Repeatability over the full month: median N 2.8 mm, E 3.0 mm, U 10.9 mm.**
Horizontal held steady as the series grew from ten days to thirty (2.9/3.4 mm at
ten), which is what a stable configuration looks like.

The result that carries weight is the *shape* of the bad days. Scanning all 30
for stations more than 30 mm from their own mean: **25 days are completely
clean**, five have **exactly one** bad station, and only **two stations** are
ever involved. A bad configuration degrades every station on every day; bad
stations degrade themselves. Nothing here points at the PCF.

**TGDN** is fully explained: its sessions run 112 to 1119 epochs against a 2880
full day, and its two worst days are its two shortest. The "43%" recorded earlier
came from a single day and understated the variability considerably.

**LGYE is not explained and is the open item.** Full 2880 epochs on every one of
its bad days, yet a **200 mm** excursion on DOY 137. Session length is ruled out.
It is recorded as open rather than attributed to a guess — the same discipline
applied to S01R in §4b.9.

### 19.7 Capacity, measured rather than assumed

Asked what a full year would cost. Measured during the run rather than
extrapolated from the per-day figure:

- 333 s/day at 30 stations, consuming **3.94 of 24 cores** — 16% of the machine.
- A year at this configuration: **~34 h serial**, or **~7 h** at five concurrent
  days. Storage is ~1.5 GB/year, so the whole sixteen-year series is ~23 GB.
- Parallelism needs **one campaign directory per worker**; `$P/LUZON` holds the
  working files for whichever day is in flight, which is why the driver takes a
  single-instance lock.
- Scaling to the ~135-station national network is **estimated** at 4–8× per day
  and must be measured, not modelled.
- **Correction, 2026-08-11.** This section originally read `MAXPAR` as a hard
  ceiling near 330 stations. Wrong: `ADDNEQ2.HLP` states plainly that `MAXPAR`
  "allocate[s] memory for the combined NEQ system. Specifying a number greater
  than necessary does not harm if the computer has enough memory," and the
  program's own default is **3000**, not the 1000 the R2S_FIN panel configures.
  It is a runtime allocation, not a compiled-in limit, and raising it on a
  62 GB machine costs nothing. The real question for scaling to a national
  network is whether troposphere is estimated per-station (as it should be
  across climate zones, unlike the near-uniform 100 km Luzon network where
  `TROPEST 0` pre-elimination was a reasonable simplification) — that decision
  drives the combined-NEQ dimension, not an arbitrary station-count ceiling.

**None of this is the binding constraint.** We hold 31 days of observations. The
compute budget for the full series is weeks, entirely tractable, and irrelevant
until the data exists.

---

## 20. PR #67 lands, S01R resolved, and a reading plan for national scale — 2026-08-11

### 20.1 Housekeeping: DOSTB unmounted, PR #67 merged properly

`scripts/sudo/mount_dostb.sh --umount` already existed and was already correct
(refuses if `lsof` finds open files, syncs before unmounting) — handed the
absolute path to the user's own terminal rather than running it, per the
standing sudo-via-script convention.

PR #67 (the whole LUZON I20 reprocessing arc — 17 commits) was merged via
`scripts/merge_pr.sh`, fast-forwarded onto `main`, and verified against
`origin/main` directly rather than trusting the exit code. Branch deleted on
GitHub, confirmed with a 404 on the branch API rather than assumed.

### 20.2 Coordinate repeatability and network coherence: checking the numbers, not just the exit code

Two scripts were added and used against the 30-day I20 run before this
session, prompted by the observation that "`Sessions finished: OK`" verifies
the pipeline ran, not that the output is any good:

- `scripts/coord_repeatability.py` — day-to-day scatter of each station about
  its own mean. Full-month result: median N 2.8 mm, E 3.0 mm, U 10.9 mm,
  horizontal holding steady as the series grew from 10 to 30 days. First real
  evidence the derived PCF is sound, not just executable. Explicit in the
  docstring: this is PRECISION, not accuracy — a wrong reference frame would
  look identical.
- `scripts/network_coherence_scan.py` — added specifically because a
  single-station outlier threshold is the wrong test for this project's actual
  purpose (earthquake detection is several NEARBY stations moving TOGETHER,
  often below any single-station threshold). It found what the single-station
  scan missed: **DOY 126 moved 14 stations 8–30 mm together** across the whole
  southern-to-central Luzon cluster, invisible to the earlier check because no
  one station individually cleared 30 mm by much. DOY 129 and 145 showed
  smaller versions of the same pattern.

**Told apart from a real earthquake by reading the day-by-day series, not by
running a script.** A coseismic offset is a permanent step; DOY 125 was quiet,
126 spiked network-wide, 127 reverted completely — a spike, not a step.
Corroborated against the actual PHIVOLCS/USGS catalog: no earthquake recorded
on any of the three flagged dates. A confirmed M4.6 near Quezon on DOY 147
produced no anomaly at the nearest stations — a useful negative control, since
M4.6 at tens of km is below what daily static GNSS resolves, and the method
correctly stayed quiet rather than manufacturing a signal from noise.

**The technical cause of the DOY 126/129/145 spikes was not identified.**
Orbit file size and the fiducial-fixing list were both checked and ruled out.
Recorded as open rather than assigned a plausible guess.

### 20.3 Full-year and national-network questions

Asked what a full year, and eventually the full ~135-station PH network,
would cost. Measured rather than modelled where possible: 333 s/day at 30
stations, 3.94 of 24 cores (16% of the machine) — a year at this
configuration is ~34 h serial or ~7 h at five concurrent days.

**`MAXPAR` correction.** Originally recorded (this same session) as a hard
ceiling near 330 stations. Wrong — `ADDNEQ2.HLP`, read directly rather than
assumed from memory, states plainly it "allocate[s] memory for the combined
NEQ system. Specifying a number greater than necessary does not harm if the
computer has enough memory," and the program's own default is 3000, not the
1000 the R2S_FIN panel configures. A runtime allocation, not a compiled
limit. Corrected in both the runbook and this log rather than left standing.

**The user's subnetwork-then-combine instinct was confirmed as Bernese's own
intended architecture**, not a workaround: `ADDNEQ2.HLP` lists "combination of
overlapping networks (regional with global networks)" and "combination of
baseline-, or cluster-specific NEQs into a network solution" as core
applications. The honest cost, from the same text: cluster/regional
combination "neglect[s] the inter-baseline, or inter-cluster correlations" —
a known, accepted approximation, the same one IGS/EPN combination centers
accept at global scale.

### 20.4 The Bernese manuals: downloaded, indexed, one version caveat

User supplied two URLs directly (not guessed): `DOCU52.pdf` and
`TERMINAL.pdf`. Downloaded to `/home/gps3/bernese-docs/` (858p and 150p,
~38 MB with `pdftotext -layout` extractions for fast `grep`).

**`DOCU52.pdf` is the Bernese 5.2 manual, not 5.4** — checked, not assumed,
given how much of this week's trouble traced to exactly that version gap
(PCF format change, `V_PCVINF` vs `V_PCV`, ANTEX SVN/PRN validation 5.2
lacked). `TERMINAL.pdf` is 5.4-native (Dach & Arnold, Jan 2026) and better
matched to how Bernese is actually run here — command-line, no GUI.

Full reference recorded in memory (`reference_bernese_manuals.md`) rather
than only in this log, since it needs to survive across sessions, not just
within this one.

### 20.5 Process note: two commits pushed directly to main

While verifying the PR #67 merge, `git checkout main` was run and every edit
afterward — including the S01R and MAXPAR corrections — was committed and
pushed directly to `main`, bypassing the PR requirement. This is the same
mistake §18.7 recorded once before (`c4bc867`). Flagged to the user plainly
rather than left to be noticed later; content was sound, route was not.
Branched properly for everything after.

### 20.6 S01R: from "mystery" to "documented, and not acted on"

Raised by the user twice, ten minutes apart, the second time sharper: *"do we
need S01R... or has this slowly devolved into a 'let's not jinx the data
processing' type of belief?"*

**Three technical hypotheses checked and ruled out**, each cheaply, against
real files rather than guessed:

1. 15 s sampling vs. the network's 30 s — `V_SAMPL=180` divides both evenly;
   doesn't explain exclusion.
2. Stale `LUZON.STA` equipment entry — the 2025-04-15 entry (`TRIMBLE ALLOY`
   / `LEIAR25 LEIT`) is clean and matches the RINEX header exactly. (A real,
   separate defect — overlapping/duplicate entries for 2017–2025 — exists
   nearby but predates the window that matters.)
3. Unrecognized antenna model — `LEIAR25 LEIT` is present in
   `REF54/ANTENNA_I20.PCV`.

**What actually changed the picture**: S01R carries an estimated velocity in
`LUZON.VEL` (`-0.02209 -0.00659 -0.01191` m/yr, EURA-relative) and appears in
**364 of the 365 days** Abegail solved in 2025 — checked across the full
year, not just the 31-day window. It fails in **all ten** of this session's
I20 runs and **none** of hers over the identical days. The pipeline is the
anomaly, not the station — something in the 5.4/I20 derivation regresses a
station that has processed reliably since 2002. Cause still not identified.

**Then the actual rationale surfaced, sourced rather than inferred.** An
earlier guess in the runbook (Luzon Strait/Taiwan collision-zone tectonic
interest) was wrong. The real answer was already written, twice, in this
repo: in PHIVOLCS's own work instructions (Cass, Dane, Abegail) and in the
user's own October 2025 technical review of that document
(`docs/work_instructions_review.md`). Quoted verbatim in the runbook now.
S01R is the fixed reference point for a **Eurasia-plate-relative velocity
frame** (every station's velocity computed relative to it) and for
XYZ-to-ENU time-series plotting — a different purpose from what the nine IGS
fiducials do (absolute ITRF/IGS20 position). But the source document already
grants permission to change it: *"the choice of reference station... is not
fixed, as other stations may be used based on needs or the intended
analysis,"* naming **PIMO** — already one of this network's own fiducials,
already flowing through the pipeline daily, zero foreign dependency — as a
named alternative.

**Verdict, stated plainly in the runbook**: not superstition, but not a hard
requirement either. The SOP already grants permission to change it; nothing
has acted on that permission, including switching to a station that would
make tonight's regression moot.

### 20.7 A reading plan for the full PH network, not the reading itself

`docs/national_network_subnetwork_prep_plan.md` — four tiers, each tied to a
specific open question rather than "read the chapter": partitioning
mechanics (Tier 1), combination and datum-tying mechanics (Tier 2), the
double- vs. zero-difference architecture choice `LUZON_DLY` inherited by
default rather than by decision (Tier 3), and FODITS/quality (Tier 4).

One question closed before the plan was even needed: **station/receiver count
is not a constraint.** `M_MAXDIM.f90` in the installed 5.4 source (not the 5.2
manual) gives `MAXSTA=3000`, `MAXREC=1000` — real compiled Fortran
`PARAMETER` limits, unlike `MAXPAR`. A ~135–425 station PH network is nowhere
close.

### 20.8 State at end of 2026-08-11

- PRs this session: #67 (merged), #69 (merged, S01R sourcing), #70 (open —
  the reading plan itself).
- Manuals live at `/home/gps3/bernese-docs/`, indexed in memory.
- Next: work through the reading plan's Tier 1, per the user's explicit
  instruction, documenting durably at the end of each tier rather than only
  in conversation.
