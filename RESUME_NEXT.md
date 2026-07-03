# RESUME — next session

**Queued 2026-07-03. Start here.**

## NEXT TASK: DA-005a — drive-arch TUI, phase 1 (picker + survey screen)

Implement the first phase of the Textual TUI. Full design already written:
**`tools/drive-archaeologist/docs/TUI_PLAN.md`** — read it first.

### Scope for DA-005a (this session)
- App skeleton (`src/drive_archaeologist/tui/app.py`, Textual `App`, screen routing).
- **Screen 1 — drive picker** (`tui/screens/drives.py` + `tui/devices.py`): lsblk/udev
  enumeration, vendor/model/size/label/fs/mount/RM/RO columns, hazard badges
  (`RO=1 → write-locked`, `du≫capacity → probable corruption`). Selection resolves by
  **identity (vendor+serial+label), never device letter** — the sdc/sdd letter-shift near-miss
  must be impossible.
- **Screen 2 — survey** (`tui/screens/survey.py` + `tui/widgets/verdict_card.py`): wraps
  `DeepScanner(stats_only=True)` in a Textual worker thread; live counter; verdict card =
  category table + disclosure block + color-coded banner (green/red/yellow).
- **Scanner seam:** add `on_progress: Callable[[int, float], None]` to `DeepScanner` (count, rate)
  so the TUI subscribes instead of parsing console output. Only scanner change needed.
- Tests: Textual `Pilot` headless snapshots (drives + survey screens) + `on_progress` seam unit test.
- Packaging: optional `drive-archaeologist[tui]` extra (Textual dep), entry point `drive-arch tui`.

### Workflow reminders (see memory)
- Worktree per protocol: `git worktree add .trees/da-005a-tui -b feat/da-005a-tui origin/main`,
  then `uv sync --extra dev --extra drive-archaeologist` INSIDE it, then `git checkout -- uv.lock`.
- Run tests via `uv run --no-sync` in the worktree venv.
- Major commit → PR via `bash scripts/open_pr.sh` (gh writes are gated). Merge via
  `bash scripts/merge_pr.sh <n>`; verify `origin/main` advanced after.
- TDD; ruff + mypy clean before commit. NO Claude/AI refs in commit messages.
- **Hard rule:** TUI is read-only toward scanned drives — never wipes/moves/modifies drive contents.

## Also open (not queued — Alfie's pick order)
- Backup Plus migration EXEC (drive-arch Phase 3): manifest ready
  `~/surveys/BackupPlus/migration_manifest_v2.tsv` (96k files, 133.7 GiB). BLOCKED: needs a
  ≥140 GiB target disk (T420 SSD is 119 G) + domain decision on 30S_01H-vs-30S_1H authoritative run.
- DOSTB recycle-bin recovery: 16k deleted GNSS, `$R`/`$I` pairing script; ~6 GB; drive replug needed.
- ING-005 gfzrnx QC backend (code-ready, license-gated for automation).
- BRN-001 R740 Bernese install.

## Async (Alfie, not code)
- GFZ license inquiry email (`~/Downloads/gfzrnx_license_inquiry_GFZ.md`).
- `scripts/deploy_r740.secrets` OAuth token rotation.

## State snapshot
- main = `52c175e` (DA-002/003 + CR fixes merged). Working branch `docs/bernese-training-notes` @ `fcd8514`.
- Two drives mounted, cataloged, NON-wipeable, untouched: DOSTB (2TB), Backup Plus (1TB).
- PAGENET weekly done: `WK__2412.NQ0` (7 dailies, 72 sta, RMS 0.011 m).
- Session log: `session_log_20260702.md` (sections 1–21).
