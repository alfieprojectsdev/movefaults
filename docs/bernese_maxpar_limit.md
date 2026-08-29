# ADDNEQ2 `MAXPAR`: why the 47-station PHREF year stalled at zero solutions

*2026-08-29, gps3 (R740), BSW 5.4.*

## Symptom

The full-year PHREF run was launched at 00:04 and by 09:08 had produced
**zero** solutions from 24 attempted days. Every day failed identically:

```
 *** SR neqckdim: DIMENSION TOO SMALL
                  Requested num. of parameters:        1001
                  Maximum size of the array   :        1000
 ERR ADDNEQ2   ERROR IN MAIN PROGRAM
```

24 of 24 completed days, one error class, no others.

## Cause

`$U/OPT/R2S_FIN/ADDNEQ2.INP` shipped `MAXPAR 1000`. That value is the size
ADDNEQ2 allocates for the normal-equation parameter array
(`ADDNEQ2.f90:201  CALL neqalloc(neq,opt%maxpar)`), and `neqckdim`
(`LIB/FOR/NEQCKDIM.f90`) aborts when a requested parameter count exceeds it.

PHREF carries 47 stations against LUZON's 33. Coordinates plus per-station
troposphere parameters push the combined NEQ past 1000.

## The number 1001 is not the requirement

`neqckdim` reports **the first request that overflows**, not the total
needed. That is why the figure was *exactly* 1001 on every one of the 24
days even though station availability varied between 35 and 38 files per
day. Reading 1001 as "we need 1 more parameter" would size the fix wrong.
Only a successful run reports the true count.

## Fix

`MAXPAR 1000` → `3000` in `$U/OPT/R2S_FIN/ADDNEQ2.INP`.
Original kept as `ADDNEQ2.INP.pre-maxpar-20260829`.

3000 is not arbitrary: it is the value BSW 5.4 ships in the generic
`$U/PAN/ADDNEQ2.INP`. The 1000 in the `R2S_*` option directories is the
conservative RNX2SNX default, sized for small regional networks.

Cost is negligible. `SINTRAN1` allocates a triangular matrix of
~`maxpar²/2` doubles:

| MAXPAR | per process | 6 parallel |
|---|---|---|
| 1000 | 4 MB | 0.02 GB |
| 3000 | 34 MB | 0.2 GB |
| 5000 | 95 MB | 0.6 GB |

against 58 GB available.

## Scope of the edit

`R2S_FIN` is shared by `LUZON_DLY`, `LZFLT_DLY`, `PHNAT_DLY`, `PHREF_DLY`
and stock `RNX2SNX`. The edit therefore changes the configuration under
which the completed LUZON year was produced.

That is acceptable because `MAXPAR` is a **capacity ceiling, not an
estimation option**: when a NEQ fits under either value the arithmetic is
identical, so it cannot alter a solution that already succeeded. LUZON's
solutions are in any case already written to `$S`.

## Why the DOY 200 pre-flight test missed this

The single test day used to validate PHREF before launch had **33 stations
with data** — enough to stay under 1000. The busiest days of the year carry
41. A one-day test drawn from the low end of the distribution certified a
configuration that fails on most of the year.

This is the same error pattern recorded three times previously in this
project: **a single sample reported as the population.** The specific
lesson here is that a pre-flight day must be chosen from the *worst* case
for the resource being tested, not an arbitrary one.

## Confirmed, with the true numbers

DOY 002 completed at 10:15 on 2026-08-29 with `MAXPAR 3000` and no error.
The saved SINEX carries **102 parameters (34 stations x 3 coordinates)** —
but that is the *reduced* solution. The pre-elimination NEQ is what
overflowed: coordinates plus per-station hourly troposphere and gradients,
roughly **30 parameters per station**, so ~1020 for a 34-station day. That
is just over the old 1000 ceiling, which is why every single day failed and
why none failed by much.

### This has a consequence for PHNAT

| network | stations | approx. params | at MAXPAR 3000 |
|---|---|---|---|
| PHREF typical | 34 | ~1020 | fine |
| PHREF busiest | 41 | ~1230 | fine |
| PHREF full | 47 | ~1410 | fine |
| **PHNAT** | **102** | **~3060** | **would fail again** |

The 102-station PHNAT campaign that never completed a day would need
`MAXPAR` of at least 5000, and its four recorded failures should be
re-examined with that in mind — the diagnosis at the time attributed them
to metadata gaps, which were real and were fixed, but MAXPAR was never
ruled out and would have blocked it regardless.

Not changed now: PHREF is mid-run at 3000 and the value is demonstrably
sufficient for it. Raise it when PHNAT is next attempted.
