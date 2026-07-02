# drive-archaeologist TUI — design plan (DA-005)

**Drafted:** 2026-07-03 · **Status:** plan only, not scheduled
**Framework:** [Textual](https://textual.textualize.io/) — Python, built on rich (already a
dependency), async, headless-testable via `Pilot`. Optional extra: `drive-archaeologist[tui]`,
entry point `drive-arch tui`.

## Why a TUI, and why this shape

The 2026-07-02/03 drive-rehab sessions showed the real workflow is a **funnel**:
plug drive → fast triage (survey) → decide → full scan → explore catalog → act
(recover / migrate / wipe elsewhere). Today that funnel is CLI invocations plus ad-hoc
python one-liners over JSONL. The TUI makes the funnel the interface. Target users are
geodesists, not devs; design is ADHD-optimized per project conventions: one decision per
screen, visible progress, every action confirmable and logged.

**Hard rule inherited from the tool:** the TUI is read-only with respect to scanned drives.
It never wipes, moves, or modifies drive contents. Wipe stays outside (udisks/wipefs);
the TUI's job ends at the verdict and the recovery/migration *scripts*.

## Screen flow

```
┌────────────┐   ┌─────────────┐   ┌────────────┐   ┌─────────────┐
│ 1 DRIVES   │──▶│ 2 SURVEY    │──▶│ 3 SCAN     │──▶│ 4 EXPLORE   │
│ pick target│   │ fast triage │   │ full JSONL │   │ browse+filter│
└────────────┘   │ + verdict   │   │ resumable  │   └──────┬──────┘
                 └─────────────┘   └────────────┘          ▼
                                                    ┌─────────────┐
                                                    │ 5 ACTIONS   │
                                                    │ manifests / │
                                                    │ recovery /  │
                                                    │ migration   │
                                                    └─────────────┘
```

### 1 · Drive picker
- Auto-refreshing list of block devices (lsblk parse; poll or udev): vendor, model, size,
  label, fs, mount state, RM/RO flags.
- Inline hazard badges learned from the field: `RO=1 → "controller write-locked (read-only
  forever)"`; `du≫capacity → "probable FAT corruption"`; unmounted-raw-vfat noted.
- **Identity is the selection**, not the device letter — the sdc/sdd letter-shift near-miss
  (2026-07-03) becomes impossible: the TUI re-resolves vendor+serial+label at every action.

### 2 · Survey (default action; wraps `DeepScanner(stats_only=True)`)
- Live counter (files, files/s, elapsed) while walking.
- Result = verdict card: category table (top N), total size, GNSS count, then the
  **disclosure block** (hidden entries skipped? archives unopened? symlinks? read errors?
  corruption flag) and the color-coded verdict banner:
  green `safe-to-wipe candidate` · red `N GNSS files — DO NOT wipe` · yellow `corrupt — unreliable`.
- Buttons: `[F]ull scan` `[H] re-survey incl. hidden` `[E]xport summary` `[B]ack`.

### 3 · Scan (full catalog)
- Output path picker (default `~/surveys/<label>/full_scan.jsonl`), clobber guard surfaced
  as a dialog (`resume / overwrite / new name`).
