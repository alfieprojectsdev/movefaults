# gps3 Claude Code — Session Handover

**Written:** 2026-07-29 by the Claude Code session running on the T420
**For:** a Claude Code session running *on gps3 itself*, to troubleshoot live
**Purpose:** storage provisioning (~32.6 TB unallocated), then GNSS orchestration

---

## 0. Provenance — how much to trust this document

Unlike the earlier `BERNESE_GPS3_HANDOVER.md` (which was reconstructed from
phone photos and got its central diagnosis **wrong**), everything marked
**VERIFIED** below was produced by running the command over SSH and reading
real output. Items marked **INFERRED** or **UNVERIFIED** were not confirmed,
mostly because they need `sudo` and the T420 session had no password.

That distinction matters. The previous handover confidently proposed a fix
(`U="${C}/USER"`) that would have caused damage — see §5. **Re-derive before
acting.** You have a shell; use it.

Also worth knowing: the T420 session that wrote this made several mistakes
during the work (a heredoc that crashed the installer under `set -u`, an
over-escaped snippet, a redaction that leaked a token, a `numfmt` fallback
that would have silently skipped a filesystem grow). All were caught by
testing. **Treat this document as a strong prior, not as truth.**

---

## 1. Confirm you are where you think you are

```bash
hostname          # expect: gps3
whoami            # expect: gps3
ip -br -4 addr    # expect: eno4  192.168.48.98/24
```

The counterpart machine is a ThinkPad **T420** (user `finch`), which holds the
reference Bernese install and the source GNSS data. It reaches gps3 over wifi
(`GNSS_5G2`). SSH key auth T420→gps3 is set up and working.

---

## 2. Verified current state

### Bernese 5.4 — installed and numerically verified

**VERIFIED 2026-07-28.** The EXAMPLE campaign RNX2SNX BPE ran clean:

```
Sessions finished: OK: 1    Error: 0    Total Time: 00:11:23
114 jobs, 0 errors, 0 reruns
```

SINEX comparison against the shipped reference:

| | |
|---|---|
| produced | `$P/EXAMPLE/SOL/FIN_20230100.SNX` |
| reference | `$S/RNX2SNX/2023/SOL/FIN_20230100.SNX.gz_REF` |
| **max diff** | **0.0000 mm** across 54 params (18 stations × STAX/STAY/STAZ) |

That is an exact match with the T420's result, so **numerical parity between
the two machines is settled**. gps3 ran it in 11m23s vs the T420's 20m40s.

Present and confirmed: `$U` (GPSUSER, freshly generated), `$T` (GPSWORK),
`DE421.EPH` at `$MODEL`, `CRX2RNX` at `$EXE`, EXAMPLE campaign under `$P`
(36 RAW / 8 ORB files), DATAPOOL REF54 symlinks.

`~/.bashrc:125` sources `LOADGPS.setvar`. **Interactive shells only** — the
Debian early-return guard at `~/.bashrc:8` means `ssh gps3 'cmd'` will NOT
have `$C`/`$U` set. Scripts must source it explicitly:

```bash
source ~/BERN54/LOADGPS.setvar
```

### Storage — the current task

**VERIFIED:** `sda` is a **32.7 TB Dell PERC H750 hardware-RAID virtual disk**
(`/sys/block/sda/device/model` = `PERC H750 Adp`, rotational). Partitioned as
`sda1` 1 G EFI, `sda2` 2 G `/boot`, `sda3` 32.7 T LVM2_member. The volume
group `ubuntu-vg` contains exactly one LV: `ubuntu-lv`, **100 G**, ext4, `/`.

**INFERRED (confirm before acting):** therefore ~32.6 TB is free extents. This
was deduced from `lsblk` because `vgs` needs sudo. **Confirm first:**

```bash
sudo vgs ubuntu-vg
sudo vgdisplay ubuntu-vg | grep -i free
```

The provisioning script re-checks this itself and refuses to run if short.

**VERIFIED:** root is at 74% (25 G avail) — which is why the 18 G PAGENET
transfer was deliberately *not* run. It would have taken root to ~93%.

---

## 3. The task: provision storage

Two scripts are already in `/home/gps3/` (copied 2026-07-29, shellcheck-clean,
tested on the T420):

| script | does |
|---|---|
| `gps3_storage_provision.sh` | grow root, create LVs, mkfs, mount, fstab. **Safe.** |
| `gps3_gpsdata_migrate.sh` | move existing GPSDATA onto its own LV. **The risky one.** |

