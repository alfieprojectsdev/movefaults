# Implementation Ticket Backlog

**Last updated:** 2026-05-03
**Source:** Codebase survey [`codebase_status_20260425.md`](codebase_status_20260425.md) cross-referenced with [`roadmap.md`](roadmap.md)

> **Priority:** P0 = critical path blocker · P1 = production deployment · P2 = feature complete · P3 = deferred
> **Size:** S ≤ 1 day · M 2–3 days · L 1 week · XL > 1 week

---

## Dependency Graph (Critical Path)

```
~~IGS-001~~ ──┐
               ├──▶ BRN-001 ──▶ BRN-002 ──▶ BRN-003 ──▶ BRN-004 ──▶ BRN-005
~~ING-003~~ ──┘

PR#33 (scanner) ──▶ ING-001 ──▶ ING-002    (parallel to Bernese track)

~~VAD-001~~
~~VAD-002~~                                 (parallel; needed before R740 go-live)
```

Shortest path to first end-to-end Bernese run: **IGS-001 → BRN-001 → BRN-002 → BRN-003 → BRN-004**.
BRN-001 (R740 install) has the longest elapsed wall-clock time and should start first.

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

### BRN-002 · P0 · L
**`BPEBackend` protocol + `LinuxBPEBackend` implementation**

`run_bpe()` in `orchestrator.py` is a logged placeholder. The Perl `startBPE.pm` API is fully documented in `memory/bernese_install.md` and `memory/bernese_bpe_phases.md`.

- Define `BPEBackend` Protocol: `prepare_campaign()`, `run()`, `collect_outputs()`
- `LinuxBPEBackend.run()`: set `PCF_FILE`, `CPU_FILE`, `BPE_CAMPAIGN`, `YEAR`, `SESSION`; invoke `perl $U/SCRIPT/rnx2snx_pcs.pl` via subprocess; block until complete
- Parse stdout for quality gates: PID 221/222 (station drop), PID 443 (ambiguity fixing rate ≥ ~80%), PID 513 (HELMCHK reference station motion < 1 cm), PID 514 (COMPARF daily repeatability < 3%)
- `WindowsBPEBackend` stub (no implementation, satisfies Protocol)

*Depends on: BRN-001.*

---

### BRN-003 · P0 · M
**Jinja2 INP templates from completed 5.2 → 5.4 diff**

INP file diff is complete (2026-03-03). Exactly 3 parameters need Jinja2 overrides. Current PCF template is a 16-line placeholder; `PHIVOL_REL.PCF` (127 lines, 7 stages) is the real target.

- Replace `templates/basic_processing.pcf.j2` with full `PHIVOL_REL.PCF`-derived template
- Parameterise server variables: `V_CRDINF`, `V_RNXDIR`, `V_B`, `V_REFINF`, `V_SAMPL`, `V_SATSYS`, `V_HOIFIL`
- Add three GPSEST INP variants (float / QIF / fixed) with Stochastic Ionosphere Parameters (SIPs) enabled — required for Philippine equatorial belt stations
- `prepare_campaign()` must stage the HOI model file in `OPT_DIR` before each BPE run
- The 3 override parameters: `RNXGRA MINOBS`, `RNXGRA MAXBAD`, `ADDNEQ2 MAXPAR`

*Depends on: BRN-001.*

---

### BRN-004 · P0 · M
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

### BRN-005 · P1 · M
**`plot_v2.py` parameterization — headless reference station**

`plot_v2.py` blocks headless execution with `input("Input the reference station: ")`. This is the sole automatable human gate in the post-BPE velocity pipeline.

- Add `--reference-station` CLI argument; maintain interactive fallback when omitted (preserves staff UX)
- Wire into orchestrator post-BPE step
- **Do not** automate `outlier_input-site.py` — the `velocity-reviewer` web UI is its intentional replacement; outlier review remains a human gate

*Depends on: BRN-004.*

---

## Ingestion Pipeline

### ING-001 · P1 · M
**drive-archaeologist → ingestion-pipeline Celery handoff**

The scanner classifies GNSS files; the Celery pipeline validates and loads them. The handoff between the two does not exist.

- Add `dispatch_to_pipeline(artifact)` in drive-archaeologist post-classification
- Wire to `ingest_rinex.delay()` Celery task with file path + station metadata
- Integration test: scan a small fixture directory, verify task fires and `IngestionLog` row is created in DB

*Prerequisite: PR #33 merged `c138806` — scanner hardening + `on_classified` callback seam.*

---

### ING-002 · P1 · M
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
| ANA-001 | Port `RUNX_v2.py` + `vel_line_v8.m` to Python library | BRN-004 stable |
| ANA-002 | Port dislocation models from `analysis/06` to pogf-geodetic-suite | ANA-001 |
| POR-001 | Public data portal + API (Deliverable 1.4) | Bernese pipeline live, NAMRIA partnership |
| DOC-002 | Automated processing documentation (Deliverable 3.2) | DOC-001, ANA-001 |