- Progress bar with rate + ETA (total estimated from survey's file count).
- Pause/resume rides the existing checkpoint mechanism; scan survives TUI exit
  (detached worker) and reattaches on reopen.

### 4 · Explore (JSONL catalog browser — replaces the ad-hoc python one-liners)
- Left: category tree (category → extension), counts + GB.
- Right: virtualized file list for current node/filter (path, size, mtime).
- Filters (composable, one keystroke each): non-media toggle, GNSS-only,
  recycle-bin/trash only, size ≥ N, year range, corrupt-only, in-archive.
- Footer aggregates for current filter: files / bytes / oldest–newest.
- Search box over paths.
- **Scale plan:** counters stream-load eagerly (1.3M rows ≈ seconds); row browsing uses an
  on-demand SQLite side-index built on first Explore of a big catalog (`full_scan.jsonl` →
  `full_scan.db`, one-time, ~30s). This is the "Database Backend" post-MVP item finally
  earning its keep.

### 5 · Actions (gated on drive-arch Phase 2/3 maturing)
From any Explore selection/filter:
- **Export manifest** (TSV/JSONL of selection).
- **Recovery script** — copy-out with `$RECYCLE.BIN` `$R`/`$I` pairing (restores original
  names), always dry-run first, target dir off-drive.
- **Migration script** — `SortPending → DATAPOOL/SITE/YYYY/DOY` proposal (Phase 2
  structure recognition), generated as reviewable bash with undo, never auto-executed.
- Later: **dispatch to ingestion** (ING-001 handoff) for GNSS selections.

## Cross-cutting

- **Command echo pane** (collapsible bottom strip): every TUI action prints its CLI
  equivalent (`drive-arch survey /run/media/... --include-hidden`). Teaches the CLI,
  makes sessions reproducible, doubles as the audit log (also written to
  `~/surveys/<label>/tui_session.log`).
- **Confirmations**: anything that writes anywhere (index build, script export) shows the
  target path; nothing ever targets the scanned drive.
- Keyboard-first (arrows/j-k, tab between panes, single-key filters), mouse works.
  Color-blind-safe palette; every color state has a text label.
- State persistence: last drive, last catalog, in-flight scan reattachment.

## Architecture

```
src/drive_archaeologist/tui/
  app.py          # Textual App, screen routing
  screens/        # drives.py survey.py scan.py explore.py actions.py
  widgets/        # verdict_card.py category_tree.py disclosure_list.py
  index.py        # JSONL -> SQLite side-index (Explore backend)
  devices.py      # lsblk/udev enumeration + identity resolution
```
- `DeepScanner` gains one tiny seam: `on_progress: Callable[[int, float], None]` (count,
  rate) — the TUI subscribes instead of parsing console output. No other scanner changes.
- Survey/scan run in a worker thread (Textual `run_worker`); UI never blocks.
- Tests: Textual `Pilot` headless snapshots per screen + seam unit tests. TDD as usual.

## Phasing (each lands separately)

| Phase | Scope | Size |
|---|---|---|
| DA-005a | App skeleton, drive picker, survey screen + verdict card | M |
| DA-005b | Scan screen: progress seam, pause/resume, reattach | M |
| DA-005c | Explore: category tree, filters, SQLite side-index | M/L |
| DA-005d | Actions: manifests, recycle-bin recovery script, migration dry-run | L (gated on Phase 2/3) |

## Mock — survey verdict (screen 2)

```
┌ drive-arch ── Seagate BUP Ultra Touch · 931.5G · "Backup Plus" ──────────────┐
│                                                                              │
│  Survey complete — 1,267,652 files · 666.6 GiB · 30m30s                      │
│                                                                              │
│  ┌ Categories ─────────────────────────┐  ┌ Disclosures ──────────────────┐  │
│  │ Source Code      447,734    1.2 GB  │  │ ⚠ 17,006 archives NOT opened  │  │
│  │ Unclassified     323,582            │  │ ⚠ 809 symlinks not followed   │  │
│  │ Image            203,109   77.3 GB  │  │ ⚠ 36 unreadable entries       │  │
│  │ GNSS Raw (Leica)  78,576            │  │ ✓ hidden/system included      │  │
│  │ GNSS Raw (Trimble)16,141            │  │ ✓ no corruption flags         │  │
│  │ …                                   │  └───────────────────────────────┘  │
│  └─────────────────────────────────────┘                                     │
│                                                                              │
│  ██ VERDICT: 97,494 GNSS files — DO NOT WIPE · full scan + excavate first ██ │
│                                                                              │
│  [F] Full scan   [H] Re-survey w/ hidden   [E] Export   [B] Back             │
├──────────────────────────────────────────────────────────────────────────────┤
│ $ drive-arch survey "/run/media/finch/Backup Plus" --include-hidden          │
└──────────────────────────────────────────────────────────────────────────────┘
```
