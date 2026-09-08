# Raw vs RINEX counterparts — is decoding worth doing?

**Measured 2026-09-08 on gps3**, against `/srv/gnss-archive` (733,321 files).
Reproduce with `scripts/raw_rinex_counterparts.py --files <listing>`.

CR-20260903 reserved this question deliberately: *how many of the raw files have
no RINEX counterpart* is the number that decides whether decoding the raw
archive is worth doing at all.

## The answer

**94.4% of raw files with a determinable date were already converted. 5.6% —
2,060 files — were not.**

| Tier | Files | Counterpart | **None** |
|---|---:|---:|---:|
| **Evidence** — site + full calendar date in the name | 36,876 | 34,816 (94.4%) | **2,060 (5.6%)** |
| *Inference* — site + DOY, year absent | 33,317 | 32,877 (98.7%) | *440 (1.3%)* |
| Site present, no date at all | 346 | — | not matchable |
| Serial-named, no site | 5,717 | — | not matchable |
| **Total raw** | **76,256** | | |

**Quote 5.6%, not 1.3%.** The inference tier matches against *any* year, which
systematically overstates coverage; it bounds the uncertainty and should not
enter a decision.

## What this converts the question into

The un-converted are not spread thinly — they concentrate in **13 sites**, and
seven of those account for 2,043 of the 2,060:

```
437 BASC   433 BULA   303 AURA   281 CATA
247 BACO   238 BAGU   104 BICA     8 PIVS
  4 BATC     2 LGYE   + 3 sites with 1 each
```

So this is not "build a decoding pipeline for 76,256 files". It is "decode
seven sites, about 2,000 files" — a different decision with a different cost,
and one that can be done by hand if it comes to it.

## Why filename matching works here, and where it must not be reused

Trimble `.T0x` and Leica `.mNN` names are **receiver-assigned and carry a
serial, not a site**. That is what the formats specify, and 5,717 files in this
archive are named exactly that way.

But PHIVOLCS named the rest by site, systematically, across at least five
conventions. Both machines derived and verified this independently:

| Convention | Example | Carries |
|---|---|---|
| site + full timestamp | `CNTA201612170700B.T02` | site, year, DOY |
| site + timestamp, padded | `STNA______202106250400B.T02` | site, year, DOY |
| site + long datetime | `AURA201510240000a0.T00` | site, year, DOY |
| site + DOY + session | `MALA350a.m00`, `JOSE217jC.T02` | site, DOY — **no year** |
| site + DOY + extra | `SABL160j00C.T02` | site, DOY — **no year** |
| 2-char prefix + site | `rbMUNZ0.m00` | site only, no date |
| serial only | `22840610.T02` | nothing |

**Do not carry this assumption to another corpus.** It is a fact about how one
institution filed its data, not about the formats.

## Stability check

The first pass used only the two dominant conventions (denominator 36,655) and
returned 2,060 un-converted. Folding in the three further conventions the T420
characterised raised the denominator to 36,876 — and the un-converted count
stayed at **exactly 2,060**. Every additional site-carrying file was already
converted, which is the result being insensitive to the parsing improvement
rather than a coincidence.

## What this does not establish

* **Not that a counterpart is a good conversion.** Only that one exists.
* **Nothing about the 5,717 serial-named files.** They carry no site to match
  on. They are unresolved, not absent — the distinction the drive-archaeologist
  work has consistently insisted on.
* **Nothing about counterparts outside this archive.** A file converted years
  ago onto media never recovered reads here as un-converted.

## A wrong answer worth recording

The first attempt matched by **directory co-location** — does a raw file sit
beside a RINEX file? — and reported **60.3% orphaned**. That is off by an order
of magnitude.

The largest apparent orphan block, 30,681 files, is under
`.../RECOVERED_SEAGATE_W2A0W9T2_DATA0/RAW/`. A tree named `RAW` holds raw files
by design; its conversions live in a parallel tree. The method measured the
filing convention and reported it as a data gap, and the giveaway was in the
path the whole time.

This is the same shape as the other errors catalogued this week — a proxy
measured in place of the thing — and it is recorded here because the plausible
wrong number came first and looked alarming.

## Related

* `docs/bern52/rinex_attribution.md` — stage 3, RINEX attributed by header
* `docs/bern52/crd_catalog.md` — the coordinate catalog and its want-list coverage
* `scripts/want_list_diff.py` — counts raw files as *unresolved*, conservatively;
  its docstring's assumption that raw names lack site is what this note revises
