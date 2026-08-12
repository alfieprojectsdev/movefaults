# GNSS Pipeline Orchestration: What We're Building for Our Processing Workflow

**Drafted:** 2026-02-27  **Revised:** 2026-08-03, **2026-08-12**

> **What has changed since this was written.** In February this described a plan.
> Since then: the NAMRIA training week (June) ran the whole PAGENET pipeline
> unattended on live data; the Dell R740 has Bernese 5.4 installed and
> verified; and in August a **full month of the LUZON network was reprocessed
> end to end, unattended, 30 days with zero failures**.
>
> Sections marked **[now real]** describe things that exist. Where something was
> tried and *didn't* work, that is stated too — "A Test That Failed" is exactly
> that, and it is here because a plan you can trust has to include the parts that
> pushed back.
>
> **Your work is now backed up.** The scripts and the `offsets` catalog that
> lived only on the file server and on individual machines are in version
> control as of 2026-08-12. More on that in "What We Need From You".

---

## The Problem We All Know

Every GNSS processing cycle involves the same invisible overhead:

- Open the Bernese menu. Navigate to RUNBPE. Check that the campaign path is set correctly.
  Hope that last session's settings weren't accidentally saved over.
- Download IGS precise orbits and clocks from CDDIS. Retry when the server is down.
  Try the IGN mirror instead. Remember which mirror worked last month.
- Decompress the RINEX files. Run `CRX2RNX`. Copy them to the right `RAW/` subdirectory.
- Check the `.STA` file. Did we update the antenna height entry for that October field campaign?
  Edit it manually. Try to remember the exact column widths.
- Run BPE. Watch the screen. Something failed at step 221 (RXOBV3) — station header mismatch.
  Find the bad station. Fix the `.STA` entry. Re-run from scratch.
- Wait out the run. Check `RNX2SNX.OUT`. Everything looks OK.
  Copy the SINEX files to SAVEDISK. Update the tracking spreadsheet.

Multiply this by every session, every campaign, every year. Then ask: **how much of this work is science, and how much is file management?**

---

## What Orchestration Actually Means

Orchestration does not replace Bernese. It does not replace you.

It is a **conductor** — a program that knows the correct sequence of steps, performs the file management automatically, calls Bernese when everything is ready, and checks the results when it finishes. You define the rules once. The conductor follows them every time.

For our workflow, one orchestrated processing run looks like this:

```
You specify:  Campaign = PAGENET, Year = 2026, Session = 0860

Orchestrator:
  1. Downloads IGS precise orbits + clocks from CDDIS (with automatic fallback to IGN/BKG)
  2. Stages the HOI model file and Earth rotation parameters
  3. Validates RINEX files against the station info (.STA) — flags mismatches BEFORE Bernese
  4. Decompresses Hatanaka files (CRX2RNX) and copies to RAW/
  5. Renders the RUNBPE.INP and OPT_DIR panel files for this specific campaign
  6. Calls Bernese non-interactively: runs every BPE step in the PCF
  7. Checks the output: station count after RXOBV3, ambiguity fixing rate, HELMCHK residuals
  8. Extracts SINEX coordinates, converts to ENU, stores in the database
  9. Sends a summary report: what ran, what succeeded, what needs attention

You receive:  A report. Processed results in the database. Any exceptions flagged for your review.
```

Every BPE step — RNXGRA, RXOBV3, MAUPRP, GNSQIF, HELMCHK, all of them — runs exactly as it does today, with exactly the same Bernese software, the same PCF, the same INP file settings. **The science does not change.** What changes is who carries the files.

---

## Why This Matters: Four Concrete Pain Points

### 1. The Reproducibility Problem  **[partly real]**

If you processed session 2023/010 in February, and re-process it in December with a newer IGS final orbit, **will you get the same answer?** Currently, probably not — and you may not be able to explain why, because the exact settings used in February are not recorded anywhere. They lived in a panel file that has since been overwritten.

