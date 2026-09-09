# Stage 4 — what actually needs deciding

`stage4_disagreements.md` reports 91 filename patterns and 110 path
patterns and has sat undecided since #171. It has been described in
handovers as ~200 judgement calls awaiting a human.

**It is not.** Most of it is two mechanical classes and one blocked
dependency. This note separates them so the genuinely undecidable
residue can be seen, and states the evidence for each split rather than
asserting it.

## Summary

**The 735 filename conflicts partition one way only: by whether the claimed
code is ambiguous.** That sums, and nothing else here does.

| | files | resolved by |
|---|---:|---|
| claims an **ambiguous** code | 644 | per-cluster catalog — nobody decides |
| claims an **unambiguous** code | 91 | see below |
| | **735** | |

**The stale-header class cuts across that partition and is not a third
bucket.** 95 files match `PHIV` while named for somewhere else, and they
split 48 / 47 across the two rows above:

```
PHIV-matched, filename != PHIV     95
  of those, claimed code ambiguous 48   <- already inside the 644
  claimed code unambiguous         47   <- inside the 91
```

An earlier version of this note listed 644, 95 and ~90 in one table as
though they were exclusive. They sum to 829 against a total of 735,
because they are not a partition — they are two classifications on
different axes. Caught in review; the arithmetic is the tell.

**So the residue is 44 files, not ~90:** 91 unambiguous-code conflicts
minus the 47 the stale-header rule resolves.

| class | files | who decides |
|---|---:|---|
| ambiguous-code | 644 | **nobody** — blocked on per-cluster catalog |
| stale-header (of the 91) | 47 | **nobody** — filename wins |
| **genuine residue** | **44** | **a person, per case** (~34 patterns) |
| campaign-directory *(paths, separate count)* | ~900 | **nobody** — flag and skim |

Path conflicts are counted separately throughout — 1,017 of them across
110 patterns — and are not part of the 735.

---

## 1. The 644 are waiting on the catalog, not on judgement

The report already says this: a code the catalog marks `ambiguous` names
more than one monument, and the published row carries only the largest
cluster. A file claiming such a code whose position matches a *different*
site is the catalog being unable to say which monument the code meant.

`feat/crd-catalog-clusters` — per-cluster catalog output — is the fix,
and it is in progress on gps3. **These 644 resolve without anyone
deciding anything**, and reviewing them before that lands is wasted work.

`SOLD` is the worked example: one code, two monuments 632 km apart, one
published coordinate, and the Muntinlupa monument consequently absent
from its own network's site count.

---

## 2. Path conflicts: the directory names a campaign, not a monument

**Evidence, not inference.** The largest path-conflict group is files
whose header matched an IGS global station while the directory says
`masb`. The actual path:

```
toto_C/GPSR/1997 masbate/970530A/RAW/
```

and the complete contents of that one session directory:

```
GUAM1501.97O   S01R1501.97o   SHAO1501.97O   TSKB1501.97O   WUHN1501.97O
ilo11501.97O   mase1501.97O   tonw1501.97o   vrc11501.97O
```

Every file is DOY 150 of 1997. The siblings are `970530A`, `970531A`,
`970601A`, `970603A` … — **one directory per session day of a campaign.**

`mase1501.97O` is the Masbate observation. `GUAM`, `TSKB`, `SHAO`,
`WUHN`, `S01R` are IGS fiducials fetched to process it. `ilo1`, `tonw`,
`vrc1` are other Philippine sites in the same network.

So `1997 masbate` names **the campaign**, and a campaign legitimately
contains files from many sites. The directory is not making a false
claim about where `GUAM1501.97O` was observed; it was never making that
claim.

**This does not mean paths are untrustworthy in general.** For
`mase1501.97O` the directory is correct. What it means is narrower:

> A directory that names a campaign is not a site claim about every file
> under it, and a conflict between such a directory and a header is not
> evidence about either.

**Mechanically detectable**, so no per-pattern judgement is needed: a
campaign directory has sibling directories matching a session pattern
(`YYMMDD` plus a session letter), or a `RAW/` child, or holds files from
three or more distinct site codes on the same DOY. Any of those is
sufficient to stop treating the parent as a site claim.

**Confirmed 2026-09-09: campaign-region directories were the general
convention** — with rare occasions where a directory instead means
"processed with", a purely functional grouping.

