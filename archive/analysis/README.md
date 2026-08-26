# Archived from `analysis/` — what each was, and why it stopped

Moved 2026-08-26, sequence item 9 of
[`analysis_port_assessment.md`](../../docs/project_documentation/analysis_port_assessment.md).

**Moved, not deleted, and moved with `git mv` so history follows.** The point of
archiving is to stop these three implying they are live, without losing what
they were. Nothing here is broken; each simply has no consumer.

---

## `05 Single Frequency`

Four `.bat` files totalling ~750 bytes, wrapping a frozen `teqc.exe`, plus an
`RMHS/` variant of the same four. A u-blox **single-frequency** side experiment:
rename → `UBX2RINEX` → edit header → `oA` → `o`.

**Why it stopped:** single-frequency data is not part of the MOVE Faults
processing chain, which is dual-frequency throughout. Nothing downstream reads
its output.

**Note:** the two `teqc*.exe` binaries in these directories are **not** tracked
— `.gitignore` excludes `*.exe`. Only the batch files are here. If the
experiment is ever revived, the binaries have to come from somewhere else, and
which build they were is unrecorded.

## `07 Sample time series from NMEA`

Eight sample VADASE series — PAPI, PGM2, PMSC, PTAG — in both `LDM`
(displacement) and `LVM` (velocity) form, each with a rendered `.jpg`, plus a
copy of `vel_line_v6_{ldm,lvm}.m`.

**Why it stopped:** it is *data*, not a pipeline. It was never a stage that
runs.

**Archived as fixtures, not as dead weight.** These are real 1 Hz NMEA series
from four named stations, already paired with the plots they produced. That
makes them the closest thing the repository has to **regression fixtures for
`services/vadase-rt-monitor`** — which currently has none from real stations.
If anyone wires up parser or integrator regression tests, start here.

The two `.m` files are byte-identical to their counterparts under
`02 Time Series/modified scripts/`; see the version map below.

## `09 Kinematic`

One driver (`RUNX_kinematic.py`), one Bernese kinematic coordinate file
(`COOR160350.KIN`), a `GUNG` series, a 3 MB spreadsheet, and a copy of
`vel_line_v7_kinematic_v3.m`.

**Why it stopped:** no downstream consumer. Kinematic processing is not in the
production chain, and nothing reads a `.KIN` anywhere else in the tree.

**Worth knowing before reviving it:** its `vel_line_v7_kinematic_v3.m` has the
**same filename** as the one under `02 Time Series/modified scripts/` and
**different contents**. See below.

---

## A competing plan that this supersedes

`reorganize_analysis_scripts.sh` at the repository root is tracked, and it
proposes a **different** destination for two of these three: `05` into
`drive-archaeologist/reference_scripts` and `07` into
`vadase-rt-monitor/reference_scripts`.

**It is a pre-monorepo artefact and would not run today.** It targets
`/home/finch/repos/movefaults/analysis` — the repository is `movefaults_clean`
— and moves into `/home/finch/repos/drive-archaeologist` and
`/home/finch/repos/vadase-rt-monitor`, which are no longer separate
repositories; they are `tools/` and `services/` subdirectories here. With
`set -e` and bare `mv`, it fails on the first missing path.

Its instinct about `07` was right and is kept above: those series belong with
VADASE, as fixtures. The move it describes is to a layout that no longer
exists.

**Not deleted here** — it is someone's tracked work and removing it is a
separate call. Flagged so the two schemes are not both treated as pending.

---

# The `vel_line` version map (sequence item 10)

**25 files, 22 distinct by content, one in production.** No record existed of
which produced which published figure. This is what could be established from
the files themselves; the parts only a person can supply are marked.

## They are not a version history

That is the finding. Several "versions" are **parallel copies differing in one
hardcoded value**, not successive revisions:

| pair | the entire difference |
|---|---|
| `v1_changeplot` / `v1_matlab_cont` | byte-identical |
| `v6_ldm` in `02` / in `07` | byte-identical |
| `v6_lvm` in `02` / in `07` | byte-identical |
| `v3_verticalline_changeplot_camp` / `_cont` | campaign vs continuous variant |
| `v7_kinematic_v3` in `02` / in `09` | **one hardcoded earthquake datetime** — `2022-07-27 00:43:24` vs `2016-02-04 22:41:37`, plus the matching axis label |

The last one is the clearest case: two files, same name, different event. They
are *per-event copies*, and the filename records nothing about which event. A
`git checkout` and a parameter would have replaced the whole practice.

## Lineage, from the files

`v8_newvelduetooffset` is the production line. Each carries its own
attribution comment:

| version | attribution | `rmoutliers` |
|---|---|---|
| `v8_newvelduetooffset` | modified by Cassandra Cabigan **09/2022** | — |
| `v8_..._v2` | modified by Cassandra Cabigan **10/2022** | — |
| `v8_..._v3` | modified by Cassandra Cabigan **11/2022** | — |
| **`v8_..._v4`** | **no attribution comment** | **2 calls** |

**Two things follow, and both matter.**

`v4` is the only version that removes outliers. So a figure made with `v3` and
one made with `v4` differ by more than cosmetics — they differ in which
observations entered the fit. Any published figure needs to say which it used,
and none of them does.

`v4` is also the only one in the production line with **no attribution and no
date**, and it is the version in use. The three that are signed are the three
that are not.

## What only a person can answer

Recorded here so the questions are asked while anyone still remembers:

1. **Which version produced the figures in the 2024 GPS Motions report?**
   Given `v4` is the only one with outlier removal, this is answerable by
   inspection if a figure shows a fit that ignores visible outliers.
2. **Who wrote `v8_..._v4`, and when?** It is the production script and the
   only unsigned one.
3. **Was the `rmoutliers` addition in `v4` a deliberate methodological change**,
   or a convenience that became permanent? `analysis.py`'s port made this
   configurable (`exclude_outliers`), and the 5e-6 mm/yr verification was run
   with it **off** — matching `v3`, not `v4`.
4. **Which event does each `v7_kinematic_v3` belong to?** One is dated
   2022-07-27 (NW Luzon), the other 2016-02-04.

Point 3 is the one with consequences: the port was verified against the
convention `v3` uses, while `v4` is what production runs.
