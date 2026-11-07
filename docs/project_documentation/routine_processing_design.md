# Routine processing and velocities: design

**Status: proposal, 2026-11-07. Nothing here is built.** Written while the PHPAR
2025 parity run was in progress. It answers two requests from the maintainer: plan
the step from orchestration toward automation (new days processed without someone
choosing them), and plan coordinates to velocities inside the same system. Read
with `automation_stages.md`, whose gaps this treats as dependencies, and
`run_worker_design.md`, which this builds on.

## The answer in short

1. **A schedule may prepare and propose, but not decide.** `docs/SETTLED.md` §3
   records "no cron for the scientific pipeline", because "its failure mode is
   silent wrong numbers; scheduling removes the person who would notice." This
   design keeps that rule. A nightly job brings in data, checks that each new day
   can be run, and proposes a run. A person still presses Start, as today.
2. **Move the person to the point where they can see the result.** At Start,
   an operator checks nothing that a script couldn't check better. The judgement
   is in reading the result. So the design adds an **acceptance** step after each
   run, and the time series and velocities use only accepted days.
3. **Unattended starts come last, as a decision to reopen §3,** and only once
   acceptance exists and has been used for a while. Then the schedule only moves
   *when* a run starts. The person who notices problems is still there, at
   acceptance. That's the case for reopening, and the conditions are in
   section 6.
4. **Velocities are already computed in the console, but not published from it.**
   Publishing from it waits on two open team decisions and one parallel
   comparison with the MATLAB, not on more velocity code (section 5).

## A correction: the MATLAB

`automation_stages.md` says the MATLAB "can now be replaced, but it hasn't been".
Both halves are still true, and an answer given on 2026-11-07 got the second half
wrong by saying velocities were "still the 5.2 team's MATLAB workflow, outside the
console".

- **Replaced, in the code.** `pogf_geodetic_suite.timeseries.analysis` reproduces
  `vel_line_v8_newvelduetooffset_v4.m`: 161 of 165 velocity components agree to
  better than 5e-6 mm/yr (`SETTLED.md` §2). The console's Time series page calls
  it in-process (`bsw_console/timeseries.py`) and shows a velocity and its
  uncertainty for every station of a campaign. Outlier review is built too
  (`bsw_console/outliers.py`, commits `6405d2a`, `c076a61`). Its decisions change
  only a side-by-side fit marked as not published.
- **Not replaced, in production.** The velocities PHIVOLCS publishes still come
  from the MATLAB, run by the 5.2 team on 5.2 solutions. Nothing published comes
  from gps3.

So for stage 3 the dependency on MATLAB is gone, but PHIVOLCS still uses it for
what it publishes. The switch is blocked by decisions, listed in section 5.

`outlier_review_design.md` still said "Nothing here is built", and
`automation_stages.md` didn't mention the console's outlier review at all. Both
are corrected in the same change as this document.

## 1. What exists, with evidence

| Piece | What it does | Evidence |
|---|---|---|
| `bernese-worker` | runs queued Start, Preflight, Redo and Stop requests, one at a time, under the BPE lock; never kills a BPE | `run_worker_design.md`; active on gps3 |
| BSW console | the operators' buttons, per-day status, plan check, failure page, Time series page with outlier review | active on gps3 behind Caddy |
| `bernese-run-year` | plan, lock, ledger, circuit breaker, day-level resume, parallel blocks | LUZON January 2026 (31/31), PHREF 2025 (360/360), PHPAR 2025 in progress |
| `bernese-notify` (cron, every 5 min) | emails run start, progress, end and trouble, and a stalled or dead worker | crontab on gps3; sender and recipients still to be set |
| `bernese-update-products` (cron, 02:20) | fetches CODE final orbits, clocks, ERP, biases and ionosphere; reports CONFIG and REF files that differ from AIUB's | crontab; on 2026-11-07 the latest complete day was DOY 304, so final products arrive about 7 days after the day |
| Ledger | each run's user, command, code commit, PCF, products and config hash | `ledger.py`, `run_start` |
| Time-series status | velocities, outlier counts, catalog sha256, outlier mode | `timeseries/status.py` |
| Pre-run header check | compares RINEX receiver and antenna with the `STA` file before a BPE | `rinex_header_validator.py`; see dependency D4 for its two disagreements with Bernese |

What does not exist: anything that brings new RINEX to gps3 without a person,
anything that proposes days to run, any acceptance of a day's result, and any
published output from gps3.

## 2. Phase A: prepare and propose (keeps §3 as it is)

A nightly job, `bernese-prepare` (name to be decided), in the same shape as
`bernese-update-products`: it only adds files, never changes a solved day, and
writes a status file the console and the notifier read.

