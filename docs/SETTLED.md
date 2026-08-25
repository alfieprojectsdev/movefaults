# Settled — do not re-derive

**Read this before investigating anything in this repository.**

Every entry below was established once, with evidence, and cost real time to
establish. Re-deriving them is the single most repeated waste in this project's
history: `CLAUDE.md` carries a *"Corrections to earlier versions of this
section"* block, the gps3 session log carries three separate *"the mistake,
this session's instances"* catalogues (§22.12, §23.8, §24.7), and both exist
because the same facts kept getting re-established from scratch.

## How to use this

- **If a question is answered here, it is answered.** Do not re-measure, do not
  re-argue, do not open with "we should check whether…".
- **Every entry carries how and when it was established.** That is deliberate —
  it lets you judge staleness instead of trusting the list blindly.
- **If you find evidence that contradicts an entry, that is a finding, not a
  violation.** Say so explicitly, show the evidence, and update the entry in the
  same change. What is forbidden is *silently* re-opening a settled question, or
  quietly working around an entry you believe is wrong.
- **"Settled" is not "good".** Several entries record decisions that are
  deliberate and imperfect. They are closed because they were *chosen*, not
  because they are ideal.

---

## 1. Ghosts — these do not exist; do not go looking

Verified absent 2026-08-25 by direct check, not by memory.

| thing | status |
|---|---|
| `src/ingestion/` | **gone.** Repo-root `src/` is now `src/db/` alone — two files |
| `services/vadase-rt-monitor/src/stream/` | **gone.** Consolidation complete |
| `services/vadase-rt-monitor/src/sources/` | **gone.** `src/ports/` + `src/adapters/inputs/` is the one input path |
| `IngestionProcessor` | **0 occurrences.** `IngestionCore` is *the* processor |
| `DataSource` protocol | **0 occurrences** |
| `manual_integration_active` | **0 occurrences.** The one-way latch bug was fixed in `934f8b3`, then removed wholesale by `a74c109`. **Do not re-report it** |
| `vadase-ingestor` console script | **never existed, deliberately.** The hatch wheel maps only `src/` dirs, so the target could not import. Run it from the service dir |
| `tools/velocity-reviewer` | **exists** — despite periodic doubt. Web replacement for the Windows-only outlier GUI |

There is no "dual-processor architecture" in vadase. That section was deleted
from `CLAUDE.md` because both duplicates were removed.

---

## 2. Settled facts — do not re-measure

