# RESUME — next session

**Updated 2026-07-06. Sessions 07-04 (DA-005a/b/006 shipped) + 07-06 (stick forensics).**

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
