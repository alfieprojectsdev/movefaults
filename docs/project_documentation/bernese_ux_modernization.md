# Bernese UX Modernization — Brainstorm

**Status:** brainstorming / idea capture (not a spec)
**Started:** 2026-06-24 (during NAMRIA PAGENET training, Modules 5–9)
**Context:** Bernese GNSS Software 5.4 BPE — the **Qt4 graphical menu** an operator clicks through
panel-by-panel (Edit PCF → Edit Program Input Files → Start BPE → tail the RUN file → open `.OUT` in a
text editor). The "DOS-based flow" = this menu-driven, panel-by-panel, file-naming-convention,
`.OUT`-grepping **manual operator progression**.

> ## Central thesis (revised 2026-06-24, per user)
> **The R740 orchestrator makes the menu UX largely MOOT — it doesn't *modernize* the menu, it DELETES it.**
> Production runs drive BPE **headless** via the `startBPE.pm` Perl API (set PCF/CPU/campaign/year/session →
> `->run()`). The operator never opens the Qt menu, never clicks a panel, never tails the RUN file.
> So most of §1–§4 below are **not "build a better menu"** — they are **"the orchestrator removes the need
> for the menu entirely."** Do **not** invest in replicating/improving the click-through menu.
>
> The menu-UX critique stays relevant ONLY in three narrow places (see partition):
> 1. **Training / learning** (what we're doing now — humans must learn the menu).
> 2. **Interactive debugging** (a single operator poking at one campaign by hand).
> 3. **Irreducibly-human steps** — the few gates that genuinely need a person (outlier/offset marking),
>    where we DO want a thin modern UI, but NOT a menu-clone.
>
> We are NOT rewriting Bernese (the Fortran core is gold-standard, AIUB-validated). The orchestrator +
> a thin UI for human gates is the whole strategy.

---

## Partition — what the orchestrator KILLS vs what still needs a UI

| Menu pain (below) | Orchestrator verdict |
|---|---|
| §1 process lifecycle (terminal kills BPE, CPU reset, resume-at-master) | **KILLED** — daemon/job-runner, never a terminal-bound menu. |
| §2 "is it stuck?" progress | **REPLACED** — headless runner pushes structured status to a monitoring dashboard (not a menu). |
| §3 input validation / vacuous pass | **OWNED by orchestrator** — pre-flight + mid-run asserts, no human in loop. |
| §4 `.INP` panel editing, naming tokens, config drift | **KILLED** — declarative config rendered to `.INP` at runtime; no one ever opens a panel. |
| §5 output `.OUT` grepping | **REPLACED** — auto-parsed QC dashboard (monitoring UI, not menu). |
| §6 human-gate steps (outlier/offset editing) | **THIN UI NEEDED** — the one place a real interactive UI earns its keep. |

**Takeaway:** items 1–4 are "delete the menu" (orchestrator work, already on the [[bernese-orchestrator-r740-gaps]] list).
Items 5–6 are "build a small monitoring + human-gate UI." Nobody should build a prettier Qt menu.

The sections below keep the menu observations as the *evidence* for why the orchestrator is the right call —
each row is a thing the human operator suffers today that the headless path makes vanish.

---

## 1. Process lifecycle & session persistence

| Observed pain | Impact | Modernization |
|---|---|---|
| **Closing the launching terminal kills the BPE** (SIGHUP to child procs). Lost a run mid-PID-222. | Catastrophic — silent loss of a 20-min run; no warning. | Run BPE as a **detached daemon / systemd service / job queue**. UI is a *client* to a persistent runner; closing the browser/tab never touches the run. |
| After a kill, **must manually "Reset CPU File"** (`USER.CPU`) or next run hangs on stale locks. | Non-obvious; new users hang forever. | Orchestrator auto-detects stale locks on startup, self-heals. No manual CPU reset ever. |
| **Cannot resume at the interruption point** — must restart at the nearest `AP` master; **starting on a `_P` slave crashes instantly**. | Requires deep PID/cluster knowledge to recover. | Checkpoint/resume by PID with dependency awareness; UI offers "resume from last good step," refuses invalid entry points automatically. |

## 2. Progress visibility ("is it stuck?")

| Observed pain | Impact | Modernization |
|---|---|---|
| **RNXGRA (201) ran 9.5 min, single-threaded, spewing warnings** → the *entire training room* thought they were stuck. | Mass false-alarm; no way to tell slow-but-working from hung. | Real-time **progress bars per PID** (X of N files), live throughput, ETA. Distinguish "working" from "hung" via heartbeat. |
| `maxjobs=2` on the T420 → parallel steps grind 2-at-a-time with **no indication of queue depth**. | User can't see why it's slow or how far along. | Live cluster/job dashboard: which stations running, queued, done; per-core utilization. |
| Status is a **text `RNX2SNX.RUN` file** you re-`tail` by hand; PID states are `waiting/running/finished` strings. | Constant manual polling (we wrote watch scripts to do exactly this). | Push status to the UI (WebSocket). The "watch script" we keep hand-rolling **should be a built-in feature.** |

## 3. Input validation / vacuous passes (data-integrity class)

| Observed pain | Impact | Modernization |
|---|---|---|
| **`.RXO`/empty-RAW vacuous pass** — validator checked an empty dir pre-BPE → "passed" while doing nothing (fixed in c002a88; same class recurs). | Silent false success — worst failure mode in science software. | Validate the **actual data source** at the right pipeline stage; assert non-empty + station-count expectations. Fail loud, never vacuous. |
| **RINEX3 decode errors** (`'  ' instead of '> '`) silently **skipped records** = data loss, run still "OK". | Thinned data, invisible. | Surface per-file ingest quality: records read/skipped, % usable, flag stations below threshold *before* processing. |
| Bad **a priori coords → ~6 m CODSPP RMS**, but you only see it by grepping `SPP_*.OUT`. | Silent quality degradation. | **Auto-QC gate** (see [[bernese-orchestrator-r740-gaps]] #9): parse RMS + `NEW−APRIORI` delta, auto-discriminate bad-a-priori (auto-fix: re-seed) vs bad-obs (alert). |

## 4. Configuration ergonomics (the `.INP` panel hell)

| Observed pain | Impact | Modernization |
|---|---|---|
| Settings live in **dozens of `.INP` files** with cryptic keys (`COORDEST`, `CLKSAVE`, `KINOUT`); GUI menu ≠ saved file (kinematic run used unsaved menu state). | Drift between what you see and what runs; reproducibility risk. | Single declarative config (YAML/TOML) → rendered to `.INP` at runtime. Version-controlled. **What you see IS what runs.** |
| **Experimenting (STATIC→KINEMATIC) required editing an `.INP` + a full re-run**; no isolation. | Slow iteration; easy to leave a panel in the wrong mode (we had to remember to revert CODSPP to STATIC). | Named config presets / experiment profiles; one-click switch; diff against baseline; auto-revert. |
| **File-naming conventions are cryptic** (`$(APR)_$YYYSS+0`, `BSL_$YYYSS+0.BSL`, `CXT_$YYYSS+0`). | High memorization load; errors. | UI abstracts names; user picks "a priori coordinates," tool resolves the token. |
| Cross-platform scripts have **hardcoded paths** (`C:/Bernese/DATAPOOL/...` in BSW_DWLD → dies on Linux) and **missing-module** failures (P3_IGSRX https on Windows). | Per-machine breakage; opaque `Died at line 94`. | Path/env abstraction via vars (`$D`); dependency pre-flight check with human-readable errors. Patched scripts in versioned repo, not hand-edited per box ([[bernese-config-versioning]]). |

## 5. Output inspection & quality gates

| Observed pain | Impact | Modernization |
|---|---|---|
| **Verification = open `.OUT` in a text editor and read/grep manually** (we opened SPP/BSL files in lite-xl every step). | Slow, error-prone; `(MARKER)` lines don't even carry the station name → loose greps mismatch. | Structured result parsing → **dashboard**: per-station RMS, bad-obs %, baselines formed, ambiguity rate. Tables, not 14k-line text dumps. |
| Quality thresholds are **tribal knowledge** (RMS <1 m good, <10% bad obs, HELMCHK <1 cm, ambiguity ~80%). PHIVOLCS has no formal gates. | Inconsistent QC; depends on the operator. | Codified, configurable gates with pass/warn/fail + explanations. Adopt Bernese official benchmarks as defaults. |
| Kinematic `.KIN` = per-epoch ECEF X/Y/Z, **no plotting** — you read raw numbers. | Can't *see* scatter or a coseismic step. | Built-in time-series plots (ENU-rotated), scatter envelope, event detection overlay. (Ties to VADASE displacement viz.) |

## 6. Human-gate steps (downstream, post-Bernese)

| Observed pain | Impact | Modernization |
|---|---|---|
| `outlier_input-site.py` needs a **GUI right-click plot** to mark offsets — hard human gate. | Blocks headless/automated pipeline. | Web-based interactive outlier/offset editor; same data, browser UI, audit trail. |
| `plot_v2.py` has an **interactive "Input the reference station" prompt** → can't run headless. | Breaks automation. | Parameterize; reference station from config. |
| `offsets` file must exist before velocity regression; materialized by hand. | Manual, error-prone. | DB-backed `offset_events` → auto-materialize at the right step (already in POGF design). |

---

## 7. Terminology collisions (Bernese overloads words across modules)

Real cognitive load even for the instructor — same term, different meaning depending on module. The
declarative-config layer must **rename these apart**; never carry the overloaded term into the orchestrator.

### "Cluster" — two orthogonal meanings (flagged 2026-06-24, Module 9 SNGDIF)
| | **Compute cluster** (Mod 6–7) | **Network cluster / subnetwork** (Mod 9 SNGDIF; GPSCLU PID 5xx) |
|---|---|---|
| What | batch of files/stations on **one CPU job** | **geodetic subnetwork** — stations grouped for baseline formation / divide-and-conquer |
| Basis | grouped by **count** (fill the cores) — geometry irrelevant | grouped by **geodesy/topology** — count secondary |
| Driver | `V_CLU`, `maxjobs`, core count (T420=2, R740=24) | `$(CRDINF)` cluster def; ADDNEQ2 stacking of subnetworks |
| Meaning | pure **engineering** load distribution | **science** — affects baseline tree + which stations difference |
| Trap | — | a station's compute-cluster ≠ its network-cluster; they overlap (subnets can also be parallelized) but the grouping criteria differ |

**Fix in config:** `compute_batch` / `job_partition` (engineering) vs `subnetwork` (geodesy). Never `cluster` for both.
**↳ Instructor-confirmed (2026-06-24):** the lecturer explicitly flagged **"subnetwork"** as the correct term
for the Module 9 sense — independent validation of this rename. Adopt `subnetwork` in the config schema verbatim.

### Other overloaded terms seen this week (running list)
- **"Campaign"** — field GPS *campaign* (temporary GNSS deployment, domain term) vs Bernese *processing
  campaign* (a BPE execution run / `$P/<NAME>` dir). Already documented in CLAUDE.md; same collision class.
- **"Baseline Theory"** (Module 9 title) — misleading; the module is hands-on execution, not theory.
- Watch for more as modules progress; each is a `rename-apart` item for the config schema.

---

## Cross-cutting themes

1. **Persistence & resilience** — runs survive client disconnect; auto-recover from kills/stale locks.
2. **Observability** — push progress + structured status; kill "is it stuck?" forever.
3. **Fail loud, never vacuous** — every gate asserts real work happened on real data.
4. **What-you-see-is-what-runs** — declarative config, no menu/file drift, version-controlled.
5. **Abstract the 1990s** — hide file-naming tokens, panel keys, CPU files, platform paths.
6. **Auto-QC with discriminators** — parse outputs, classify failures (auto-fix vs human-alert), don't make the operator grep.

## Relationship to POGF / this repo
- The orchestrator (`services/bernese-workflow`) is the natural home for items 1–5; many map directly to
  open gaps in [[bernese-orchestrator-r740-gaps]] (validator timing #1, CPU self-heal, CODSPP-QC gate #9,
  script portability #8).
- The web UI direction overlaps the field-ops PWA stack already in the repo (FastAPI + React).
- **This is a wrapper strategy, not a fork** — the Fortran core stays untouched & AIUB-validated.

## Open questions
- How much can be driven via `startBPE.pm` Perl API vs needing menu interaction? (API can set
  PCF/CPU/campaign/year/session + `->run()` — most of the lifecycle is scriptable already.)
- Which steps *genuinely* need a human (outlier editing) vs just *currently* use a GUI by habit?
- Multi-user / multi-campaign concurrency on the R740 (24 cores) — job queue design.
- Where to draw the validation line: pre-flight only, or live mid-run assertions?
