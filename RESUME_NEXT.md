# RESUME — next session

**Updated 2026-07-28 (gps3/R740 Bernese install COMPLETE + VERIFIED — 0.0000 mm
SINEX match — START HERE). Prior: 07-22 (thumb-drive
backup), 07-16 (Backup Plus→DOSTB migration complete, sdd2-scan diagnosis
corrected), 07-15 (migration/scan kicked off), 07-14 (clean shutdown, VADASE
PRs, EVACUATE verdict), 07-13 (RAW done), 07-08 (freeze), 07-07
(excavation+crossref), 07-04 (DA-005).**

## ⚠ ACTION REQUIRED — revoke the leaked Claude OAuth token

**On 2026-07-29 I (Claude, T420 session) accidentally printed the plaintext
`OAUTH_TOKEN` from `scripts/deploy_r740.secrets` into the transcript** — a
redaction fallback (`${val:-}`) printed the raw value when the char-count
expansion failed. It is a 108-char `sk-ant-oat01-…` static token.

**Remaining action: revoke it at claude.ai → Settings.** Everything else is
already done (2026-07-29):

- ✅ **Stripped from gps3's `~/.bashrc`** (was line 120). Verified: absent from
  interactive shells, `.bashrc` still parses, the Bernese `LOADGPS` line
  survived (now line 124).
- ✅ Both `~/.bashrc.bak*` files on gps3 **shredded** — each still contained
  the token line, and neither held anything else unique.
- ⬜ **Still to do:** revoke at claude.ai, and remove `OAUTH_TOKEN` from
  `scripts/deploy_r740.secrets` on the T420.

**Correction to an earlier assumption:** gps3's Claude Code session does NOT
use this token. Alfie re-authenticated via the interactive browser flow
(`platform.claude.com/oauth/code/callback`), which writes
`~/.claude/.credentials.json` holding a `claudeAiOauth` object
(`accessToken` + `refreshToken` + `expiresAt`, `subscriptionType=pro`) — a
distinct, self-renewing credential. **Note both credential kinds share the
`sk-ant-oat01-` prefix**, so grepping for that prefix matches the *legitimate*
credentials file too; a hit there is expected, not a leak.

Consequence: **revoking the leaked token will not disrupt the gps3 session**,
so it can be revoked at any time without staging a replacement first.

