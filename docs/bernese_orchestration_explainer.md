# GNSS processing orchestration: what it does for our processing work

This is for the processing staff. It explains what "orchestration" means for
our Bernese processing, what runs automatically on gps3 today, what still
needs a person, and what we need from you.

Where things stand:

- **Production Bernese runs go through the processing service on gps3** since
  4 November 2026. The first production run was LUZON January 2026: 31 of 31
  days, in 53 minutes.
- **PHREF 2025 has been reprocessed through it**, all 360 planned days. Its
  positions differ from the ones it replaced, by 0.02 mm on a typical day and
  by 40.5 mm at most. **Why is not yet known**, and no velocity has been
  re-measured from the reprocessed year yet.
- Preparing a campaign (staging, products, ocean loading) and checking results
  afterwards are still done with the scripts in `scripts/`.
- A browser console on gps3 shows the processing to anyone with a login. Its
  Start, Stop and Redo buttons work for the people the maintainer names as
  operators. How to use it, step by step, is in
  `docs/bsw_console_work_instruction.md`.

---

## The problem we all know

Every GNSS processing cycle carries the same overhead:

- Open the Bernese menu. Navigate to RUNBPE. Check that the campaign path is set correctly.
  Hope that last session's settings weren't accidentally saved over.
- Download IGS precise orbits and clocks from CDDIS. Retry when the server is down.
  Try the IGN mirror instead. Remember which mirror worked last month.
- Decompress the RINEX files. Run `CRX2RNX`. Copy them to the right `RAW/` subdirectory.
- Check the `.STA` file. Did we update the antenna height entry for that October field campaign?
  Edit it manually. Try to remember the exact column widths.
- Run BPE. Watch the screen. Something failed at step 221 (RXOBV3): station header mismatch.
  Find the bad station. Fix the `.STA` entry. Re-run from scratch.
- Wait out the run. Check `RNX2SNX.OUT`. Everything looks OK.
  Copy the SINEX files to SAVEDISK. Update the tracking spreadsheet.

Multiply this by every session, every campaign, every year. Then ask: **how much of this work is science, and how much is file management?**

---

## What orchestration means

Orchestration does not replace Bernese. It does not replace you.

It is a program that knows the correct sequence of steps, does the file
management, calls Bernese when everything is ready, and checks the results when
it finishes. The rules are written down once, in code, and followed the same
way every time.

On gps3, one processing run goes like this:

```
Someone asks for:  Campaign = LUZON, Year = 2025, Days = 121-151
                   (an operator on the console's Plan page, or the maintainer
                   on the command line)

Before the run (the maintainer, with scripts/):
  - fetch CODE orbits, clocks, ERP, biases and ionosphere maps from the SWITCH
    S3 mirror (the AIUB FTP server is blocked from gps3)
  - stage the RINEX files and merge the ocean-loading (BLQ) file

The run (the processing service):
  1. Plan: leave out days with fewer than three reference stations; check the
     PCF's steps and their WAITs, and (on the console's Plan page) every day's
     products; check the station files (STA, CRD, BLQ, ATL, ABB) the way
     Bernese reads them, and refuse the run on a blocking finding; show MAXPAR
     beside the busiest day's station count, and run that day first as the
     real test of it
  2. Take the machine-wide BPE lock, so only one run uses Bernese at a time
  3. Check each day's RINEX headers against the .STA and refuse on a mismatch,
     then run Bernese non-interactively, several days at once, each day in its
     own working campaign, every step of the PCF
  4. On a failure: name the failed step, look the message up in the
     known-errors list, and decide whether the run stops
  5. Keep each finished day's results in SAVEDISK and mark them done, so a
     run that is started again skips them
  6. Record every attempt in the run record (the ledger)

Afterwards:
  The console shows each day's state, the run's progress, each day's results,
  the stations in the solution and any dropped since the day before, and the
  HELMCHK RMS. There is no database of coordinates yet.
```

Every BPE step (RNXGRA, RXOBV3, MAUPRP, GNSQIF, HELMCHK and the rest) is
Bernese's own. **Orchestration does not change the science.** What changes is
who carries the files. gps3 does differ from production in other ways: it runs
Bernese 5.4 with 5.4's stock panels, not your 5.2 panels, and its network and
constraints are different too, so its results agree with production rather than
reproduce it. PHREF 2025 against production, week by week, after a 7-parameter
Helmert alignment: median 1.26 mm north, 2.28 mm east, 6.99 mm up. That was
measured on the 29 August solutions and hasn't been re-measured on the
reprocessed year.