Both are **dry-run by default** and print every command before running it.

### Planned layout

| LV | Size | FS | Mount | Purpose |
|---|---|---|---|---|
| `ubuntu-lv` *(exists)* | 100 G → **250 G** | ext4 | `/` | OS only |
| `lv_gpsdata` | **4 TB** | XFS | `~/GPSDATA` | live campaigns, DATAPOOL, SAVEDISK |
| `lv_archive` | **20 TB** | XFS | `/srv/gnss-archive` | legacy data from external drives |
| `lv_work` | **1 TB** | XFS | `~/GPSWORK` | BPE scratch (`$T`) |
| *free* | **~7 TB** | — | — | headroom |

Mount points were chosen so **`LOADGPS.setvar` needs no edits** — `$P`/`$D`/`$S`
already resolve under `$HOME/GPSDATA` and `$T` is `$HOME/GPSWORK`.

~7 TB is left unallocated deliberately: **LVM grows online in seconds, XFS can
never shrink.** Free extents cost nothing and cover a wrong guess.

### Order of operations

```bash
# ALWAYS in tmux — the T420's wifi has dropped mid-session before, and an
# SSH drop during resize2fs would SIGHUP it
tmux new -As storage

sudo ./gps3_storage_provision.sh              # dry run, read the output
sudo ./gps3_storage_provision.sh --apply
sudo ./gps3_gpsdata_migrate.sh --sync         # rsync + verify, repeatable
sudo ./gps3_gpsdata_migrate.sh --swap         # cutover, asks for typed confirmation
```

### ⚠ PREREQUISITE — verify the RAID level first

**UNVERIFIED and important.** If gps3 becomes the archive's home, we must know
whether that 32.7 TB is redundant. The legacy GNSS archive currently exists as
a *single copy* on an external drive with a pending sector, so this matters.

```bash
sudo dmesg | grep -i megaraid
sudo apt install megacli && sudo megacli -LDInfo -Lall -aALL
# or read it from the iDRAC web UI
```

**RAID 6/10 → proceed. RAID 0 → gps3 must not be the only copy.**

---

## 4. DO NOT

1. **Do not run `scripts/deploy_r740.sh` against gps3.** Its Phase 1 step
   `[6/6]` does `rsync -avz ~/GPSUSER/ gps3:~/GPSUSER/`, which would push the
   **T420's** GPSUSER over the clean one generated here. The T420's copy has
   **56 INP files with hardcoded `/home/finch` paths**. That reintroduces the
   original blocker in a worse form — not a missing directory, but wrong paths
   silently baked into panel files. The script is otherwise untested.

2. **Do not repoint `$U` at `${C}/USER`.** See §5.

3. **Do not `mkfs` with `-f`** on anything in this plan. The scripts omit `-f`
   on purpose so mkfs refuses a device that already holds a filesystem. That
   guard is what turns a typo into an error instead of a wipe.

4. **Do not mount a new volume over a non-empty directory.** It hides the
   contents and strands the old copy consuming root space. The migrate script
   renames first, then mounts.

5. **Do not delete `GPSDATA.old-<date>`** until Bernese has been re-verified
   against the new mount. That directory *is* the rollback.

6. **Do not run bulk transfers and a BPE at the same time.** Headless BPE on
   the T420 is known to hang (lost RUNBPE→server handshake) under concurrent
   heavy I/O. Both scripts refuse to run while a BPE process is detected.

7. **Do not trust `rsync` exit=0 as proof of a complete copy.** This project
   lost a session to exactly that. Verify with per-directory counts.

---

## 5. Things that look broken but are not

These wasted real time. Check here before diagnosing.

### `$U` vs `$USR` — the trap the last handover fell into

`$USR` = `${C}/USER` = `/home/gps3/BERN54/USER` — the **template** area shipped
inside BERN54.
`$U` = `${HOME}/GPSUSER` = `/home/gps3/GPSUSER` — the **live per-user working
tree**.

These are **distinct by design**. The previous handover saw `$U` missing,
concluded the variable was misconfigured, and proposed `U="${C}/USER"`. That
would collapse the template and live areas into one and misdirect BPE campaign
paths — the same failure its own "Do NOT symlink" section warned against.

The correct fix (already applied) generates the tree fresh:

```bash
source ~/BERN54/LOADGPS.setvar
printf "3\ny\nx\n" | perl $C/SCRIPT/EXE/configure.pm    # menu option 3
```

Guard it with `timeout` — `configure.pm`'s `_yesNo()` is a `while(1)` that
spins forever on unexpected stdin EOF.

