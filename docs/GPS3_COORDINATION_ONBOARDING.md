# gps3 Claude Code — Repo Sync & Inter-Machine Coordination

**Written:** 2026-07-29 (late) by the Claude Code session on the T420
**For:** the Claude Code session running on gps3
**Supersedes:** the coordination parts of `~/HANDOVER.md` (§8). That file's
storage-task content is still accurate but the task is **done** — see §1.

**This document lives in the repo** at `docs/GPS3_COORDINATION_ONBOARDING.md`.
Once you have pulled (§3), read it from there rather than from a `scp`'d copy —
the repo version is the one that gets updated.

---

## 0. Standing instruction: verify, don't inherit

Everything here was produced by running commands over SSH and reading real
output. Even so — **re-derive before acting on anything consequential.**

This project's recent history is a list of confident, plausible, wrong
diagnoses that cost real time:

- The first gps3 handover diagnosed the `$U` blocker and proposed a fix that
  would have collapsed the template and live user areas. Wrong.
- The T420 session (me) shipped a heredoc that crashed the installer under
  `set -u`, an over-escaped snippet, a `numfmt` fallback that would have
  silently skipped a filesystem grow, and a redaction that leaked a token.
- I told you `apt install storcli`. It is not in the repos. You found that.
- I claimed revoking the leaked token would not disconnect you. `/status`
  proved the opposite.
- You found `fuser -m` in my migrate script — a genuine blocker that made
  `--swap` fail unconditionally. My testing never exercised that branch.

That last pair is the point of running two sessions. **You are not a
subordinate executing my plan; you are the second pair of eyes.** When
something here is wrong, say so — that has already happened twice today and
both times you were right.

---

## 1. Storage task: DONE. Do not redo it.

Completed and verified 2026-07-29. Current state:

| LV | Size | FS | Mount |
|---|---|---|---|
| `ubuntu-lv` | 250 G | ext4 | `/` (30% used) |
| `lv_gpsdata` | 4 T | XFS | `~/GPSDATA` |
| `lv_archive` | 20 T | XFS | `/srv/gnss-archive` — **still empty** |
| `lv_work` | 1 T | XFS | `~/GPSWORK` |
| free extents | ~7.5 T | — | headroom |

Verified from the T420 against a pre-change baseline: **0 files missing**, and
`~/GPSDATA.old-20260729` is byte-identical to the baseline (4,262 files /
3 symlinks / 4,807,040,204 bytes). BPE re-verified on the new volumes:
11 m 28 s, max SINEX diff 0.000020 mm.

**Census gotcha, still true:** the live mount now reads **more** files than
that baseline (4,274 / 4,807,069,710 B) because the BPE re-verify wrote 12 new
files and rewrote 728. Data loss shows as **fewer**. Always compare against
`~/GPSDATA.old-20260729`, never across a BPE run.

`~/GPSDATA.old-20260729` (4.5 G on `/`) is the rollback. Do not delete it
without the user explicitly saying so.

---

## 2. Your RAID work — verified, and it changed the plan

Your conclusion (**16 × Toshiba AL15SEB24EQY 2.4 TB SAS, RAID 5**) was
independently re-derived on the T420 from the measured VD size. It holds:

| candidate | capacity | vs measured 35,997,194,649,600 B |
|---|---|---|
| RAID 0 (16 data) | 38.400 TB | +6.67% |
| **RAID 5 (15 data)** | **36.000 TB** | **+0.01%** ✓ |
| RAID 6 (14 data) | 33.600 TB | −6.66% |

Your dismissal of "15 × RAID 0 + hot spare" is sound, and the same arithmetic
rules out a hot spare existing at all. Reporting `optimal_io_size=4` as
**uninformative rather than corroborating** was the right call — dressing it
up would have been the easy mistake.

One number to add: the rebuild reads all 15 survivors = 36 TB. At the
enterprise-SAS spec of 1e-16, URE risk per rebuild is **~3.1%** — real but not
alarming. The widely-quoted "RAID 5 is dead" figure of ~94% assumes consumer
SATA at 1e-14 and does not apply to these drives. Worth stating precisely,
because the scary version of that number gets repeated a lot.

---

## 3. Pulling changes (your clone is 3 commits behind right now)

State as of writing: branch `docs/bernese-training-notes`, HEAD `0d18054`,
clean tree, **3 commits behind**, and `git push --dry-run` is **rejected**
(non-fast-forward) — you must pull before you can push.

```bash
cd ~/repos/movefaults_clean
git pull --rebase          # ALWAYS --rebase, see below
git log --oneline -5
```

**Always `--rebase`, never a plain merge.** Two machines committing to one
branch with plain merges produces a lattice of merge commits that makes the
history unreadable — which matters more than usual here, because this repo's
commit log is doubling as the project's decision record (see §6).

