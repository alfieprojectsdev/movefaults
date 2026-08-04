# GNSS Pipeline Orchestration: What We're Building for Our Processing Workflow

**Drafted:** 2026-02-27  **Revised:** 2026-08-03

> **What has changed since this was written.** In February this described a plan.
> Since then the NAMRIA training week (June) ran the whole PAGENET pipeline
> unattended on live data, and the Dell R740 (§4 below) now has Bernese 5.4
> installed and verified. Sections marked **[now real]** describe things that
> exist; the rest is still ahead. Timings have been replaced with measured ones.

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

## Why This Matters: Three Concrete Pain Points

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

### 2. The Knowledge Concentration Problem

The processing procedure is documented — the work instruction covers it thoroughly. But a document that describes what to do is different from a system that does it. Every manual step is an opportunity for the document and reality to quietly diverge: a mirror URL changes, a `.STA` column format gets adjusted, a new instrument introduces a filename pattern the document hasn't caught up to yet.

An orchestrator is a **runnable specification** of the processing procedure. It is the procedure, written in code — and the code either works or it fails visibly, which is a much shorter feedback loop than a document drifting out of sync with practice. The work instruction does not disappear; it becomes the authoritative reference for what to do **when the orchestration flags an exception** — exactly the cases where human judgment is needed. For new staff, the orchestrator handles the routine; the work instruction teaches the reasoning behind it.

### 3. The Scale Problem

PHIVOLCS operates approximately 270 active stations nationwide as of December 2024 — continuous CORS sites and campaign deployments combined — with over 300 GPS sites contributing data since 1995. Processing each station's daily data manually was feasible when the network was small. It is not feasible at 270 active stations across the archipelago, and the network is not getting smaller.

An orchestrated pipeline processes all stations in parallel, overnight, every night, without anyone sitting at a terminal. The processing staff review the exception report in the morning — they spend their time on the results that need judgment, not on the steps that don't.

### 4. The Workstation Problem  **[now real]**

A BPE run occupies whatever machine it runs on, and it is not a coffee break. Measured: the 54-station EXAMPLE campaign takes **11 minutes**, but a real **72-station PAGENET day took about 2 hours** on the T420 — roughly 40 minutes of it inside a single step (PID 502, GPSCLU_P) solving the final system on one core. Multiply by seven days of a processing week.

The orchestrated pipeline runs on the dedicated Dell server (R740). You submit a
processing job from your desk, and your workstation is immediately free. The server
handles the computation; you receive the results. Your desktop is no longer a
processing node.

**This part now exists.** Bernese 5.4 was installed on the R740 on 2026-07-29 and
verified against the reference solution to **0.0000 mm** — the same numbers as the
laptop, on twelve cores instead of two, with the campaign data on a dedicated 4 TB
volume. Jobs can also be supervised remotely: a run started at the office was
driven from a home network, with no terminal left open and nothing exposed to the
internet.

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
| **Outlier flagging** (browser-based point selection — same judgment, better tool) | Deciding which epochs to remove from the time series before velocity calculation |

The orchestrator flags — it does not decide. Every exception it surfaces is a question that requires your domain knowledge to answer.

One step in particular deserves a direct explanation: **manual outlier removal stays human**. After BPE completes and daily coordinates are extracted, the velocity calculation requires a visual inspection of each station's time series to identify and remove bad epochs. Today this is done via a Windows-only interactive plot (right-click to flag). In the new pipeline, the same step happens through a browser-based tool — you still look at the time series, you still decide which points to remove, and the result is written to the same file the MATLAB velocity script reads. The judgment is identical; the tool is better and works on any machine.

What the browser tool adds that the current script does not: automatic pre-flagging of statistical outliers (IQR method) so that obvious bad epochs are already highlighted when you open the plot. You confirm or override — you do not hunt from scratch.

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

*Rewritten 2026-08-03. The original version of this section asked for three files,
one of them at a path that does not exist and one that should not be copied
between machines at all. What is actually needed is now known precisely.*

**The one thing still blocking a production run on the R740:**

1. **`PAGENET_DLY.PCF`** — the daily Process Control File that drove the training
   week. It exists **only on the T420**. It is the sequence of BPE steps for a
   PAGENET day, and it must be copied rather than rebuilt: reconstructing it by
   trimming the stock `RNX2SNX.PCF` leaves a step waiting on another step that no
   longer exists, and the BPE then waits forever rather than failing. A rebuilt
   file would also not be the one that has actually been proven to work.

2. **`${U}/OPT/PGN_WK/`** — the weekly-combination panel directory, if it exists
   on your machine. Expect our tooling to **reject it on the first attempt**: it
   is known to contain Windows-style `\` path separators (literal characters on
   Linux), a reference to a step that was removed, and session dates hardcoded
   from the instructor's demo week. Being rejected is the tool doing its job.
   The offending lines get remapped once, and then the corrected version is the
   one everybody uses.

**What we specifically do *not* want copied:**

- **`USER.CPU`.** The original asked for this from `${U}/CPU/` — a directory that
  does not exist (the file lives in `${U}/PAN/`). More importantly, it records
  **how many CPU cores to use**, which is a property of the machine, not of the
  processing. Copying it between machines is how the R740 came to be running the
  laptop's setting of 2 — using two of its twelve cores on a step that already
  takes forty minutes. It is now generated automatically from whatever hardware
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

| | Today | With Orchestration |
|---|---|---|
| Time per session (staff) | 3–4 hours | 20 minutes (exception review only) |
| Reproducibility | Settings not recorded | Every run fully logged and version-controlled |
| Error detection | After BPE runs | Before BPE runs (pre-flight validation) |
| Scale | ~1 session per person-day | Unlimited parallel sessions overnight |
| Knowledge transfer | Person-to-person | Readable, runnable code |
| Recovery from failure | Manual restart from scratch | Automatic retry of failed step; audit trail |

The goal is not to make the software do the science. The goal is to make the software do the filing, so that you can do the science.

---

*Questions or concerns? Bring them — we want to build this with your input, not around it.*
