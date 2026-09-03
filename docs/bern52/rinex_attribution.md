# RINEX attribution by header position — stage 3

`scripts/match_rinex_to_site.py` reads `APPROX POSITION XYZ` from a RINEX
header and asks the stage-2 catalog which monument that is.

**Candidates, not determinations.** `APPROX POSITION` is a single-point fix
good to roughly 100 m, and a cold start can be kilometres out. Every row
carries the distance that produced it.

## Results over 84,194 files

| verdict | files | meaning |
|---|---:|---|
| `unique` | 59,642 | one catalog site within the radius |
| `aliases` | 19,110 | several codes, all one monument (BLN2/BLNA are 3 m apart) |
| `ambiguous` | 2,919 | several codes genuinely far apart — the header cannot choose |
| `none` | 1,122 | nothing within radius: uncatalogued monument, or a useless header |
| `bad-position` | 1,030 | header position not on the Earth's surface |
| `no-header` | 371 | no `APPROX POSITION` line |

**78,752 of 84,194 (93.5%) attributed to a single monument.**

## Agreement with the filename

The filename and marker are recorded but never preferred over the position.

- **78,471** agree
- **92** conflict — the file names a catalog site that is not where the
  receiver was
- **189** carry a name the catalog does not know (`TEMP`, `DEFA`, receiver
  numbers like `7239`). A position that differs from those is not a conflict;
  it is the attribution this stage exists to produce.

Whether a name counts as contradicting evidence is tested against the catalog,
not a hardcoded placeholder list — campaign point numbers such as `0194` and
`02G1` are legitimate site codes.

## The 92 conflicts are real

The question a conflict raises is whether the header was simply imprecise. The
`claimed_m` column answers it — the distance from the header position to the
site the *filename* claims:

```
matched-site distance   max     144 m
claimed-site distance   min     240 m
                        median  126 km
                        max   12,351 km
0 of 92 conflicts have the claimed site within 200 m
84 of 92 have it more than 1 km away
```

No conflict is inside header noise. These are files whose name points somewhere
the receiver demonstrably was not.

| matched ← claimed | files |
|---|---:|
| PHIV <- MASM | 17 |
| PHIV <- PALA | 10 |
| MASK <- CEBB | 4 |
| MAB2 <- MAB1 | 4 |
| BARA <- BARB | 4 |
| PHIV <- TCDR | 3 |
| MASA <- MASI | 3 |
| MASB <- MAB1 | 3 |
| MAD1 <- MASF | 3 |
| MASK <- LEYD | 3 |

`PHIV ← MASM` is the largest group at 17 files: the header sits 35 m from PHIV
and **1,062 km** from MASM.

## What this does not establish

- **Not which is wrong.** A conflict says the filename and the position
  disagree, not which to believe. The catalog entry could be the error.
- **Nothing about the 1,122 `none` files.** Uncatalogued monument and
  unusable header look identical from here; the distance to the nearest site is
  recorded so they can be told apart later.
- **Nothing about raw files.** This reads existing RINEX. `runpkr00` is not
  installed, so Trimble `.T0x` cannot be decoded on this machine.

## Reproducing

```bash
scripts/match_rinex_to_site.py --root /srv/gnss-archive -o matches.csv
```