Never copy a working `$U` from another machine; its INP files carry that
machine's absolute paths.

### `pgrep -f rnx2snx_pcs.pl` always says "running"

Over SSH it **matches its own command string**. Use `pgrep -af` and look at
what actually matched.

### `grep -c error` on `RNX2SNX.OUT` returns 3 on a *successful* run

The summary line `Error: 0` and two table headers contain the word. Read the
`Sessions finished: OK: n  Error: n` line instead.

### `Cannot open INP file .../GEN/SESSIONS.SES`

Normal fallback probe, **not a defect**. `SESSIONS.SES` is **per-campaign**
(`$P/<CAMPAIGN>/GEN/SESSIONS.SES`); gps3's EXAMPLE campaign has one. The
verified T420 has no `$U/GEN` either. **Do not create `$U/GEN/SESSIONS.SES`** —
a user-level table could override per-campaign ones.

### Fortran binaries reference `/home/finch/...` in error messages

Compiled-in debug paths from the T420 build. Cosmetic, not functional.

### `/home/gps3/home/ltpt420`

A botched-rsync artifact from Nov 2025. Unrelated, harmless.

---

## 6. Network — why things are slow

**VERIFIED by measurement:**

| path | throughput |
|---|---|
| T420 wifi `GNSS_2G` (2.4 GHz) | **0.56 MB/s** |
| T420 wifi `GNSS_5G2` (5 GHz) | **6 MB/s** ← currently in use |
| direct cable | ~110 MB/s *(estimated, untested)* |

The T420's **ethernet is on `192.168.40.0/24` while gps3 is on
`192.168.48.0/24`, with no route between them** (verified: 100% loss forcing
`-I enp0s25`). That is why wifi is involved at all.

**gps3 has three unused gigabit NICs** — `eno1np0`, `eno2np1`, `eno3` are all
`down`; only `eno4` carries the LAN. A direct cable into any of them gives a
private gigabit link. `~/repos/hardline/direct_link.sh` on the T420 (11.6 KB,
exists) plus `deploy_r740.sh --direct` were written for this, but **both are
untested** — and see §4.1 before running the latter.

**Remote access available:** Cockpit is listening on `:9090` (**VERIFIED**),
and `/dev/ipmi*` exists so the BMC/iDRAC is present (**VERIFIED** — but whether
its NIC is cabled and reachable is **UNVERIFIED**; confirm before relying on it
for boot recovery).

`sudo` **requires a password** — `ssh gps3 'sudo ...'` fails without `-t`.

---

## 7. Outstanding

| item | status |
|---|---|
| **Rotate the Claude OAuth token** | **urgent** — see below |
| Verify PERC RAID level | blocks treating gps3 as the archive's only home |
| Run the storage scripts | ready, needs sudo |
| PAGENET transfer | deliberately deferred; only ~12.5 G of the 18 G is worth copying (`RAW`+`SOL`; skip `OUT` logs and `OBS`, which RXOBV3 regenerates) |
| Deploy the orchestrator | `services/bernese-workflow/` — 128 tests pass but it has **never driven a real BPE**. This is the actual next unknown. |
| Legacy archive → `lv_archive` | ~150 G, currently single-copy on an external drive with a pending sector |
| `deploy_r740.sh` GPSUSER hazard | unfixed |

### Token — UPDATED 2026-07-29 11:35, supersedes anything above

A 108-char `sk-ant-oat01-…` static token was accidentally printed into the
T420 session's transcript. Cleanup already performed from the T420:

- ✅ `export CLAUDE_CODE_OAUTH_TOKEN=…` **removed from `~/.bashrc`** (was line
  120; `LOADGPS` is now line 124). Verified absent from interactive shells,
  `.bashrc` parses, Bernese env still resolves.
- ✅ Both `~/.bashrc.bak*` files **shredded** — both contained the token line.
- ⬜ **Remaining: revoke it at claude.ai → Settings** (a human must do this),
  and strip `OAUTH_TOKEN` from `scripts/deploy_r740.secrets` on the T420.

**CORRECTED 2026-07-29 15:40 — this session IS authenticated with that
token.** `/status` reports `Auth token: CLAUDE_CODE_OAUTH_TOKEN`, so the env
var takes **precedence** over `~/.claude/.credentials.json`. An earlier
version of this file said the opposite; it was wrong.

It survived the `.bashrc` strip because the Cockpit shell started 11:20:54,
~13 min before the line was removed at 11:33:41 — it exported the token into
its live environment and every child since inherits it. All files are clean;
it is a stale in-memory export in one long-lived shell.

