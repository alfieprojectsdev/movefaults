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

A complete IBAZ session is ~700 KB. These are fragments of roughly 4 %.

### They are record-aligned, not block-aligned — but the copy stopped, not the recording

An earlier version of this note read the 4,096-byte minimum as a filesystem
block and inferred a copy damaged mid-transfer. **That does not survive the
data**, which the T420 checked and gps3 confirmed:

```
multiples of  512 :   5/113
multiples of 4096 :   5/113
gcd of all sizes  :   1
```

Five. A copy stopping at a block boundary would leave nearly all of them
multiples of 512, and the single 4,096-byte file is a coincidence of the
minimum — the one datum that made the block reading look right.

They are structured on the **record**. Repeated exact sizes recur across
different files, and the sizes differ by multiples of **135 bytes**:

```
31,131 x8    31,266 x7    30,726 x6    30,861 x5    31,401 x4
```

29 of the 55 distinct sizes appear more than once. Arbitrary truncation
essentially never produces identical file sizes.

**The control makes it decisive.** Residues mod 135, failures against the 239
successful files from the same site:

| | distinct residues (of 135) |
|---|---:|
| the 113 failures | **8** — three classes hold 106 |
| the 239 successes | **119** — effectively uniform |

Random truncation would give ~55, one per distinct size. Instead the failures
are *more* structured than the complete files, which is the opposite of what
damage produces.

**So the likelier mechanism is a recording that ended cleanly**: short sessions,
a receiver powered down, a deployment cut short. Median 30,861 bytes against a
full session's ~700 KB, tightly clustered, fits a site that kept being
interrupted.

**Stated as far as it goes:** block alignment is disproved, record alignment is
demonstrated, and the *cause* is inferred rather than shown. The remaining
discriminator is inside these files — whether the final MDB record is complete
and its timestamp lands at a plausible session end.

teqc reads them correctly. It reports the survey start with the right year:

```
! Notice ! Leica MDB 130: survey starts @ 2012 Aug 31 05:41:34.940 GPS time
```

...and then writes no RINEX, because there are no observation epochs after the
header. **This is not a teqc limitation, a missing flag, or a rollover
problem.** No option recovers observations that are not in the file. The
failures are correct behaviour on incomplete input.

**IBAZ itself is fine** — 239 of its files converted. The split is within the
site, not between sites.

**Nothing here is worth retrying** — no decoder change recovers data absent
from the file, and retry logic would be worse than nothing.

**But better copies do exist, and this note previously argued they would not.**
That argument is retracted below.

## RETRACTION — 105 of the 113 are recoverable, and were the whole time

Measured 2026-09-09 against `DATA0`, docked on the T420. Every one of the 113
has a same-named copy there; 224 copies in total were found and stat'd, none
unreadable.

```
distinct files with a LARGER copy : 105 / 113
no larger copy                    :   8

median truncated    ~30,000 bytes
median drive copy    757,681 bytes      24x larger (range 22x - 186x)
larger-copy sizes    726,497 - 770,337  vs this site's successes 57,344 - 758,603
total recoverable    79,056,949 bytes
```

Genuine MDB, not merely larger — same Leica magic as the files that converted:

```
IBAZ245A.M00   9c ae 88 00 65 ac 07 96 ...   769,065 bytes
IBAZ246A.M00   9c ae 88 00 65 ad 07 96 ...   768,446
IBAZ244F.M41   9c ae 88 00 65 a7 06 5c ...   truncated, matches the archive
```

The 8 without a better copy are the odd extensions — `.M41 .M49 .M55 .M32
.M38 .M44` — plus `IBAZ366A.M00`.

### What was wrong, since the measurement was not

The residue analysis above is correct and stays. 8 residues mod 135 across the
113 against 119 across the 239 successes is real structure, and the control is
sound.

**The inference drawn from it was wrong.** Record-aligned truncation
distinguishes structured truncation from arbitrary truncation. It does not
distinguish *a recording that ended* from *a copy that ended*, because a copy
stopping on buffered record boundaries produces the identical signature. The
note used a correct measurement to settle a question that measurement could not
reach, and then argued against opening the search on that basis.

This is not an instrument returning a wrong answer, which is the failure this
project has catalogued all week. The instrument was right and was over-read.
The nearest relative is `spread_m`: a real number, correctly computed, asked to
mean something it does not.

**The cheap test that settled it was cheaper than the one being argued about.**
224 `stat` calls against drives already docked, versus reverse-engineering an
MDB record layout. When a claim is about whether a file exists somewhere, look
for the file.

### Not yet done

Transferring the 105 to `/srv/gnss-archive` and re-decoding them. 79 MB, but it
modifies the archive tree and belongs to whoever owns that decision.

**These close no new want-list site-years** — IBAZ 2012 is already closed. What
they recover is 105 full observation days that exist in the archive only as
30 KB fragments.

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
