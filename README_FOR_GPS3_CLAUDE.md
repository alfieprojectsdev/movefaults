# READ ME FIRST — instructions for the Claude Code session on gps3

**Written 2026-08-04 by the Claude Code session on the T420** (user `finch`),
immediately before this drive was unplugged and carried to the R740.

You are reading this because the drive is now plugged into the server's USB
port. This file is your entry point. **Read all of it before touching
anything** — this drive is a single point of failure for the project, and §1
explains why.

---

## 0. What this drive is

Label `DOSTB20150918`, 1.9 TB, **NTFS**. It is the user's personal drive, and
after the 2026-07 evacuation of the failing Backup Plus drive it became the
**only complete copy of the PHIVOLCS legacy GNSS archive**.

Two separate things are on it that concern you:

| Path | Size | What |
|---|---|---|
| `processing_files/` | **22 GB** | Bernese **5.2** LUZON processed set from Abegail — the new work (§3) |
| `RECOVERED_*/` (3 dirs) | **26 GB** | the legacy archive rescued from three dead/dying drives (§4) |

Also present and **none of your business**: `ps4e/` (99 GB InSAR pipeline from
prior paid work — valuable, never suggest deleting it), plus personal media,
`Pictures`, `Books`, `Music`, `Obsidian`. **Do not scan, index, catalogue or
copy anything outside the two paths above.** This is a personal drive that
happens to carry work data.

---

## 1. ⚠ Before you run a single command

**Mount it read-only.** On the T420 it was mounted `ro` and that is how it
should stay:

```bash
sudo mkdir -p /mnt/dostb
sudo mount -o ro,noatime /dev/sdX1 /mnt/dostb     # confirm sdX1 with lsblk -f first
```

Three reasons, in order of seriousness:

1. **It is the only complete copy of the legacy archive.** `/srv/gnss-archive/legacy`
   on this machine is still empty (your own §13.6). Until a second copy exists,
   a write error here is unrecoverable data loss for the project.
2. **The source drives are dead or dying.** The `RECOVERED_*` directories were
   rescued from failed hardware. There is nothing to re-rescue from.
3. **NTFS-3G write support is fine but not free.** A read-only mount removes
   the entire class of accident.

**Confirm the device letter with `lsblk -f` every time.** It is not stable
across reboots or other USB devices, and this project has a documented history
of `sdX` shifting between sessions.

---

## 2. The opportunity this drive being here creates

**This unblocks §13.6 of your own session log.** That entry records
`/srv/gnss-archive/legacy` as empty, with the transfer *"blocked on the push
from the T420's DOSTB mount"* — over wifi measured at **6 MB/s**.

The drive is now on your USB bus. That bottleneck is gone. 26 GB of
`RECOVERED_*` at USB speed is minutes, not a day.

**This is the single highest-value thing you can do while the drive is
attached**, and it is worth more than the Bernese work in §3. It takes the
archive from one copy on failing-media-derived personal hardware to two copies
on independent hardware, which is item 5 of the continuity audit.

Suggested, but **confirm with the user before starting** — it is their drive
and their call:

```bash
tmux new -As archive          # FIRST. A process cannot be moved into tmux later.
rsync -aHAX --info=progress2 /mnt/dostb/RECOVERED_HD-LBU2_WD20EARS_WCAZA4430660/ \
      /srv/gnss-archive/legacy/RECOVERED_HD-LBU2_WD20EARS_WCAZA4430660/
# repeat per RECOVERED_* directory
```

Then **verify with a census, not with rsync's exit code.** Your §13.6 already
records why: rsync exits 0 having skipped files it could not read, and exits 23
on a run that copied 99.99% successfully. `/srv/gnss-archive/verify_archive.sh`
is staged for this — count files, symlinks, directories and bytes *separately*
and compare against the same census taken on the source.

**Expect zero symlinks on the source side.** The drive is NTFS; a `find` across
`processing_files/` returned 0 symlinks in 67,553 files. That is a property of
the source, not a transfer failure — do not chase it as a bug.

