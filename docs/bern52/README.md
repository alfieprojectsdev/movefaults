# The recovered GNSS archive — what it is and what you can rely on

**Read this before using `/srv/gnss-archive` or anything in this directory.**
Everything here is measured, and every number carries the command or document
that produced it. You should not need to read the argument that produced this
archive in order to use it — that argument runs to eight documents and two
session logs, several of which retract each other.

*State as of 2026-09-09.*

## 1. What is in it

```
/srv/gnss-archive          746,977 files, 827 GB
  legacy/                  faithful per-drive copies -- DO NOT WRITE HERE
  derived/                 things this project produced from legacy/
  manifests/               drive walks and transfer records
```

`legacy/` holds **five** trees. Four are the evacuated drives; the fifth is
scoped out and named here so a reader counting directories does not find one
they cannot account for.

| tree | source | status |
|---|---|---|
| `RECOVERED_HD-LBU2_WD20EARS_WCAZA4430660` | HD-LBU2 | evacuated, verified |
| `RECOVERED_GPS_1TB_2_WD10EARS_WCAV5M032380` | GPS_1TB_2 | evacuated, verified |
| `RECOVERED_SEAGATE_W2A0W9T2_DATA0` | DATA0 | evacuated, verified |
| `RECOVERED_SEAGATE_W2A0W9T2_DC9A88` | DC9A88 | evacuated, verified |
| `RECOVERED_DOSTB20150918_from_BackupPlus` | DOST-B backup | **9.0 GB, 14,269 files — deliberately out of scope** as a source of missing GNSS data |

Those four are verified complete by per-extension count comparison and **can
stay undocked permanently**.

### A sixth drive exists, was walked, and was never transferred

**`New Volume`** — HGST, 465.8 GB, 269 GB used — was walked on 2026-09-08
(`manifests/t420-drive-arch-runs/all_NewVolume.txt`, 426,992 files) and is
**not in `legacy/` under any name**. It may still be docked.

It was skipped because it is substantially a copy of HD-LBU2, sharing 297,601
basenames with it. Measured before this was written:

```
New Volume GNSS-shaped basenames     98,877
on the four transferred drives      193,406
present ONLY on New Volume                0
```

**Nothing on it carries a name absent from the transferred drives.** So it is
safe to leave, and this paragraph exists so nobody re-docks and re-walks 269 GB
to rediscover that.

**Read the limit of that measurement carefully.** It compares *basenames*, and
this archive has twice demonstrated that a name is not an identity — Leica
`.mNN` and Trimble `.T0x` names carry no year, so the same basename recurs
across years. The result is conclusive in one direction only: **nothing there
is uniquely named.** Two files sharing a name could still differ in content. It
answers "is anything unique here", not "is every byte duplicated".

`legacy/` mirrors each drive's own layout. Paths are as-mounted, so a
`/run/media/finch/<LABEL>/` prefix appears in the manifests and not on disk.

**479,697 RINEX observation files**, 1993–2026.

## 2. Coverage against the want-list

The want-list (`gnss_want_list.csv`) records what the processing team believed
was missing: **954 site-years across 271 sites**.

| | |
|---|---:|
| site-years closed by this archive | **347 of 954**, across 175 sites |
| still missing | 607 |
| sites with a coordinate in the catalog | **261 of 271** |

The remaining **10 sites** — `CALC CEBM CTE1 JONA KBNK LEY5 LOP2 MATA QZN1
QZNA` — have neither raw nor RINEX anywhere on any drive. That is *"it is not
here"*, which is settled, rather than *"we have not found it"*, which would not
be.

## 3. What attribution means

Every RINEX file was matched to a monument **by the position in its own
header**, not by its name or its directory. `docs/bern52/rinex_attribution.md`
has the method; `crd_catalog.csv` is the site list it matches against.

**89.3% attributed.** Each file carries a verdict:

| verdict | meaning |
|---|---|
| `unique` | one catalogued monument within the radius |
| `aliases` | several codes at one location — a real monument, ambiguous name |
| `ambiguous` | the claimed code names more than one monument |
| `none` | no monument near the header position |
| `bad-position` | header position fails the geocentric radius check |
| `no-header` | unreadable or absent header |

