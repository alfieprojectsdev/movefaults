# RESUME — next session

**Updated 2026-07-07 (evening halt). Sessions 07-04 (DA-005a/b/006 shipped),
07-06 (stick forensics), 07-07 (Seagate excavation + logsheet crossref, PAUSED
mid-copy for the night — see HALT STATE below, start here).**

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