**What it does, per campaign named in its configuration:**

1. **Bring in new RINEX** from the file server, read-only, with a sha256 per file
   (`transfer_phivolcs_datapool.py`'s fixity, made incremental). New files land
   in the datapool. Nothing is overwritten. A file whose name already exists with
   different bytes is reported, not copied.
2. **Stage** each new day into the campaign's RINEX directory, under the
   campaign's station list (D6).
3. **Decide whether each day is ready**, and say why not when it isn't:
   - final products complete for the day;
   - RINEX present for the reference stations the PCF needs, and a station count
     close to the campaign's usual count (a day at half strength waits, and is
     reported, rather than being solved thin and then becoming a station-set step);
   - `bernese-check-stations` clean for every station with data;
   - the header check passing, under the policy in D4;
   - no new station without ocean and atmospheric loading (D5).
4. **Wait for late data.** A day becomes ready no sooner than a set number of days
   after it ends, so that late files arrive before it is solved instead of after.
   The number comes from measuring how files arrive (D1).
5. **Propose** the ready days as one Start request per block of consecutive days.
   The proposal is shown in the console ("12 days ready, DOY 300–311") with one
   button that submits the existing `start` request. Nothing is queued without a
   person.
6. **Tell someone** through `bernese-notify`: days ready, days blocked and why.
   A day blocked for a week is a message, not a silent gap.

**Cadence.** Weekly, by GPS week, once its final products are in (about 7 days
after the week ends) and the late-data wait has passed. Weekly matches how both
teams already look at results. On current arrival times the late-data wait is
by far the longer of the two (D1, measured below). Our weeklies include Sunday, and the 5.2 team's
2025 weeklies don't: each stack's output lists its input days by name, and in
all 52 full weeks the one day missing is the Sunday (the 53rd, GPS week 2347,
holds only DOY 1–4 of 2025 and omits nothing). Found in the PHPAR pilot. So the
two must be stacked on the same days when compared.

**Why this is allowed under §3:** it doesn't run Bernese and doesn't change a
result. Its failure mode is a proposal that is wrong or missing, which is
visible to the person who would press Start. §3's cron exemption names only run
status and product fetching, so building this job means adding it to that list,
with this argument, in the same change.

## 3. Phase B: accept results before they are used

After each run, compute a **day report** and ask a person to accept or reject the
day. The time series and anything published read accepted days only. Days not
yet accepted are shown, marked, never silently mixed in.

**The day report, all from files that already exist:**

