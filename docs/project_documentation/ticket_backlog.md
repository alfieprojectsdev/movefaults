# Implementation Ticket Backlog

**Last updated:** 2026-07-02
**Source:** Codebase survey [`codebase_status_20260425.md`](codebase_status_20260425.md) cross-referenced with [`roadmap.md`](roadmap.md) and [`bernese_orchestrator_r740_readiness.md`](bernese_orchestrator_r740_readiness.md) (14 gaps from NAMRIA training week, 2026-06)

> **Priority:** P0 = critical path blocker · P1 = production deployment · P2 = feature complete · P3 = deferred
> **Size:** S ≤ 1 day · M 2–3 days · L 1 week · XL > 1 week

---

## Dependency Graph (Critical Path)

```
~~IGS-001~~ ──┐
               ├──▶ ~~BRN-002~~ ─▶ ~~BRN-003~~ ─▶ ~~BRN-004~~ ─▶ ~~BRN-005~~ ─▶ ~~BRN-006~~
~~ING-003~~ ──┘                                                          │
                                                                          ▼
   R740 orchestrator hardening:  ~~RH-001~~ ─ ~~RH-002~~ ─ ~~RH-003~~ ─ RH-004* ─ **RH-007** ──▶ BRN-001 (R740 install)
                                  (P1 side: RH-004* / RH-005* code done, content/action remainder · RH-006 solve tuning)
                                  └── acceptance: re-run PAGENET week on R740, gaps auto-cleared
                                  * = code mechanisms shipped, non-code remainder open (see tickets)

~~PR#33~~ ──▶ ~~ING-001~~ ──▶ ~~ING-002~~     (Bernese-parallel track)
                                └──▶ DA-001 (validate GNSS classification on a real legacy drive)

~~VAD-001~~  ~~VAD-002~~                       (done; were needed before R740 go-live)
```

**Status shift (2026-06/07):** the core Bernese orchestrator is BUILT (BRN-002..006) and the real
PAGENET pipeline ran headless end-to-end on live data (NAMRIA training week). The critical path is no
longer "start Bernese" — it is **R740 orchestrator hardening** (RH-00x below, from the 14-gap readiness
eval) plus the BRN-001 install. **Progress (2026-07-02):** RH-001..003 DONE, RH-004/RH-005 code
mechanisms DONE (PRs #38–#41, stacked on #38). **Next critical-path P0 = RH-007** (retire FTP_DWLD,
wire Option-B IGS pre-download). RH-004/RH-005 non-code remainders + RH-006 (solve tuning) are P1/P2.

---

## VADASE RT Monitor

### ~~VAD-001~~ · P1 · M · **DONE** `08fd153`
**TimescaleDB compression + retention policies**

At 35 stations × 1 Hz, uncompressed rows accumulate ~3 M rows/day. Without policies the R740 drives fill silently. Explicitly deferred as DL-012 in the TimescaleDB adapter.

- Add migration 012 (or standalone ops script) enabling `timescaledb.compress` on `vadase_velocities` and `vadase_displacements`
- `add_compression_policy()` after chunk age ≥ 7 days
- `add_retention_policy()` dropping raw 1 Hz rows after 60 days
- `CREATE MATERIALIZED VIEW` continuous aggregates at 1-min and 1-hour resolution for long-term tectonic drift analysis
- Document first-run instructions in docker-compose README

*Unblocks: R740 go-live with all 35 stations.*

---

### ~~VAD-002~~ · P1 · M · **DONE** `0c9768d`
**TCPAdapter: complete NTRIP client handshake for Leica GR50**

`TCPAdapter` opens a TCP socket but does not implement the NTRIP HTTP/1.0 handshake required by the GR50 NTRIP caster. Without this, live ingestion silently reads nothing.

- Implement NTRIP request: `GET /mountpoint HTTP/1.0\r\nAuthorization: Basic <b64>\r\n\r\n`
- Parse `ICY 200 OK` vs `SOURCETABLE` vs error response
- Implement reconnect-on-drop with exponential backoff
- Test against `scripts/mock_ntrip_caster.py`

*Unblocks: live 35-station ingestion on R740.*

---

### ~~VAD-003~~ · P2 · S · **DONE** `9cd8795`
**Remove Trimble parser dead code; update roadmap stale entries**

