# RESUME — next session

**Updated 2026-07-07. Sessions 07-04 (DA-005a/b/006 shipped), 07-06 (stick forensics),
07-07 (Seagate ST500DM002 excavation + logsheet crossref).**

## Session 2026-07-07 — Seagate ST500DM002 excavation (IN PROGRESS at handoff)
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
