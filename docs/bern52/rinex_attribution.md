# RINEX attribution by header position — stage 3

`scripts/match_rinex_to_site.py` reads `APPROX POSITION XYZ` from a RINEX
header and asks the stage-2 catalog which monument that is. Implements
`docs/project_documentation/CR-20260903-stage3-rinex-first.md`.

**Candidates, not determinations.** `APPROX POSITION` is a single-point fix
good to roughly 100 m; a cold start can be kilometres out. Every row carries
the distance that produced it.

## Results over 471,874 files

| verdict | files | meaning |
|---|---:|---|
| `unique` | 332,719 | one catalog site within the radius |
| `aliases` | 88,554 | several codes, all one monument (BLN2/BLNA are 3 m apart) |
| `none` | 24,146 | nothing within radius — see below, this is a finding |
| `ambiguous` | 20,724 | codes genuinely far apart; the header cannot choose |
| `bad-position` | 5,482 | header position not on the Earth's surface |
| `no-header` | 249 | no `APPROX POSITION` line |

**421,273 of 471,874 (89.3%) attributed to a single monument.**

### File selection took three attempts, and the first two failed silently

| attempt | files read | what was missing |
|---|---:|---|
| glob list, uncompressed only | 84,198 | every compressed RINEX 2 — 81% of the corpus |
| glob list + `.gz` and `.Z` | 443,195 | lowercase `.z` — 28,679 files, mostly `.YYd.z` |
| **one pattern** | **471,874** | — |

Each omission looked exactly like a smaller archive: a glob that matches
nothing is indistinguishable from a corpus that contains nothing. The rule is
now stated once as a case-insensitive pattern rather than enumerated, so a new
suffix is covered by construction.

Compression is detected by **magic bytes, not extension**, and the archive
punishes any other choice: 165 of 200 sampled plain `.YYd` are `.Z` data with
the suffix stripped, and `PBAS3500.17d.z` is *gzip* despite its `.z` name. No
`CRX2RNX` is used — a Hatanaka header is plaintext.

## The 24,146 `none` files are mostly another agency's network

Not a failure of the matcher. Of these, **18,199 carry a site code the
catalog has never heard of**, across **40 distinct codes**, and the
biggest ones sit in directories named `RAW/2018/Pagenet_*`:

| code | files |
|---|---:|
| `PMRV` | 945 |
| `PMOG` | 878 |
| `PMAS` | 817 |
| `PDUM` | 810 |
| `PZAM` | 810 |
| `PDIP` | 809 |
| `PTGO` | 802 |
| `PDDN` | 797 |

28 of the 40 codes are
`P`-prefixed. **These are PAGENET stations — NAMRIA's national network, not
PHIVOLCS'.** The catalog is built from PHIVOLCS `.crd` files, so it has no
reason to contain them, and no amount of matching will attribute them until
NAMRIA coordinates are added.

Their median distance to the nearest catalog site is ~8 km — too far for header
imprecision, too close for garbage. That is the signature of a real monument
that is simply absent from the index.

**This is why the headline figure fell from 92.7% to 89.3% when the
corpus grew.** Attribution did not get worse; files that were previously
invisible became visible, and a large block of them belongs to another agency.

## Against the filename and marker

- **419,570** agree
- **735** conflict
- **968**
  carry a name the catalog does not know. A position that differs from `TEMP`,
  `DEFA` or a receiver number is not a conflict — it is the attribution this
  stage produces.

`claimed_m` is the distance from the header to the site the *filename* claims:

```
claimed-site distance   min 240 m   median 263 km   max 12,351 km
0 of 735 within 200 m
```

None is inside header noise.

## Against the directory path

**77,932 agree, 1,017 disagree.** Path attribution is inference from how
somebody once filed a folder; this is the first evidence that can contradict
it. `Obsfiles/masb/1991/033/` holds `masf`, `mash` and `masc` files — filename
and header agree with each other and both contradict the directory.

Grouped and ranked in `stage4_disagreements.md`.

## Duplicates: file count is not observation count

**9.5% of these files (44,957) share a filename with another**, and **26% of
those same-name groups are not byte-identical**. No two share a directory, so
this is cross-drive repetition. The archive is deliberately **not**
deduplicated — which drive held which copy is evidence `drive-archaeologist`
exists to recover.

## What this does not establish

* **Not which source is wrong** where two disagree — the catalog entry may be
  the error. `PHIV` is in the catalog and looks like an institution name.
* **Nothing about the 20,724 `ambiguous` files**, which were never
  attributed at all.
* **Nothing about the raw files.** Whether the 75,381 `.T0x`/`.mNN` files have
  RINEX counterparts is the separate question the CR reserves.

## Reproducing

```bash
scripts/match_rinex_to_site.py --root /srv/gnss-archive -o matches.csv
```

~2 hours; compressed files are decompressed to 64 kB only.