- Delete or clearly tombstone Trimble sentence stubs in `nmea_parser.py` (GR50 is Leica, not Trimble)
- Update `roadmap.md` §6: one-way latch bug is resolved (`a74c109`) — remove stale entry
- Update `deliverables_tracker.md` Near-Term Work Items accordingly

---

## Bernese Workflow

### BRN-001 · P0 · L
**R740 Bernese 5.4 installation**

T420 install is verified (EXAMPLE BPE ran 47 steps, solutions ≤ 0.09 mm). R740 is the production server. Same Ubuntu 24.04 OS; no ISA mismatch (Haswell = x86-64-v3, unlike Sandy Bridge T420 — no `objcopy` patch needed).

- Follow verified procedure in `memory/bernese_install.md`
- Install gfortran-14, g++-14, Qt 4.8.7 from source with the same three patches (gnu++98, Q_FOREACH rewrite, unsigned cmp fix)
- Run EXAMPLE campaign; verify solutions match reference at ≤ 0.09 mm
- Stage `CRX2RNX` at `$EXE` and `DE421.EPH` at `$MODEL`
- No per-machine license activation required (AIUB institution license)

*Unblocks: BRN-002 through BRN-005.*

---

### ~~BRN-002~~ · P0 · L · **DONE** `bead683`
**`BPEBackend` protocol + `LinuxBPEBackend` implementation**

`run_bpe()` in `orchestrator.py` is a logged placeholder. The Perl `startBPE.pm` API is fully documented in `memory/bernese_install.md` and `memory/bernese_bpe_phases.md`.

- Define `BPEBackend` Protocol: `prepare_campaign()`, `run()`, `collect_outputs()`
- `LinuxBPEBackend.run()`: set `PCF_FILE`, `CPU_FILE`, `BPE_CAMPAIGN`, `YEAR`, `SESSION`; invoke `perl $U/SCRIPT/rnx2snx_pcs.pl` via subprocess; block until complete
- Parse stdout for quality gates: PID 221/222 (station drop), PID 443 (ambiguity fixing rate ≥ ~80%), PID 513 (HELMCHK reference station motion < 1 cm), PID 514 (COMPARF daily repeatability < 3%)
- `WindowsBPEBackend` stub (no implementation, satisfies Protocol)

*Depends on: BRN-001.*

---

### ~~BRN-003~~ · P0 · M · **DONE** `bead683`
**Jinja2 INP templates from completed 5.2 → 5.4 diff**

INP file diff is complete (2026-03-03). Exactly 3 parameters need Jinja2 overrides. Current PCF template is a 16-line placeholder; `PHIVOL_REL.PCF` (127 lines, 7 stages) is the real target.

- Replace `templates/basic_processing.pcf.j2` with full `PHIVOL_REL.PCF`-derived template
- Parameterise server variables: `V_CRDINF`, `V_RNXDIR`, `V_B`, `V_REFINF`, `V_SAMPL`, `V_SATSYS`, `V_HOIFIL`
- Add three GPSEST INP variants (float / QIF / fixed) with Stochastic Ionosphere Parameters (SIPs) enabled — required for Philippine equatorial belt stations
- `prepare_campaign()` must stage the HOI model file in `OPT_DIR` before each BPE run
- The 3 override parameters: `RNXGRA MINOBS`, `RNXGRA MAXBAD`, `ADDNEQ2 MAXPAR`

*Depends on: BRN-001.*

---

### ~~BRN-004~~ · P0 · M · **DONE** `e11a135`
**Campaign file generation pipeline (8-step)**

Before any BPE run the campaign directory must be populated in dependency order. Architecture decisions are finalised (see `memory/bernese_inp_settings.md`).

- Implement `prepare_campaign()` in `LinuxBPEBackend` generating files in order: STA → CRD+ABB → ATL → PLD → VEL → CLU → BLQ
- BLQ from Chalmers web service (FES2004 model, 24-char fixed-column format, no tabs)
- Create required subdirs: `ATM BPE GRD OBS ORB ORX OUT RAW SOL STA`
- Two pipeline variants:
  - **Campaign GPS**: single-pass BPE
  - **Continuous GPS**: two-pass BPE (output CRD replaces input CRD; re-run)
- Pre-download IGS products via `igs_downloader` (bypass BPE step 000 FTP_DWLD)