| fact | established |
|---|---|
| Bernese 5.4 installed and verified on the **T420** (≤0.09 mm vs reference) and the **R740** (0.0000 mm, no `objcopy` patch needed) | 2026-02 / 2026-07-29. **BRN-001 is DONE** |
| `services/bernese-workflow` **invokes BSW for real** — `backends.py` → `startBPE.pm` over Perl | verified in code |
| `timeseries/analysis.py` reproduces `vel_line_v8_newvelduetooffset_v4.m` — 161/165 components to <5e-6 mm/yr | verified against PHIVOLCS' own published MATLAB output |
| The 2025 LUZON year is **358/365**, over three runs plus a DOY 036 recovery; the final run was **249 days in 476 min = 1.91 min/day** | session log §24.1, corrected in PR #138 after review |
| **DOY 036** failed on wrongly-fixed integer ambiguities. Float RMS 1.68 mm vs fixed 37.98 mm; recovered as a float solution at 1.79 mm | §24.3, closed by controlled experiment |
| `\\192.168.48.99` (Windows file server) is the **system of record** — not this repo, not gps3 | — |
| PAGENET is **NAMRIA's** national network. Bernese `PAGENET` campaign data is NAMRIA's | — |
| **PLWN (Brooke's Point, Palawan)** is the slowest site because it sits on the Eurasian Plate, not the Philippine Mobile Belt | 2024 report |
| Palawan has **PKLY/PNDO/PPPC only, all continuous CORS** — not a seeding gap | — |
| The repository is **PUBLIC**. `LICENSE` is MIT, holder **PHIVOLCS/DOST** | verified 2026-08-25 |
| `offsets`: **within-station chronological order is clean** (70 stations, 89 events). The BR14/LUZD corruption is fixed | verified 2026-08-25 |
| **No production month has run through `services/bernese-workflow`.** The service has never created a campaign on the R740 | confirmed 2026-08-25 from run history: every 2025 solution came from a Perl driver in `$U/SCRIPT` launched by `scripts/run_luzon_year.sh`. The 2025 run made this *more* true — 358 days through `scripts/` while the service gained tests |

### Do not quote the "implementation maturity" table as current

`CLAUDE.md`'s table was measured 2026-08-18 and is now **wrong by 31 and 20
tests**: `bernese-workflow` collects **229** against the 198 recorded,
`pogf-geodetic-suite` **144** against 124. Both figures were measured
independently on the T420 and the R740, a day apart, and agreed exactly — so
this is real drift, not a counting artefact.

**Do not cite those numbers at all.** "Re-measure before citing" understates it;
the recorded values are not stale-ish, they are wrong. What is settled is the *shape*: `bernese-workflow` is **~60% complete,
not ~10%**, and that misreport stood for months.

---

## 3. Settled decisions — do not re-propose the alternatives

| decision | why it is closed |
|---|---|
| **Per-component architecture** (VADASE hexagonal, ingestion Celery, bernese BPEBackend+Command/Builder, others flat) | decided 2026-04-15 |
| **teqc first, gfzrnx as fallback** on exactly two triggers: teqc refusing a RINEX 3 file, and teqc not installed. Any *other* teqc failure raises | teqc is more exercised and its output is what downstream parses. gfzrnx needs a commercial licence for operational use |
| **All substantive work reaches `main` through a PR**; branches live ≤1 week | a branch that outlived its purpose became a second trunk and cost a full session to reconcile (PR #57) |
| **Comms between the T420 and R740 sessions go as PR comments** when PR-scoped; rsync'd markdown otherwise. Never paste, never hand-relay through the user | SOP 2026-08-25 |
| **Human-in-the-loop at outlier review.** The target is decision support, not autonomy | `automation_stages.md` |
| **No cron for the scientific pipeline.** Run *status* has cron; the pipeline does not | its failure mode is silent wrong numbers; scheduling removes the person who would notice |
| **Non-commercial free tiers are a legitimate fit** (Vercel Hobby et al.) | PHIVOLCS work generates no profit by design |
| **`analysis/` `01 RINEX conversion` is not ported yet** | downstream of the digital logsheet; porting now automates the wrong half |

---

## 4. Known and accepted — these are not defects

Do not open these as findings.

- **`decay_factor` defaults to 1.0** in the VADASE leaky integrator — no leak at
  all. The decay is opt-in per station, by design.
- **Integration is skipped when the epoch gap is outside `0 < dt < 5s`** — so an
  outage cannot inject a step. Intended.
- **`offsets` is not globally alphabetical** (first break: `SOMH` → `SOLH`).
  Irrelevant — `parse_offsets_file` groups by station, and within-station order
  is what matters and is clean.
- **`--cov=src` measures almost nothing.** Known; name `packages/ services/
  tools/` instead.
- **`vadase-rt-monitor` and `field-ops` fail collection** without `structlog`
  and `uvicorn`. Environmental, pre-existing, fixed by `uv sync --all-extras`.
- **`RESUME_NEXT.md` discloses the R740 sudo password in prose** and the repo is
  public. The user accepted this 2026-07-31. Do not re-raise it; **do** keep new
  documents free of host and credential detail.
- **The 99 GB `ps4e` directory on DOSTB** is a valuable InSAR pipeline, not
  clutter. Never suggest deleting it to free space.
- **The Backup Plus drive is retired read-only** after corrupting fresh writes.
  DOSTB holds the complete verified GNSS copy. That migration is done.

---

## 5. Superseded claims still in circulation

Old documents and older memory still assert these. They are wrong.

| still says | actually |
|---|---|
| `bernese-workflow` is "~10% complete" | **~60%**, 229 tests, invokes BSW. The real gap is that production still runs through `scripts/` |
| `vel_line_v8.m` "remains to port" (`roadmap.md` Deliverable 2.4) | **done and verified** |
| gfzrnx is "not wired into any module" | **wired**, on two triggers |
| VADASE has a one-way integration latch bug | **fixed, then removed.** The `ReceiverMode` state machine moves both ways |
| `automation_stages.md` Stage 3 | the file has **two `## Stage 3` sections** (lines 206 and 393), overlapping and non-identical. One is stale |
| `CLAUDE.md`: repo-root `src/` is "`src/db/` alone, **four files**" (twice) | **two** tracked source files — `__init__.py` and `models.py`. The four counts `__pycache__/*.pyc`, which is not in the repository. Verified 2026-08-25 |

---

## 6. Still open — this list is not a gag

A settled-list that suppresses live questions is worse than none. These are
genuinely unresolved as of 2026-08-25 and *should* be worked on:

- **Decimal year disagrees between `RUNX_v2.py` (`DOY/365.25`) and the merged
  `crd_pipeline.py` (`(DOY-1)/365.25`)** — exactly one day. Live in merged code.
  Settle it before anything generates PLOT files. (PR #139, finding 6)
- **No production month has run through `services/bernese-workflow`.** Until one
  is compared byte-for-byte against `scripts/` output, its 229 tests are
  evidence about the service, not about the science.
- **No solution reaches TimescaleDB.** Steps 2–3 of the designed flow are
  aspirational.
- **Which ambiguities were wrongly fixed on DOY 036, and why that day.**
- **The field-ops server holds zero logsheets** while a handset holds three
  marked `synced`. Cheapest check: is the deployment still pointed at the same
  Neon DB as 2026-08-20, when the password was rotated?
- **GitHub Actions is disabled at repo level**, so `tests.yml` has never run.
- **The stage-1 `.exe`s are unverified** as builds of the Python we hold.
- **`disloc3d` has no source in-tree**; `disloc.c` does. (PR #139, finding 1)
- **Which of three inversion methods** — grid search, bootstrap, MCMC — is the
  one to port. (PR #139, finding 5)

---

## 7. Maintenance

- **Add an entry the moment a question is closed**, in the same change that
  closes it. Entries added later are guesses about what was decided.
- **Every entry needs the evidence and the date.** An entry that says only
  "settled" is unusable in six months.
- **Move entries out of §6 when they close**, and into §5 when a document goes
  stale rather than deleting the claim — knowing what the old docs *say* is what
  stops the next person believing them.
- **Name the symbol, not the line number.** Line numbers are the first thing to
  rot in this repository; `CLAUDE.md` says so explicitly and it is right.