With orchestration, every processing run produces a complete record:
- Which IGS orbit product was used (rapid, final, or ultra-rapid — and which version)
- Which `.STA` file version was active at run time
- Which OPT_DIR INP settings were applied
- Which stations survived RXOBV3 and which were dropped
- What the HELMCHK residuals were

This is the difference between a result you can publish and a result you can only
use internally.

**Where this stands:** the settings side is now version-controlled — panels, PCFs
and drivers live in the repository and are applied to the server by one command,
so "which settings were active" is answerable from the commit history rather than
from memory. The per-run record of *outcomes* (which stations survived, what the
residuals were) is still to come.

**A real example of why this matters, found in our own files.** While rewriting
the velocity script (see "Your Velocity Script Now Runs Without MATLAB"), the new version was checked against the existing
`Velocity_rover(regress)_10` output for the Luzon campaign set. Four sites
disagreed. The new code was not wrong: **the saved velocity file was written on
9 July, and the `offsets` catalog it depends on was edited on 29 July.** The
output and its input had drifted twenty days apart, and nothing in either file
recorded that.

Once the catalog was reconstructed as it stood on 9 July, every site agreed
exactly. No harm was done here — but it is precisely the situation where, months
later, nobody can say whether a number is reproducible. **A velocity file is
only meaningful alongside the exact catalog that produced it**, and recording
that pairing automatically is what the per-run provenance record is for.

### 2. The Knowledge Concentration Problem

The processing procedure is documented — the work instruction covers it thoroughly. But a document that describes what to do is different from a system that does it. Every manual step is an opportunity for the document and reality to quietly diverge: a mirror URL changes, a `.STA` column format gets adjusted, a new instrument introduces a filename pattern the document hasn't caught up to yet.

An orchestrator is a **runnable specification** of the processing procedure. It is the procedure, written in code — and the code either works or it fails visibly, which is a much shorter feedback loop than a document drifting out of sync with practice. The work instruction does not disappear; it becomes the authoritative reference for what to do **when the orchestration flags an exception** — exactly the cases where human judgment is needed. For new staff, the orchestrator handles the routine; the work instruction teaches the reasoning behind it.

### 3. The Scale Problem

PHIVOLCS operates approximately 270 active stations nationwide as of December 2024 — continuous CORS sites and campaign deployments combined — with over 300 GPS sites contributing data since 1995. Processing each station's daily data manually was feasible when the network was small. It is not feasible at 270 active stations across the archipelago, and the network is not getting smaller.

An orchestrated pipeline processes all stations in parallel, overnight, every night, without anyone sitting at a terminal. The processing staff review the exception report in the morning — they spend their time on the results that need judgment, not on the steps that don't.

**Measured, not estimated (2026-08-06).** A 30-station LUZON day takes **5 minutes
33 seconds** on the R740 and uses about **4 of its 24 cores**. A full month —
30 days — ran unattended in **2 hours 47 minutes, 30 of 30 days successful**.

**The comparison that matters, and the honesty it needs.** Cass reprocessed the
full 2025 PH network a few weeks ago on one of the Windows R740 servers, and it
took **several weeks**. Our measured LUZON rate — 5m33s a day — would put a year
at roughly a day and a half of machine time.

That gap is large enough to be worth understanding rather than celebrating,
because the two runs are **not the same job**:

- Cass's run processed the national network (**~52 stations a day**); ours
  processed LUZON (**30**).
- Hers used the full production PCF including `FTP_DWLD`, which fetches IGS
  products over the network for every session; ours had products pre-staged
  locally.
- Hers produced weekly and monthly combinations (`ADD_WK`, `ADD_MON`); ours did
  not.
- Hers ran attended, in working hours, on Windows; ours ran overnight on Linux.

So the right conclusion today is **"this looks very promising and we should
measure it properly"**, not "we are twenty times faster". A like-for-like run —
same station set, same PCF, same products — is the honest way to find the real
number, and it is worth doing precisely because if even part of that gap is
real, it changes what is possible for reprocessing the full archive.

If the difference turns out to be mostly `FTP_DWLD` waiting on remote servers,
that is worth knowing too: it would mean the win is in **staging data once**
rather than in the processing at all.