*Depends on: BRN-002, BRN-003, IGS-001.*

---

### ~~BRN-006~~ · P1 · S · **DONE** `e1f2de2`
**Pre-BPE RINEX header validator — receiver/antenna code cross-check**

Staff-identified bottleneck (2026-05-05): RXOBV3 (PID 221/222) silently drops stations whose RINEX `REC TYPE` / `ANT TYPE` headers don't match the STA file or the staged ATX file. Stations disappear from the solution with no upfront warning.

- Implement `rinex_header_validator.py` in `bernese_workflow/`: reads RINEX OBS headers from the campaign RAW/ directory, extracts `REC # / TYPE / VERS` and `ANT # / TYPE` per station
- Cross-check against the campaign `.STA` TYPE 002 entries (receiver and antenna fields)
- Cross-check antenna type against the staged ATX file (IGS antenna calibration coverage)
- Return a structured `ValidationReport`: list of `Mismatch(station, field, header_value, sta_value)` — never silently pass
- Wire into `LinuxBPEBackend.run()` as a pre-flight check; raise `ValidationError` with the full mismatch list if any station would be silently dropped
- Reference source for expected equipment codes: `gpsdb_rev.receiver_models` + `gpsdb_rev.antenna_models` (legacy CORS dashboard MySQL DB) — import optional, fall back to STA-only check if DB unreachable

*Depends on: BRN-004. The legacy CORS dashboard already catalogued receiver/antenna inventory — this ticket makes that data load-bearing.*

> **Follow-up shipped (RH-001, `1e3c952`):** training exposed that the validator ran on the campaign
> `RAW/`, which is empty until RNX_COP stages data inside the BPE → 0 stations → vacuous pass. Now
> reads the DATAPOOL source per-session with a `no_rinex_found` guard. See RH-001.

---

### ~~BRN-005~~ · P1 · M · **DONE** `c0b23ca`
**`plot_v2.py` parameterization — headless reference station**

`plot_v2.py` blocks headless execution with `input("Input the reference station: ")`. This is the sole automatable human gate in the post-BPE velocity pipeline.

- Add `--reference-station` CLI argument; maintain interactive fallback when omitted (preserves staff UX)
- Wire into orchestrator post-BPE step
- **Do not** automate `outlier_input-site.py` — the `velocity-reviewer` web UI is its intentional replacement; outlier review remains a human gate

*Depends on: BRN-004.*

---

## R740 Orchestrator Hardening (from readiness eval — the 14 training-week gaps)

> Source: [`bernese_orchestrator_r740_readiness.md`](bernese_orchestrator_r740_readiness.md) +
> `memory/bernese_orchestrator_r740_gaps.md`. The core orchestrator is built; these close the
> un-happy paths so it can run unattended on R740. Acceptance test: re-run the PAGENET week on R740
> and have it clear the PLG2/PTAG/MAXPAR failures AUTOMATICALLY (this week they were fixed by hand).

