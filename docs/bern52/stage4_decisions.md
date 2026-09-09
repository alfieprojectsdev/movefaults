# Stage 4 — what actually needs deciding

`stage4_disagreements.md` reports 91 filename patterns and 110 path
patterns and has sat undecided since #171. It has been described in
handovers as ~200 judgement calls awaiting a human.

**It is not.** Most of it is two mechanical classes and one blocked
dependency. This note separates them so the genuinely undecidable
residue can be seen, and states the evidence for each split rather than
asserting it.

## Summary

| class | files | patterns | who decides |
|---|---:|---:|---|
| ambiguous-code conflicts | 644 | 57 | **nobody** — blocked on per-cluster catalog |
| campaign-directory conflicts | ~900 est. | most of 110 | **nobody** — mechanical, see below |
| stale-header conflicts | ~120 est. | ~15 | **nobody** — mechanical, see below |
| genuine residue | ~90 | ~34 | **a person, per case** |

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

**What this leaves for you:** confirm that campaign-region directories
were in fact the filing convention — you would know, and everything
above is one directory generalised. If some regional directories *were*
meant as site claims, the rule needs a carve-out.

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

**The likely mechanism is a header carrying the HQ position rather than
the field position** — a receiver initialised, tested or last-positioned
at PHIVOLCS before deployment, whose `APPROX POSITION XYZ` was never
updated. `match_rinex_to_site.py` warns of exactly this: the header is a
single-point fix and *"a cold start can be kilometres out."*

If so these files are **correctly named and wrongly headered**, which is
the reverse of what a conflict normally implies, and the filename should
win for this class.

**Testable before anyone decides.** `TIME OF FIRST OBS` against the
deployment date, and whether the same receiver serial appears in HQ
files. Neither has been checked.

**What this leaves for you:** confirm that receivers were staged at HQ
before deployment. If yes, this class is mechanical and the filename
wins.

---

## 4. The residue — this is the part that needs a person

After the three classes above, roughly 34 patterns and 90 files remain
where the filename and the header genuinely disagree about an
unambiguous code, the marker agrees with the filename, and no mechanism
explains it.

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
3. Confirm HQ staging → removes the `PHIV` class, filename wins.
4. Then look at ~34 patterns, of which the sub-kilometre pairs need
   somebody with site knowledge and the rest need case-by-case reading.

Doing 4 first — which is what "review the stage 4 report" has meant so
far — means reading 200 patterns to find 34.

## What is asserted here versus measured

**Measured:** the session directory contents, the sibling session
directories, `PHIV`'s catalog row and position, the paths of the
`PHIV`-matched files, the 644/91 split, the 240 m minimum.

**Inferred and not yet tested:** that campaign-region directories were
the general filing convention rather than one person's habit on one
drive; that the `PHIV` matches are stale headers from HQ staging. Both
are stated as questions above rather than folded into the counts.
