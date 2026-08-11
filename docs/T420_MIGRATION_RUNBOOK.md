# T420 → New Laptop: Migration Runbook

**Drafted:** 2026-07-30 · **Execute:** when the replacement machine arrives
**Scope:** the workstation that holds MOVE Faults' reference Bernese install,
the GNSS working data, and SSH access to gps3.

Personal and client-work migration is out of scope here — §7 gives the method
for those without enumerating them in an agency-bound repo.

---

## 0. Why this exists, and the honest risk picture

The T420 is a **single point of failure for the project**, not just for Alfie.
It holds the only local reference Bernese install, the campaign data, the keys
to gps3, and the accumulated working context. This runbook exists so a
replacement is a half-day of checklist rather than a reconstruction.

**Measured 2026-07-30:**

| item | size | also exists elsewhere? |
|---|---|---|
| `~/BERN54` | 2.5 G | ✅ gps3 (verified 0.0000 mm parity) + 2 thumb drives |
| `~/GPSDATA` | 22 G | ⚠️ partial — gps3 has 4.5 G; PAGENET 18 G is T420-only |
| `~/Qt4.8.7` | 261 M | ✅ gps3 + SANDISK8G offline kit |
| `~/GPSUSER` (`$U`) | 28 M | ❌ **T420-only** — but must NOT be copied (see §4) |
| `~/surveys` | 8.9 G | ❌ **T420-only** — crossref reports, scan JSONLs |
| `~/.claude` | 418 M | ❌ **T420-only** |
| `~/scripts` | 420 K | ❌ **T420-only** |
| `repos_finch` | 26 G, 57 repos | mostly on GitHub — see §7 |

**Disk state at drafting** — this is the "ageing drives" premise, and one row
is a live problem independent of migration:

```
/dev/sda2   48G   27G   19G  59%  /
/dev/sda3  144G  132G  4.2G  97%  /home     <-- 97%, act on this now
/dev/sdb2  117G   90G   21G  82%  /mnt/ssd
```

- `sda` = Kingston SA400S37240G (240 G SSD) — holds `/` and `/home`
- `sdb` = **KimMiDi SSD TB900 128 GB** — an off-brand SSD holding **all 57
  repos**. Unknown endurance, no meaningful warranty path. This is the disk
  whose failure would hurt most and the one least worth trusting.

**Not yet checked: SMART.** Needs sudo, so it wasn't captured at drafting. Do
this FIRST — if either SSD shows reallocated or pending sectors, the migration
stops being scheduled work and becomes urgent:

```bash
sudo apt install -y smartmontools
for d in /dev/sda /dev/sdb; do
  echo "=== $d ==="
  sudo smartctl -H -A "$d" | grep -E "overall-health|Reallocated|Pending|Uncorrectable|Percent|Power_On_Hours"
done
```

---

## 1. Before the laptop arrives (do these now — they reduce risk either way)

- [ ] **Run the SMART check above.** Escalate if anything is non-zero.
- [ ] **Free space on `/home`** (97% is failure-adjacent). `lean_machine.sh
      --dry-run` measured ~8.8 G reclaimable, of which 3.7 G is Trash.
      ⚠️ If Docker is running, that script's `docker system prune -f --volumes`
      will destroy the `db_data` and `grafana_data` volumes (TimescaleDB +
      Grafana). Stop Docker or drop that line before running it.
- [ ] **Push the one repo with unpushed work** — `webdevportfolio_ap`, 6
      commits, local-only.
- [ ] **Audit the 8 repos whose current branch has no upstream** (§7) — those
      are the ones a dead disk would erase.
- [ ] **Get `~/surveys` (8.9 G) onto a second disk.** It is T420-only and it is
      the derived analysis behind the retrieval-priority work.
- [ ] **Rotate the leaked OAuth token** if still outstanding (see
      `RESUME_NEXT.md`) — do it before, so the new machine starts clean.

---

## 2. Claude memory → private repo

**Verified by scan 2026-07-30, on the exact directory proposed:**

| | size | verdict |
|---|---|---|
| `memory/*.md` (30 files) | 196 K | ✅ zero secret patterns, zero client references |
| transcripts `*.jsonl` | 89 M | ❌ **2 files contain the leaked `sk-ant-oat01` token** |
| `~/.claude/CLAUDE.md` (global) | 9 K | ❌ ~40 references to non-PHIVOLCS client work |

`AKIA` hits in transcripts were **false positives** — 0 matches against the
strict AWS-key shape.

