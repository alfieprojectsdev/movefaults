# From Manual BPE Runs to Reproducible Science: A Proposal for GNSS Pipeline Orchestration

*Prepared for PHIVOLCS GNSS Data Processing Staff*

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
- Wait 35 minutes. Check `RNX2SNX.OUT`. Everything looks OK.
  Copy the SINEX files to SAVEDISK. Update the tracking spreadsheet.

Multiply this by every session, every campaign, every year. Then ask: **how much of this work is science, and how much is file management?**

---

## What Orchestration Actually Means

Orchestration does not replace Bernese. It does not replace you.

It is a **conductor** — a program that knows the correct sequence of steps, performs the file management automatically, calls Bernese when everything is ready, and checks the results when it finishes. You define the rules once. The conductor follows them every time.

For our workflow, one orchestrated processing run looks like this:

```
You specify:  Campaign = PIVSMIND, Year = 2023, Session = 0100

Orchestrator:
  1. Downloads IGS precise orbits + clocks from CDDIS (with automatic fallback to IGN/BKG)
  2. Stages the HOI model file and Earth rotation parameters
  3. Validates RINEX files against the station info (.STA) — flags mismatches BEFORE Bernese
  4. Decompresses Hatanaka files (CRX2RNX) and copies to RAW/
  5. Renders the RUNBPE.INP and OPT_DIR panel files for this specific campaign
  6. Calls Bernese non-interactively: runs all 47 BPE steps
  7. Checks the output: station count after RXOBV3, ambiguity fixing rate, HELMCHK residuals
  8. Extracts SINEX coordinates, converts to ENU, stores in the database
  9. Sends a summary report: what ran, what succeeded, what needs attention

You receive:  A report. Processed results in the database. Any exceptions flagged for your review.
```

The 47 BPE steps — RNXGRA, RXOBV3, MAUPRP, GNSQIF, HELMCHK, all of them — run exactly as they do today, with exactly the same Bernese software, the same PCF, the same INP file settings. **The science does not change.** What changes is who carries the files.

---

## Why This Matters: Three Concrete Pain Points

### 1. The Reproducibility Problem

If you processed session 2023/010 in February, and re-process it in December with a newer IGS final orbit, **will you get the same answer?** Currently, probably not — and you may not be able to explain why, because the exact settings used in February are not recorded anywhere. They lived in a panel file that has since been overwritten.

With orchestration, every processing run produces a complete record:
- Which IGS orbit product was used (rapid, final, or ultra-rapid — and which version)
- Which `.STA` file version was active at run time
- Which OPT_DIR INP settings were applied
- Which stations survived RXOBV3 and which were dropped
- What the HELMCHK residuals were

This is the difference between a result you can publish and a result you can only use internally.

### 2. The Knowledge Concentration Problem

Right now, the full processing procedure exists primarily in the heads of the people who do it regularly. The steps for handling a problematic station, the correct mirror to use when CDDIS is down, the `.STA` column format — none of this is written down in a form that survives staff turnover.

An orchestrator is a **runnable specification** of the processing procedure. It is the procedure, written in code. When a new staff member joins, they do not need to be taught the steps — they read (and run) the orchestrator. When a processing expert goes on leave, processing does not stop.

### 3. The Scale Problem

PHIVOLCS currently operates 35+ CORS stations producing continuous data, plus periodic campaign GPS deployments. Processing each station's daily data manually is feasible for a small number of stations. It is not feasible at 35, and will not be feasible at 50 or 100.

An orchestrated pipeline processes all stations in parallel, overnight, every night, without anyone sitting at a terminal. The processing staff review the exception report in the morning — they spend their time on the results that need judgment, not on the steps that don't.

---

## What Stays in Your Hands

Orchestration automates the mechanical steps. The judgment steps remain human:

| Automated | Human |
|-----------|-------|
| IGS product download and staging | Deciding which IGS product tier to use (ultra-rapid vs. rapid vs. final) |
| RINEX decompression and file staging | Reviewing HELMCHK flags for possible co-seismic displacement events |
| BPE execution (all 47 steps) | Interpreting anomalies in the ambiguity fixing rate |
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

> Staff member spends 2–3 hours per campaign session on file management, downloads, and manual BPE setup. BPE runs ~35 minutes attended. Post-processing (SINEX extraction, spreadsheet update) takes another hour. Outlier review requires running a separate Windows script per station, right-clicking bad points, then manually editing PLOT files. One person's full day is consumed by a single session. Errors from manual steps (wrong `.STA` entry, stale orbit file, missed outlier epoch) are caught late.

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

To build the templates correctly, we need copies of the INP files from a working production run:

1. The **`R2S_GEN` subdirectory** from `${U}/OPT/` — the ~20 INP files that configure each BPE step
2. The **`USER.CPU`** file from `${U}/CPU/` — the CPU slot configuration
3. The **`RUNBPE.INP`** from `${U}/PAN/` — the pre-configured BPE panel file

These files become the ground-truth reference for the templates. Your production settings are preserved exactly — the orchestrator generates files that are functionally identical to what you would configure interactively.

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