---

## 3. The Bernese 5.2 set — what it is for

`processing_files/` is a complete processed run of the **LUZON** network from
**Abegail** (she runs that network at PHIVOLCS), produced under **Bernese 5.2**.
The user's goal, in his words: *"i-reprocess ko sa GPS3 under Bernese 5.4 for
comparison ng results / adjustment (fine tuning) ng PCF."*

### Already captured into git — do not re-derive

The **configuration** half is committed to the repo, so you can work from
version control rather than from this drive:

```
config/bernese/gpsuser52-luzon/     PHIVOL_REL.PCF (+ PAGENET/PAGENET2 ancestors),
                                     11 OPT dirs, LUZON.{STA,CRD,VEL,ABB,CLU,BLQ,ATL,PLD}
config/bernese/gpsuser/              the 5.4 PAGENET counterpart from the T420
```

**Read `config/bernese/gpsuser52-luzon/PROVENANCE.md` before using any of it.**
It records the hazards. Two matter most:

- **Six live `.INP` panels carry `C:\Bernese\…` absolute paths.** On Linux a
  backslash is a literal character, not a separator, so these do not fail
  loudly. Run `scripts/provision_gpsuser.py` over the tree first.
- **The OPT tree is not uniformly a LUZON set.** Of the live `.INP` panels, 38
  name campaign `${P}/PHIVOLCS`, 9 name `LUZON`, 2 name `SAMR_LYT`, 1 `EXAMPLE`.
  These are last-saved menu states from different work, not a curated
  gold standard. The BPE sets the campaign at runtime so this is mostly
  cosmetic — but do not assume the directory name describes the contents.

### The data half stays here

| Path on this drive | Contents |
|---|---|
| `processing_files/GPSDATA/DATAPOOL/LUZON/` | **741 RINEX obs, DOY 121–151 of 2025** (31 days), 25 stations |
| `processing_files/GPSDATA/CAMPAIGN/LUZON/` | OBS 2064, ORB 554, ATM 154, **SOL 1944**, OUT 6582 |
| `processing_files/GPSDATA/CAMPAIGN/LUZON/SOL/` | **the comparison target** — `F1_*.NQ0` dailies, `WK_2413`/`WK_2414` `.NQ0`/`.SNX` |
| `processing_files/DATAPOOL_IGS/` | 94 SP3 |
| `processing_files/DATAPOOL_BSW52/` | 39 ION |
| `processing_files/BERN52/GPS/GEN/` | `C04_*.ERP` from 1986, `BULLET_A.ERP`, `ANT_COD_I14.PCV`, `ANT_COD_I20*.PCV` |

`CAMPAIGN/LUZON/RAW`, `ORX`, `GRD` are **empty and that is fine** — `OBS` holds
the converted observations. Not a truncated delivery.

### ⚠ The comparison is invalid unless you control the models

This is the part most likely to go wrong, because the failure produces a
plausible number rather than an error.

| | 5.2 LUZON (hers) | 5.4 PAGENET (this machine) |
|---|---|---|
| Antenna / PCV | **I14** | **I20** |
| GNSS for ambiguity resolution | **ALL** | **GRE** |
| Baselines, `V_CLU` | 6000/2000/200/20, 10 | identical |

The tuning parameters agree. The **models do not.** I14 → I20 is a cm-level,
largely vertical, systematic shift — comfortably inside the range a PCF tuning
change could produce.

**So: reprocess under I14 first and reproduce her numbers.** Only once you can
land on her `SOL/` values should you vary anything. A fresh I20 run compared
against her I14 result would show a difference that is real, reproducible, and
has nothing to do with the PCF.

The `ANT_COD_I14.PCV` you need is on this drive at `BERN52/GPS/GEN/`.

---

## 4. The `RECOVERED_*` directories

