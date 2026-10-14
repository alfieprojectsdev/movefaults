# Drive Archaeologist

Excavate decades of data from old hard drives.

Scans, classifies and catalogues legacy GNSS data, field notes and mixed
personal/work files scattered across old drives, and recovers deleted files from
Windows recycle bins. **It never writes to the drive it scans.**

Status: about 60% (see `CLAUDE.md` at the repo root). The scanner has been run
on real drives, including a 2015 DOST media drive, but GNSS classification has
been tested only on synthetic data; validating it on a real legacy GNSS drive is
ticket DA-001, still open.

## Commands

All four run as `drive-archaeologist` or the short alias `drive-arch`.

| command | what it does |
|---|---|
| `survey PATH` | Fast triage: one walk, no catalog, no hashes, archives not opened by default. Prints a category and extension breakdown and a wipe/keep verdict that names anything the walk did not cover |
| `scan PATH` | Full catalog: one JSONL record per file, resumable, looks inside archives |
| `recover pair` / `recover copy` | Recycle-bin recovery in two reviewed stages: pair `$R`/`$I` files into a manifest, then copy out size-verified (DA-006) |
| `tui` | Interactive drive picker, survey and detached scans (needs the `drive-archaeologist-tui` extra) |

## Installation

This tool lives in the movefaults monorepo and has no `pyproject.toml` of its
own. From the repository root:

```bash
uv sync --extra drive-archaeologist                 # CLI
uv sync --extra drive-archaeologist --extra drive-archaeologist-tui   # plus the TUI
```

## Quick start

```bash
# Triage first: is anything on this drive worth keeping?
uv run drive-arch survey /media/usb

# Full scan
uv run drive-arch scan /media/usb                       # writes scan_<name>_<timestamp>.jsonl and a .log
uv run drive-arch scan /media/usb -o my_scan.jsonl      # refuses to overwrite unless --force
uv run drive-arch scan /media/usb -o my_scan.jsonl --resume

# Useful scan options
#   --include-hidden          also scan $RECYCLE.BIN, .Trash*, dot-files (survey includes them by default)
#   -x/--exclude GLOB         skip a subtree; repeatable
#   --max-archive-depth N     nested-archive extraction depth (default 3; 0 = never)
#   --ingest [--dry-run]      send classified GNSS files to the ingestion pipeline (Celery)

# Recover deleted files from a Windows recycle bin, reviewing the plan in between
uv run drive-arch recover pair my_scan.jsonl --dest-root /srv/recovered -o manifest.tsv
uv run drive-arch recover copy manifest.tsv --dest-root /srv/recovered
```

Archives read inside a scan: `.zip`, `.tar`, `.gz`, `.tgz`, `.bz2`, `.tbz2`,
`.xz`, `.txz`, `.7z`, `.rar`.

## Output format

One JSON object per line:

```json
{"path": "/media/usb/ALGO0010.22o", "name": "ALGO0010.22o", "extension": ".22o", "category": "GNSS Data", "size_bytes": 4251840, "size_mb": 4.05, "modified": "2022-04-10T14:23:15", "created": "2022-04-10T14:20:00", "parent_dir": "/media/usb", "depth": 1, "scan_timestamp": "2026-10-14T21:36:05", "in_archive": false, "archive_path": null}
```

`category` comes from the extension profiles in `profiles.py` ("GNSS Data",
"GNSS Raw (Trimble)", "Document", "Archive" and so on). `in_archive` and
`archive_path` mark files found inside an archive. A scan does not hash files;
`--ingest` computes SHA-256 for the files it dispatches.

```bash
jq -r '.category' my_scan.jsonl | sort | uniq -c | sort -rn     # files per category
jq 'select(.size_mb > 100) | {name, size_mb, path}' my_scan.jsonl
```

## How resume works

The scan appends each finished path to `checkpoint_<scan_id>.log`, one JSON
string per line, in batches. A crash loses at most one unflushed batch, which
`--resume` re-walks. The TUI starts scans as detached `drive-arch scan`
processes, recorded in `~/.local/state/drive-arch/active_scans.json` by drive
identity (vendor, serial and label, never the device letter), so a scan
survives the TUI closing.

## Development

From the repository root:

```bash
uv run pytest tools/drive-archaeologist/tests      # 133 tests, 2026-10-14
ruff check tools/drive-archaeologist
```

## Documents

- `CLAUDE.md`: guidance for working on this tool.
- `docs/TUI_PLAN.md`: the TUI design (DA-005); screens 1–3 are built.
- The other files in `docs/` (`PHASE_*`, `EXECUTIVE_SUMMARY`,
  `IMPLEMENTATION_RECOMMENDATIONS`, `TAILORED_IMPLEMENTATION_PLAN`,
  `QUICK_DECISION_GUIDE`, `TECH_STACK_QUESTIONS`, `Smart USB data ingestion
  system`) are the November 2025 planning set from before the tool existed.
  They are kept for the reasoning; they do not describe the code.

## License

MIT, copyright PHIVOLCS/DOST: see the repo-root `LICENSE`.

## Author

Alfie Pelicano. Built for PHIVOLCS to organize decades of GNSS data and field
observations.
