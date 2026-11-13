# Design brief: Bernese processing console

> **Status, 5 November 2026.** `services/bsw-console` was built from this brief
> in #315. Stages 1 and 2 (read-only status, plans and checks) are wired, and
> so are the equipment panel (#333), each attempt's run provenance on the Day
> page and the read-only Time series page (#335, #337). Stage 3 (Start, Stop,
> Redo and preflight) queues requests for the run worker (#334); it is off by
> default and is switched on per deployment, only for named operators, once
> sign-in is in place. Sign-in is a per-person login front end on gps3 that
> passes the user's name to the console, which trusts it only from that front
> end (the console side fixed in #338). This brief is the 26 October
> record and is not updated as the console changes; where it describes plans,
> they are plans, and the console's README says what is wired today.

*For the screen-design tool. Drafted 26 October 2026. Produce screens and a clickable
prototype for the screens in section 7. The rest of this brief is the context
those screens have to fit.*

## 1. What this is

PHIVOLCS processes GNSS station data into daily coordinates with the Bernese
GNSS Software (BSW). The processing staff (COS) run BSW 5.2 on Windows PCs,
through its desktop menu program. A newer install, BSW 5.4, runs on a Linux
server (gps3), where it has so far been driven from the command line by one
person.

The console is a web application served from gps3. Staff use it from their own
PCs, in a browser, to see what the 5.4 processing is doing, to plan and check a
run before it starts, and later to start one. Their PC's operating system
stops mattering, and nobody needs an X server, a remote desktop or a shell
account to use it.

The console doesn't replace BSW and doesn't hide it. It sits on top of the
processing service (`services/bernese-workflow`), which already:

- plans a set of days and checks them before anything runs;
- runs the days one at a time and records each attempt;
- reads BSW's protocol and log files after a failure and names the program and
  message that failed;
- looks that message up in a list of known errors, kept by the processing lead,
  and prints the recorded remedy;
- stops a run after 3 identical failures in a row, after 5 failed days of any
  kind, or at once on an unknown or configuration error.

The console's job is to put those results in front of a person. It makes no
decisions of its own, and no AI takes part in running it.

## 1a. Scope: a status portal, with the BPC as the only part that acts

*Added 26 October, after the first review.*

Staff need one place that shows the whole workflow: what was collected in the
field, which instruments are up, what data has arrived, what is processed, and
what the analysis says. The console is that place. To keep it from becoming
one module that knows everything, it is split in two:

- **A thin shell (name to be decided) shows the status of every part of the
  workflow, side by side.** It holds no business logic. Each panel shows what
  the service that owns that data reports, through that service's own
  read-only status endpoint. If a number is on screen, the owning service
  computed it, and its command line gives the same number.
- **The Bernese processing console (BPC) is the shell's Bernese section, and
  the only part that changes anything.** It acts on Bernese through
  `services/bernese-workflow` alone.

| Panel | Owner | What it reports |
|---|---|---|
| Data collection | field-ops | field visits, logsheets, equipment and antenna heights |
| Instruments | the CORS/VADASE side | station up/down, latest data, receiver mode |
| Data received | archive / ingestion | raw files received, RINEX in DATAPOOL, QC results |
| Processing (the BPC) | bernese-workflow | plans, runs, the attempt record, diagnoses |
| Results | timeseries / velocities | series, offsets, flagged outliers, velocities |

**Checks that cross two areas belong to a service, not to the shell.** For
example, "the logsheet's antenna height differs from the STA file" is a
planning check in bernese-workflow, which reads field-ops through field-ops'
own interface. Outlier detection stays in the timeseries package. The shell
shows both results and computes neither.

**Panels arrive when their owner has a status endpoint.** The shell and the
BPC come first. No panel waits on all the others.

## 1b. Analyses run on gps3, from the console

*Added 13 November. Supersedes the 11 November position, recorded only in the
gps3 session log (§43), that modelling stays out of the console.*

The processing team should not need to install anything. Post-processing
analyses run on gps3 and are started from the console:

| Analysis | Command it runs | Stage |
|---|---|---|
| Velocities, the MATLAB's table and outliers file | `pogf-timeseries velocities` | with the Results panel |
| Export of model inputs (velocities projected on a profile) | to be ported from `velproj_loop.m` | next |
| 2-D dislocation grid search and bootstrap | to be ported from `makeG_2ds_v3_loop.m` and `bootstrap_v2.py` | next |
| MCMC inversion | to be ported from `06 Ku-en` | later |

- **These are jobs, like a Bernese run.** The page submits a request; the run
  worker queues it, runs it and records it. The page shows the result and the
  settings that produced it. It computes nothing itself (section 1a).
- **The person still chooses.** A page offers defaults for fault geometry and
  parameter ranges, each with its published source, and the user can change
  them. The defaults are still being compiled (`SETTLED.md`, section 6).
- **Who may submit** follows the run buttons: named operators.
- **This is still one console.** VADASE's live view and alerts stay in Grafana,
  a separate process, so they stay up whatever the console or the BPE is doing.

## 2. Who uses it

**COS processing staff.** They know BSW 5.2 well, from the PHIVOLCS work
instruction (October 2025 revision) and from years of routine processing. They
are not programmers. They work on Windows, with Notepad++, Total Commander or
File Explorer, FileZilla, Excel and MATLAB.

They already own this vocabulary, so use it as written and don't explain it:

- campaign, active campaign, session, session table, DOY, GPS week;
- DATAPOOL, CAMPAIGN52, SAVEDISK, the RAW/STA/OUT/SOL/ATM/BPE folders, REF52;
- the eight campaign files: STA, CRD, ABB, ATL, PLD, VEL, CLU, BLQ;
- PCF, PID, script, "Start with script", "Skip scripts", RUNBPE 1 and 2;
- PHIVOL_REL.PCF, FTP_DWLD, R2S_COP, RNXGRA, GPSEST, ADDNEQ2, HELMCHK;
- F1_ files, NQ0, SNX, PRC, SUM, TRO, TRP;
- the protocol and log files named `$YSS+0_$PID_$SUBID`;
- the W and A flags in a CRD file;
- IGS fiducials by code (AIRA, ALIC, BTNG, CUSV, DAEJ, DARW, GUUG, MCIL, NTUS,
  PIMO, PNGM, TNML).

What they don't have is the 5.4 server's layout and conventions, which differ
from 5.2 in ways that mislead a careful 5.2 user (section 3).

**The processing lead.** Keeps the troubleshooting notebook behind the known-
errors list and decides what a remedy says. Needs to see which known errors
fire, and how often.

**The 5.4 maintainer.** Starts and stops runs today, and approves changes to
PCFs and campaign files.

### Habits to keep

A role-play on 25 and 26 October had an experienced 5.2 operator work through a
5.4 month run on gps3. The operator's habits carried over and caught real
problems:

- checking SAVEDISK first;
- stopping before deleting anything;
- reading the HLM and AMB summary listings down to the real cause, instead of
  trusting a summary line;
- refusing to run a PCF nobody had explained, or a second BPE beside a running
  one.

**So the console shows BSW's own outputs.** Every status, diagnosis and count
links to the file it came from: PRT, LOG, PRC, HLM, `AMB_*.SUM`, OUT. A green
light with no way to open the evidence behind it is a defect in this design.

## 3. Where 5.4 on gps3 misleads a 5.2 user

These came out of the role-play. Each one needs a place in the design.

| What a 5.2 user does | What happens on 5.4/gps3 | What the console should do |
|---|---|---|
| Types `G` to open the menu | "cannot connect to X server" | Be the way in. Nobody needs the menu to monitor or plan |
| Checks the campaign's RAW folder to see what data is there | RAW holds leftovers from earlier runs; the real input is the DATAPOOL | Show DATAPOOL as the input of record, per day and per station. Label RAW as working space |
| Copies files into RAW by hand | Nothing guards RAW, and a hand-copied file can change a run | Warn when RAW holds files the plan didn't stage |
| Recognises files by 5.2 names | 5.4 uses long names and new extensions (`.RXO`, `.SMT`) | Show the 5.2 name beside the 5.4 name wherever a file is listed |
| Re-runs a day by deleting its F1/FIN files | Only 2 of the day's 7 archived results are replaced; old RED, CRD and the rest stay, and later steps take them by name | Make "redo a day" one action that moves all of that day's results aside first (section 6, stage 3) |
| Reads the PRC summary after a run | Each day overwrites the run's summary, and a failure line reported "at 0" (a real bug, fixed in #295 on 26 October) | Keep every day's summary, and name the failed PID, script and program from the scanner |
| Asks "what produced this file?" | Only file dates tell three runs apart, and a float solution is named FIN_ like a fixed one | Show, per day, how it was produced: command, PCF, fixed or float, code version |

## 4. Current 5.2 procedure, and where each step lands

From the work instruction, sections 5 and 6. The middle column is what staff
do today in the BSW 5.2 menu.

| Work instruction step | In BSW 5.2 today | In the console |
|---|---|---|
| 5.2.2–5.2.3 Edit list of campaigns, select active campaign | Campaign menu, list panel | Campaign switcher in the header; the selected campaign is in the URL, so two tabs can show two campaigns |
| 5.3.2, 5.6.1.4 Set session | Date Selection Dialog; type a date and Compute | Range picker over a calendar coloured by day status. It shows YYYY MM DD, DOY and GPS week together, as the dialog's Compute does |
| 5.5.1–5.5.4, 5.6.1.5–6 Start BPE: number of sessions, Start with script, Skip scripts | RUNBPE 1 and 2 panels; scripts chosen from a list by PID | The Plan screen: a range of days, and the PCF as a list of PIDs and scripts with their WAITs. Choosing where to start and what to skip is checked against the PCF's dependencies before it can run |
| 5.4.2 Set V_ATLINF, V_BLQINF, V_CRDINF, V_RNXDIR in EDITPCF 4 | Edit the PCF in place | Read-only PCF variables, with differences from the stock PCF highlighted. Changing them is a reviewed change, not an edit in the browser (stage 3 and later) |
| 5.4.3 RNXGRA thresholds by observation method | Edit RNXGRA 3 by hand (campaign 100/70/3, continuous 200/10/3) | Show which preset the run uses, and flag a mismatch with the campaign's method |
| 5.5.1, 5.7 FTP_DWLD, or manual CDDIS and AIUB downloads | Run FTP_DWLD with every other script skipped, or download in FileZilla | A Products panel: for each day, are the orbits, ERP, DCB, ionosphere and IGS RINEX present, and from where. gps3 fetches from a mirror, because the AIUB FTP is firewalled |
| 5.3.4–5.3.11, 5.5.3, 5.6.3, 5.6.4 Create and update the eight campaign files | Eight programs and panels, Notepad++ copy-paste, a separate STA file so nothing gets overwritten | A Station files view (stage 4): one row per station, one column per file, showing where each station is listed and where it is missing. Adding a site is a guided change with a diff and a backup |
| 5.3.10 BLQ from the Chalmers ocean loading service, by email | Paste coordinates into a web form, paste the emailed block into a BLQ file | Still manual (the service is external). The console produces the coordinate block to paste, and checks the pasted reply for missing stations and for anything after `END TABLE` |
| 5.5.5 Check SAVEDISK outputs, or open `$YSS+0_$PID_$SUBID.LOG` on error | Browse folders by the naming convention | The Day screen lists the day's outputs, with a viewer. A failed day opens on the diagnosis |
| 5.5.6 Replace the a priori CRD with the final one | Copy, rename, overwrite in two places | A "use as a priori" action (stage 4), with a diff of the coordinates and the old file kept |
| 5.6.5 Update the GEN folder | Back up, then FileZilla from AIUB | Read-only: the age of each GEN file against AIUB's. Updating stays with the maintainer |
| 6.2–6.3 Time series, offsets, outlier removal | `plot_v2.py`, MATLAB `vel_line_v8.m`, right-click outliers, hand-edit PLOT files | Later (stage 5). The velocity code is already ported to Python and checked against the MATLAB output |

**Raw data to RINEX (work instruction section 4)** stays out of scope. It's
the one stage that is deliberately not automated yet, and it waits on the
digital field logsheets, which now exist. Leave a place for it in the
navigation and design nothing more.

## 5. Improvements over the native BSW interface (5.2 and 5.4)

Each item is something the BSW menu program, on either version, doesn't do,
paired with the problem it solves here.

1. **Any PC, many people.** The menu is a desktop program for one user: native
   on Windows for 5.2, needing an X display on Linux for 5.4. The console is a
   browser page. Each person has their own login, and every action is recorded
   with the person's name.
2. **The whole run at a glance.** The menu shows one program's panel at a time.
   The console shows days × PCF steps as a grid, coloured by state (not
   started, running, finished, failed, skipped), with the running step
   highlighted.
3. **The plan is checked before it runs.** In RUNBPE 2 any combination of
   "Start with script" and "Skip scripts" is accepted, including one that
   leaves a script waiting on a step that will never run. The service checks
   for that, and for days with too few reference stations and parameter counts
   above MAXPAR. It also runs the hardest day first as a preflight. The console
   shows the result as a list of findings before the Start button is enabled.
4. **Failures come with a diagnosis.** BSW reports `Script finished ERROR` and
   leaves the operator to find the right LOG by its file name. The console
   shows:
   - the failed PID, script and program;
   - the message, with the station or baseline it names;
   - the known remedy, if one is on file;
   - the raw lines of the PRT or LOG, highlighted, beside the remedy.

   An unknown error says plainly that nothing is on file and the run has
   stopped for a person.
5. **The stop rule is visible.** "Stopped: neqckdim DIMENSION TOO SMALL
   (configuration error), remedy: raise MAXPAR …" in the header of a halted
   run. On 29 August a year run lost nine hours to exactly
   this error.
6. **Every day records how it was produced.** The PCF, fixed or float
   ambiguities, the driver command, the code version, who started it, and each
   attempt with its outcome and duration. BSW keeps none of this beside the
   result.
7. **A redo is one safe action.** The day's whole set of results is moved
   aside, and put back if the redo fails. The redo is marked with BSW's own
   reprocessing title line (`REPROCESSING.FLG`), so the files themselves say so.
8. **One BPE at a time, enforced.** gps3 must not run two BPEs. The 5.2 habit
   enforces it today; the console makes it a lock. The header shows what holds
   the lock, since when, and who started it, and Start is disabled while it's
   held.
9. **Runs don't depend on a window.** A run started from the console runs as a
   service on gps3. Closing the browser, or losing the connection, doesn't stop
   it. A deliberate Stop lets the current day clean up first.
10. **Notification.** A halted or failed run notifies the people watching it.
    Nobody has to keep a window open to find out.
11. **Campaign files checked as a set.** The eight files must agree on the
    stations they list. Where 5.2 relies on care (and on the work instruction's
    warning that some programs overwrite files), the console shows the
    station × file coverage and blocks a run with a station missing from a
    file it needs.
12. **5.2 terms on 5.4 files.** Wherever a 5.4 file name differs from 5.2's,
    the 5.2 name is shown next to it.

## 6. Stages

The console is built in stages, and each stage is usable by itself. Two
prerequisites come before stage 1, outside the console: personal accounts on
gps3 with a network route from the office PCs to the server's subnet, and the
run lock with runs started as a service. Both are on the 26 October to-do
list.

| Stage | What staff can do | Writes anything? |
|---|---|---|
| 1. Status | Start from the inventory (screen 0): per site and day, how far the data has got and what is waiting at each step. Then campaigns, the calendar of days, a run's progress grid, a day's outputs, failure diagnoses, the lock holder, the known-errors list | No |
| 2. Plan and dry run | Choose a campaign, a range of days and the PCF steps; see the plan's checks and the preflight result; save a plan for the maintainer | Saves plans only |
| 3. Run | Start a saved plan, stop a run, redo a day under the supersede rule | Yes, through the service, one run at a time |
| 4. Station files | Station × file coverage, add a site as a reviewed change, use a final CRD as a priori | Yes, as reviewed changes with backups |
| 5. Time series | ENU plots per station, the offsets catalogue, marking outliers (recorded, not deleted) | Annotations only |

**Design stages 1 to 3 in full. Sketch 4 and 5 as navigation entries and one
low-fidelity screen each.**

## 7. Screens to design

Use real-looking data from these campaigns: LUZON (continuous stations,
2025), PHREF (the 2025 reprocessing compared with 5.2 production),
and PHDEN (a densified network trial).

0. **Inventory (the home screen).** Per site and day, how far the data has
   got, one column per step:

   | Step | Shown from |
   |---|---|
   | Field visit logged | field-ops |
   | Raw data received | archive / drive catalogue |
   | RINEX in DATAPOOL, QC passed | DATAPOOL, RINEX QC |
   | Processed, fixed or float | SAVEDISK, attempt record |
   | In the time series and velocity | timeseries |

   Above the grid, what is waiting at each step: raw data not yet converted
   (RAW to RINEX is still manual, so this backlog is real and should be
   visible), RINEX not yet processed, processed but not in a velocity, and
   logsheets whose equipment or antenna height differs from the STA file.
   Panels whose owner has no status endpoint yet show "not connected" rather
   than a guess.

1. **Home / campaigns.** A card per campaign: days solved, days failed, last
   run and its outcome, whether a run holds the lock now.
2. **Campaign calendar.** A year as a grid of days, coloured by state: solved
   fixed, solved float, failed, excluded by the plan, not attempted. Clicking
   a day opens the Day screen. Selecting a range opens the Plan screen with it
   filled in.
3. **Run progress.** Days × PCF steps grid for the current or a past run, with
   the circuit breaker's state ("1 of 3 identical failures"). Show a running
   state, a finished state and a halted state. **Several days can run at
   once:** parallel sessions, each in its own campaign (REPR_MODE), are how a
   year is meant to run. The grid must show more than one running row, and the
   lock belongs to the run, not to a day.
4. **Day.**
   - The attempts for that day, in order.
   - The outputs in SAVEDISK, with sizes and 5.2 names.
   - How the day was produced (improvement 6), including the IGS product tier
     used (final, rapid or ultra-rapid).
   - The day's quality numbers: stations in the solution after RXOBV3 (with
     stations dropped since the previous day highlighted), the ambiguity
     fixing rate, and the HELMCHK RMS. Each links to the listing it came from.
   - A text viewer for PRT, LOG, PRC, OUT, SUM, HLM and AMB summaries. It
     needs a fixed-width font, column-preserving wrapping off, line numbers,
     search, and highlighting of `***` error and `###` warning lines.
5. **Failure diagnosis.** The day's failed step and its raw lines beside the
   known-errors entry. Show three cases:
   - **Known, by session:** HELMR1 "NO REDUNDANCY" (too few fiducials left
     to check a day's solution). The run counts it and continues to the next
     day.
   - **Known, by configuration:** neqckdim "DIMENSION TOO SMALL" (more
     parameters than MAXPAR allows), or GTOCNL, a station missing from the
     ocean loading file. The run stops at once.
   - **Unknown:** no entry on file, so the run stops for a person.

   Also show an entry whose remedy is marked `proposed`, not yet `established`
   by the processing lead.
6. **Plan.** Campaign, range of days, PCF and its steps (start-with and skip,
   as in RUNBPE 2), the RNXGRA preset, and the IGS product tier (choosing it
   is a human decision). Under it, the checks:
   - days excluded for fewer than 3 reference stations, with the stations
     named;
   - MAXPAR headroom;
   - dangling WAITs from the chosen skips;
   - Products present for every day;
   - the preflight result.

   Then "Save plan", or in stage 3 "Start".
7. **Redo a day (stage 3).** A confirmation that lists every file that will be
   moved aside, where it goes, and what happens if the redo fails. No
   `confirm()` dialogs; the confirmation is part of the page.
8. **Known errors.** The list behind the diagnoses: program, message, scope
   (session or configuration), diagnosis, remedy, source, status (established or
   proposed), and how often each fired in the last 30 days. Read-only in the
   console; the processing lead edits the file.
9. **Station files (stage 4, low fidelity).** Station × file coverage matrix
   for one campaign.
10. **Time series (stage 5, low fidelity).** One station's E, N, U series,
    with offsets marked by type: EQ, CE (equipment change), VE (volcanic
    eruption), UK (unknown). Statistical outliers arrive already flagged by
    the timeseries package; a person confirms or overrides each, and the
    decision is recorded with their name. Whether a confirmed outlier is
    excluded from the velocity fit or only recorded is an open team decision:
    design both states and label which one applies.

A persistent header across all screens: active campaign, the lock state ("idle"
or "LUZON 2025 DOY 041–070, day 12 of 30, started 08:14 by …"), and the
signed-in person.

## 8. Look and feel

- **An operations console for specialists.** Dense, calm and precise. Tables
  and grids over cards. No marketing hero, no illustrations.
- **Office PCs.** Windows PCs, commonly at 1366×768 or 1920×1080. Design for
  1366 wide first. It must still be readable on a laptop; phone use is not a
  goal.
- **Fixed-width text is first-class.** BSW's files are column-formatted, and
  staff read them by column.
- **Status colours** must be distinguishable without colour (shape or label as
  well), and work in light and dark themes.
- **Dates** always show DOY with the calendar date (e.g. "2025-02-10, DOY 041").
  Times are local (UTC+8), with UTC available.
- **English**, matching the work instruction.
- **Self-contained.** No third-party fonts, analytics or CDNs at run time. It
  runs on PHIVOLCS hardware for PHIVOLCS staff.

## 9. How it should be built (for the implementers, after design)

- **Stack.** FastAPI and React, the same as the field logsheet app
  (`services/field-ops`), so the team maintains one pattern. Reuse its login
  approach, with per-person accounts.
- **Where it runs.** A service on gps3, reachable only from the office network.
  It is not exposed to the internet.
- **Reads.** The service's attempt record, the plan output, the scanner and
  known-errors list, and the BPE, SAVEDISK and DATAPOOL folders, all
  read-only. Stage 1 needs no write access to anything.
- **Writes, from stage 3.** Through the processing service's own commands only,
  via a queue served by one worker that holds the run lock. The browser never
  runs Perl, BSW or shell commands directly, and never takes a file path from
  the user.
- **Stop.** Sends the service a stop that ends the current day cleanly and
  cleans up its process group.
- **Same evidence.** The console shows what the service's command-line tools
  print, from the same code. If the two ever disagree, the console is wrong.
- **One status endpoint per owner.** Each panel in section 1a reads its owning
  service's read-only status endpoint, with a documented response shape. The
  shell never reads another service's database or files directly. Where the
  owner is on another machine (field-ops), access goes through that service's
  API, not a shared database login.
- **Location.** The BPC lives in `services/bsw-console`. The shell can start
  inside it and move out to a neutral name once a second section exists; that
  choice is still open.

## 10. Not in scope

- Editing BSW program panels in the browser. Panel and PCF changes stay
  reviewed changes made by the maintainer.
- Any automatic decision about a failure. Remedies are shown, never applied.
- Raw data to RINEX conversion (work instruction section 4).
- Driving BSW 5.2 on the Windows file server. The console is for the 5.4
  service only; 5.2 production carries on as it does now.