### Rules

1. **A commit is permanent.** There is no "temporary commit" — deleting a file
   later leaves it in history, and forks/clones/caches keep it. If a secret
   lands, **rotating it is the only remedy**. Decide as if irreversible.
2. **Private ≠ secret-safe.** Repos get flipped public by accident and access
   widens over time. Private is a courtesy, not a control.
3. **Its own repo — NOT `movefaults`.** That repo is heading toward agency
   records (records disposition schedule, possible IGS/EarthScope deposit).
   Claude's working memory is personal scaffolding, not a project record. The
   project's own succession material already lives in the repo properly:
   `RESUME_NEXT.md`, the gps3 handovers, the runbooks.
4. **Never commit global `~/.claude/CLAUDE.md`** anywhere PHIVOLCS-adjacent.
   It carries another client's team roster, system ownership and commercial
   arrangements — that is a professional problem, not a technical one. (Named
   deliberately vaguely here for the same reason.)

### Steps

- [ ] Create **private** repo `claude-memory-movefaults`.
- [ ] `.gitignore` FIRST, before any `git add`:
      ```gitignore
      *.jsonl
      .credentials.json
      *.log
      shell-snapshots/
      todos/
      statsig/
      ```
- [ ] Copy **only** `memory/` in.
- [ ] **Re-scan the staged content** before the first commit — do not trust the
      2026-07-30 scan, the files will have changed:
      ```bash
      git diff --cached | grep -nE 'sk-ant-|ghp_|gho_|AKIA[A-Z0-9]{16}|BEGIN [A-Z ]*PRIVATE KEY'
      ```
      Any hit → stop, do not commit.
- [ ] Commit, push, verify the repo shows no `.jsonl`.

---

## 3. ⚠ The path-encoding trap (this WILL bite)

Claude Code derives the memory directory name from the working directory,
**replacing every `/` and `_` with `-`**. Current:

```
/mnt/ssd/home/ltpt420/repos_finch/movefaults_clean
  → ~/.claude/projects/-mnt-ssd-home-ltpt420-repos-finch-movefaults-clean
```

On a new laptop with a different layout, **Claude will not find the memory** —
it will silently start empty. This already caused a whole remediation cycle on
this machine (see the SSD-migration section of the global config).

Two ways to avoid it, in order of preference:

- **Reproduce the path exactly** on the new machine — same mount point, same
  directory names. Costs nothing at setup time and makes every encoded key
  match without intervention.
- **Or** rename the memory directory to the new encoding, and symlink the old
  name to it for historical sessions:
  ```bash
  cd ~/.claude/projects
  new="-$(realpath /path/to/movefaults_clean | sed 's|/|-|g; s|_|-|g; s|^-||')"
  mv -- "-mnt-ssd-home-ltpt420-repos-finch-movefaults-clean" "$new"
  ln -s -- "$new" "-mnt-ssd-home-ltpt420-repos-finch-movefaults-clean"
  ```
  The same applies to `~/.cache/claude-cli-nodejs/`, and session `.jsonl` files
  store an absolute `cwd` that `/resume` matches against.

---

## 4. Bernese — rebuild, do NOT copy blindly

`~/BERN54` transfers fine (it is already proven on gps3 and two thumb drives).
`~/GPSUSER` (`$U`) **must not be copied**: its INP panel files carry absolute
paths baked in — **56 such files** on this machine, all pointing at
`/home/finch`. Copying it reproduces the exact class of bug that blocked the
gps3 install.

- [ ] Copy `~/BERN54`, `~/Qt4.8.7`, `~/GPSDATA` (`rsync -aHAX` — **never**
      through a FAT32 drive, which silently destroys symlinks and exec bits).
- [ ] Patch `LOADGPS.setvar`: `$C`, `$BPE_SERVER_HOST`, `$QTBERN`.
- [ ] **Generate `$U` and `$T` fresh:**
      ```bash
      source ~/BERN54/LOADGPS.setvar
      printf "3\ny\nx\n" | timeout 150 perl $C/SCRIPT/EXE/configure.pm
      ```
      Guard with `timeout` — `_yesNo()` is a `while(1)` that spins on stdin EOF.