Before you commit anything:

```bash
git pull --rebase && <make your change> && git add -p && git commit && git push
```

If a rebase conflicts, **stop and tell the user** rather than resolving a
conflict in a file you do not own (§5). `git rebase --abort` is always safe.

---

## 4. ⚠ The branch problem — no single branch holds the truth

This is currently the **single worst structural problem in the project**, and
it is not yours to fix unilaterally — but you must know about it before you
touch git.

| | commits |
|---|---|
| `origin/main` has, this branch lacks | **22** — VADASE PRs #53–56, drive-arch DA-002/DA-006 hardening |
| this branch has, `origin/main` lacks | **39** — the entire gps3 Bernese install, storage provisioning, handovers, `scripts/gps3_*.sh` |

Consequences that will bite you:

- **A fresh clone lands on `main` and gets none of the gps3 work.**
- Conversely, **your current branch is missing DA-002/DA-006** — so
  `tools/drive-archaeologist` here is the old, unhardened version. Do not use
  `drive-arch` from this checkout for real scanning work; it lacks the symlink
  cycle guard and the `recover` subcommand.

Reconciling these is Tier 0 work (§6) and needs the user's decision on
approach. **Do not merge or rebase the branches on your own initiative.**

---

## 5. Coordination protocol — one writer per file

Both machines can now push to `docs/bernese-training-notes`. To avoid races:

| file / area | owner |
|---|---|
| `RESUME_NEXT.md` | **T420 only** — do not edit |
| `docs/GPS3_SESSION_HANDOVER_*.md`, this file | **T420 only** |
| your session logs | **you** — new dated files under `docs/gps3-sessions/` |
| `scripts/gps3_*.sh` | either, `git pull --rebase` first |
| anything executed on gps3 | **you are authoritative for observed results**; the T420 verifies independently |

That last row is the important one. When you run something on gps3, your
observation is the primary evidence. The T420 session holds pre-change
baselines and re-derives your conclusions from them — not to second-guess you,
but because a claim confirmed two independent ways is worth far more than one
asserted confidently. Both of today's corrections came out of that loop.

**Please move your session log into the repo.** It currently lives at
`/home/gps3/SESSION_LOG_20260729_storage.md`, outside version control, on the
one machine it documents. Suggested:

```bash
mkdir -p ~/repos/movefaults_clean/docs/gps3-sessions
git mv 2>/dev/null || cp /home/gps3/SESSION_LOG_20260729_storage.md \
  ~/repos/movefaults_clean/docs/gps3-sessions/SESSION_LOG_20260729_storage.md
cd ~/repos/movefaults_clean && git pull --rebase && git add docs/gps3-sessions && \
  git commit -m "docs(gps3): storage provisioning session log 2026-07-29" && git push
```

It is a good log — the `fuser`/`lsof` root-cause writeup and the "gotchas
discovered" section are exactly the kind of thing that gets lost otherwise.

---

## 6. Why the git history matters more than usual

An audit this session found that a successor inheriting this project today
would face, in order of severity:

1. **The code of record is on a personal GitHub account**
   (`alfieprojectsdev/movefaults`). Nobody at PHIVOLCS can grant access to it.
   The risk is not losing the data — it is losing *the knowledge of how to use
   the data*.
2. **No single branch holds the truth** (§4).
3. **No archive manifest** — 157 GB / ~155k files with no document stating
   stations, date ranges, raw-vs-derived, gaps, or provenance.
4. **No fixity** — zero checksums anywhere, so silent bit rot is undetectable.
5. Only complete copy on personal hardware. *The hardware ranks fifth.*

The user is a 15-year PHIVOLCS employee thinking explicitly about how this data
outlives staff turnover. That reframes routine work: commit messages, session
logs, and runbooks are not housekeeping here, they are the succession plan.
Write them for someone who arrives in 2031 with no context.

**Tier 0 items where you can help directly** (all free, all on gps3):

- **Mirror the repo onto agency hardware** — gps3 has 32 TB and git:
  ```bash
  git clone --mirror git@github.com:alfieprojectsdev/movefaults.git \
    /srv/gnss-archive/git/movefaults.git
  # then a cron: git --git-dir=/srv/gnss-archive/git/movefaults.git remote update --prune
  ```
  This puts the knowledge on PHIVOLCS property regardless of what happens to
  any personal account. ~10 minutes.
- **Populate `/srv/gnss-archive`** — 20 TB of RAID 5 sits empty while the only
  complete copy of the legacy archive (157 G) is on the user's personal
  external drive. This alone goes from one copy to two on independent
  hardware. Source is the T420's DOSTB mount; coordinate with the user.