**That exception is why the rule must flag rather than reclassify.** The
two conventions need opposite readings for the namesake site's own
files:

| directory means | `mase*.97O` under `1997 masbate` | `GUAM*.97O` under it |
|---|---|---|
| campaign region *(general)* | **is** Masbate data — path is good evidence | fiducial — path says nothing |
| "processed with" *(rare)* | **not necessarily** Masbate data | fiducial — path says nothing |

For the non-namesake files the answer is the same either way, which is
most of the ~900 and is safe to suppress automatically. For the
namesake's own files the two conventions disagree, and nothing in the
directory structure distinguishes them.

So: **the detector emits a list, it does not rewrite attributions.** A
rule that silently applied the general case would quietly mis-file the
rare one, and the rare one is invisible precisely because it is rare —
the same shape as every failure this project has catalogued. The cost of
flagging is a list somebody skims once; the cost of auto-applying is
wrong attributions nobody ever looks at again.

Cheap discriminator if the rare cases need finding later: in a
campaign-region directory the namesake's files should be present across
most session days, since it is the site being surveyed. In a
"processed with" grouping there is no reason for that pattern to hold.

---

## 3. `PHIV` is a real monument, and the conflicts are stale headers

`PHIV` appears as the matched site in most of the genuine-looking
filename conflicts — 32 files claiming `ALCA`, plus `JARO`, `ORAS`,
`TCDR`, `AGUS`, `SAPN`, `MUNT`, `PALA`, `ATIM`, `MASM`.

It is in the catalog:

```
PHIV   14.6521880 N  121.0587259 E   236 files   spread 67.31 m
       nearest other site: PIVS at 23.8 m
```

That is **Quezon City — PHIVOLCS HQ**, with `PIVS` 23.8 m away, so the
two are markers at the same compound.

The conflicting files are ordinary station data named for their real
sites:

```
datapool/PHIVOLCS/2016/MUNT2800.16d.gz   header matched PHIV, 28 km away
datapool/PHIVOLCS/2018/AGUS3240.18d.gz   header matched PHIV
```

**Mechanism confirmed.** Receivers are tested at PHIVOLCS HQ before
field use as standard practice, and the header keeps the position it
fixed there. Confirmed as domain practice 2026-09-09, and the data
agrees on three independent counts.

**The header positions are a tight cluster at HQ, not cold-start
scatter** — which matters, because `match_rinex_to_site.py` warns a cold
start can be kilometres out, and that would be a different and less
tractable problem:

```
122 PHIV-matched files
header -> PHIV distance    min 0.7 m   median 34.9 m   max 67.3 m
```

A receiver that has genuinely fixed its position at HQ writes a good HQ
position. That is what these are.

**Filename and marker agree with each other on every one:**

```
name == marker : 122 of 122
name != marker :   0
```

Two independent records — what somebody typed as the filename, and what
was configured as the RINEX marker — both name the *field* site, while
only the position names HQ. A typo produces one disagreement, not two
records agreeing against a third.

**27 of the 122 are named `PHIV` and are not conflicts at all** — they
are genuinely HQ data. The remaining **95 are the class**:

```
ALCA 32   MASM 19   PALA 10   MUNT 7   ATIM 6   TCDR 3   ORAS 3
LABO 3    JARO 3    and a tail
```

So these files are **correctly named and wrongly headered**, the reverse
of what a conflict normally implies. **The filename wins for this
class**, and it is identifiable mechanically: header within ~70 m of
`PHIV`, filename equal to marker, filename not `PHIV`.

**Consequence worth stating.** Stage 3 attributes by header position, so
every one of these 95 is currently attributed to HQ instead of the site
it was observed at. This is not only a reporting artifact — it is 95
files filed under the wrong monument.

### The HQ rooftop is many codes on one location — the inverse of `SOLD`

The antenna on the PHIVOLCS roof has been relocated several times, likely under
a different site code each time. Confirmed as history 2026-09-09, and the
catalog shows it:

```
site   dist from PHIV   n_files   spread_m   catalog epochs
PHIV        0.0 m          236      67.31    1998-02-15 .. 2008-08-28
PIVS       24.0 m          949      19.17    2012-01-01 .. 2014-03-12
PHIC       24.1 m           94      79.40    1998-02-21 .. 2006-12-05
UP02      352.7 m          319     116.61    1997-05-08 .. 2006-12-13
```