- [ ] Recreate DATAPOOL REF54 symlinks (`EXAMPLE.CRD/.VEL/.ABB → *_REF`).
- [ ] **Verify by running the EXAMPLE campaign**, not by eyeballing files:
      ```bash
      perl $U/SCRIPT/rnx2snx_pcs.pl 2023 0100
      ```
      Pass = `Sessions finished: OK: 1  Error: 0`, and SINEX ≤ 0.09 mm vs
      `$S/RNX2SNX/2023/SOL/FIN_20230100.SNX.gz_REF` (`gunzip -c` it — it really
      is gzipped). Both T420 and gps3 hit 0.0000 mm; anything worse means
      something moved that shouldn't have.

`scripts/install_bernese_dell.sh` automates most of this and is idempotent —
adapt rather than rewrite.

---

## 5. SSH, and not locking yourself out of gps3

`~/.ssh` holds **one** key (`id_ed25519`) and it is what authorises this
machine to gps3 *and* GitHub.

- [ ] Copy `~/.ssh` with permissions intact (`rsync -aHAX`; the private key
      must stay `600`, the directory `700`).
- [ ] **Preferred alternative:** generate a *new* key on the new laptop and
      `ssh-copy-id` it to gps3 **while the T420 still works**. Two valid keys
      beats moving one — if the copy is botched you still have a way in.
- [ ] Verify before decommissioning: `ssh -o BatchMode=yes gps3@192.168.48.98 true`
- [ ] Then remove the old key from gps3's `authorized_keys`.

---

## 6. GNSS data — the part that is not really about the laptop

The archive's home is gps3 (`/srv/gnss-archive`, 20 T, RAID 5) and the interim
second copy is the DOSTB external drive. **Neither depends on this laptop.**

What is T420-only and needs a destination:

- [ ] `~/GPSDATA/CAMPAIGN54/PAGENET` — 18 G, never transferred anywhere.
- [ ] `~/surveys` — 8.9 G of crossref reports and drive-arch scan JSONLs.

Both should land on gps3 rather than the new laptop. That is the correct home
regardless of migration, and doing it now removes them from the critical path.

---

## 7. Repos — method, not enumeration

57 repos on `/mnt/ssd`. Most are on GitHub and need no migration beyond
re-cloning. Two categories do not:

- [ ] **Unpushed commits.** At drafting: **1 repo** (`webdevportfolio_ap`, 6
      commits). Re-check on the day:
      ```bash
      for d in */.git; do r="${d%/.git}"; (cd "$r" &&
        n=$(git log --oneline @{u}..HEAD 2>/dev/null | wc -l)
        [ "$n" -gt 0 ] && echo "$r: $n unpushed"); done
      ```
- [ ] **No upstream at all.** At drafting: **8 repos**. These may exist nowhere
      but this disk — the single largest data-loss risk in the whole migration.
      ```bash
      for d in */.git; do r="${d%/.git}"; (cd "$r" &&
        git rev-parse --abbrev-ref @{u} >/dev/null 2>&1 || echo "$r: NO UPSTREAM"); done
      ```
      For each: confirm whether a remote exists, and push or archive it.
- [ ] Uncommitted work in ~25 repos (mostly 1–2 files; `washboard` had 21).
      Commit or explicitly discard — do not migrate a dirty tree and hope.

---

## 8. Order of execution

| # | step | est. |
|---|---|---|
| 1 | SMART check; free `/home`; push unpushed; audit no-upstream repos | 1 h |
| 2 | Claude memory → private repo (scan first) | 30 m |
| 3 | New laptop: OS, reproduce the directory layout exactly (§3) | 2 h |
| 4 | New SSH key → gps3 + GitHub, verified while T420 still lives | 20 m |
| 5 | `rsync -aHAX` BERN54, Qt4.8.7, GPSDATA, scripts, surveys | 1 h |
| 6 | Bernese: patch setvar, generate `$U`/`$T` fresh, REF54 symlinks | 30 m |
| 7 | **Verify: EXAMPLE campaign ≤ 0.09 mm** | 30 m |
| 8 | Clone repos; restore Claude memory; check the path encoding | 1 h |
| 9 | PAGENET + surveys → gps3 | 1 h |
| 10 | Run a real task end-to-end before decommissioning the T420 | — |

**Do not wipe the T420 until step 10 passes.** Keep it intact and bootable for
at least a week after cutover — a rollback that costs nothing is worth more
than the disk space.

---

## 9. What this runbook cannot cover

Written from a scan of the machine as it stood on 2026-07-30. Things will have
drifted. **Re-derive rather than trusting the numbers here** — particularly the
repo audit in §7, the disk usage in §0, and the memory scan in §2.

That instruction is not boilerplate. This project's recent history is a list of
confident, plausible, wrong claims caught only because someone re-checked.