Scaling that to the national network: `PHIVOLCS.CRD` catalogues **439 stations**,
but a daily solution actually estimates **52** (50 PHIVOLCS + 2 IGS). That is
comfortably inside every limit that matters, so the national daily processing
does **not** need to be split into subnetworks as things stand today. If we ever
process substantially more of those 439 sites, that changes — and PHIVOLCS'
existing regional grouping (Luzon; Ragay-Bondoc-Marinduque-Masbate; **CBPN** —
Cebu, Bohol, Panay, Negros; Samar-Leyte; Cotabato-Sindangan; Eastern Mindanao)
is the partition we would use, because it already follows the island groups
rather than anything invented for the software.

### 4. The Workstation Problem  **[now real]**

A BPE run occupies whatever machine it runs on, and it is not a coffee break. Measured: the 54-station EXAMPLE campaign takes **11 minutes**, but a real **72-station PAGENET day took about 2 hours** on the T420 — roughly 40 minutes of it inside a single step (PID 502, GPSCLU_P) solving the final system on one core. Multiply by seven days of a processing week.

The orchestrated pipeline runs on the dedicated Dell server (R740). You submit a
processing job from your desk, and your workstation is immediately free. The server
handles the computation; you receive the results. Your desktop is no longer a
processing node.

**This part now exists.** Bernese 5.4 was installed on the R740 on 2026-07-29 and
verified against the reference solution to **0.0000 mm** — the same numbers as the
laptop, on twenty-four cores instead of two, with the campaign data on a dedicated
4 TB volume. Jobs can also be supervised remotely: a run started at the office was
driven from a home network, with no terminal left open and nothing exposed to the
internet.

**And it has now done a real month of work.** LUZON, 2025 DOY 121–151, ran
overnight without supervision: 30 days, zero failures. The resulting coordinates
have a day-to-day repeatability of **2.8 mm north, 3.0 mm east, 10.9 mm up** —
ordinary for daily solutions, which is the point. Nobody sat with it.

---

## A Test That Failed, and What We Learned  **[honest]**

The plan was to process a year by running twelve months at once. Bernese turns
out to support exactly that natively — a documented "Run sessions in parallel"
option we simply had never switched on.

Switching it on, five days of LUZON genuinely ran side by side. Then **four of
the five failed**, all at the same step, all with the same message: *"No input
files"*.

The cause is in the Bernese manual, stated plainly: running many sessions inside
**one campaign directory** requires that every script and temporary filename be
independent of the session. Ours are not — the five sessions were staging their
RINEX into the same working folder and quietly consuming each other's files.

The fix is also in the manual: **one campaign directory per session**, which
Bernese will create automatically. That is the next thing to test.

This is written up here for two reasons. Parallel processing across a year is
**not yet proven**, so nobody should plan around it. And a failed test that gets
recorded is worth more than a successful one that gets assumed — the whole point
of this project is that results come with evidence attached.

*(Nothing was lost. The 30-day results were copied aside before the test and
verified identical afterward — all 30 solutions, byte for byte.)*

---

## Your Velocity Script Now Runs Without MATLAB  **[now real]**

`vel_line_v8_newvelduetooffset_v4.m` is the last step of the workflow and the
one that produces the actual scientific output: per-site E/N/U velocities, split
at the offsets in the catalog. It is also the only part of the pipeline that
needs MATLAB — which is licensed, and which the server does not have.

It has been rewritten in Python. **It reproduces the MATLAB output exactly:
171 of 171 velocity components, to the last decimal place.**

The port deliberately keeps the existing behaviour as the default, so results
can be compared before anything changes. Two things came out of doing it that
are worth knowing:

**Outliers are detected but not actually removed.** The MATLAB calls
`rmoutliers` and stores the result — and then fits the velocity using the
original data anyway. That is why the work instruction has you remove outliers
by hand and re-run. The Python version reproduces this exactly by default, and
offers a one-pass option that excludes them properly. **Which behaviour we
publish with is a decision for the team, not for the code.**