---

## Why this matters: four problems it solves

### 1. Reproducibility

If you processed session 2023/010 in February, and re-process it in December
with a newer IGS final orbit, **will you get the same answer?** With the menu,
you may not be able to say, because the settings used in February are not
recorded anywhere. They lived in a panel file that has since been overwritten.

On gps3 two things are recorded.

The settings can be checked. The driver scripts live in this repository
(`config/bernese/gpsuser/`) and are applied to the server by one command
(`scripts/provision_gpsuser.py`). The production PCFs (LUZON_DLY, PHREF_DLY,
PHDEN_DLY) and panels (`${U}/OPT/R2S_*`) are on gps3, not in the repository, so
the commit history does not answer "which settings were active". The panels are
Bernese 5.4's stock ones, apart from MAXPAR in two `ADDNEQ2.INP` files, changed
on the server with a backup beside each. The run record names the PCF each run
used and keeps a checksum over it and every panel it uses, so a setting that
changed between two runs shows as a different checksum. That says something
changed, not what.

Every run is recorded. The run record (`ledger.jsonl`, beside each year's
`SOL/` folder) keeps one line for each attempt at a day, with its outcome,
error, duration and station count. For each run it also keeps who started it,
the exact command, the code version, the PCF, that checksum and the orbit
products it read. The console shows this on each day's page. What it does not
yet keep is the ambiguity fixing rate: Bernese's ambiguity summaries are not
archived.

**An example from our own files of why this matters.** When the velocity script
was rewritten in Python (see "Your velocity script runs without MATLAB"), the
new version was checked against the saved `Velocity_rover(regress)_10` output
for the Luzon campaign set. Four sites disagreed. The new code was not wrong:
**the saved velocity file was written on 9 July, and the `offsets` catalog it
depends on was edited on 29 July.** The output and its input had drifted twenty
days apart, and nothing in either file recorded that.

With the catalog rebuilt as it stood on 9 July, those sites agreed. No harm was
done, but it is exactly how, months later, nobody can say whether a number is
reproducible. **A velocity file only means something alongside the exact
catalog that produced it.** The console's Time series page shows the catalog's
path and a checksum (sha256) beside every velocity for that reason.

### 2. Knowledge in a few heads

The processing procedure is documented, and the work instruction covers it
thoroughly. But a document that describes what to do is different from a
system that does it. Every manual step is a chance for the document and reality
to drift apart: a mirror URL changes, a `.STA` column format gets adjusted, a
new instrument brings a filename pattern the document hasn't caught up with.

An orchestrator is the procedure, written as code that runs. It either works or
fails visibly, which is a much shorter feedback loop than a document drifting
out of step with practice. The work instruction does not disappear: it is the
reference for what to do **when the orchestration flags an exception**, which
is exactly where human judgement is needed. For new staff, the orchestrator
handles the routine; the work instruction teaches the reasoning behind it.

### 3. Scale

PHIVOLCS operated about 270 active stations nationwide as of December 2024,
continuous and campaign sites together, with over 300 GPS sites contributing
data since 1995. Processing each station's daily data by hand was feasible when
the network was small. It is not feasible at 270 stations, and the network is
not getting smaller.

What we have measured on gps3, the Dell R740:

- One LUZON day of 30 stations takes **5 minutes 33 seconds**, using about a
  sixth of the machine. A month run one day at a time, 30 days, took **2 hours
  47 minutes, 30 of 30 successful** (August 2026).
- Run several days at once, LUZON January 2026 took **53 minutes for 31 days**,
  with 23 to 25 stations a day.

The processing lead reprocessed the full 2025 PH network on one of the Windows
servers, and it took **several weeks**. That gap is worth understanding rather
than celebrating, because the runs are **not the same job**:

- That run processed the national network (**about 52 stations a day**); ours
  process LUZON or PHREF.
- That run used the full production PCF including `FTP_DWLD`, which fetches
  products over the network for every session; ours read products staged
  beforehand.