Residual copies of the secret are the two Claude session transcripts (T420's
and gps3's `.jsonl` files). Those are historical logs; revocation is what
makes them inert. Deleting a live session's transcript is not worth the
disruption.

**`deploy_r740.sh` Phase 3 writes `CLAUDE_CODE_OAUTH_TOKEN` into gps3's
`~/.bashrc`** — if that script is ever run, it will reintroduce the line we
just removed. Drop that phase, since interactive login now covers auth.

Also: `R740_PASS` in that same secrets file is `gps3` — same as the username,
on a LAN-reachable box with sudo. Worth changing while you're in there.

## ✅ VERIFIED 2026-07-28 — gps3/R740 Bernese install COMPLETE

`perl $U/SCRIPT/rnx2snx_pcs.pl 2023 0100` ran detached on gps3
17:58:09 → 18:09:33. **PASSED:**

- `Sessions finished: OK: 1  Error: 0  Total Time: 00:11:23`
- 114 jobs, **0 errors, 0 reruns**
- **SINEX diff vs reference: 0.0000 mm max**, all 54 params (18 stations ×
  STAX/STAY/STAZ), `$P/EXAMPLE/SOL/FIN_20230100.SNX` vs
  `$S/RNX2SNX/2023/SOL/FIN_20230100.SNX.gz_REF` — identical to the T420
  result recorded in [[bernese-install]].
- **11m23s vs the T420's 20m40s** — R740 is ~1.8× faster.

Two false alarms when reading the results, noted so they don't confuse a
future check:
- `pgrep -f rnx2snx_pcs.pl` over SSH **matches your own command string** and
  reports RUNNING forever. Use `pgrep -af` and eyeball it, or match on the
  BPE server PID instead.
- `grep -ciE "error|\*\*\*"` on `RNX2SNX.OUT` returns **3 on a fully
  successful run** — the summary line `Error: 0` and two table headers all
  contain the word. Don't treat nonzero as failure; read the
  `Sessions finished:` line instead.

Reproduce the SINEX check:
```bash
source ~/BERN54/LOADGPS.setvar
gzip -dc $S/RNX2SNX/2023/SOL/FIN_20230100.SNX.gz_REF > /tmp/ref.SNX
# compare SOLUTION/ESTIMATE STAX/STAY/STAZ (field 10) against
# $P/EXAMPLE/SOL/FIN_20230100.SNX — want <=0.09 mm
```

## DONE 2026-07-28 — gps3 install unblocked, entirely over SSH

**SSH key auth established** T420→gps3 (`ssh-copy-id`, existing ed25519 key).
gps3 = `192.168.48.98`, user `gps3`. This is what made everything below
possible without physical access.

**The `$U` blocker from `docs/BERNESE_GPS3_HANDOVER.md` is FIXED**, but note
**the handover doc's proposed fix (§3) was wrong — do not apply it.** It
claimed `$U` "was left at the stock default" and proposed `U="${C}/USER"`.
Ground truth showed `$USR` **already** points at `${C}/USER` and resolves
fine: `$USR` (template area, ships inside BERN54) and `$U` (live per-user
working tree under `${HOME}`) are **distinct by design**. Repointing `$U`
would collapse them — the same failure the doc's own "Do NOT symlink"
section warns about.

Real cause: `$U`=`/home/gps3/GPSUSER` and `$T`=`/home/gps3/GPSWORK` simply
never existed, because they live outside the `BERN54` tree the thumb-drive
backup copied. Fixed by generating them fresh:
```bash
source /home/gps3/BERN54/LOADGPS.setvar
printf "3\ny\nx\n" | perl $C/SCRIPT/EXE/configure.pm    # menu option 3
```
Result: `$U/PAN/MENU_EXT.INP` present (the exact file that was failing),
104 PAN INPs, USER.CPU, 138 scripts, 9 PCFs, 49 OPT dirs, `$T` created, and
**0 stale `/home/finch` references**.

**Why NOT to copy `$U` from the T420 instead:** its INP panel files carry
absolute paths baked in — verified 56 such files (`"U" "/home/finch/GPSUSER"`,
`"P" "/home/finch/GPSDATA/CAMPAIGN54"`, …). Generating fresh is correct.

**`setup.sh` turned out unnecessary** for this: it's only a 174-line shell
wrapper that execs `configure.pm`, which already ships inside `BERN54`.
Option 3 reads solely from `$C/SUPGUI/PAN/` and `$C/USER/`, both already
present. `configure.pm` has no flag to pick a menu item (only `--init`,
`--perl`, `--path`, `--qtBern`), so it must be driven on stdin — safe here,
but **guard with `timeout`**: `_yesNo()` is a `while(1)` that spins forever
if stdin hits EOF unexpectedly.

**Also fixed / found:**
- **DATAPOOL REF54 symlinks recreated** (`EXAMPLE.CRD/.VEL/.ABB` →
  `*_REF`). FAT32 cannot store symlinks so the thumb-drive transfer
  flattened all of them — zero symlinks survived anywhere in `BERN54`.
  BPE step R2S_COP fails without these.
- **`BSW54Unx_2024-11-11` transferred** to `/home/gps3/` (1.3G, 13/13 files
  verified). Not needed for option 3 as it turned out, but useful for menu
  options 2/5 and the Plan-B recompile.
- **No FAT32 exec-bit damage** — 0/88 non-executable in `EXE_GNU`, 0/28 in
  `SCRIPT/EXE`. Better than the handover doc feared.
- **`DE421.EPH` and `CRX2RNX` were already present** on gps3 — both live
  inside `BERN54` and transferred with it. My `install_bernese_dell.sh`
  scope note wrongly listed them as excluded; corrected.
- Claude Code **is** set up on gps3 (v2.1.133 at `~/.local/bin/claude`,
  node v24.15.0, `CLAUDE_CODE_OAUTH_TOKEN` at `~/.bashrc:120`, plus
  `~/.claude/.credentials.json` from an interactive login). It's an **OAuth
  token, not an API key**. Earlier "UNSET" readings were a false alarm —
  `~/.bashrc:8` has the standard Debian non-interactive early-return guard,
  so line 120 never runs over a non-interactive `ssh cmd`.
- **`scripts/deploy_r740.sh` was never actually run against gps3** — it
  installs Claude Code via `sudo npm install -g` (would land in
  `/usr/lib/node_modules`, not `~/.local/bin`) and its Phase 3 appends a
  `LOADGPS.setvar` line to `~/.bashrc` (zero such references there). gps3
  was set up by hand. The script remains untested.
- `/home/gps3/home/ltpt420` — confirmed a real botched-rsync artifact from
  Nov 2025. Unrelated, harmless, left alone.
- **`$U/GEN/SESSIONS.SES` is missing** — BPE logs `Cannot open INP file …
  SESSIONS.SES / Using standard session definition`. Non-fatal fallback, but
  this is exactly the gap already recorded in
  [[bernese-orchestrator-r740-gaps]]. Address before real campaign work.

### `install_bernese_dell.sh` — 3 bugs fixed (all mine)

1. **`QTDIR: unbound variable` crash** (the failure in the handover doc's
   §2, line 148). I'd switched the Plan-B heredoc from `<<'PLANB'` to
   `<<PLANB` so paths would expand — which also made bash try to expand an
   *illustrative* `export QTDIR=$HOME/…` line that's meant to be read, not
   run. Under `set -u` that killed the whole install. Reverted to a quoted
   delimiter; comment added so nobody re-breaks it.
2. **No exec-bit restoration.** The `ldd` check verifies linkage but not
   `+x`, and vfat can't store the bit. Added an explicit `chmod +x` pass
   over `EXE_GNU`, `SCRIPT/EXE`, `*.sh`, `*.pl`, `menu`.
3. **Over-escaped REF54 snippet** printed `EXAMPLE.\$f`, which if pasted
   would create a file literally named `EXAMPLE.$f`. Fixed and verified by
   actually executing the rendered command.

Plus **idempotency**: rsync now uses `--size-only` (FAT32's 2-second mtime
granularity makes unchanged files look modified, forcing needless re-copies).
Re-run against an already-correct tree completes in ~0.1s. shellcheck clean;
both flash drives carry the fixed copy (md5-verified identical).

## PLAN 2026-07-29 — gps3 storage allocation + external-drive migration

### Discovery: gps3 has 32.6 TB unallocated

`sda` is a **32.7 TB Dell PERC H750 hardware-RAID virtual disk** (spinning
media, no software RAID). The Ubuntu installer carved out only a **100 G**
root LV — everything else is free extents in `ubuntu-vg`. This changes the
migration picture completely: gps3 can hold the entire GNSS archive.

**PREREQUISITE — verify the RAID level first.** If gps3 becomes the archive
home (Backup Plus is retired, DOSTB is currently the only good copy), we
must know whether that 32.7 TB is redundant:
```bash
sudo dmesg | grep -i megaraid
sudo apt install megacli && sudo megacli -LDInfo -Lall -aALL
```
or read it from iDRAC. **RAID 6/10 → fine. RAID 0 → must not be the only copy.**

### Recommended LV layout

| LV | Size | FS | Mount | Purpose |
|---|---|---|---|---|
| `ubuntu-lv` *(exists)* | 100 G → **250 G** | ext4 | `/` | OS/packages only |
| `lv_gpsdata` | **4 TB** | XFS | `/home/gps3/GPSDATA` | live campaigns, DATAPOOL, SAVEDISK |
| `lv_archive` | **20 TB** | XFS | `/srv/gnss-archive` | legacy data from external drives |
| `lv_work` | **1 TB** | XFS | `/home/gps3/GPSWORK` | BPE scratch (`$T`) |
| *free* | **~7 TB** | — | — | headroom |

Reasoning:
- **Data off root** — a full data volume must never wedge the OS.
- **Mount points chosen so `LOADGPS.setvar` needs no edits**: `$P`/`$D`/`$S`
  already resolve under `$HOME/GPSDATA`, `$T` is `$HOME/GPSWORK`.
- **Scratch isolated** — BPE churns small files; keeps the archive
  unfragmented and lets `$T` be excluded from backups.
- **Leave ~7 TB unallocated** — LVM grows online trivially; **XFS cannot
  shrink at all**. Free extents cost nothing and cover a wrong guess.
- **XFS on data** (dynamic inodes — archives are millions of small files;
  better multi-TB large-file throughput). Root stays ext4 (shrinkable).
- **`noatime`** in fstab across data volumes.
- If ext4 is used on any data LV, `mkfs -m 0` — the default 5% reserve is
  1 TB wasted on a 20 TB volume.

**Scripts written 2026-07-29 — use these, don't hand-type LVM:**
`scripts/gps3_storage_provision.sh` and `scripts/gps3_gpsdata_migrate.sh`
(both shellcheck-clean, dry-run by default, idempotent).

```bash
# copy over, then run inside tmux so an SSH drop can't interrupt a resize
scp scripts/gps3_*.sh gps3@192.168.48.98:~/
ssh -t gps3@192.168.48.98 'tmux new -As storage'
#   sudo ./gps3_storage_provision.sh            # dry run — prints every command
#   sudo ./gps3_storage_provision.sh --apply
#   sudo ./gps3_gpsdata_migrate.sh --sync       # rsync + census verify (repeatable)
#   sudo ./gps3_gpsdata_migrate.sh --swap       # gated cutover
```

Safety properties built in (verified by test, not just asserted):
- `mkfs` runs **without `-f`** — refuses any device that already holds a
  filesystem, so a typo cannot wipe a populated volume.
- provision **never** touches the live `~/GPSDATA`; it mounts `lv_gpsdata`
  at `/mnt/lv_gpsdata_staging` instead.
- migrate's **census** compares file count + symlink count + total bytes.
  Tested to catch both failure modes this project has actually hit:
  truncated copies and dropped symlinks. `rsync` exit=0 alone is not
  treated as proof (see [[backup-plus-health-crisis]]).
- cutover **renames** the old tree to `GPSDATA.old-<date>` and never deletes
  it — rollback is one `mv`. Reclaiming that root space is a manual step.
- fstab entries use **`nofail`** and are validated with `findmnt --verify`
  *before* any reboot can act on them.
- both refuse to run while a BPE process is active.

### Network is the migration bottleneck — measured

gps3 is wired gigabit (`eno4`, 1000 Mb/s). **The T420 is the problem**: its
ethernet `enp0s25` sits on `192.168.40.0/24` while gps3 is on
`192.168.48.0/24`, **with no route between them** (verified: 100% loss
forcing `-I enp0s25`). Hence wifi.

| path | measured | PAGENET 12.5G | archive ~150G |
|---|---|---|---|
| GNSS_2G (2.4 GHz) | **0.56 MB/s** | ~6 hr | ~3 days |
| GNSS_5G2 (5 GHz) | **6 MB/s** | ~35 min | ~7 hr |
| direct cable | ~110 MB/s (est.) | ~2 min | ~25 min |

Switched to **`GNSS_5G2`** (ch149, same subnet, 11× faster, latency
40 ms → 2.4 ms). 2.4 GHz here is badly congested — many SSIDs, and the link
dropped entirely once mid-session needing an `nmcli` bounce.

**Best option for bulk migration: direct cable.** gps3 has **three unused
gigabit NICs** (`eno1np0`, `eno2np1`, `eno3` — all `down`). This is exactly
what `scripts/deploy_r740.sh --direct` + `~/repos/hardline/direct_link.sh`
were written for.

### PAGENET — only ~12.5 G of the 18 G is worth copying

| dir | size | verdict |
|---|---|---|
| `RAW` | 12 G | **copy** — source RINEX, irreplaceable *(check first whether DOSTB already has it — avoid a second copy)* |
| `SOL` | 329 M | **copy** — the actual solutions |
| ORB/GEN/STA/BPE/ATM | ~155 M | copy, trivial size |
| `OUT` | 2.6 G | **skip** — program logs |
| `OBS` | 2.5 G | **skip** — regenerable from RAW via RXOBV3 |

Value beyond benchmarking depends on whether gps3 will *reprocess* PAGENET.
Note per [[pagenet-namria-provenance]] this is NAMRIA data held under MOU —
worth considering who has accounts on gps3 (3 users were logged in).

### Migration order

1. Verify RAID level.
2. Create LVs, move `GPSDATA` onto `lv_gpsdata`.
3. Establish the direct cable link (or accept 5 GHz for the smaller sets).
4. PAGENET `RAW`+`SOL`+small dirs → `lv_gpsdata`.
5. DOSTB archive → `lv_archive`, `rsync -aHAX` (preserves symlinks/modes —
   the thing FAT32 destroyed).
6. Verify with per-directory `find | wc -l` source-vs-dest, per the lesson in
   [[backup-plus-health-crisis]] (rsync exit=0 ≠ complete).

## STILL TO DO
- **Rotate the OAuth token** (see top) and change `R740_PASS`.
- Verify the PERC RAID level, then execute the storage + migration plan
  above (all needs sudo on gps3).
- **PAGENET transfer** — deliberately NOT run yet: 18 G into 25 G free would
  take root to ~93%, and it belongs on `lv_gpsdata` once that exists. Copy
  only `RAW`+`SOL`+small dirs (~12.5 G), not `OUT`/`OBS`:
  ```bash
  rsync -aHAX --info=progress2 \
    --exclude=OUT/ --exclude=OBS/ \
    ~/GPSDATA/CAMPAIGN54/PAGENET/ \
    gps3@192.168.48.98:/home/gps3/GPSDATA/CAMPAIGN54/PAGENET/
  ```
  `-aHAX` preserves symlinks/modes (the thing the FAT32 hop destroyed).

### Closed this session (kept for context)
- ~~Create `$U/GEN/SESSIONS.SES` on gps3~~ — **no action needed, and doing it
  would be wrong.** `SESSIONS.SES` is a **per-campaign** file
  (`$P/<CAMPAIGN>/GEN/SESSIONS.SES`); gps3's EXAMPLE already has one, and the
  verified T420 has no `$U/GEN` either. The BPE log line is a normal fallback
  probe, not a defect. A user-level table could override per-campaign ones.
- ~~Add `source ~/BERN54/LOADGPS.setvar` to gps3's `~/.bashrc`~~ — **done**,
  verified in an interactive shell (`$C`, `$U` resolve). Appended after the
  non-interactive early-return guard, so `ssh host 'cmd'` still won't see it
  by design — scripts must source it explicitly.

## DONE 2026-07-22 — Bernese backed up to 2 thumb drives (LAN-cable transfer still to be tried)

Goal: get the working T420 Bernese 5.4 install onto the Dell R740 as a
backup route, in case the planned direct LAN-cable transfer doesn't happen
or the R740 install needs redoing. Two drives now hold this:

**`FLASH16G`** (15G, 7.0G used) — the primary payload:
- `BERN54/` (2.5G, 8,367 files, verified count match) — full software install
- `GPSDATA/` (4.3G, 4,250 files) — campaign data **minus `CAMPAIGN54/PAGENET`**
  (18G, deliberately excluded — doesn't fit any available drive, and isn't
  needed for the R740 bring-up; PAGENET/NAMRIA provenance noted in
  [[pagenet-namria-provenance]])
- `install_bernese_dell.sh` — run this ON the Dell after copying the drive
  contents over. Patches `LOADGPS.setvar`'s `$C`, `BPE_SERVER_HOST`
  (auto-detects via `hostname`), and `QTBERN`; runs an `ldd`-based runtime
  library check on the Fortran binaries and the MENU GUI separately (MENU's
  Qt is statically linked — only needs system X11 libs, not a Qt runtime);
  prints the full resolved environment variable block; and includes a
  documented **Plan B: recompile from source** section if the copied
  binaries don't run (ABI/libgfortran mismatch etc.) — apt gfortran-13, Qt
  static build, the 2 required symlinks, X11 -dev packages, `setup.sh` in
  the verified option order. shellcheck-clean.
- `BERNESE_INSTALL_NOTES.md` — offline copy of the `bernese_install.md`
  project memory (full procedure + all T420/R740 gotchas), in case the Dell
  has no access back to this session's memory.

**`SANDISK8G`** (7.5G, 2.7G used) — redundant second copy, software-only
(GPSDATA doesn't fit alongside it — 4.81G needed vs 4.8G free, same margin
problem, explicitly skipped rather than risk a partial FAT32 copy):
- `BERN54/` (2.5G, same content, verified count + wasn't the file that got
  killed by a 2-min tool timeout on the first attempt — redone properly
  backgrounded, then verified)
- `install_bernese_dell.sh` + `BERNESE_INSTALL_NOTES.md` (checksums match
  FLASH16G's copies)
- `qt-build-offline/` — the Qt 4.8.7 source tarball (230M, from
  `~/Downloads/qt-build/`) + `temp/build_qt4.sh` from this repo. Added as
  insurance for Plan B in case the Dell's internet is flaky: Qt 4.8.7 isn't
  in any apt repo and the qt.io archive mirror can be slow/unreliable;
  `build_qt4.sh` skips its own download step when the tarball is already
  sitting next to it. (`gfortran-13`/X11-dev weren't bundled — those are
  current Ubuntu packages any mirror serves, low value to pre-stage.)

Both drives' contents verified (file counts + md5sum on the small files,
tarball checksum match) before unmounting. Both cleanly unmounted.

**Still to do:** the actual direct LAN-cable transfer T420→R740 (this
backup is the fallback, not the primary plan) — not started this session.

## DONE 2026-07-16 — Backup Plus → DOSTB migration COMPLETE

Laptop had an unclean shutdown mid-session on 07-15 (manual power-off, no
drives unmounted first) which killed both background jobs. On reconnect:
**no corruption found** on Backup Plus/DOSTB/DATA0/sdd2-partition (checked
`journalctl -k -b` for I/O errors/dirty ntfs flags — clean). One unrelated
drive, `HD-LBU2` (1.5TB FAT32, WD desktop drive from earlier in the week),
had its dirty bit set (`FAT-fs (sdf1): Volume was not properly unmounted`);
ran `dosfsck -n` (clean, only the dirty-bit itself + a harmless boot-sector
backup mismatch), then `dosfsck -a` to clear it, remounted OK.

The migration script (`/tmp/migrate_bp_to_dostb.sh`) had been wiped by the
reboot (`/tmp` doesn't survive power-off despite being its own partition) —
recreated from this doc's prior revision and rerun; `rsync -a --partial`
picked up cleanly where the interrupted run left off. Finished 13:46:12,
all stages exit=0. **Verified dest vs. source file counts:**

| dir | src | dest | match |
|---|---|---|---|
| RAW | 116,835 | 115,272 | short by 1,563 — expected, the known 139-corrupt-dir block on Backup Plus (unreadable at source, NOT a copy failure) |
| SP3 | 6 | 6 | ✅ |
| TimeSeries | 346 | 346 | ✅ |
| wvfs | 3,330 | 3,330 | ✅ |
| RECOVERED_DOSTB20150918 | 14,269 | 14,269 | ✅ |

**DOSTB is now the complete, verified working GNSS store** superseding
Backup Plus (see [[backup-plus-health-crisis]]). Backup Plus should be
treated read-only/retired pending a real Windows `chkdsk /f /r` or
replacement — no more bulk writes to it.

## BLOCKED 2026-07-16 — sdd2 scan resume, do NOT just `--resume` again (RESOLVED: use `main`, no code fix needed)

`drive-arch scan` on the 200GB partition (`DC9A88179A87EBF8`, Seagate) hit a
**symlink-loop hang**, not a normal interruption. Inspected the output file
post-mortem: of 5,152,000 lines written, **4,520,088 (87%) are garbage** —
repeating paths like `/tmp/da_dirsymlink2a.tar_vccs6_lp/cur/cur/cur/.../par/
da_dirsymlink2a.tar_.../cur/cur/...`. `dirsymlink2a.tar` is a known GNU-tar
testsuite fixture (a deliberate `cur`↔`par` symlink cycle used to test tar's
own loop handling) — presumably embedded inside some dev-tools backup on
this partition, extracted as a nested archive.

**Root cause was branch staleness, not a live bug.** Diffed
`tools/drive-archaeologist/src/drive_archaeologist/scanner.py` on this
branch against `main`: `main` already has a `filepath.is_symlink()` gate in
`_scan_directory` (part of `DA-002`, "finding #8") that records any symlink
via `readlink` and `continue`s — before any `is_dir()`/`is_file()` check —
so it can never recurse into a symlink loop. It's covered by an existing
test, `test_symlink_loop_is_harmless`
(`tools/drive-archaeologist/tests/test_hardening.py:121`), which is this
exact scenario (a self-referential dir symlink + a real file, asserts the
file is only recorded once). **This branch (`docs/bernese-training-notes`)
just never received `DA-002` (or `DA-003`/`DA-005a`)** — same root cause
already flagged for the missing `drive-arch recover` command.

**Fix: do not patch drive-arch.** Either merge/rebase `main` into this
branch, or just run the `drive-arch` scan from a `main` checkout (or
`main`'s installed `.venv`) instead of this branch's. Once on a
DA-002-equipped build, `--resume` is safe to retry as normal.
The existing `sdd2_full_scan.jsonl` should be truncated back to before the
garbage starts (~line 630,000) before resuming, since a hardened build will
correctly skip the symlink outright rather than hang on it.

**Why this session rerouted away from Backup Plus:** GPSR recopy attempt
found Backup Plus's copy still stuck at 12,949/20,555 (63%) — same 139-dir
corrupt block from 07-14, confirmed STILL PRESENT/UNFIXED via a fresh `du`
(identical error list). Per [[backup-plus-health-crisis]] verdict, did a
**fresh full copy of GPSR (all 20,555 files) to DOSTB instead** — verified
20,555/20,555, 0 errors. Then deleted the stale partial GPSR off Backup Plus
(corrupt block also blocks `rm`, left an unremovable 1.2MB stub — harmless,
not worth chasing) and started the fuller migration above to get everything
off Backup Plus onto DOSTB while its media reliability is unresolved.
**DOSTB is now the de facto working GNSS store** (not just interim) until
Backup Plus is repaired (`chkdsk /f /r`, needs Windows) or replaced.

## DOSTB 2026-07-15 — freed 1.4TB, GNSS payload from 2 new WD drives added

**Space freed:** DOSTB went from 1.7T used (93%) to 304G used (17%) — user
manually cleared Movies (800G, 678 titles) + Shows (487G, 37 titles,
including a 131G orphaned "Doctor Who" recovered from a chkdsk `found.001`)
+ `.Trash-1000` (83G) via Double Commander plain-delete (which did a REAL
permanent delete on this ntfs-3g mount, not move-to-trash — Recycle Bin
stayed at 0 files). **`ps4e` (99G, protected InSAR pipeline — see
[[dostb-ps4e-insar-pipeline]]) verified intact, untouched.**
- Along the way, 38 titles initially failed `rm -rf` ("Directory not empty")
  — traced to a REAL but MINOR SMART fault on DOSTB (`/dev/sdc`,
  `Current_Pending_Sector=1`, `Reallocated_Sector_Ct=0` — one bad sector,
  no history, not comparable to Backup Plus's crisis). Double Commander's
  delete succeeded anyway on a later pass — either the sector read cleared
  on retry, or DC handles stat-failures differently. Worth a `smartctl -A`
  recheck sometime to confirm the pending count actually cleared, not urgent.
- Built a `Deaccession Ledger` artifact (checklist UI, clipboard export of an
  `rm -rf` script) for the triage — superseded by the full manual clear but
  URL kept for reference: https://claude.ai/code/artifact/e2654d29-491c-45c0-9821-d67d90efb069

**Two new WD desktop drives scanned + copied to DOSTB:**
- `GPS_1TB_2` (WD10EARS, 1TB): 1,141 GNSS files classified, 1,127 copied
  (16 discrepancy = extraction path-prefix edge cases, not data loss) to
  `RECOVERED_GPS_1TB_2_WD10EARS_WCAV5M032380/`, verified count match.
- `HD-LBU2` (WD20EARS, 2TB): 7,488 GNSS files classified, 7,423 copied to
  `RECOVERED_HD-LBU2_WD20EARS_WCAZA4430660/`, verified count match.
- **Crossref against `~/surveys/consolidated_gnss_retrieval_priority.md`:**
  NAUJ + PUER = genuine zero-coverage closures (report updated: 139→137).
  JOSE/MAMB/SABL = real 2011 raw archives (1,400-1,600 files each) but wrong
  years vs. the requested gaps (2010/2012/2013/2016) — flagged in the report,
  does NOT close those gaps. SOLE = false positive, ruled out (coincidental
  Bernese processing-dir name "sole", actual stations inside are SOLC/SOLD +
  IGS reference sites, not the requested SOLE).
- **Gotcha discovered:** `drive-arch recover` (DA-006, PR #49, merged to
  main 2026-07-04) does NOT exist on this branch (`docs/bernese-training-notes`)
  — branch is stale relative to main, missing `recovery.py` entirely. Used
  plain `rsync --files-from=<jsonl-derived-list>` instead (worked fine,
  simpler than expected for pure category-filtered copy). **Needs a rebase/
  merge of main into this branch before DA-006/DA-009 tooling is usable here.**

## HALT STATE 2026-07-14 — clean shutdown, everything verified

**BACKUP PLUS: VERDICT ESCALATED TO EVACUATE.** Full story in memory
`backup_plus_health_crisis` — read it first. Short: 3rd write-corruption
episode found (GPSR "exit=0" was short 7,606 files — a CONTIGUOUS 139-dir
block 140211P–140708P exists on dest but refuses all writes, I/O error 5;
140211P died mid-write 33/63). SMART is UNOBTAINABLE (bridge rejects all
passthrough, even Seagate's own openSeaChest — apt 23.12 installed) AND the
bridge is SELF-ENCRYPTING (TCG/IEEE-1667: bridge PCB death = total data
loss; shucking useless). Backup Plus is READ-ONLY by policy; it holds sole
copies of the DOSTB recovery. **Next actions: (1) procure replacement drive
2-4TB (BP carries ~796GB, 86% full), (2) Windows chkdsk /f only as a
read-stabilizer, (3) evacuate everything to the new drive, (4) re-copy GPSR
from Seagate DATA0 (intact master: 20,555 files; only 12,949 landed).**
wvfs verified complete 3,330/3,330. RAW verified complete 07-13 (+4 corrupt
dest dirs 2016/VCAC, 2016/temp, 2017/CACA_*, 2017/ATIM_* still pending the
_recovered workaround — do that on the REPLACEMENT drive, not BP).

**sdd2 (200GB partition DC9A88179A87EBF8) scan: PAUSED mid-run, resumable.**
2,943,000 records so far (vastly more than DATA0's 140k — dense tree, likely
a system volume). SIGINT-paused cleanly, "Progress saved. Use --resume".
Resume: `uv run drive-arch scan /run/media/finch/DC9A88179A87EBF8 -o
~/surveys/SEAGATE-W2A0W9T2/sdd2_full_scan.jsonl --resume` (mount sda2/sdd2
by label first; letters shift). Then classification breakdown + crossref
against the retrieval priority list.

**VADASE: review cycle CLOSED.** PRs #53/#54/#56/#55 all squash-merged to
main 2026-07-14; full 51-test suite verified passing on merged origin/main;
all 8 worktrees pruned (4 DA + 4 VADASE), local branches deleted.
**Gotcha for stacked PRs: GitHub did NOT auto-retarget #56 when #53's branch
merged, and `gh pr edit --base` fails silently (GraphQL Projects-classic
deprecation — same as PR #51). Working fix: `gh api -X PATCH
repos/<owner>/<repo>/pulls/<n> -f base=main`, then VERIFY with gh pr view.**
Deferred tickets from the review: threshold single-source-of-truth (15mm/s
in 4 Grafana places, thresholds.yml empty), src/→named-package rename
(monorepo-wide), jules/vadase-ingestion-fix salvage review, PR #55 runtime
verification (needs docker compose up — R740).

**Dock (JMicron 152d:0561) status:** SMART CHECK-POWER-MODE tick fails every
10 min against the ST500DM002 — logged, non-fatal all day. Real dropout
signatures (USB disconnect/device offlined/IO error) never fired 07-14.
Next dock experiment queued: swap in the legacy 3.5" HDD (needs the powered
dock — it's 12V) to isolate dock-vs-drive.

**Drives: all unmounted + powered off cleanly** (scan SIGINT-checkpointed
first, watchdog killed, sync'd). Safe physical unplug.

## HALT STATE 2026-07-13 — clean shutdown, copy nearly done, VADASE fixes shipped

**Drive copy (DATA0 → Backup Plus): RAW IS GENUINELY COMPLETE.**
- Morning: Backup Plus refused to mount — `$MFTMirr does not match $MFT
  (record 0)`. Fixed with real `sudo ntfsfix /dev/sdc2` (not -n), mounted
  clean after. Root cause chain: 07-08 freeze was triggered by the Seagate/
  JMicron dock dropping SMART `CHECK POWER MODE` (all-zero sense data) —
  same signature recurred 07-13 at idle (09:26) and mid-copy (12:26)
  WITHOUT killing the drive. Recurring but so-far non-fatal.
- During the resumed copy, 4 MORE corrupt dest dirs surfaced beyond the 9
  known 2014 ones: `2016/VCAC/`, `2016/temp/`, `2017/CACA_20170513_*/`,
  `2017/ATIM_20170512/`. NOT yet worked around — copy skipped them
  (rsync skip-and-continue). **Batch-fix next session: grep full
  rsync_copy.log for "Input/output error", extract distinct dirs, copy each
  to `<name>_recovered/` (same JOSE trick), verify counts.**
- 16:59:46: `finished RAW, exit=0` — REAL this time (to-chk showed full
  114,674-file denominator; the 07-08 "ALL DONE" was a kill-race artifact).
- GPSR restarted from ~0% and was killed cleanly at ~89% of first chunk for
  shutdown. wvfs at 27%, TimeSeries/SP3 done (verified counts 346/346, 6/6).
- **Resume command: rerun `/tmp/resume_copy2.sh` logic for GPSR+wvfs only**
  (RAW done; excludes only matter for RAW). Simplest:
  `for d in GPSR wvfs; do rsync -rt --partial --info=progress2 "$SRC/$d/" "$DEST/$d/"; done`
  with SRC=/run/media/finch/DATA0, DEST="/run/media/finch/Backup Plus/RECOVERED_SEAGATE_W2A0W9T2_DATA0".
- After ALL DONE: delete SP3 (redundant, CDDIS re-downloadable), verify RAW
  dest-vs-source counts, batch-fix the 4 new corrupt dirs, THEN sdd2 scan.
- Watchdog pattern that worked: `journalctl -f` grep for
  `CHECK POWER MODE|Unexpected sense|USB disconnect|I/O error, dev sd` —
  detached copy in /tmp/detached_watchdog.sh, log at
  `~/surveys/SEAGATE-W2A0W9T2/watchdog.log`.

**VADASE code review COMPLETE + fixes shipped as 4 PRs (2026-07-13):**
- Review of unreviewed Apr-May direct-to-main range `9aff14d^..main`:
  8 finder angles + verify pass; 8 CONFIRMED findings + ~20 secondary.
  Full details: `~/surveys/vadase_review_banked_candidates.json`.
- **PR #53** (fix/vadase-ingest-runtime): shared-adapter lifecycle (silent
  total data loss for 34/35 stations — worst finding), NTRIP v1 drain ate
  32 sentences/reconnect, handshake timeout, FatalConfigError (401/404 no
  longer retried forever), full-jitter backoff, replay TaskGroup deadlock
  fix, dead .env reloaded. 46 tests pass, TDD, end-to-end verified both
  happy + DB-down paths.
- **PR #54** (fix/vadase-replay-timing): `.seconds`→`.total_seconds()` day-
  rollover bug (realtime replay NEVER slept; --speed was a no-op) + 
  run_demo.sh (--help, dataset check, bc removed, matplotlib probe removed).
- **PR #55** (fix/vadase-grafana-ops): alert email showed boolean 1.0000
  instead of measured velocity ($values.C→B), AVG(v_horizontal), env-driven
  DB password + alert email (personal gmail removed), station variable off
  the hypertable. NOT runtime-verified (needs docker compose up — R740).
- **PR-D IN PROGRESS, uncommitted** in worktree `.trees/vadase-pr-d`
  (branch fix/vadase-packaging-docs, STACKED on PR #53's branch):
  done so far: deleted 0-byte validate_parser.py (git rm), created
  src/adapters/outputs/composite.py (CompositeOutputPort) +
  src/adapters/outputs/logging.py (LoggingOutputPort for dry-run).
  REMAINING: remove both dead entry points from pyproject.toml:29-30,
  drop unused `date` import nmea_parser.py:6, wire LoggingOutputPort into
  run_ingestor dry-run, swap replay_events+stress_test_parallel to the
  shared CompositeOutputPort, add checksum-contract tests to
  test_nmea_parser.py (restores NMEAChecksumError coverage + fixes F401),
  README working invocations (PYTHONPATH=. — documented invocations are ALL
  broken), purge writer.py refs from ONBOARDING.md:106,142 /
  DATABASE_SCHEMA.md:3,37 / tree.md:34. Then pytest+ruff+commit+
  `scripts/open_pr.sh --base fix/vadase-ingest-runtime` (stacked).
- Tickets deferred from review: threshold single-source-of-truth
  (15mm/s hardcoded in 4 Grafana places, thresholds.yml EMPTY),
  src/→named-package rename (wheel packaging fundamentally broken —
  `uv run vadase-ingestor` ModuleNotFoundError, only PYTHONPATH=. works),
  salvage review of unmerged jules/vadase-ingestion-fix branch (504
  insertions incl. nmea_parser fix + 68 test lines).
- Worktrees active: .trees/vadase-pr-a (merged into #53's branch, keep
  until merge), -pr-b, -pr-c, -pr-d (uncommitted work!).

**Also 2026-07-13:** Gmail draft for Cassandra→Lucille Masbate/Marilao
open-file-report follow-up created in apelicano@gmail.com Drafts (threaded
under the forwarded thread; copy body into gpspivs01 to send). /statusline
setup request pending (deferred at shutdown).

## HALT STATE 2026-07-08 — machine hard-froze mid-copy, drives safely powered off
**Root cause: dock/drive dropout under I/O load, NOT the fixed autosuspend issue.**
At 14:46:12 `udisksd`'s routine SMART housekeeping sent `CHECK POWER MODE` to the
Seagate (DATA0, serial W2A0W9T2) and got back all-zero sense data — the JMicron
dock (152d:0561) stopped responding to the bridge. System hard-froze ~1 min later
(journal just stops mid-routine-logging at 14:47:25, no clean shutdown target
reached). Came back up on its own/forced at 14:52:27 — **5-min gap, not a REISUB
this time**, nobody was at the keyboard when it happened. **This is the same dock
as the 07-07 incident; the `USB_DENYLIST` TLP fix did NOT prevent this one** — so
either it's a load-triggered dropout distinct from autosuspend, or the fix is
incomplete. Needs real investigation before trusting this dock with another long
unattended copy (maybe: try a different USB port, check the dock's own power
supply/cable, watch `dmesg -w` live during a resume to catch the exact failure
signature).

**Both drives cleanly powered off at session end** (`udisksctl power-off`,
verified gone from `lsblk`) — safe to unplug physically, no unmount was pending.

**Copy progress is genuinely uncertain — do NOT trust the last logged "ALL DONE".**
Sequence of what actually happened today, in order:
1. Resumed yesterday's halted copy (JOSE-workaround excluded) — hit **8 more**
   corrupt `RAW/2014/` directories beyond JOSE: GUMA, GUNY, IBAZ, ILN3, INFA,
   ISB4, ITBA, ITGN (3,646 `Input/output error (5)` lines total across all 9).
   `sudo ntfsfix -n /dev/sdc2` came back clean **again** — confirms (as expected)
   it only checks `$MFT`/boot sector, never sees directory-index corruption.
   Fixed via the same workaround as JOSE: copied all 8 into fresh
   `RAW/2014/<SITE>_recovered/` dirs. **1,629/1,629 files, 0 errors, verified.**
2. I killed the running rsync to apply that exclude list, but only killed its
   forked child PIDs, not the outer loop script — the loop has no error-gating
   between stages (`rsync ...; echo finished`), so it barreled through
   GPSR→wvfs→TimeSeries→SP3 in ~13 seconds and logged "ALL DONE" while most
   of it never actually transferred. **Real dest-vs-source counts at that
   point: RAW 50,251/116,489 (43%), GPSR 42/20,555 (0.2%!), wvfs 915/3,330
   (27%), TimeSeries 346/346 (100%), SP3 6/6 (100%).** Lesson: never trust a
   loop script's own "finished, exit=$?" line when you killed a child PID
   directly instead of the parent — verify with real file counts.
3. Kicked off a proper resume at 13:42 (RAW+GPSR+wvfs, now excluding all 9
   corrupt dirs). **This is the run that got cut off by the freeze at 14:47** —
   unknown how far RAW got past the 50,251 mark before the drive dropped out.
4. **First action tomorrow: re-mount both drives, re-run the dest-vs-source
   `find | wc -l` comparison per top-level dir (RAW/GPSR/wvfs — TimeSeries/SP3
   already 100%, skip those) before deciding whether to resume or restart.**
   `--partial` on all these rsyncs means no data was corrupted by the abrupt
   cut, just incomplete — safe to blind-resume once counts are known, same
   command as before (9-dir exclude list, see 07-07 section below for the
   original command shape).

## DA-010 consolidated report — DONE (but see caveat below)
`~/surveys/consolidated_gnss_retrieval_priority.md` — merges ALA_ADP + CJVC
crossrefs + VFS color-coded table, grouped by geodetic network, **excludes
sites the logsheet already marks Complete** (my first draft wrongly counted
those as "zero coverage" — corrected). Final: **197 sites with a real
outstanding request, 139 zero-coverage (top priority), across 10 networks.**
Script: `/tmp/build_consolidated_final.py` (not persisted to repo — rerun from
here if needed, self-contained, reuses `site_to_group.json` + the crossref
TSVs + inventory-indexing logic already described below).
**Open caveat, not resolved tonight:** only 10 of the 14 expected CJVC networks
show up (Palawan, Romblon, Samar, Marinduque all absent). Could be genuine
(those networks' logsheet rows are all "Complete", nothing to retrieve) or a
tagging gap in `site_to_group.json` (Marinduque's heading `**MARINDUQUE\***`
lacks the "NETWORK"/"CGPS" keyword the original regex required — suspected,
unconfirmed). **Verify before treating this report as final** — check the
raw CJVC doc for those 4 networks' actual retrieve-column contents.

## MISSED FROM NOTES 2026-07-07 — MOVE Faults Midyear slide deck (this repo has no
context for this, but it happened yesterday same session — added retroactively)
- Built `2026 Midyear Performance - MOVE Faults (DRAFT).pptx`
  (`/home/finch/Documents/movefaults/`) — 11 slides, format from the 2026 template,
  content pattern from the 2025 deck, all figures from Q1/Q2 2026 QDRRs + Project
  Plan Section 5/6 + (later) real budget PDFs. Script: `/tmp/build_midyear_deck.py`
  (not persisted anywhere durable — recreate from source docs if needed again,
  it's fully described in this note).
- **Budget slide (10) — now backed by real numbers, verified across all 5 monthly
  "Status of Reprogrammed MOOE" GGRDD reports** (Dec25/Feb26/Mar26/Apr26/May26,
  scanned PDFs, MOVE FAULTS section page varies per month — Alfie supplies it).
  **Full detail + monthly-update instructions now in a DEDICATED PERSISTENT
  memory file** (`movefaults_2026_budget_tracking` — not just this doc, since
  Alfie flagged this as important to keep current through H2 2026): 37%
  utilization as of May 31 (₱4.56M / ₱12.38M updated LIB), steady ~₱1.05M/month,
  trend 10%→18%→27%→37% Feb-May, ₱54.45M capital outlay (10 GNSS receivers)
  has zero utilization visibility (separate line, not in the MOOE report — and
  cross-checks against Q1/Q2 QDRRs show no confirmed new-CORS install either).
- Roster corrected: Baldemoro → Garcia (per `movefaults-staff.md`, fills the
  Project Plan's previously-TBA slot).
- Deliberately-honest gaps left IN the deck (not fabricated): new-CORS
  installation/procurement status unconfirmed in Q1-Q2 QDRRs (flagged on slides
  2, 7, 11); VFS Single-Frequency Network table's color legend was recovered
  from the real .docx (`w:shd/@w:fill`, python-docx) since markdown export lost
  it — legend swatch hex drifted from data-cell hex, matched by color family,
  noted as such.
- Alfie sent this to Cass for integration into the master
  `2026 Midyear Performance Review - EGGRDS` deck + proofread — **already
  integrated as of today** (confirmed by Alfie). Proofread ask covered: verify
  figures vs the 3 source docs, check for import formatting breakage, confirm
  the roster swap, don't erase the deliberate gap-flags, watch for a June 30
  MOOE report landing before the presentation (would need a budget-slide update).

## UPDATE 2026-07-07 later — forced REISUB reboot (unmount hung on shutdown)
A later shutdown attempt hung trying to unmount a drive; Alfie forced a REISUB
reboot. **DATA0 (sdc2+sdc3) verified clean after reboot**: df sizes identical to
pre-reboot, spot-read 3 real files across the tree (2012/2017/GPSR areas), dir
listing intact, zero I/O errors in dmesg — no corruption. Drive re-enumerated as
`sdc` this time (was `sdd` before) — pure letter-shift, identity resolution
already accounts for this. **Backup Plus was NOT attached during this check —
do the same quick spot-check on it first thing tomorrow** (df sizes match +
`stat` a couple of files under `RECOVERED_SEAGATE_W2A0W9T2_DATA0/RAW/` +
`RECOVERED_DOSTB20150918/`) before resuming the rsync copy, since it's the
more likely candidate for whatever was stuck mid-unmount.

## HALT STATE 2026-07-07 evening — safe to resume tomorrow
Everything below was stopped cleanly (no kill -9, no unplugged-mid-write). Physical
Seagate ST500DM002 + Ugreen/JMicron dock: **left connected/mounted overnight** unless
Alfie decides otherwise — no destructive step was pending.

**CORRECTION 2026-07-08:** the "~95%" below was wrong — rsync's `--info=progress2`
percentage on a huge incrementally-recursed tree is relative to files DISCOVERED
so far, not the true total. Actual state when resumed: only ~21 GB / 15,425 files
of RAW's 126 GB / 116,489 files had really copied. Verify with `du`+`find` on the
destination, never trust the live percentage on a tree this size/shape.

**ALSO 2026-07-08: found + worked around real NTFS corruption on Backup Plus.**
`RAW/2014/JOSE/`'s own directory index (inode 1420320) is damaged — every
attempt to add a filename into that directory fails with `Input/output error`
(ntfs-3g: "Failed to read vcn 0x11 from inode 1420320" / "Failed to add filename
to the index"). `ntfsfix -n /dev/sdc2` (needs `sudo`) came back clean ($MFT/
$MFTMirr/boot sector all OK) — this is a deeper directory-index fault ntfsfix
doesn't reach; a real fix needs Windows `chkdsk /f`. **Workaround: copied
DATA0's `RAW/2014/JOSE/` (1,263 files, 3.3G) to a FRESH directory name,
`RAW/2014/JOSE_recovered/`, on Backup Plus — sidesteps the corrupt inode
entirely (new directory = new index). 1,263/1,263, 0 errors.** The main copy
loop's RAW pass now runs with `--exclude="2014/JOSE/"` since that path is a
dead end on the destination. **If reorganizing this recovery later, remember
`JOSE_recovered/` is really just `2014/JOSE/`'s content, misplaced only because
of this corruption — not a distinct site/directory.**

**1. rsync copy (DATA0 → Backup Plus) — stopped at RAW ~95%, SIGTERM (clean).**
Resume tomorrow with the exact same command (idempotent — already-copied whole files
are skipped, `--partial` kept the in-flight file so at most one file re-transfers):
```
SRC="/run/media/finch/DATA0"
DEST="/run/media/finch/Backup Plus/RECOVERED_SEAGATE_W2A0W9T2_DATA0"
LOG=~/surveys/SEAGATE-W2A0W9T2/rsync_copy.log
for d in RAW GPSR wvfs TimeSeries SP3; do
  echo "=== $(date +%H:%M:%S) starting $d ===" >> "$LOG"
  rsync -rt --partial --info=progress2 "$SRC/$d/" "$DEST/$d/" >> "$LOG" 2>&1
  echo "=== $(date +%H:%M:%S) finished $d, exit=$? ===" >> "$LOG"
done
echo "=== $(date +%H:%M:%S) ALL DONE ===" >> "$LOG"
```
(SP3 output should be deleted after copy — redundant, re-downloadable from CDDIS,
per Alfie's call.) TLP/dock autosuspend fix from earlier today (`USB_DENYLIST` in
/etc/tlp.conf) is persistent — no need to redo.

**2. sdd2 scan — still queued, unchanged.** Full-scan the 200GB `sdd2` partition
(mount `DC9A88179A87EBF8`, 32 GNSS files per its earlier survey) only AFTER the
rsync loop above hits `ALL DONE` — same physical spindle, sequenced to avoid I/O
contention (Alfie's explicit choice).

**3. DA-010 logsheet crossref — TWO source docs done, THIRD (consolidation) not
started.** Cross-referenced against DATA0+DOSTB+Backup Plus catalogs:
- ALA_ADP (IESAS Luzon/Mindanao/PHIVOLCS-owned): 47 found / 405 missing / 14
  zero-coverage sites. `~/surveys/SEAGATE-W2A0W9T2/crossref_found_all_drives.tsv`
  + `crossref_still_missing_all_drives.tsv`.
- CJVC (Cebu-Bohol-Panay-Negros/Cotabato-Sindangan/Luzon campaigns + Leyte/
  Marinduque/Mindoro/Romblon/Masbate/Samar/Palawan CGPS + VFS single-freq):
  36 found / 864 missing / 104 zero-coverage sites (of 129).
  `crossref_cjvc_found.tsv` + `crossref_cjvc_still_missing.tsv`. VFS table
  needed the real `.docx` (cell-shading colors) — markdown export lost the
  color legend; extracted via python-docx `w:shd/@w:fill`, mapped by color
  family (exact hex drifted from the legend swatches, matched by family):
  8 cells "to retrieve", 30 "no data/pulled out" (confirmed absent everywhere
  too — no false negative), rest available/RINEX-only/uncolored.
  `vfs_network_colorcoded.tsv`.
- **NOT DONE: consolidated report grouped by geodetic network** (Alfie's actual
  ask — "proper geodetic network groupings by province etc"). Site→group mapping
  already extracted and saved: `~/surveys/site_to_group.json` (ALA_ADP: 60 sites
  → IESAS LUZON/MINDANAO/PHIVOLCS-OWNED; CJVC: 172 sites → 9 campaign/CGPS-network
  names + VFS). **Next step: merge this mapping with the four found/missing TSVs
  above into one report, grouped by network** (province-level grouping needs a
  verified site→province lookup that doesn't exist yet — flag this gap rather
  than guess). Scripts (crossref3.py, crossref_cjvc.py, crossref_cjvc_final.py,
  consolidate.py — the last one is the unfinished piece) copied to
  `~/surveys/SEAGATE-W2A0W9T2/scripts/` for persistence.
- **Known caveat carried over: DOSTB contributed 0 matches to either crossref,
  not fully debugged** (plausible given different campaign geography, but
  unverified).
- **Process lesson from today, worth remembering:** an f-string regex brace-escape
  bug (`{0,3}` vs `{{0,3}}` inside an `rf'...'` string) silently broke the Leica
  DOY-suffix matcher twice in a row — once in the original script, once in a
  "fix" that re-introduced the same mistake. Always test a regex fix against one
  known real filename before rerunning the full crossref.

## Session 2026-07-07 — Seagate ST500DM002 excavation (background/earlier, mostly superseded by HALT STATE above)
- Drive: 500GB Seagate, 3 partitions. `sdd3` DATA0 (265.6G): surveyed → full-scanned
  (140,760 files, 133.8 GiB; 55,266 GNSS-classified, 68.9 GiB loose + 14,933 archives
  w/ GNSS content, 13.2 GiB via entry-listing triage) → **copy to Backup Plus
  `RECOVERED_SEAGATE_W2A0W9T2_DATA0/` running at session end** (RAW/GPSR/wvfs/
  TimeSeries/SP3, ~132 GiB; SP3 to be deleted post-copy — redundant, re-downloadable
  from CDDIS). `sdd2` (200.1G, mount DC9A88179A87EBF8): **surveyed only** — 32 GNSS
  files, DO NOT wipe verdict, not yet full-scanned/copied. **Queued: full-scan sdd2
  once sdd3 copy chain hits ALL DONE** (same spindle — sequenced to avoid I/O
  contention, per Alfie's explicit choice over "start sdd2 right after RAW").
- Dock: Ugreen/JMicron JMS551 (152d:0561) via bare USB2, port 2-1.2. Confirmed real
  enumeration flakiness (error -71 at boot; one mid-session bridge-identity blip)
  root-caused to **TLP autosuspend fighting a udev rule** — fixed via
  `USB_DENYLIST="152d:0561"` in /etc/tlp.conf + `tlp start` (cleaner than the udev
  rule alone, which TLP kept overriding). Verified: `power/control` = `on`.
- **DA-010 (NEW) — logsheet cross-reference, proven working use case.** Given a paper
  logsheet gap-list (site + year-month ranges expected) and one or more scan
  catalogs, report FOUND (data already excavated, needs pulling) vs STILL MISSING
  (no catalogued drive has it) vs ZERO-COVERAGE sites (nothing anywhere, top hunt
  priority). Proven on `~/Downloads/Data to be retrieved (ALA_ADP).md` (IESAS
  Luzon/Mindanao/PHIVOLCS-owned, 452 requested site-months) against DATA0+DOSTB+
  BackupPlus catalogs: 47 found, 405 still missing, 14 zero-coverage sites (ANGT,
  ANTP, BALA, BTUN, LBAN, LGYE, MALY, MUNT, SOLA, STNA, TAWI, TCGN, TNDG, VIGN).
  Site+date extraction must handle real-world messy naming: `SITE_yyyymmdd`
  deployment-suffixed dirs, `YYYYMM` campaign subdirs, Trimble
  `SITEyyyyMMddHHMM.T02`, Leica `SITEdddX.mNN` (DOY + session letter — first attempt
  missed all 2017+ data by requiring site-folder to be exactly 4 chars; fixed by
  matching site code as a prefix anywhere in the path). Scripts + results:
  `~/surveys/SEAGATE-W2A0W9T2/crossref*.py`, `crossref_found_all_drives.tsv`,
  `crossref_still_missing_all_drives.tsv`. **Caveat: DOSTB contributed 0 matches,
  not fully debugged (plausible — different campaign geography); sdd2 not yet
  scanned, may close a few more gaps once it lands.**
- **DA-009 (NEW) — bulk export command.** `drive-arch recover` (DA-006) only handles
  `$RECYCLE.BIN` pairing. Live-directory copy-out (DOSTB `_LIVE`/`_COMPANIONS`, this
  session's DATA0 dirs) keeps getting hand-rolled. Proposal:
  `drive-arch export <catalog.jsonl> --dest-root DIR [--category ...] [--path-prefix ...]`
  reusing `recovery.copy_from_manifest`'s verified/idempotent backend; split
  `pair_recycle_bin`'s catalog-filter logic from its bin-specific path
  reconstruction so recover+export share one backend. Should get append-only
  checkpoint/resume from day one (DA-005b-1 pattern) — this dock has demonstrated,
  repeatable disconnect risk, not hypothetical.
- **DA-007 archive-triage — priority bumped.** Proven at scale twice now (DOSTB
  3.8k archives; DATA0 16k archives, 14,933 w/ GNSS). Promote from low-pri
  carve-mode prototype to a real subcommand.
- Memory: `drive_arch_export_resilience_lessons` (dock/TLP details, DA-009/007
  rationale).

## Session 2026-07-06 — TCT stick investigation (CLOSED, negative)
- 4GB "General UDisk" (mount D113-F76B): survey 0 files → raw-device forensics:
  boot sector = fresh Linux `mkfs.fat`; full 3.75 GiB signature scan (PDF/JPEG/PNG/
  PK/TCT-strings) = zero hits; data area = 0xFF fill (NAND erased state).
- VERDICT: TCT document never recoverably on this stick — new/blank stick, or dead
  controller (erased-mapping failure) reformatted afterward. Software recovery
  exhausted; chip-off only theoretical path.
- Alfie's follow-ups (non-code): ask developer to re-send scan; certified true copy
  from Registry of Deeds; locate paper owner's duplicate.
- Artifacts: `~/surveys/UDisk-D113-F76B/` (carve_scan.py + findings). Lessons →
  memory `drive_arch_forensics_lessons` → tickets DA-007/DA-008 below.
- Cleanup: `sudo setfacl -b /dev/sdc` or replug clears the read ACL.

## Completed 2026-07-04
- **DA-005a** TUI phase 1 (drive picker + survey) — PR #48 merged.
- **DOSTB GNSS evacuation COMPLETE** — 14,269 files verified on Backup Plus
  `RECOVERED_DOSTB20150918/`: 14,080 from $RECYCLE.BIN ($I/$R pairing) + 86 live
  (`_LIVE/`) + 103 campaign companions (`_COMPANIONS/`). Checksum-verified (rsync -c).
  Bulk = 2021 June North Luzon cGPS (IESAS). Archive triage: no field GNSS in the
  3,831 archives (all IGS/EU-station test data). Manifests/scripts:
  `~/surveys/DOSTB20150918/`. SSD staging deleted. DOSTB bin-empty = Alfie manual.
- **DA-006** `drive-arch recover pair|copy` — PR #49 merged (incl. CR fixes:
  `..` traversal → `_orphaned/`, errors persisted to `<output>.errors.txt`).
- **Drive policy set:** 1TB Backup Plus = project property, official GNSS home;
  2TB DOSTB = personal, GNSS evacuated.

## DA-005b DONE 2026-07-04 (design approved then implemented same day)
- PR #50: append-only checkpoint log (3.6s vs 18.5s @200k paths; API unchanged).
- PR #51 (landed on main via #52 — gh retarget silently failed, watch for that):
  detached-subprocess scan jobs (`scanjobs.py`), registry in
  `$XDG_STATE_HOME/drive-arch/`, TUI scan screen + clobber dialog + reattach,
  survey [F] wired. SIGINT-pause/resume proven over 8000-file real subprocess run.

## NEXT TASK (recommended): DA-005c — Explore screen
Category tree + filters + SQLite side-index over full-scan JSONL (TUI_PLAN.md §4).
Alternative next: classifier tickets (below) — small, self-contained.

## Also open
- **Legacy 3.5" HDD — BLOCKED ON HARDWARE (diagnosed 2026-07-06):** adapter is a
  bare bus-powered Ugreen USB-SATA cable (174c:225c, serial 20D11E806285) — 5V only.
  3.5" drives need 12V; "Media removed" = platters never spin. NOT a drive fault.
  ACTION: buy powered USB-SATA dock/enclosure (12V brick, 3.5"-capable — also covers
  the 5TB NAS drives). Then: mount READ-ONLY, `drive-arch survey`, standard funnel.
- **DA-008 survey forensics (NEW, small):** empty-drive diagnostics proven on the
  D113-F76B stick hunt 2026-07-06 — boot-sector OEM string disclosure, suspicious-empty
  warning instead of bare safe-to-wipe, 0x00/0xFF blank-media sampling (needs optional
  raw read access). Details in memory `drive_arch_forensics_lessons`.
- **DA-007 carve mode (low-pri):** signature scan as escalation; working prototype
  `~/surveys/UDisk-D113-F76B/carve_scan.py`.
- **Classifier tickets:** $I/$R prefix awareness (5,500 stubs counted as GNSS on
  DOSTB, +28% inflation); `.iNN` ancillary pattern (APAR132m.i46 missed); archive
  entry-listing triage mode (list zip/gz contents without extraction).
- **Backup Plus migration EXEC** (Phase 3): manifest ready
  `~/surveys/BackupPlus/migration_manifest_v2.tsv` (96k files, 133.7 GiB). Still
  blocked: ≥140 GiB target disk + 30S_01H-vs-30S_1H decision. Note: recovered
  DOSTB data now also on this drive awaiting canonical DATAPOOL placement.
- ING-005 gfzrnx QC backend (license-gated); BRN-001 R740 Bernese install.
- Worktrees `.trees/da-005a-tui`, `.trees/da-006-recovery`, `.trees/da-005b1-checkpoint`, `.trees/da-005b2-scanscreen` — all merged, prunable.

## Workflow reminders (see memory)
- Worktree per feature; `uv sync --extra dev --extra drive-archaeologist
  [--extra drive-archaeologist-tui]` inside; `git checkout -- uv.lock` unless deps changed.
- Tests via `uv run --no-sync`. PRs via `bash scripts/open_pr.sh`; merge via
  `bash scripts/merge_pr.sh <n>`; verify origin/main advanced (retry on
  "base branch was modified" race). NO Claude/AI refs in commits.

## State snapshot
- main = `c5007ab` (PRs #48-#52 all merged: TUI, recover, checkpoint, scan screen).
- Backup Plus (1TB, project): mounted rw, holds RECOVERED_DOSTB20150918 (9 GB).
- DOSTB (2TB, personal): GNSS evacuated; bins await Alfie's manual empty.
- /home freed to ~7.7G (lean_machine run 2026-07-04; docker prune line is a hazard
  when TimescaleDB is up — volumes of stopped containers get wiped).
