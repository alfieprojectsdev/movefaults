# Archive fixity manifests

sha256 fingerprints for everything on `/srv/gnss-archive`. **These live in git
deliberately.** A manifest stored only next to the data it describes cannot
prove anything if that disk is what went wrong — which is the exact failure this
guards against.

The project's succession audit listed *"no fixity — zero checksums anywhere, so
silent bit rot is undetectable"* as a standing risk from 2026-07-29. These files
close it.

## What is here

| Manifest | Covers | Files | Generated |
|---|---|---|---|
| `legacy-sha256-20260812-163812.txt.gz` | `/srv/gnss-archive/legacy` — the legacy GNSS archive rescued off the DOSTB drive | 162,328 | 2026-08-12 |
| `datapool-sha256-20260812-084209.txt.gz` | `datapool/PHIVOLCS/2010` — the transfer proof run | 5,224 | 2026-08-12 |
| `datapool-sha256-20260812-084854.txt.gz` | `datapool/PHIVOLCS` — the full PH observation archive, 2010 to present | 325,530 | 2026-08-12 |
| `processed-sha256-20260813-035031.txt.gz` | `/srv/gnss-archive/processed` — Abegail's sixteen-year `SOL/` series | 67,554 | 2026-08-13 |

Together: **560,636 files**. The two datapool manifests are disjoint (the second
skipped 2010 as already present), so they sum to the full 330,754-file set
surveyed on the source server.

`processed/` is now covered too — it was the gap that `verify_archive.sh`'s
hardcoded target created, and it went unnoticed for six weeks.

## How the datapool manifest differs from the others

The `legacy` manifest was produced *after* the fact by reading the disk. The
**datapool manifests were written during the copy** — each hash is of the bytes
as they were streamed from the source server and written to the array, not of a
later re-read. That is cheaper (no second full read of 476 GiB) and strictly
stronger: it also detects a corrupt *transfer*, not just later bit rot.

## Verifying

```bash
# whole archive, from the directory the paths are relative to
cd /srv/gnss-archive/legacy
zcat /path/to/legacy-sha256-20260812-163812.txt.gz | sha256sum -c

# the datapool manifests carry absolute paths, so run from anywhere
zcat datapool-sha256-20260812-084854.txt.gz | grep -v '^#' | sha256sum -c
```

Expect this to take hours — it reads every byte, which is the point.

`sha256sum -c` prints `FAILED` per mismatching file and a count at the end. A
single failure is worth investigating rather than dismissing: on a RAID 5 array
with no hot spare, silent corruption is the failure mode that has no other
alarm.

## Regenerating

`scripts/verify_archive.sh` (also deployed at `/srv/gnss-archive/`):

```bash
scripts/verify_archive.sh census                                   # fast
ARCHIVE=/srv/gnss-archive/processed scripts/verify_archive.sh manifest
```

`ARCHIVE` was hardcoded to `legacy/` until 2026-08-12, which is why
`processed/` had no fixity for six weeks and nobody noticed. It is selectable
now; the mountpoint guard still refuses any target off the array.