- **`sha256sum` manifest** of whatever lands in `/srv/gnss-archive`, stored
  both with the archive and in git.

---

## 7. Your open question: yes to smartd, with one hard constraint

You offered to write the smartd config. Please do — with this caveat, which I
verified on gps3:

**Do not use `-m root`.** There is **no MTA installed** (no
postfix/exim/sendmail/msmtp), and `/etc/smartmontools/run.d/` contains only
`10mail`. Mail-based alerts would be generated and silently discarded. That
would be *worse* than the current state, because a configured-looking monitor
that drops every alert is more dangerous than an obviously absent one.

Current state confirms the problem you identified: `smartd` is **active** but
its config is stock `DEVICESCAN`, which cannot see behind the PERC. It is a
green service monitoring **zero drives**.

Requirements:

1. **16 explicit lines**, `/dev/sda -d megaraid,0` … `megaraid,15`.
2. **A non-mail sink**: `-M exec /usr/local/sbin/smartd-alert`, where that
   script does `logger -t smartd-alert -p daemon.crit "$SMARTD_MESSAGE"` **and**
   appends to `/var/log/smartd-alerts.log`. journald has 322 MB retained, and
   the flat file is pollable from the T420 — which makes the alerting
   externally observable instead of something we assume works.
3. **Stagger the long self-tests.** Sixteen `L/../../6/03` lines scrub all
   drives simultaneously at 03:00 Saturday; spread them so a scrub cannot
   collide with a BPE run.
4. **Verify registration, don't trust status.** `smartd -q onecheck` must
   report **16 devices**, not 0. "Service is active" is exactly the false
   signal we are fixing.

Then please **test the alert path end to end** — e.g. `-M test` on one device —
and confirm a line actually lands in both journald and the log file. An
untested alert path is an assumption, and this array has **no hot spare**, so
early warning is the primary defense against a degraded-array window that
lasts until someone physically swaps a drive.

Also still open: kernel `6.8.0-136` is installed, `6.8.0-111` running. The
first reboot is also the first real test of the new fstab — all entries are
`nofail` and `findmnt --verify` passed, so it should be uneventful, but it is
better done deliberately with someone watching than during an unplanned
reboot.

---

## 8. Still true, still worth not relearning

- **`!` gives sudo no controlling tty**, and priming `sudo -v` does not help —
  the Bash tool's shell has **no controlling terminal at all** (`ps` shows
  `TT=?`), so with sudo's default `tty_tickets` a ticket cached in the user's
  pts can never match. Run privileged commands in a real terminal, tee to a
  log, and read the log. This works well; keep doing it.
- **`pgrep -f <pattern>` matches your own command line.** Bit both sessions.
  Use `pgrep -af` and inspect, or match on a pinned PID.
- **`grep -ciE "error"` on `RNX2SNX.OUT` returns 3 on a clean run** — the
  `Error: 0` summary line plus two table headers. Read the
  `Sessions finished: OK: n  Error: n` line instead.
- **Completion strings differ by launcher:** `rnx2snx_pcs.pl`'s own log says
  `BPE finished at ...`; `Sessions finished: ...` appears in
  `$P/EXAMPLE/BPE/RNX2SNX.OUT`. Both real, different files.
- **`*.SNX.gz_REF` is gzipped** — compare with `gunzip -c`.
- **`$U` vs `$USR` are distinct by design** — never repoint `$U` at
  `${C}/USER`, and never copy a working `$U` from another machine (the T420's
  has 56 INP files with `/home/finch` baked in).
- **Do not run `scripts/deploy_r740.sh`** — Phase 1 step `[6/6]` rsyncs the
  T420's contaminated `GPSUSER` over the clean one here, and Phase 3
  reintroduces the `CLAUDE_CODE_OAUTH_TOKEN` line that was just removed from
  `~/.bashrc`.

## 9. Token status

The leaked static token has been removed from `~/.bashrc`, and both
`~/.bashrc.bak*` files (which still contained it) were shredded. All config
files are clean.

**But it may still be live in your process environment.** The Cockpit shell
that launched you started at 11:20:54, ~13 minutes *before* the line was
stripped at 11:33:41, so it captured the value and passes it to every child.
`/status` showed `Auth token: CLAUDE_CODE_OAUTH_TOKEN`, meaning the env var
**outranks** `~/.claude/.credentials.json`.

Before the user revokes that token at claude.ai: close that terminal / open a
fresh shell (or `unset CLAUDE_CODE_OAUTH_TOKEN`), relaunch `claude`, and
confirm `/status` no longer names the env var. Revoking first breaks your
session mid-work.

Note when scanning: interactive OAuth credentials use the **same
`sk-ant-oat01-` prefix**, so a `grep` hit on `.credentials.json` is expected
and legitimate — do not "clean" it.