- That run produced weekly and monthly combinations (`ADD_WK`, `ADD_MON`); ours
  do not.
- That run was attended, in working hours, on Windows; ours run on Linux,
  overnight if need be.

So the right conclusion is **"this looks very promising and we should measure
it properly"**, not "we are twenty times faster". A like-for-like run (same
station set, same PCF, same products) is the honest way to find the real
number, and it has not been done yet. If the difference turns out to be mostly
`FTP_DWLD` waiting on remote servers, that is worth knowing too: the win would
be in staging data once, not in the processing.

For the national network: `PHIVOLCS.CRD` catalogues **439 stations**, but a
daily solution estimates **52** (50 PHIVOLCS and 2 IGS). That is comfortably
inside every limit that matters, so the national daily processing does **not**
need to be split into subnetworks. If we ever process many more of those 439
sites, that changes, and PHIVOLCS' existing regional grouping (Luzon;
Ragay-Bondoc-Marinduque-Masbate; **CBPN**, that is Cebu, Bohol, Panay and
Negros; Samar-Leyte; Cotabato-Sindangan; Eastern Mindanao) is the partition we
would use, because it already follows the island groups rather than anything
invented for the software.

### 4. Your workstation

A BPE run takes over whatever machine it runs on. On the T420 laptop a single
real processing day took **about 2 hours**, roughly 40 minutes of it inside one
step solving the final system on a single core. Seven days of processing, and
the machine is gone for the week.

The processing runs on the R740 (gps3) instead. Bernese 5.4 was installed there
on 29 July 2026, and rebuilt on the machine on 2 September with AIUB's published
patches. The rebuild was compared with the previous binaries: 0.00 mm on one of
our own days, and at most 0.010 mm on Bernese's 340-station EXAMPLE campaign,
which is the precision the CRD file prints. The R740 has 12 cores (24 threads),
with the campaign data on its own 4 TB volume. Runs are supervised remotely: a
run started at the office has been followed from a home network, with no
terminal left open and nothing exposed to the internet.

Starting a run from your desk is done in the browser console: an operator
queues a preflight and then Start on the Plan page, and the run worker on gps3
carries it out. Your PC stays free. The maintainer decides who is an operator.

LUZON 2025, DOY 121 to 151, ran overnight without supervision: 30 days, zero
failures (DOY 139 was left out, because too little data exists for that day).
The coordinates have a day-to-day repeatability of **2.8 mm north,
3.0 mm east, 10.9 mm up**, ordinary for daily solutions, which is the point.
Nobody sat with it.

---

## A test that failed, and what we learned

The plan was to process a year by running many sessions at once. Bernese
supports exactly that: a documented "Run sessions in parallel" option we had
never switched on.

With it switched on, five days of LUZON genuinely ran side by side. Then **four
of the five failed**, all at the same step, all with the same message: *"No
input files"*.

The cause is in the Bernese manual, stated plainly: running many sessions inside
**one campaign directory** requires that every script and temporary filename be
independent of the session. Ours are not: the five sessions were staging their
RINEX into the same working folder and consuming each other's files.

The fix is also in the manual: **one campaign directory per session**. That was
tested next. Five sessions, each in its own campaign, finished in 16 minutes 51
seconds. The evidence that this gives the same answer comes from a later test
on PHREF 2025: DOY 094, 096 and 098, run one at a time, came out identical,
coordinates included, to the same days run six at a time. That is three days,
not a whole year. It is how production runs now: each day in its own working
campaign (for example `LZY250360`), several at a time.

This stays written up because a failed test that gets recorded is worth more
than a successful one that gets assumed. The whole point of this work is that
results come with evidence attached.

*(Nothing was lost. The 30-day results were copied aside before the test and
checked identical afterwards, all 30 solutions, coordinates included.)*

---

## When a run fails

On 29 August 2026 a year-long run produced nothing for nine hours: 24 days in a
row failed on the same message, because one setting (`MAXPAR`, the largest
number of parameters ADDNEQ2 may combine) was too small. The fix had been
written down since March. Nothing in the processing could look it up, so a
person found it again by hand.

Three things now stand between a failure and a lost night.

- When a day fails, the failed step is read, not guessed. The run reads the
  step's own protocol and log files and names the PID, the script, the program
  and the `***` message that failed. A rerun of the same day writes to the same
  folder, so only files from the latest attempt are read.