This is `SOLD` inverted. There, **one code named two monuments** 632 km apart.
Here, **several codes name one rooftop**, 24 m apart with spreads of 19-79 m.
Both break attribution, and neither is a data error — they are how the naming
was actually done.

**Position cannot separate these codes and never will.** They are closer
together than the spread of any one of them, and far closer than the ~35 m a
header fix is good for. Stage 3's `aliases` verdict on these files is therefore
correct behaviour, not a defect: it is reporting that the position does not
decide.

### Epoch does separate them, and stage 3 does not use it

The file's observation year against the matched site's catalog epoch range
splits the `PHIV` matches perfectly:

```
the 95 stale-header files    2016  2018  2019  2020  2022  2023
                             -- every one AFTER PHIV's last epoch, 2008-08-28

the 27 genuinely-PHIV files  1998  1999  2000  2004  2006
                             -- every one INSIDE PHIV's range
```

Zero overlap. A 2020 file cannot be an observation of a monument whose catalog
coverage ended in 2008; it is a 2020 receiver carrying a stale HQ position. That
is a fourth independent confirmation of the staging explanation, and it arrived
free from data already in the catalog.

**Recommendation for stage 3:** compare the observation epoch against the
matched site's `epoch_min`/`epoch_max` and flag matches falling outside it. It
costs two columns already present in `crd_catalog.csv`, it would have isolated
this entire class automatically, and it generalises — any site whose code was
retired and whose position is still being matched will show the same signature.

**Caution on the rooftop codes specifically.** Because the antenna moved, a
single code's spread is tens of metres, so any position-based rule near HQ
should treat `PHIV`, `PIVS` and `PHIC` as one location family rather than
three sites. Distinguishing *which* rooftop position a given file used is an
epoch question, not a position question, and may not be answerable at all for
files inside the overlapping 1998-2006 window where `PHIV` and `PHIC` ran
concurrently.

---

## 4. The residue — this is the part that needs a person

**44 files** remain, across roughly 34 patterns, where the filename and
the header genuinely disagree about an unambiguous code, the marker
agrees with the filename, and no mechanism explains it. That is the 91
unambiguous-code conflicts minus the 47 the stale-header rule resolves.

```
matched   filename says   files   header -> claimed
ESEQ      ORAS                8     1,320 km
MAB2      MAB1                4       682 m
PTGYYTAY  TONU                4       524 km
MASB      MAB1                3       664 m
LHOV      0500                2     1,245 km   (marker disagrees, 0/2)
```

Two shapes, and they are not the same question:

**Sub-kilometre pairs** — `MAB2`/`MAB1` at 682 m, `MASB`/`MAB1` at
664 m. Adjacent monuments with adjacent names. Plausibly a transcription
slip, plausibly two real markers. **A person who has been to the site
settles this in a sentence**; no amount of analysis will.

**Continental-scale** — 500 to 1,300 km. Not header error, not a typo in
a digit. Something was filed or copied from elsewhere, and the answer is
probably specific to each case.

Across all 735 conflicts, **none is within 200 m** — i.e. none is
explainable by header imprecision alone. Every one is a real
disagreement about something.

---

## Recommended order

1. Land `feat/crd-catalog-clusters` → removes 644 with no decisions.
2. Confirm the campaign-directory convention → removes most of 110.
3. ~~Confirm HQ staging~~ **done** → 95 files, filename wins.
4. Then look at ~34 patterns, of which the sub-kilometre pairs need
   somebody with site knowledge and the rest need case-by-case reading.

Doing 4 first — which is what "review the stage 4 report" has meant so
far — means reading 200 patterns to find 34.

## What is asserted here versus measured

**Measured:** the session directory contents, the sibling session
directories, `PHIV`'s catalog row and position, the paths of the
`PHIV`-matched files, the 644/91 split, the 240 m minimum.

**Confirmed 2026-09-09:** HQ receiver testing before field deployment is
standard practice, which explains the `PHIV` class. The supporting
measurements — the 0.7-67.3 m clustering and the 122/122 name-marker
agreement — were made after the confirmation and agree with it.

**Inferred and not yet tested:** that campaign-region directories were
the general filing convention rather than one person's habit on one
drive. Stated as a question above rather than folded into the counts.
