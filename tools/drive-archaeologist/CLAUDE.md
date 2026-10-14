# CLAUDE.md

Guidance for working on **drive-archaeologist**, a CLI and TUI for excavating
legacy GNSS data from old drives. It is one component of the movefaults
monorepo: the repo-root `CLAUDE.md` and `docs/SETTLED.md` apply here too, and
are read first.

## Status (re-checked 2026-10-14)

About 60%. 25 modules, 133 tests. Working and tested:

- `scan`: resumable JSONL catalog, archive recursion, hardened against corrupt
  filesystems (DA-002)
- `survey`: fast triage with a wipe/keep verdict (DA-003)
- `recover`: recycle-bin `$R`/`$I` pairing and manifest-driven copy-out (DA-006)
- `tui`: drive picker, survey screen, detached scan jobs (DA-005a, DA-005b)
- `--ingest`: hands classified GNSS files to `services/ingestion-pipeline`

**Open, and the reason for the 60%:** GNSS classification has only been tested
on synthetic fixtures. The scanner's mechanics have run on a real drive, but it
was a DOST media drive, not a GNSS one. Validating classification on a real
legacy GNSS drive is DA-001. Trimble raw formats (`.T01`, `.T02`, `.T04`,
`.DAT`, `.TGD`) need profile work.

## Hard rule

**Nothing in this tool writes to, moves or deletes anything on the drive being
scanned.** `recover copy` refuses any destination outside its `--dest-root`.
Wiping stays outside the tool. Keep it that way.

## Layout

```
src/drive_archaeologist/
  cli.py                  click entry point: scan, survey, recover {pair,copy}, tui
  scanner.py              walk, metadata, archive recursion, skip reporting, stats-only mode for survey
  classifier.py           extension -> category, using profiles.py
  profiles.py             category -> extensions ("GNSS Data", "GNSS Raw (Trimble)", "Document", ...)
  strategies/gnss.py      GNSS-specific handling
  strategies/media.py     media-specific handling
  archive_handler.py      zip, tar(.gz/.bz2/.xz), 7z (py7zr), rar (rarfile) into a temp dir
  recovery.py             recycle-bin recovery (DA-006)
  ingestion_dispatch.py   on_classified callback -> ingestion pipeline; lazy imports, so the
                          tool installs without that package
  scanjobs.py             detached scans for the TUI: registry, liveness, progress
  utils/checkpoint.py     append-only checkpoint log for --resume
  utils/paths.py          Windows reserved names, long paths, system directories
  tui/                    Textual app: screens/drives.py, survey.py, scan.py; devices.py
tests/                    15 test files, 133 tests
docs/                     TUI_PLAN.md (current design) plus the November 2025 planning set
```

## Commands

From the repository root (this tool has no `pyproject.toml` of its own):

```bash
uv sync --extra drive-archaeologist [--extra drive-archaeologist-tui]
uv run drive-arch --help
uv run pytest tools/drive-archaeologist/tests
ruff check tools/drive-archaeologist
```

Dependencies are the `drive-archaeologist` and `drive-archaeologist-tui`
extras in the root `pyproject.toml`. Classification is by extension profile
only: no content sniffing, no `python-magic`, so no `libmagic` system
dependency. (`filetype` is listed in the extra but nothing imports it.)

## Design decisions worth knowing before changing code

- **Drives are identified by vendor + serial + label, never by device letter.**
  Letters shift when drives are re-plugged; every TUI action re-resolves the
  identity and refuses ambiguous or vanished matches (the sdc/sdd near-miss,
  2026-07-03).
- **Resume is an append-only log**, `checkpoint_<scan_id>.log`, one
  JSON-encoded path per line, written in batches. The old format rewrote the
  whole path set on every save, which dominated NAS-scale scans. A crash loses
  at most one batch; a torn last line is skipped.
- **The TUI never runs a scan in-process.** It spawns `drive-arch scan` in its
  own session and records it in `~/.local/state/drive-arch/active_scans.json`,
  so a multi-hour scan outlives the TUI. Progress is read by counting lines in
  the output JSONL.
- **A scan does not hash.** Only `--ingest` computes SHA-256, for the files it
  dispatches.
- **Do not deduplicate the recovery archive** (SETTLED.md §3): which drive held
  which copy is the evidence this tool exists to recover.
- **Detect compression by magic bytes, never by extension** (SETTLED.md §2):
  165 of 200 sampled plain `.YYd` files were `.Z` data with the suffix stripped.

## Domain knowledge: RINEX names

- RINEX 2 short name `ALGO0010.22O`: 4-character site, 3-digit day of year,
  session character (`0` for a daily file, `a`–`x` for hourly), 2-digit year,
  type letter (`O` observation, `N` navigation, `M` meteorological, `D`
  Hatanaka-compressed observation). Extensions may be upper or lower case.
- RINEX 3 long name `ALGO00CAN_R_20220010000_01D_30S_MO.crx`.
- A digit in the fourth character often marks an **auxiliary benchmark**, a
  physically separate mark, not an alias (`BUGS` → `BUG2`). SETTLED.md §2
  explains how to tell the cases apart and why the name alone cannot.

## The planning documents

Everything in `docs/` except `TUI_PLAN.md` was written in November 2025, before
the tool existed (phases, tech-stack questions, executive summary). They are
kept for the reasoning. They do not describe the code. Where they conflict with
it, the code wins.