| Check | Why | Source |
|---|---|---|
| Stations solved against stations staged, by name | a station Bernese dropped shows here, not weeks later in a plot | FIN SINEX `SITE/ID` against the staged RINEX (the ledger's `stations` is only a count) |
| Fiducials passing the datum check, and the datum RMS | a datum resting on 2 stations is a different solution | BPE output |
| Station-set fingerprint, and whether it changed from the previous day | a set change makes a step with no physical cause (`provenance_record_design.md`) | sorted codes, hashed |
| Each station's departure from its own recent median | the jumps found in the 5.2 solutions (D14) would show here on day one | `coord_repeatability.py` logic |
| Groups of stations moving together | one station is an outlier; 14 together is a network problem | `network_coherence_scan.py` |
| Header mismatches the run continued past | they were allowed, so they must be visible | the run's log |

**Accepting** is one click with a name, as outlier decisions are already
recorded: an append-only line naming the day, the files' sha256 and who accepted
it. Rejecting needs a reason and offers Redo. A reprocessed day loses its
acceptance, because the sha256 no longer matches, the same rule
`outliers.py` uses for decisions made on a superseded solution.

**The aim is under a minute for a normal day**, not yet measured. The report
highlights only what is outside its thresholds. Like outlier review, this is decision support: the
software finds the thing to decide about, and a person decides.

## 4. Phase C: unattended starts (needs §3 reopened)

When phases A and B have run for a while, the remaining manual step is pressing
Start on a proposal nobody has reason to refuse. Phase C lets the worker submit
the proposal itself. It is a change to a settled decision, so it is the
maintainer's to make, and only with evidence.

**What would justify it, measured from phases A and B, not argued:**

- some number of weekly cycles in which no proposal was refused at Start for a
  reason the day report would not also have shown;
- every rejected day in that period caught by the day report, not later;
- at least two people accepting days (D9), so one absence doesn't stop results;
- notification working, so a halted run or a dead worker reaches a person.

**What stays manual even then:** acceptance, every Redo, anything after a
circuit-breaker halt, any change to CONFIG or REF files, and the offsets catalog.
The breaker already stops a run on repeated failures; under Phase C a halt ends
the automatic cycle until a person restarts it.

## 5. Stage 3: from accepted coordinates to velocities

**Recomputed on acceptance.** When a week's days have all been accepted or
rejected (acceptance is per day, section 3), the console recomputes
each station's series and velocity from accepted days only. This is the existing
Time series code reading a narrower set of files, plus a record of which
accepted set produced which numbers.

**Candidates, not changes.** Two kinds of candidates are shown for a person to
confirm:

- **outliers**, detected on residuals from the fit rather than on raw values
  (`automation_stages.md` task 6; the console's rule and `velocity-reviewer`'s
  disagree today, as `outlier_review_design.md` notes);
- **offsets**, by a statistic that compares populations before and after a date
  (task 7; IQR can't find a step). A confirmed offset is written to the catalog
  by a person. Software never writes the catalog. A step at a known
  station-set change is labelled as such, with a reprocessing type code
  (`PR`), proposed in `provenance_record_design.md` but not yet added to the
  catalog.

**Publishing is a separate, explicit action.** A published velocity file names
the accepted CRD set (by hash), the catalog's sha256, the reference station, the
outlier mode and the code commit. Without those, a published number can't be
reproduced, which is what happened with `Velocity_rover(regress)_10`
(`provenance_record_design.md`).

**What blocks publishing from gps3**, two decisions and one comparison, none of
them new code:

1. **Outliers in the published fit** (`SETTLED.md` §6). The console records
   decisions but can't publish a velocity until the team decides whether
   confirmed outliers leave the fit.
2. **Joining IGS14/I14 history to IGS20/I20 solutions** (§6). Published series
   reach back years on 5.2 solutions. A velocity spanning both needs a rule for
   the join, and none exists.
3. **Running both for one cycle.** `automation_stages.md` already proposes
   comparing `RUNX_v2.py` and `crd-to-plots` in parallel before switching; the
   same applies to the MATLAB and `analysis.py`.

## 6. Dependencies

Each gap below is from `automation_stages.md`, `SETTLED.md` §6, or found in the
PHPAR 2025 work. The column on the right says which phase it blocks.

| # | Dependency | State on 2026-11-07 | Blocks |
|---|---|---|---|
| D1 | **How new RINEX reaches the file server, and how late.** Stage 1 is manual on Windows (`automation_stages.md` stage 1), so arrival depends on people. Measured below | **about three months behind**, in batches | A, and it sets the cadence |
| D2 | **Bringing it to gps3.** `transfer_phivolcs_datapool.py` copies the whole share once; there's no incremental mode | not built | A |
| D3 | **Which campaign runs routinely.** LUZON runs in production; PHREF is the 35-station reference; the national network (PHNAT, 102 stations) is undiagnosed (`SETTLED.md` §6). PHPAR and PHSUP, now running, will show what a 90–100 station national run looks like on 5.4 | decision needed | A |
| D4 | **The header check against Bernese's own settings.** It found 466 receiver or antenna mismatches in 2025's solved station-days; RXOBV3 is set to warn, not drop, on these, so the check's message that they "will be silently dropped" is wrong for these panels. It reads the station name from `MARKER NUMBER` where RXOBV3 uses the file name (`STANAM FILE_NAME`), so MNAY's files, whose marker number says `MNA2`, are reported missing when Bernese finds them. A routine run needs the check to agree with the panels it guards. `--allow-header-mismatches` (in review, `feat/parity-2025`) is the stopgap | partly fixed | A |
| D5 | **Loading for new stations.** BLQ still needs the Onsala email round-trip; 5.4 stops on a station without it, which is the right failure but a slow one | manual | A |
| D6 | **Generalised staging and PCF derivation.** `derive_luzon_pcf.py` hardcodes LUZON; staging is one script per network | not built | A |
| D7 | **Current CONFIG and REF files.** 5 of 11 differ from AIUB's, and `SAT_2026.CRX` (satellite problems, 2026-06-23 here, 2026-11-06 at AIUB) matters most for new days: a satellite problem it doesn't list goes into the solution unflagged. Updating changes solved days, so it needs a boundary and a record (`SETTLED.md` §6) | decision needed | A for new days |
| D8 | **Station-set fingerprint and a `PR` catalog code** (`provenance_record_design.md`) | not built | B, stage 3 |
| D9 | **A second operator** (`automation_stages.md` task 1) | not started | B, C |
| D10 | **Notification sender and recipients** | waiting on a sender address | A, B, C |
| D11 | **Outliers in the published fit** (`SETTLED.md` §6) | team decision | publishing |
| D12 | **The I14/I20 join** (`SETTLED.md` §6) | open | publishing |
| D13 | **The continuous `offsets` catalog** is not snapshotted (task 5) | not started | stage 3 |
| D14 | **Jumps in the 5.2 dailies.** In the 5.2 team's 2025 F1 solutions, 1,692 station-days sit more than 100 mm from their own ±15-day median, on 280 days from DOY 44 onward, up to about 1.3 m, in groups that move together (PLWN, PPPC, NTUS; and about 20 stations including ISAB, PALM, TCDR). The weeklies mostly hide it. Any series built from those dailies, including a joined one (D12), needs this looked at first | found 2026-11-07, cause unknown | stage 3 |
| D15 | **Residual-based outlier detection and offset detection** (tasks 6 and 7) | not started | stage 3 candidates |

### D1 measured: data arrives months late, so stage 1 sets the pace

Read from the file server's `DATAPOOL\PHIVOLCS\2026` folder over SMB on
2026-11-07, counting distinct stations per day of RINEX 2 observation files:

| 2026 DOY | Stations per day (median) |
|---|---|
| 1–60 | 75 |
| 61–120 | 80 |
| 121–180 | 78 |
| 181–240 | 54.5 (range 25–79) |
| 241–270 | 15 |
| 271–285 | 6 |
| 286–296 | 3 (four stations in all: DGOS, MAR2, MASM, VNHS) |

The last day with 50 or more stations is DOY 214 (2 August). Files are written
in batches: of those for the last 60 days on file, 183 were written on 30
September, 264 on 9 October, 48 on 12 October and 221 on 3 November. Their
modification time is a median of 33 days after the observation day (10th
percentile 16, 90th 52), and is most likely when each file was converted. The
IGS stations' RINEX 3 files are in a separate folder (3,552 for 2026, not
analysed here).

**What this means for the design.** Products arrive about 7 days after a day.
Most stations' RINEX arrives about three months after it: the last full-strength
day was about 97 days before the count. The 33-day median above is lower
because it counts only files that had arrived, so it leaves out the stations
still missing. So a weekly schedule
would mostly report that days aren't ready yet. Processing earlier, on whatever
is in, would solve each day thin and again later at full strength. That makes
two solutions per day, and the time series would show a station-set step
wherever the two meet. **Routine processing can't be faster than stage 1**, and
stage 1 is people converting raw files on Windows.

That changes the order of work:

- Phase A's readiness rule (a station count close to normal) and its late-data
  wait are needed from the start. The wait is set in weeks, from these numbers,
  not days.
- What would shorten the delay is upstream of this design: a faster conversion
  and upload by the team, or a faster source of the same data. gps1's caster
  doesn't write daily RINEX (maintainer, 2026-11-07). The VADASE sites also
  send files over a separate FTP channel. Where those files land, in what format
  and how soon after the day hasn't been checked, and it's the first lead.
- Phase A is still worth building. It turns "has anyone uploaded March yet?"
  into a status the console shows, and runs a day as soon as it is complete.

## 7. Order of work

Only item 5 needs the BPE (it is a real run), so the rest can proceed while
PHPAR and PHSUP run.

1. **Ask the team how files reach the file server** (D1): who converts them, how
   often, and where the VADASE sites' FTP channel delivers its files, in what
   format and how soon.
   Decide D3 once PHPAR and PHSUP are compared. These set the numbers Phase A
   needs.
2. **Fix D4** in the PHPAR pull request: make the header check read the station
   name the way the panel says, and correct its message.
3. **Build Phase A** for one campaign: incremental transfer (D2), readiness,
   proposals in the console. It needs D6 only when a second campaign is added.
4. **Build the day report and acceptance (Phase B).** Most checks exist as
   scripts; the work is running them per day and recording the decision.
5. **Put a second operator through a run** (D9), using Phase A's proposal and
   Phase B's acceptance as the exercise.
6. **Decide D7** at a natural boundary, such as the start of the first routine
   campaign.
7. **Stage 3 candidates (D15)**, then publishing once D11 and D12 are decided.
8. **Phase C**, only if the evidence in section 4 is there.

## 8. Decisions for the maintainer and the team

| Decision | Who | Needed before |
|---|---|---|
| Which campaign runs routinely (D3) | maintainer, with the team | Phase A |
| When to update CONFIG and REF files (D7) | maintainer | the first routine week |
| How long to wait for late data, and the station count that makes a day ready | maintainer, from D1's numbers | Phase A |
| Whether stage 1 conversion and upload can be faster or more regular | team | anything faster than about three months |
| Whether accepted-only is the rule for the console's time series | maintainer | Phase B |
| Outliers in the published fit (D11) | team | publishing |
| How to join I14 and I20 series (D12) | team | publishing |
| Whether to reopen `SETTLED.md` §3 (Phase C) | maintainer | Phase C, with the evidence in section 4 |