- The message is looked up in a list of known errors, a plain file,
  `config/bernese/bpe_errors.yaml`. Each entry says what the error means
  here, what to check and change, and where that knowledge came from. An entry
  is *established* when we have seen the error on our own runs and the fix was
  confirmed by a run that then worked, and *proposed* when it comes from AIUB's
  FAQ or reasoning and has not been seen here yet. Today it holds 11 entries,
  7 established and 4 proposed, written by the developers. The processing lead
  is asked to review them, drawing on the notebook of errors and fixes the team
  already keeps. The console's Known errors page lists them with how often each
  has fired.
- The run stops itself. An error marked as a configuration problem (like
  `MAXPAR`) stops the run at once, because every remaining day would fail the
  same way. An error with no entry also stops it at once: there is no remedy on
  file, so a person has to look. So does a day whose RINEX headers are refused
  before Bernese starts, or a call that runs past its time limit. An error that
  belongs to one day's data is
  counted: 3 days in a row failing with the same error stop the run, and so do
  5 failed days in a row of any kind. A day that succeeds resets the count.

**Nothing is fixed automatically.** The list tells a person what to check; it
never changes a setting or re-runs a day by itself. The 29 August run, put
through the service, would have stopped after its first failed day, with the
`MAXPAR` remedy on screen.

**If an entry is wrong, or missing, say so.** The list is only as good as the
experience behind it, and most of that experience is yours.

---

## Your velocity script runs without MATLAB

`vel_line_v8_newvelduetooffset_v4.m` is the last step of the workflow and the
one that produces the scientific output: per-site East, North and Up
velocities, split at the offsets in the catalog. It is also the only part of
the workflow that needs MATLAB, which is licensed, and which gps3 does not
have.

It has been rewritten in Python (`pogf_geodetic_suite.timeseries.analysis`).
Checked against PHIVOLCS' own `Velocity_rover(regress)_10` for the Luzon
campaign set, **161 of 165 velocity components agree to better than
0.000005 mm/yr**, which is the rounding of the five decimal places the MATLAB
writes, **and the other four to 0.000023 mm/yr**, two or three units in that
last place. Three sites were left out of that check,
each for a reason: BR14 and LUZD (below), and KA08, whose last segment has a
single point, which the MATLAB reports with no error bars and the Python
refuses to fit.

The console's Time series page runs this code. The velocities PHIVOLCS
publishes are still produced the existing way, with the MATLAB.

Two things came out of the rewrite that are worth knowing.

**Outliers are detected but not removed.** The MATLAB runs an IQR test
(`rmoutliers`), writes the `outliers` file, and then fits the velocity to the
original data anyway. That is why the work instruction has you remove outliers
by hand and re-run. The console's numbers keep the MATLAB's behaviour: flagged
epochs are reported and stay in the fit, the same method the published
velocities use. They are fitted to gps3's own daily solutions, so they are not
the published numbers themselves. **Whether we publish with outliers left out
is a decision for the team, not for the code,** and it is still open.

**BR14 and LUZD get wrong velocities from the MATLAB** when their two 2022
entries in `offsets` are in the wrong order (the later date first), as they
were in the copy on the file share. The MATLAB builds its time segments in file
order, which then gives an impossible range, and the calculation silently
reuses the previous segment's data. It does not error; it just produces a
number that isn't right, so velocities already published for those two sites
from the old order are wrong. The copy in this repository was put in date order on
21 August 2026, and the Python sorts the catalog when it reads it, so it is not
affected. **If the copy you run the MATLAB with still lists 2022.8159 before
2022.5695 for BR14 or LUZD, swap them.** It is worth checking any other site
whose offsets were entered out of order.

Neither of these is a criticism of the script, which has done years of real
work. They are the kind of thing that only surfaces when a second
implementation is made to agree with the first, which is why porting it was
worth doing.

---

## What stays in your hands

Orchestration takes the mechanical steps. The judgement steps stay with people:

