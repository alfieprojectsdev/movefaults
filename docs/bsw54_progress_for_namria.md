# BSW 5.4 on the new PHIVOLCS server: progress to 18 September 2026

*Written for Charisma (NAMRIA), to judge whether the setup and results are
sound and to flag where they differ from NAMRIA's own practice. Draft, not yet
reviewed by anyone at PHIVOLCS.*

Bernese 5.4 is installed, patched, verified, and has processed a full year of
daily solutions. The comparison against PHIVOLCS' production results is an
agreement test, not a reproduction.

## Installation and verification

Bernese 5.4 runs on a Dell PowerEdge R740 (a rack server, 24 cores, 62 GB RAM)
under Linux. Verification was against AIUB's own reference campaign: the server
reproduces it to 0.0000 mm. An earlier install on a ThinkPad T420 reproduced it
to 0.09 mm or better. That was signed off on 29 July 2026.

Since 2 September 2026 the software is compiled locally (gfortran 13.3.0)
instead of run from AIUB's prebuilt binaries. All 88 executables were rebuilt,
and the locally built ones reproduce the prebuilt results on both our own
pipeline and AIUB's example campaign. Until that date the machine had no
Fortran compiler at all.

## The published fixes are applied

The install is release 2024-11-11. All 7 published fixes were applied together
on 2 September 2026, as AIUB requires, since the fixes are cumulative and
applying a subset can damage an install. All 88 executables were rebuilt.

The two that could have changed results didn't, for a reason worth stating. One
sets the geomagnetic field model used for higher-order ionospheric corrections,
which this processing doesn't apply. The other removes redundant station
lookups when troposphere SINEX output is off. Verified rather than assumed:

| test | result |
|---|---|
| our own processing, day 201, same 35 stations | 0.00 mm RMS |
| AIUB's EXAMPLE campaign, 340 stations | 0.010 mm maximum 3-D difference, which is the coordinate file's print precision |

So the 2025 year and the comparison below, which were produced before patching,
remain valid statements about this pipeline, and later reprocessing on the
patched build is comparable with them.

The third fix worth knowing about cuts RNXGRA runtime by a factor of 5 to 6,
and we run RNXGRA once per session.

An earlier draft of this page said none of the fixes were applied. That was
wrong. Two of our own documents said so in the present tense for three weeks
after the work was done, because both were written three days before it and
neither was dated. Corrected here rather than quietly removed, in case an
earlier version was read.

## Production runs

The 2025 LUZON year is at 358 of 365 days, across three runs plus a recovery of
day 036. The final run did 249 days in 476 minutes, about 1.91 minutes per day.
An earlier month-long run completed 30 of 30 days unattended at 5 minutes 33
seconds per day.

## The failure worth telling you about

A 47-station national run was launched at 00:04 and by 09:08 had produced zero
solutions from 24 attempted days. Every day failed the same way, in ADDNEQ2:

```
*** SR neqckdim: DIMENSION TOO SMALL
                 Requested num. of parameters:        1001
                 Maximum size of the array   :        1000
```

The cause was `MAXPAR 1000` in `$U/OPT/R2S_FIN/ADDNEQ2.INP`, the size ADDNEQ2
allocates for the normal-equation parameter array. Raising it to 3000 fixed it:
day 002 completed on 29 August 2026 with no error, and 309 or more days have
since succeeded.

We still don't know the actual requirement. We know only that it exceeds 1000
and is below 3000. The value 1001 in the message is where the check tripped,
not what the run needed. A pre-flight test on a single day had missed the
problem because that day's station count was lower.

One related item, in case it saves you time: a campaign needs seven reference
file types present, `.CRD .VEL .ABB .STA .BLQ .ATL .CLU`, and the `.ATL` file
needs a trailing blank line as a block terminator or it isn't read.

## Comparison against PHIVOLCS production

On 1 September 2026 we compared our 2025 solutions against PHIVOLCS' retained
production results. All 53 weeks had a counterpart, giving 1,979 station-week
residuals. After a 7-parameter Helmert alignment, the median residuals were:

| component | median | mean | range |
|---|---|---|---|
| North | 1.29 mm | 1.36 | 0.67 to 2.38 |
| East | 2.37 mm | 2.75 | 1.57 to 6.47 |
| Up | 7.09 mm | 7.31 | 5.84 to 10.25 |

This is an agreement test, not a reproduction. The two differ in version (5.4
on Linux against 5.2 on Windows) and in constraints, and our daily solutions
are stacked to weekly while theirs were computed weekly. The networks differ
in size: PHIVOLCS' 2025 weekly solutions carry 87 to 95 stations (median 91),
and ours about 35. Every station we process is in theirs. The difference is
which stations each network includes, not missing data: we hold 2025
observations for 53 of the 58 stations they process and we don't. It is also
not PAGENET: only two NAMRIA stations, PMAT and PTAG, appear in their weekly
solutions. It can't be bit-for-bit and isn't offered as such.

## Open items

- 7 days of the 2025 LUZON year are still missing
- The parameter requirement behind `MAXPAR` hasn't been measured, only bounded
- We hold PAGENET observations for ten days only: 2026 DOY 081 to 090 (22 to
  31 March), which is all of GPS week 2411 plus the first three days of 2412
  and appears to be the NAMRIA training campaign. DOY 084 to 090 are complete
  at 71 to 72 sites; 081 to 083 are partial at 59 to 60. The 72 sites in
  `PGN.CRD` are **62 PAGENET stations plus 10 global fiducials** (CUSV, DAEJ,
  DARW, GUAM, HKSL, HUMG, JOG2, NTUS, PIMO, TWTF), so it is 62 of your marks we
  hold for those ten days, not 72. Note that the `P` prefix does not separate
  the two: PIMO is a fiducial, operated by JPL and hosted at Manila
  Observatory. For 2025, the year of the comparison above, we hold three
  PAGENET site codes: PBOG, PMAT and PTAG. Reference coordinates for all 72 are
  already staged here, so what is missing is observations, not setup.

That last item is the one where you can tell us something we can't work out
here. PAGENET data is NAMRIA's, and if it should be in this processing as a
matter of course, the gap is a data feed rather than anything in Bernese.

One case shows a feed already working, which is why we ask. PMAT, at Mati City,
is a PAGENET station that PHIVOLCS added to its own processing after an
earthquake in the area, and its 2025 files here carry a `MOVEFaultsProject
PHIVOLCS` header where PBOG's and PTAG's carry `PAGeNet NAMRIA`. So a route
exists and has been used at least once, for one station, on one occasion.
Whether that was a standing arrangement or a one-off request is the part we
can't see from here.
