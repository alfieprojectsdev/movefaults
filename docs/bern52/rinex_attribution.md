# RINEX attribution by header position — stage 3

`scripts/match_rinex_to_site.py` reads `APPROX POSITION XYZ` from a RINEX
header and asks the stage-2 catalog which monument that is. Implements
`docs/project_documentation/CR-20260903-stage3-rinex-first.md`.

**Candidates, not determinations.** `APPROX POSITION` is a single-point fix
good to roughly 100 m; a cold start can be kilometres out. Every row carries
the distance that produced it.

## Results over 443,195 files

| verdict | files | meaning |
|---|---:|---|
| `unique` | 327,001 | one catalog site within the radius |
| `aliases` | 84,268 | several codes, all one monument (BLN2/BLNA are 3 m apart) |
| `ambiguous` | 20,219 | codes genuinely far apart — the header cannot choose |
| `none` | 6,196 | nothing within radius: uncatalogued monument, or a useless header |
| `bad-position` | 5,478 | header position not on the Earth's surface |
| `no-header` | 33 | no `APPROX POSITION` line |

**411,269 of 443,195 (92.8%) attributed to a single monument.**

No decoding was required. A Hatanaka `.YYd` header is plaintext — only the
observation records are compressed — so `CRX2RNX` is not needed to read a
position. Compression is detected by **magic bytes, not by extension**: 165 of
200 sampled plain `.YYd` files are `.Z` data whose suffix was stripped, and
trusting the suffix reads them as text and finds nothing.

## Against the filename and marker

- **409,567** agree
- **735** conflict
- **967**
  carry a name the catalog does not know (`TEMP`, `DEFA`, receiver numbers like
  `7239`). A position that differs from those is not a conflict — it is the
  attribution this stage exists to produce.

Whether a name counts as contradicting evidence is tested against the catalog,
not a placeholder list: campaign point numbers like `0194` and `02G1` are
legitimate site codes.

### The 735 conflicts are real

`claimed_m` is the distance from the header to the site the *filename* claims,
and it is what makes a conflict readable:

```
matched-site distance   max     ~150 m  (the match radius)
claimed-site distance   min     240 m
                        median  263 km
                        max     12,351 km
0 of 735 have the claimed site within 200 m
```

None is inside header noise. These are files whose name points somewhere the
receiver demonstrably was not.

## Against the directory path — the product

Path-derived attribution is inference from how somebody once filed a directory.
This is the first evidence that can contradict it.

- **75,014** agree
- **1,017** disagree

| matched ← path | files |
|---|---:|
| TANY ← path CACA | 99 |
| TSKB ← path MASB | 57 |
| S01R ← path MASB | 54 |
| GUAM ← path MASB | 44 |
| WUHN ← path MASB | 31 |
| MASG ← path MASB | 29 |
| S01R ← path SOLE | 29 |
| GUAM ← path SOLE | 29 |

The pattern is a campaign directory holding more than its own site.
`Obsfiles/masb/1991/033/` contains `masf`, `mash` and `masc` files — the
filename and the header agree with each other and both contradict the
directory. Filing by directory would have mislabelled every one.

`TANY ← path CACA` is the largest group at 99 files.

## What this does not establish

- **Not which source is wrong.** A conflict says two sources disagree, not
  which to believe — the catalog entry could be the error. `PHIV`, which the
  catalog holds as a site, appears to be an institution name.
- **Nothing about the 6,196 `none` files.** Uncatalogued monument and
  unusable header look identical from here; the distance to the nearest site is
  recorded so they can be separated later.
- **Nothing about the raw files.** Whether the 75,381 `.T0x`/`.mNN` files have
  RINEX counterparts is the separate question the CR reserves.

## Reproducing

```bash
scripts/match_rinex_to_site.py --root /srv/gnss-archive -o matches.csv
```

~90 minutes; `.Z` files each need a `zcat`.