| Automated | Human |
|-----------|-------|
| Product download and staging (by the maintainer's scripts) | Deciding which product tier to use (ultra-rapid, rapid or final) |
| RINEX staging | Reviewing HELMCHK results for possible co-seismic displacement |
| BPE execution, every step in the PCF | Interpreting the ambiguity fixing rate (not shown in the console yet: the summaries aren't archived) |
| Listing the stations in each day's solution, and any dropped since the day before | Deciding whether a dropped station reflects a real data problem |
| Archiving each day's results in SAVEDISK | Velocity model review and publication |
| Checking each day's results are complete and marking the day done | Final QC sign-off before results enter the velocity product |
| Showing each run's state in the console | Offset event classification (EQ, VE, CE, UK) |
| **Outlier flagging** (statistical, automatic) | **Confirming or overriding** each flag |
| Looking a failed step up in the known-errors list | **Writing and confirming** the entries in that list |
| Stopping a run: at once on a configuration error, an error with no entry, a refused header check or a timeout; after 3 same failures in a row; or after 5 failed days in a row | **Deciding what to change** before the run is started again |

The orchestrator flags; it does not decide. Every exception it raises is a
question that needs your knowledge of the network to answer.

One step deserves a direct explanation: **manual outlier removal stays human**.
After the daily coordinates exist, each station's time series has to be looked
at so bad epochs can be identified. On Windows this is an interactive plot
(right-click to flag) followed by editing the PLOT files by hand. In the
console, it is the Time series page:

- The plot already highlights the epochs the statistic flagged, so you start
  from those instead of hunting.
- Clicking an epoch records your decision (outlier, not an outlier, or clear
  your earlier decision) with your name. A decision that goes against the
  automatic flag needs a reason, which is kept with the epoch. Nothing is
  removed from any file, and every decision stays in the record.
- Your decisions change only a second, side-by-side fit that the page marks as
  not published. Whether confirmed outliers are left out of the published fit
  is the open team decision above (`docs/SETTLED.md` section 6).

The detection itself is not new. The MATLAB has always run an IQR test and
written the `outliers` file; what was missing is that the flags never reached
the velocity fit, and that a person's decision about them was never recorded.
The console's own flags are 3 times the IQR within each segment, on the raw
values.

Can it be *fully* automated? The detection, yes: it already is. The decision
should not be, and the reason is concrete. An offset missing from the catalog
produces a cluster of points that look exactly like outliers but are a real
step in the ground. Removing them would erase the very signal the network
exists to measure. That distinction needs someone who knows the site.

---

## Before and after: a processing day

**With the Bernese menu on a workstation:**

> A staff member spends the day on file management, downloads and manual BPE
> setup. A real processing day takes about 2 hours of machine time on the T420,
> attended. Then SINEX extraction and a spreadsheet update. Outlier review means
> running a separate Windows script per station, right-clicking bad points, then
> editing PLOT files by hand. Errors from manual steps (a wrong `.STA` entry, a
> stale orbit file, a missed outlier) are caught late.

**With the processing service and the console:**

> An operator checks a range of days on the Plan page, queues a preflight, then
> Start. The run worker on gps3 runs it under the BPE lock, overnight if need
> be. The next morning the Calendar shows each day fixed, float or failed. A
> failed day opens on its Failure page with the failed step and, if the error is
> known, the remedy. After the cause is fixed (say a `.STA` entry), the operator
> uses Redo on that day: a daily solution is one network, so the whole day runs
> again, and the day's earlier results are moved aside first so old and new are
> never mixed. On the Time series page, flagged epochs are already highlighted;
> the staff member confirms or overrides them.

---

## Technical foundation (for the interested)

The processing service does not replace Bernese. It calls Bernese's own
non-interactive interface (`startBPE.pm`, the Perl module the Bernese
documentation describes for automated processing) through a driver script,
`sessions_pcs.pl`, kept in this repository. Bernese does all the geodetic
computation. The service handles everything around it. It checks the inputs
before a run starts, and takes the machine-wide BPE lock so only one run uses
Bernese at a time. It calls Bernese several days at once and stops a call that
runs past its time limit, with every job that call started. Afterwards it
checks that each day's results are complete in SAVEDISK and marks the day done.
On a failure it names the step and program,
looks the message up in the known-errors list, and decides whether the run
stops. Throughout, it writes the run record: one line per attempt, with who
started the run, the command, the code version, the PCF and the products.

The panel settings (the GPSEST ionosphere configuration, the MAUPRP cycle-slip
thresholds, the HELMR1 reference station list, the ADDNEQ2 outlier thresholds)
are the panels in `${U}/OPT` on gps3: Bernese 5.4's stock R2S panels, with MAXPAR
raised in two `ADDNEQ2.INP` files. The daily PCFs are derived from the stock
Bernese 5.4 `RNX2SNX.PCF`, changing only its variables (the LUZON one by
`scripts/derive_luzon_pcf.py`); the float fallback, `LZFLT_DLY`, also leaves out
the ambiguity-resolution steps. A PCF in which a step waits on one that will
never run is refused when a run is planned. These files live on gps3, not in the
commit history; the checksum in the run record is what shows that one changed.

---

## What we need from you

**First: your work is backed up.** On 12 August 2026 the scripts on the Scripts
share on the Windows file server were copied into version control: 142 files,
including every `vel_line` version, the RINEX conversion scripts, the RINEX
checkers and the per-region site lists. Most importantly, the **`offsets`
catalog**: 89 records across 70 sites, from 2003 to 2026, classifying every
event as EQ, VE, CE or UK.

That file is twenty-three years of accumulated judgement about which coordinate
jumps were earthquakes and which were antenna swaps. **It cannot be regenerated
from anything.** It was copied as it was; the only change since is the BR14 and
LUZD reordering above. It is also in a version-controlled repository that is
mirrored onto agency hardware.

**What would help:**

1. **A newer `offsets`**, if anyone keeps one. That is the file we least want
   to be tracking a stale copy of.
2. **Any `.STA`, `.CRD` or panel settings you have changed** from what the
   national campaign carries, especially for sites added or re-equipped
   recently. We have the campaign files as they stand on the server; what we
   cannot see is anything living only on a workstation.
3. **Corrections to this document.** If something here does not match what you
   actually do, that mismatch is the useful part. Tell the maintainer.
4. **The known-errors list.** If you know an error and its fix that is not in
   it, or an entry that is wrong, say so.

**What we specifically do *not* want copied:**

- `USER.CPU`, in `${U}/PAN/`. It records **how many CPU cores
  Bernese may use**, which is a property of the machine, not of the processing.
  Copying it between machines is how gps3 came to run the laptop's setting of 2
  on a 12-core server, against a step that already takes forty minutes on one
  core. On gps3 it is generated from the machine's own core count, by
  `scripts/provision_gpsuser.py`.
- Stock Bernese panels: we have the vendor's own files. We only want the
  ones PHIVOLCS has actually changed.

Panel settings you supply go into `config/bernese/gpsuser/` and are applied by a
single command, which matters because the MIS team does reconfigure the server.
That command corrects path separators and sizes MAXPAR in `ADDNEQ2.INP` from the
station count, and stops on anything it will not fix safely. `.STA` and `.CRD`
changes go into the reference files the campaigns read, in `${D}/REF54`.

---

## Summary

| | With the Bernese menu | With orchestration on gps3 | Status |
|---|---|---|---|
| Machine time per day | about 2 h attended (T420) | 5 min 33 s unattended for one LUZON day | measured |
| A month of processing | weeks of attended work | 53 min for LUZON January 2026, several days at once | in production since 4 November 2026 |
| Starting a run | the RUNBPE panels, at the machine | the console's Plan page, from any office PC | operators only; the maintainer sets who |
| Reproducibility | settings not recorded | driver scripts version-controlled; every run recorded with who, what, which code and a checksum of its settings | in use; PCFs and panels are on gps3, not in version control |
| Velocity calculation | MATLAB (licensed) | Python, agreeing with the MATLAB | runs in the console; published velocities still come from the MATLAB |
| Outlier review | right-click, then edit PLOT files | decisions recorded with your name; a side-by-side fit | in use; leaving outliers out of the published fit is still open |
| Your scripts and `offsets` | one share, some laptops | in version control, mirrored | done, 12 August 2026 |
| When a run fails | read the log files after the run | failed step named, known errors looked up, run stops itself | in use |
| Running many days | one session at a time | several days at once, each in its own campaign | in use |
| PHREF 2025 reprocessed | | all 360 planned days | differences from the old solutions not yet explained |

The goal is not to make the software do the science. The goal is to make the
software do the filing, so that you can do the science.

---

*Questions or concerns? Bring them. We want to build this with your input, not
around it.*