**Two sites have velocities that are wrong today: BR14 and LUZD.** Their entries
in the `offsets` catalog are recorded out of chronological order (the later date
appears first). The MATLAB builds its time segments in file order, which in this
case produces an impossible range, and the calculation then silently reuses the
previous segment's data. It does not error — it just produces a number that
isn't right. Reordering those two entries fixes it. Worth checking any other
site whose offsets were entered out of order.

Neither of these is a criticism of the script, which has done years of real work.
They are the kind of thing that only surfaces when a second implementation is
made to agree with the first — which is exactly why porting it was worth doing.

---

## What Stays in Your Hands

Orchestration automates the mechanical steps. The judgment steps remain human:

| Automated | Human |
|-----------|-------|
| IGS product download and staging | Deciding which IGS product tier to use (ultra-rapid vs. rapid vs. final) |
| RINEX decompression and file staging | Reviewing HELMCHK flags for possible co-seismic displacement events |
| BPE execution (every step in the PCF) | Interpreting anomalies in the ambiguity fixing rate |
| RXOBV3 station drop detection | Deciding whether a dropped station reflects a real data problem |
| SINEX coordinate extraction | Velocity model review and publication |
| Daily ENU coordinate storage | Offset event classification (EQ, equipment change, unknown) |
| Run status report generation | Final QC sign-off before results enter the velocity product |
| **Outlier detection** (statistical, already automatic) | **Confirming or overriding** which epochs to actually remove |

The orchestrator flags — it does not decide. Every exception it surfaces is a question that requires your domain knowledge to answer.

One step in particular deserves a direct explanation: **manual outlier removal stays human**. After BPE completes and daily coordinates are extracted, the velocity calculation requires a visual inspection of each station's time series to identify and remove bad epochs. Today this is done via a Windows-only interactive plot (right-click to flag). In the new pipeline, the same step happens through a browser-based tool — you still look at the time series, you still decide which points to remove, and the result is written to the same file the MATLAB velocity script reads. The judgment is identical; the tool is better and works on any machine.

What the browser tool adds that the current script does not: automatic
pre-flagging of statistical outliers so that obvious bad epochs are already
highlighted when you open the plot. You confirm or override — you do not hunt
from scratch.

**A correction to what this section used to say.** It described outlier
detection as something orchestration would add. It is already there: the MATLAB
script has always run an IQR test and written the `outliers` file. What was
missing is that the detected outliers were never fed back into the velocity fit
(see that section). So the honest description is not "we will automate this" but **"this was
already automated; we are closing the loop and making the decision visible."**

Can it be *fully* automated? The detection, yes — it already is. The decision
should not be, and the reason is concrete: an unrecorded offset produces a
cluster of points that look exactly like outliers but are actually a real step
in the ground. Removing them would erase the very signal the network exists to
measure. That distinction needs someone who knows the site.

---

## Before and After: A Processing Day

**Before orchestration:**

> Staff member spends 2–3 hours per campaign session on file management, downloads, and manual BPE setup. A real PAGENET day runs ~2 hours attended. Post-processing (SINEX extraction, spreadsheet update) takes another hour. Outlier review requires running a separate Windows script per station, right-clicking bad points, then manually editing PLOT files. One person's full day is consumed by a single session. Errors from manual steps (wrong `.STA` entry, stale orbit file, missed outlier epoch) are caught late.

**After orchestration:**

> Staff member submits a processing job (campaign, year, session). Orchestrator handles all pre-processing and runs BPE overnight. The next morning, a report shows: 12 stations processed, 11 OK, 1 flagged (RXOBV3 header mismatch at XBOG — likely antenna info update needed). Staff member investigates the flag, corrects the `.STA` entry, re-queues that station. Then opens the browser-based outlier reviewer: statistical outliers are already pre-highlighted across all 12 stations. Staff member reviews, confirms or adjusts, clicks Export. MATLAB velocity script runs on the cleaned data. Total active time: 30–40 minutes.

---

## Technical Foundation (for the interested)