**Before the token is revoked:** close that terminal / open a fresh shell (or
`unset CLAUDE_CODE_OAUTH_TOKEN`), relaunch `claude`, and confirm `/status` no
longer names the env var. Revoking first will break this session mid-work.

**Gotcha when scanning:** interactive OAuth credentials use the **same
`sk-ant-oat01-` prefix**, so `grep -r sk-ant-oat01 ~` matches
`.credentials.json` legitimately. A hit there is expected — do not "clean" it.

Do NOT re-add the token to `~/.bashrc`. Note `deploy_r740.sh` Phase 3 would
reintroduce it — another reason not to run that script (see §4.1).

---

## 7a. UPDATE 2026-07-29 ~15:00 — storage work is DONE

The storage task in §3 was **completed and independently verified**. Do not
redo it. Current state: `lv_gpsdata` 4 T on `~/GPSDATA`, `lv_archive` 20 T on
`/srv/gnss-archive`, `lv_work` 1 T on `~/GPSWORK`, root grown to 250 G,
~7.5 T free extents. BPE re-verified on the new volumes: 11 m 28 s, max SINEX
diff 0.000020 mm. Rollback copy retained at `~/GPSDATA.old-20260729`.

Verified from the T420 against a pre-change baseline: **0 files missing**, and
the rollback copy is byte-identical to the baseline (4,262 / 3 / 4,807,040,204).

**Census gotcha for any future check:** the live mount now reads **4,274 files
/ 4,807,069,710 bytes — higher** than the baseline, because the BPE re-verify
wrote 12 new files and rewrote 728. Loss shows as FEWER files. Compare against
`~/GPSDATA.old-20260729`, not across a BPE run.

**Thanks for the `fuser -m` catch** — that was a real blocker in the migrate
script (it escalates to the whole filesystem when `$SRC` isn't yet a
mountpoint, so `--swap` always died). Your `lsof +D` fix is now in the repo
copy, with both traps documented in comments: the exit-1-on-clean-tree that
needs `|| true` under `set -euo pipefail`, and the self-match if cwd is inside
`$SRC`. Verified separately that the `[ "$MODE" = swap ] && die` pattern
elsewhere in the script is safe under `set -e`.

One reconciliation: your note says the handover's `Sessions finished: OK: 1`
phrasing came from a different wrapper. Both strings are real —
`rnx2snx_pcs.pl`'s own log says `BPE finished at ...`, while
`Sessions finished: OK: n  Error: n` appears in
`$P/EXAMPLE/BPE/RNX2SNX.OUT`. Different files, not a contradiction.

## 8. Repo sync + two-machine coordination

**`~/repos/movefaults_clean` is NOT a clone** — one stray
`.claude/settings.local.json` from a Claude session started there. You have
been working from `scp`'d copies.

**gps3 already has working GitHub auth** (`ssh -T git@github.com` →
"Hi alfieprojectsdev!", git identity set), so cloning needs no new credentials:

```bash
rm -rf ~/repos/movefaults_clean
git clone git@github.com:alfieprojectsdev/movefaults.git ~/repos/movefaults_clean
cd ~/repos/movefaults_clean && git checkout docs/bernese-training-notes
```

Caveats: `gh` CLI auth is **expired** here (irrelevant for git-over-SSH; run
`gh auth login` only if you want `gh pr`). And that branch is **stale vs
`main`** for `tools/drive-archaeologist` — missing DA-002/DA-006.

### One writer per file — both sessions can now push

| file / area | owner |
|---|---|
| `RESUME_NEXT.md` | **T420 only** — don't edit it here |
| `docs/GPS3_SESSION_HANDOVER_*.md` | **T420 only** (this file) |
| your session logs | **you** — dated files under `docs/gps3-sessions/` |
| `scripts/gps3_*.sh` | either, `git pull --rebase` first |
| results observed on gps3 | you are authoritative; T420 verifies independently |

Always `git pull --rebase` before committing. The T420 session holds the
pre-change baselines and will keep cross-checking your results — that is the
point of running two sessions, not redundancy.

## 9. If you get stuck

The T420 session has the full history and can be consulted through the user.
Its notes live in `RESUME_NEXT.md` (see §8 for how to get a real clone).

Bias toward **verifying over assuming**. Every significant error in this
project's recent history came from acting on a plausible-but-unchecked
diagnosis. You have a shell and the machine is idle — grounding a claim is
usually a single command.