**Three sources of evidence exist and none is authoritative.** The header
position is measured but is a single-point fix worth ~100 m. The filename and
marker are what somebody typed. The directory is inference from how somebody
once filed a folder. Where they disagree, `stage4_disagreements.md` groups the
conflict; **nothing is auto-corrected**, because a rule that silently applies
the general case mis-files the rare one invisibly.

## 4. What you can rely on, and what you cannot

**Rely on:**

- the archive is a faithful copy — every drive verified by extension counts
- any file with verdict `unique` has a header position matching exactly one
  catalogued monument
- `epoch_min`/`epoch_max` in the catalog are **solution reference epochs, not
  an operating period** — see `crd_catalog.md`; a check built on the other
  reading flagged 19% of a datapool as suspect
- `best_kind = RNXHDR` marks the two sites whose coordinate came from a RINEX
  header rather than a Bernese solution — metre-level, gap-fill only, never
  blended into a site with CRD coverage

**Do not rely on:**

- **118 catalog codes are flagged `ambiguous`** — one code, more than one
  monument, and the published row is the largest cluster only. `SOLD` spans
  632 km. Filter on `ambiguous` before using a coordinate as an identity.
- **44 filename-conflict patterns are undecided** and need a human, not more
  analysis (`stage4_decisions.md`)
- **95 files are attributed to PHIVOLCS HQ rather than where they were
  observed** — receivers tested at HQ carry the HQ position into the field.
  The rule is confirmed and mechanical but **not yet applied**; these are
  known-wrong attributions still in the product.
- a filename is a claim about identity; a header is evidence of it. Leica
  `.mNN` and Trimble `.T0x` names carry no year, so the same basename recurs
  across years at one site.

## 5. Raw receiver data, and why decoding stopped

**76,256 raw files.** Of those with a determinable date, **94.4% already had a
RINEX counterpart** — they were converted years ago
(`raw_rinex_counterparts.md`).

The 2012 gap was decoded: **3,869 files**, closing **4 site-years** — `CCA5`,
`ITGN`, `LAG1`, `NV47`. **113 failed and are unrecoverable**: truncated Leica
MDB fragments, truncated on every drive at identical sizes, with no complete
copy anywhere (`decode_113_failures.md`).

**Decoding the rest is not worth doing, and this is the bound rather than an
impression:**

```
remaining raw exists only for            2011-2020
its site codes that are want-list sites  15
want-list entries at those sites in that window   27      <- arithmetic ceiling
want-list entries OUTSIDE 2011-2020      490 of 954  (51%)
```

**27 is the absolute maximum** site-years that decoding *every* remaining raw
file could close, before subtracting those already closed. Against 607 missing.
And it cannot touch a single pre-2011 or post-2020 gap, which is more than half
of what is absent.

24,656 raw files remain unattributed. Unattributed is not the same as valuable.

## 6. Where the detail is

| question | document |
|---|---|
| how RINEX was attributed | `rinex_attribution.md` |
| the site catalog and its caveats | `crd_catalog.md` |
| which conflicts need deciding | `stage4_decisions.md`, `stage4_disagreements.md` |
| whether to decode raw | `raw_rinex_counterparts.md` |
| why 113 files cannot be decoded | `decode_113_failures.md` |
| per-file decode outcomes | `decode_outcomes_20260909.csv` |

Session logs in `docs/gps3-sessions/` and `docs/t420-sessions/` carry the
reasoning, including several conclusions that were reached, retracted and
restored. **They are the argument, not the result.** This file is the result.

**The per-topic documents above may contain superseded conclusions**, and
reading them in the wrong order will hand you something that was overturned
hours later. `decode_113_failures.md` was correct, retracted, and restored
inside a single day, and it carries all three states because the reasoning
failed instructively. **This README is the only file guaranteed current.**
Where it disagrees with anything else in this directory, it wins — and if it is
the one that is wrong, correct it here first.