The orchestration layer we are building is not a replacement for Bernese — it wraps Bernese's own non-interactive API (`startBPE.pm`, the Perl module that the Bernese TUTORIAL documentation describes for automated processing). Bernese itself handles all the geodetic computation. The orchestrator handles everything outside Bernese:

- **Pre-flight**: validates inputs before committing to a BPE run
- **Data staging**: downloads and organises IGS products, RINEX files, reference data
- **INP provisioning**: renders the OPT_DIR panel files with the correct per-run parameters
- **Execution**: calls Bernese non-interactively; monitors for completion or crash
- **Harvest**: parses the BPE log, extracts SINEX, converts to ENU, writes to database
- **Reporting**: surfaces quality metrics (ambiguity fixing rate, HELMCHK residuals, daily repeatability)

The INP file settings — the GPSEST ionosphere configuration, the MAUPRP cycle slip thresholds, the HELMR1 reference station list, the ADDNEQ2 outlier thresholds — are all encoded from your existing production configuration. They do not change unless you deliberately change them, and any change is version-controlled and auditable.

---

## What We Need From You

*Rewritten 2026-08-03, and again 2026-08-12 — this time because most of it is
no longer needed.*

**First: your work is backed up.** On 2026-08-12 the scripts on
`\\192.168.48.99\GPS Data\Scripts` were copied into version control — 142
files, including every `vel_line` version, the RINEX conversion scripts, the
RINEX checkers, and the per-region site lists. Most importantly, the **`offsets`
catalog**: 88 records across 70 sites, from 2003 to 2026, classifying every
event as EQ, VE, CE or UK.

That file is twenty-three years of accumulated judgement about which coordinate
jumps were earthquakes and which were antenna swaps. **It cannot be
regenerated from anything.** It existed in exactly two places — that share, and
individual machines. It now also exists in a version-controlled repository that
is mirrored onto agency hardware. Nothing was changed; it was copied as-is.

If anyone maintains a newer copy of `offsets` than the one on the share, please
say so — that is the one we should be tracking.

**Correction (2026-08-12): the file this section spent months asking for is
already here.**

`PAGENET_DLY.PCF` — the Process Control File that drove the training week — has
been in version control since **2026-08-05**, and is byte-identical to the
working copy on the T420. Earlier versions of this document, including one
circulated the same day as this correction, said it existed only on the T420.
That was out of date and is the kind of thing this project is supposed to catch,
so it is corrected here rather than quietly edited away.

It is now installed into the Bernese tree on the R740 as well
(`md5 b4d5c52ee6f3289fc5de4a1dcb6da5be`), and it passes our own checks: **52 of
52 process rows are in Bernese 5.4 format, with zero dangling wait conditions.**
Structurally it is sound.

**So the real gap turns out to be somewhere nobody was looking.** The PCF names
nine panel directories, and **eight of them are missing** from both the server
and the repository:

| Needed by | Panel directory | Have it? |
|---|---|---|
| 24 steps | `PGN_GEN` | **no** |
| 6 steps | `PGN_FIN` | **no** |
| 3 steps each | `PGN_EDT`, `PGN_AMB` | **no** |
| 2 steps each | `PGN_QIF`, `PGN_L53`, `PGN_L12`, `PGN_GE2` | **no** |
| 8 steps | `NO_OPT` | yes (ships with Bernese) |
| weekly combination only | `PGN_WK` | yes (already in the repository) |

The one directory we *do* have from PHIVOLCS — `PGN_WK` — is for the **weekly**
combination, not the daily run. Every panel directory the daily PAGENET
processing actually needs is absent.

This is worth saying plainly because the ask in this document was wrong in both
directions: it asked for a file we already had, and did not ask for the eight
directories we actually need.

**Still genuinely useful to have:**