### ~~RH-001~~ · P0 · S · **DONE** `1e3c952`
**Per-session RINEX validation against the DATAPOOL source (gaps #1, #12)**

- Validator read the empty pre-BPE `RAW/` → 0 stations → vacuous pass. Now reads `$D/$V_RNXDIR`
  per-session with a `no_rinex_found` guard (`require_stations`) so empty/wrong source fails loudly.
- Per-session DOY filter (RINEX2/3/RXO names) so intermittent stations (PLG2) are checked on the day
  they appear. Catches the RXOBV3 hard-abort pre-BPE. Backward compatible; 65 tests, ruff+mypy clean.

### ~~RH-002~~ · P0 · S · **DONE** `e544492` (PR #38)
**Parameterize `backends.run()` — PCF_FILE / campaign / CPU_FILE + MAXPAR sizing (gaps #3, #10)**

- ~~`run()` hardcodes `PCF_FILE="RNX2SNX"`, `CPU_FILE="PCF"` → cannot run PAGENET (the real workflow).~~
  **Shipped:** `LinuxBPEBackend` constructor now takes `pcf_file` (default `RNX2SNX`), `cpu_file`
  (default `USER` — the shipping `USER.CPU`, not the phantom `PCF.CPU`), `driver_script`, and `max_par`.
  `run()` exports the parameterized `PCF_FILE`/`CPU_FILE`/`BPE_CAMPAIGN` and passes the PCF as `argv[2]`
  for `pagenet_pcs.pl`-style drivers (stock `rnx2snx_pcs.pl` ignores it). Defaults preserve the stock
  contract.
- ~~Size `ADDNEQ2 MAXPAR` from station count.~~ **Shipped:** `compute_maxpar(n_sta)` (≈ N_sta×4 + 500,
  floor 1000) + `_count_crd_stations()`; `run()` auto-sizes from the campaign CRD (or `max_par` override)
  and exports `MAXPAR` as a BPE variable. NOTE: the value is *exported*; wiring it into the ADDNEQ2 panel
  templates themselves is **RH-004 / readiness task B** (panel templating). Left unset when uncomputable
  so the panel default stands.
- Tests: `test_backends.py` +10 (compute_maxpar bounds, CRD count, env-var flow, default preservation).
  75 tests pass, ruff + mypy clean.

*Consumer wiring: orchestrator still constructs the backend with defaults; thread `pcf_file`/`max_par`
through `BerneseOrchestrator` when driving PAGENET (small follow-up, out of this ticket's scope).*

### ~~RH-003~~ · P0 · S · **DONE** `b84c4a6` (PR #39)
**`prepare_campaign()` adds GEN/ + SESSIONS.SES (gap #2)**

- ~~`_SUBDIRS` omits `GEN`; no session table → BPE dies.~~ **Shipped:** `GEN` added to `_SUBDIRS`;
  `campaign_builder.generate_sessions_ses()` + `stage_sessions_ses()` write the stock daily `???0` table
  into campaign `GEN/`, unconditionally in `prepare_campaign()` (BPE needs it regardless of config),
  preserving a hand-tuned existing file; `sessions_template=` copies an exact install file. +5 tests.

### RH-004 · P1 · M · **PARTIAL** — all code mechanisms DONE `6c0d8a2`/`425735b`/`11bb672` (PR #40)
**Panel/script sanitizer + gold-standard config provisioning (gaps #8, #14)**

- **Shipped `panel_sanitizer.py`:** `sanitize_panel_text()` converts *mixed* Bernese/Windows separators
  but **flags, never rewrites** foreign drive paths (`C:\Bernese\...`) + hardcoded session/date literals;
  `find_dangling_waits()` (WAIT→undefined PID); `set_addneq2_maxpar()` (readiness task B, from RH-002
  `compute_maxpar`); `provision_opt_dir()` — sanitizes `*.INP` on the way to `$U/OPT`, copies `*.pl`
  verbatim, **two-pass atomic** strict-refusal of dirty panels. INP-only (Perl `\`=escape). +12 tests.
- **STILL OPEN:** author the **gold-standard panel content** — hand-remap real `PGN_WK`/`PGN_MO`
  `C:\Bernese\` paths to `${X}/${U}/${P}`, strip frozen sessions, commit under
  `services/bernese-workflow/script/` for `provision_opt_dir` to sync. Data/ops task (domain remap), not
  code; the strict provisioner enforces it can't be skipped. Also patch BSW_DWLD / ADD_MON (gap #8).

### RH-005 · P1 · M · **PARTIAL** — CODSPP-QC core DONE `26cc914` (PR #41)
**CODSPP-QC + tropo auto-recovery gates (gaps #9, #11)**

- **Shipped `codspp_qc.py`:** `parse_codspp_output()` (RMS OF UNIT WEIGHT, BAD/USED obs, X/Y/Z
  `NEW- A PRIORI` → `coord_shift_m`), `classify_codspp()` → `ok`/`bad_apriori`/`bad_obs`/`unknown`
  (tunable thresholds), `parse_codxtr_summary()`. Verified on the real CUSV 0840 block. +9 tests.
- **STILL OPEN:** the re-seed **action** (on `bad_apriori`, rewrite `.CRD` from CODSPP NEW coords, retry —
  applied/orchestrator layer) + the PID-322 **tropo quarantine** (quarantine the malformed/short-baseline
  NON-IGS partner, retry; never drop an IGS fiducial — needs a failed-322 output sample to parse against).

### RH-006 · P2 · S · **PARTIAL** — plumbing DONE (PR #43); empirical value pending R740
**Final-solution clustering tuning (gap #13)**

- **Shipped (plumbing):** `cpu_config.py` — `compute_maxjobs(physical_cores, ram_gb=…, reserve_cores=…)`
  (task L: physical cores not threads, FPU-bound; RAM-capped) + `set_user_cpu_maxjobs()` rewrites the
  `localhost` maxjobs field in `USER.CPU`. `PCFContext` now exposes `v_clu` (default 10) and **`v_clufin`**
  (default `"A"`), and the template templates both (`V_CLUFIN` was absent before). +13 tests.
- **STILL OPEN (needs R740):** the actual `V_CLUFIN` value that splits the final GPSCLU_P solve across
  cores. Correction from the real PCF: `V_CLUFIN` is a MODE flag (`A` auto / `N` skip), not a
  cluster-size number — `A` produced ONE giant single-core solve. Finding the split that parallelizes
  it is empirical and needs the R740's core count + real timing (BRN-001). The orchestrator can now
  *inject* both the chosen `V_CLUFIN` and a core-sized `maxjobs`; the value itself is a tuning task.
  **The multi-core R740 payoff is CONFIG, not free hardware** — untuned, R740 runs the same single-core
  solve on a bigger network = worse than T420.

### RH-007 · P0 · S
**Wire Option-B IGS pre-download; retire FTP_DWLD from the template**

Reconciliation debt found 2026-07-01: the "pre-download products, skip in-BPE FTP_DWLD" decision
(Option B) is only half-built. Three sources disagree:
- Decision (memory/roadmap): skip FTP_DWLD, pre-download via `igs_downloader`.
- Production PAGENET PCF (`~/GPSUSER/PCF`): no download step at all — matches Option B (relies on
  pre-staged `$D/COD0OPSFIN`). Empirically what PHIVOLCS/NAMRIA run (Eldar PCFs ship without FTP_DWLD).
- Orchestrator template `basic_processing.pcf.j2`: **still ships `000 FTP_DWLD`** (Option-A leftover).
- Orchestrator code `campaign_builder.py:273` `download_igs_products`: **defined but never called**
  (zero call sites) — the Option-B pipe is dead code.

Why Option B wins for orchestration: separation of concerns (retry download independently of the
multi-hour run), pre-flight-validatable products, reproducible product vintage, CDDIS/IGN/BKG mirror
fallback (IGS-001 already built it; FTP_DWLD has none), and resilience to the AIUB endpoint move
(gap #6) that would break in-BPE download silently.

- Strip `000 FTP_DWLD` from `basic_processing.pcf.j2` (folds into gap #4 — retemplate to PAGENET
  `PGN_GEN` flavor, not stock `R2S_GEN`).
- Wire `download_igs_products` into `prepare_campaign()` so Option B actually executes.
- Add a pre-flight product-existence + naming check: `COD0OPSFIN_YYYYDDD0000_..._{ORB.SP3,CLK.CLK,
  ERP.ERP,OSB.BIA}.gz` — verify IGS-001's downloader emits exactly what `V_ORB=COD0OPSFIN` expects
  (gaps #6, #7). Fail the run BEFORE launching BPE if products are missing/incomplete.

*P0-adjacent: no full run works without staged products. Depends on IGS-001 (done). See
`bernese_orchestrator_r740_readiness.md` gaps #4/#6/#7.*

---

## Ingestion Pipeline

### ~~ING-001~~ · P1 · M · **DONE** `2aeac1b`
**drive-archaeologist → ingestion-pipeline Celery handoff**

The scanner classifies GNSS files; the Celery pipeline validates and loads them. The handoff between the two does not exist.

- Add `dispatch_to_pipeline(artifact)` in drive-archaeologist post-classification
- Wire to `ingest_rinex.delay()` Celery task with file path + station metadata
- Integration test: scan a small fixture directory, verify task fires and `IngestionLog` row is created in DB

*Prerequisite: PR #33 merged `c138806` — scanner hardening + `on_classified` callback seam.*

---

### ~~ING-002~~ · P1 · M · **DONE** `e11a135`
**Trimble raw file classification in drive-archaeologist**

`.T01`, `.T02`, `.T04`, `.DAT`, `.TGD` (Trimble proprietary formats) are absent from `profiles.py`. PHIVOLCS has Trimble NetR9 receivers in the field; these files exist in the archive.

- Add Trimble profile to `profiles.py` with extensions and known filename patterns
- Add `TrimbleStrategy` in `strategies/gnss.py`; tag classified files as `requires_conversion`
- Stage conversion via `runpkr00` or `teqc -tr d` before RINEX ingestion step
- Update `drive-archaeologist` tests for new profile

*Depends on: ING-001.*

---

### ~~ING-003~~ · P2 · S · **DONE** `6a697eb`
**teqc as RINEX QC backend**

`rinex_qc.py` now shells to `teqc +qc` (replacing placeholder `gfzrnx` stub). Structured `RINEXQCResult` dataclass; QC metrics propagated to `IngestionLog` through the Celery chain. Two CodeRabbit review cycles addressed (timeout, QC persistence, error propagation, test coverage). 12 unit tests.

---

### ING-004 · P3 · S
**Stable checkpoint key for archive-extracted files**

During archive recursion, `mark_scanned(filepath)` records the ephemeral temp-extraction path. Across interrupted/resumed scans the temp dir changes, so previously processed archive members are rescanned rather than skipped. Correctness impact is low (rescanning is safe; just slow).

- Key should be `str(archive_path) + "::" + member_relative_path` rather than the temp path
- Requires threading `extraction_root` through `_scan_directory` and `_process_file`

*Deferred — Heavy Lift; correctness impact is bounded to extra work on resume, not data loss.*

---

### DA-001 · P1 · S
**Validate drive-archaeologist GNSS classification on a REAL legacy GNSS drive**

Found 2026-07-01: `artifacts.db` shows the scanner ran on a real mounted drive — but a **DOST
media/movies drive** (`/run/media/finch/DOSTB20150918`), NOT GNSS data. So scanner *mechanics*
(walk/dedup/checkpoint) have real-FS exercise, but the **GNSS-classification path** (RINEX / Trimble
`.T0x` / Hatanaka / legacy profiles in `profiles.py` + `classifier.py`) has only synthetic/mock
coverage (`mock_drive/`, `test_data/`, `tmp_path`). A movies drive tests everything EXCEPT the tool's
actual purpose — the classifier could mis-tag or miss real RINEX/Trimble files and no test would catch it.

- Mount a real legacy GNSS drive (DOST/PHIVOLCS archive — same drive class as the DOSTB one)
- Run the scanner; verify RINEX/Trimble/Hatanaka files classify correctly (spot-check against known content)
- Capture any mis-classifications as profile fixes; add a real-data regression fixture if feasible

*Do before trusting excavation output for the ingestion pipeline (ING-001 handoff). See
`memory/drive_archaeologist_test_gap.md`.*

---

## pogf-geodetic-suite

### ~~IGS-001~~ · P0 · M · **DONE** `f742571`
**IGS downloader rewrite — correct IGS20 naming + CDDIS/IGN/BKG fallback**

IGS20 long filenames, `.gz` decompression in-memory, IGN→BKG→CDDIS mirror order (anonymous first), legacy fallback for pre-week-2238 dates. 21 unit tests.

*Unblocks: BRN-004.*

---

## Infrastructure & Ops

### ~~OPS-001~~ · P1 · S · **DONE** `c52a138`
**Grafana alerting rule — velocity threshold breach**

The Grafana dashboard is provisioned. An alerting rule turns it from visualisation into an operational tool.

- Add alert rule: `avg(v_horizontal) > 0.015 m/s` (15 mm/s) over 10 s evaluation window
- Contact point: email to `alfieprojects.dev@gmail.com`; optionally Telegram (bot client already in vadase extras)
- Provision via `services/vadase-rt-monitor/grafana/provisioning/alerting/vadase_threshold.yml`

---

## Deferred (P3)

| Ticket | Title | Blocked on |
|---|---|---|
| DOC-001 | MkDocs documentation portal (Deliverable 3.1) | Most P0/P1 tickets |
| ~~ANA-001~~ | Port `RUNX_v2.py` + `vel_line_v8.m` to Python library — **DONE** `7f79174` | BRN-004 stable |
| ANA-002 | Port dislocation models from `analysis/06` to pogf-geodetic-suite | ANA-001 |
| POR-001 | Public data portal + API (Deliverable 1.4) | Bernese pipeline live, NAMRIA partnership |
| DOC-002 | Automated processing documentation (Deliverable 3.2) | DOC-001, ANA-001 |