| Directory | Size | Origin |
|---|---|---|
| `RECOVERED_HD-LBU2_WD20EARS_WCAZA4430660` | 14 G | a dead Buffalo external |
| `RECOVERED_DOSTB20150918_from_BackupPlus` | 9.0 G | rescued off the failing Backup Plus |
| `RECOVERED_GPS_1TB_2_WD10EARS_WCAV5M032380` | 3.0 G | a dead 1 TB WD |

**26 GB total, not the ~157 GB the continuity audit refers to.** That figure
covers the whole legacy holding; what is on this drive is the portion recovered
from dead hardware. Do not report "the archive is backed up" after copying
these — report exactly what you copied, by directory and by census.

They have never been checksummed. A `sha256sum` manifest written into
`/srv/gnss-archive/manifests/` **and committed to git** is item 4 of the
continuity audit and costs nothing while the drive is attached. Fingerprints
stored only beside the data prove nothing if that disk is what failed.

---

## 5. House rules that apply to you here

From `docs/gps3-sessions/SESSION_LOG_20260729_storage.md` and
`docs/GPS3_COORDINATION_ONBOARDING.md` — all earned the hard way:

- **`tmux` first, always.** A running process cannot be moved into it
  afterwards. A multi-GB rsync outside tmux dies with the connection.
- **Do not run a bulk transfer and a BPE at the same time.** Headless BPE hangs
  under concurrent heavy I/O. Check with `pgrep -af 'rnx2snx|RUNBPE'` — and
  note `pgrep -f` matches its own command line, which has produced false
  readings three times on this machine.
- **Exit codes lie in both directions here.** `rsync` 0 on skipped files;
  `lsof +D` 1 on a clean tree; `grep -c error` returning 3 on a successful BPE
  run; `slow_cmd | grep -q` returning 141 under `pipefail`. Verify the effect,
  not the status.
- **A check that reports success without having inspected anything** is this
  project's recurring defect — your own §15.5 names five instances. A census
  that counts zero files and passes is the same bug.
- **Everything reaches `main` through a PR** (Rule 1). Branches live at most a
  week.

---

## 6. What the T420 session did today, so you do not repeat it

- Committed **`PAGENET_DLY.PCF` + `PGN_WK` panels** from the T420 →
  `config/bernese/gpsuser/`. This closes your §15.3 blocker. Note the finding:
  **that PCF has no dangling WAIT** — §14.5 expected `599` to wait on an
  undefined `522`, but it waits on `512 514` and there is no 521/522 in the
  file. It is a deliberate reduction, not an unsafe truncation. **PR #65.**
- Committed the **5.2 LUZON configuration** → `config/bernese/gpsuser52-luzon/`
  (same PR). `PHIVOL_REL.PCF` (84 PIDs, dated 2025-09-12) contains the
  `521/522` R2S_RED branch, `530 ADD_WK`/`531 ADD_MON`, and the
  `901/902/903/991` save-summarise-clean tail that `PAGENET_DLY` lacks — so
  **readiness item M now has a reference implementation.**
- Corrected the R740 hardware figures in a sibling handover after your §14.2
  measured **12 physical cores / 62 GB**, not the 24 two documents assumed.

**Check whether PRs #61–#65 have merged before assuming `main` has any of
this.** As of writing, `origin/main` was still at `1d1082e` (PR #60) while
your §15.4 stated all work had landed — it had not. Verify `origin/main`
actually advanced rather than trusting a command's exit code; that is Rule 5,
and this is the case it was written for.

---

## 7. Priority order, if you want one

1. **Confirm with the user, then copy `RECOVERED_*` to `/srv/gnss-archive/legacy/`.**
   Time-boxed by how long the drive is attached. Nothing else on this list is
   irreversible if skipped; this one is.
2. **`sha256sum` manifest** of what landed, into git.
3. **Copy the LUZON data** needed for the reprocessing into `$P`/`$D`.
4. **Reprocess under I14** and reproduce Abegail's `SOL/` numbers.
5. Only then vary models or tune the PCF.

If the drive has to come off before 1 is done, say so plainly and say what did
not get copied. An honest partial is worth more than a hopeful summary.