1. **The eight `${U}/OPT/PGN_*` panel directories** listed above — `PGN_GEN`,
   `PGN_FIN`, `PGN_EDT`, `PGN_AMB`, `PGN_QIF`, `PGN_L53`, `PGN_L12`, `PGN_GE2`.
   These hold the actual processing settings for each PAGENET step. Without them
   the PCF is a list of instructions with nothing to instruct.

   Expect our tooling to **reject some of them on the first attempt**: `PGN_WK`,
   the one we already have, contains Windows-style `\` path separators (literal
   characters on Linux), a reference to a step that was removed, and session
   dates hardcoded from the instructor's demo week. Being rejected is the tool
   doing its job; the offending lines get remapped once and then everybody uses
   the corrected version.

2. **A newer `offsets`**, if anyone keeps one — as noted above.

**Why the PCF must never be rebuilt from scratch**, since the reasoning still
matters even though the file is now in hand: it is the version *proven to run
end to end*. Deriving one instead by trimming the stock `RNX2SNX.PCF` leaves a
step waiting on a step that no longer exists, and BPE's failure mode there is
the worst kind — **it waits indefinitely instead of failing.** No error, no exit
code, no timeout: a job that looks busy forever. Our provisioning tooling now
refuses that condition, so it surfaces before a run rather than during one.

*(For LUZON none of this is blocking — a working 5.4 configuration was derived
and has processed a full month. PAGENET still needs its own 5.4 configuration;
this PCF is the specification of the step sequence, not a drop-in for 5.4.)*

**What we specifically do *not* want copied:**

- **`USER.CPU`.** The original asked for this from `${U}/CPU/` — a directory that
  does not exist (the file lives in `${U}/PAN/`). More importantly, it records
  **how many CPU cores to use**, which is a property of the machine, not of the
  processing. Copying it between machines is how the R740 came to be running the
  laptop's setting of 2 — using two of its twenty-four cores on a step that
  already takes forty minutes. It is now generated automatically from whatever hardware
  the job runs on.

- **Stock Bernese panels.** `${U}/OPT` and `${U}/PCF` on the R740 are currently
  byte-identical to what Bernese 5.4 ships. We only want the files PHIVOLCS has
  actually changed; the vendor's own files we already have.

Everything supplied is version-controlled at `config/bernese/gpsuser/` and applied
by a single command, so the environment can be rebuilt from scratch if the server
is ever reconfigured — which matters, because the MIS team does reconfigure it.
Your production settings are preserved exactly; nothing is silently reinterpreted.

---

## Summary

| | Today | With Orchestration | Status |
|---|---|---|---|
| Time per session (staff) | 3–4 hours | 20 minutes (exception review only) | in progress |
| Machine time per day | ~2 h attended (T420) | **5 min 33 s unattended (R740)** | **measured** |
| A month of processing | weeks of attended work | **2 h 47 min, 30/30 days** | **done, 2026-08-06** |
| Reproducibility | Settings not recorded | Every run logged and version-controlled | settings done; per-run record to come |
| Velocity calculation | MATLAB (licensed) | **Python, verified identical** | **done, 2026-08-12** |
| Your scripts + `offsets` | One share, some laptops | **In version control, mirrored** | **done, 2026-08-12** |
| Error detection | After BPE runs | Before BPE runs (pre-flight validation) | in progress |
| Scale | ~1 session per person-day | Parallel sessions overnight | **not yet — see "A Test That Failed"** |
| Knowledge transfer | Person-to-person | Readable, runnable code | in progress |

The goal is not to make the software do the science. The goal is to make the
software do the filing, so that you can do the science.

**What is genuinely done, as of 2026-08-12:** Bernese 5.4 runs unattended on the
server and has processed a real month; the velocity step no longer needs MATLAB
and gives identical numbers; and the scripts and event catalog are backed up
where they cannot be lost with a hard drive.

**What is not:** parallel processing across a year ("A Test That Failed" above — tested, failed,
understood, fixable); the per-run provenance record; and the browser-based
outlier reviewer.

---

*Questions or concerns? Bring them — we want to build this with your input, not
around it.*

*Two specific asks, if you have a moment: (1) if you keep a newer `offsets` than
the copy on the share, tell us — that is the one we should be tracking; (2)
BR14 and LUZD have out-of-order entries in `offsets` that are affecting their
velocities today, and someone who knows those sites should decide the
correct order rather than us guessing.*
