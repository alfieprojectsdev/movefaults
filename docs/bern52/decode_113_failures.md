# The 113 decode failures: truncated Leica MDB, not a tool problem

**Measured 2026-09-09 on gps3.** `decode_raw_gap.py` reported 113 conversion
failures in a 3,984-file run and did not record which files, so they could not
be investigated without redoing the run. This is that re-run, with per-file
outcomes in `decode_outcomes_20260909.csv`.

## The answer

**All 113 are the same thing: truncated Leica MDB files from one site.**

```
site        IBAZ, all 113
format      Leica .mNN, all 113
size        every failure  <= 33,684 bytes
            every success  >= 57,344 bytes
```

**The separation is clean and has no overlap.**

| | n | min | mean | max |
|---|---:|---:|---:|---:|
| `convert_failed` | 113 | 4,096 | 29,538 | 33,684 |
| `ok` | 239 | 57,344 | 703,094 | 758,603 |

A complete IBAZ session is ~700 KB. These are fragments of roughly 4 %, and the
smallest is **exactly 4,096 bytes — one filesystem block.**

teqc reads them correctly. It reports the survey start with the right year:

```
! Notice ! Leica MDB 130: survey starts @ 2012 Aug 31 05:41:34.940 GPS time
```

...and then writes no RINEX, because there are no observation epochs after the
header. **This is not a teqc limitation, a missing flag, or a rollover
problem.** No option recovers observations that are not in the file. The
failures are correct behaviour on incomplete input.

**IBAZ itself is fine** — 239 of its files converted. The split is within the
site, not between sites, which is what points at recovery damage rather than a
format or firmware difference. That these are block-aligned fragments recovered
from a failing drive is the likely explanation and fits how the archive was
assembled.

**Nothing here is worth retrying.** Any effort belongs in the drive-archaeologist
question of whether better copies of those 113 sessions exist elsewhere, not in
the decoder.

## The 2 epoch rejections are the guard working

```
JOSE139aB.T02   got 2011, want 2012
LUZC050a.m01    got 2011, want 2012
```

Both are files filed under a 2012 directory containing 2011 data. The rollover
guard caught a filing error, which is what it is for, and rejecting them is
right: accepting either would have written a 2011 observation into a 2012
want-list slot, and it would have looked correct.

## Reproduction

The run reproduces the original exactly:

```
ok 3,869    convert_failed 113    bad_epoch 2      (this run)
ok 3,869    conversion failed 113    epoch-rejected 2   (the original)
```

Same selection, 3,984 files, on an independently regenerated archive listing.

## Two method notes, both of which cost a run

**The tool poisons its own input.** `--archive-list` regenerated from a live
`find` now includes `derived/decoded-2012/`, whose 2,977 outputs match the RINEX
pattern, satisfy the want-list entries, and empty the selection. The first
attempt here selected **1 file instead of 3,984** and reported success. Exclude
the output directory when generating the listing; `decode_raw_gap.py` now also
drops such paths and prints the count.

**A script written to investigate unrecorded failures buffered its own record.**
The first complete attempt was killed at file 3,200 having found 12 failures,
and lost all 12 because the CSV writer had never flushed — the exact defect it
existed to study, in the tool studying it. The rerun writes and `fsync`s every
row and resumes from what is already recorded.

## Related

* `scripts/decode_raw_gap.py` — the decoder; now writes `decode_manifest.csv`
* `docs/bern52/raw_rinex_counterparts.md` — why only these files are decoded
