# Deliverables Tracker

**Last updated:** 2026-08-03

> Quick-reference status and date targets for all project deliverables.
> For architectural context and dependency rationale, see [`roadmap.md`](roadmap.md).

---

## Status Key

| Symbol | Meaning |
|--------|---------|
| ✅ | Complete — implemented, tested, committed |
| 🔄 | In progress |
| 🔬 | Research complete; implementation not started |
| ⏳ | Not started |
| 🚧 | Blocked |

---

## Deliverables

| ID | Deliverable | Status | Completed / Target | Notes |
|----|-------------|--------|-------------------|-------|
| 1.1 | Centralized Geodetic Database | ✅ | 2026-01-30 | Alembic 001–008; commit `bafa06b` + migrations 007/008 |
| 2.3 | Digital Field Operations PWA | ✅ | 2026-02-24 | `services/field-ops/`; schema extended (migration 008) |
| 1.2 | Unified Data Ingestion Pipeline | 🔄 | Q2 2026 | 1B-i consolidation done (PR #32); teqc + Trimble step pending |
| 2.1 | drive-archaeologist Integration | 🔄 | Q2 2026 | Scanner mechanics validated on a REAL mounted drive (a DOST media/movies drive — walk/dedup/checkpoint work). BUT the GNSS classification path (RINEX/Trimble/Hatanaka profiles — the tool's actual purpose) has ONLY synthetic/mock coverage (mock_drive/, test_data/, tmp_path). **Untested against a real legacy GNSS drive.** Also pending: Trimble profiles, pipeline handoff (ING-001) |
| 2.2 | Automated IGS Product Downloader | 🔄 | Q2 2026 | Partial; needs IGS20 naming + mirror fallback chain |
| 2.5 | RINEX QC Module | 🔄 | Q2 2026 | teqc wrapper exists (GPS-only RINEX-2). **gfzrnx migration trigger MET (2026-07-01, empirical):** teqc `2019Feb25` HARD-REFUSES the RINEX 3.04 IGS fiducials (`must be RINEX <= 2.11`); gfzrnx 2.2.0 QC's all constellations. Evidence: `gfzrnx_vs_teqc_rinex3_evidence.md`. Cass (MOVE Faults COS) has run gfzrnx for years. Next: dual-tool QC (teqc for RINEX-2 CORS, gfzrnx for RINEX-3 fiducials) or gfzrnx-primary; commercial license for the automated pipeline |
| 2.4 | Geodetic Post-Processing & Modeling Suite | 🔄 | Q3–Q4 2026 | `velocity-reviewer` complete (`bd743bb`); MATLAB port deferred |
| 1.3 | Automated Bernese Processing Workflow | 🔄 | Q3 2026 | **Core orchestrator BUILT** (BRN-002..006). NAMRIA training week (2026-06) PROVED the real PAGENET pipeline runs headless end-to-end on live data. **BRN-001 DONE 2026-07-29** — Bernese 5.4 installed and verified on the R740 (EXAMPLE campaign, 0.0000 mm vs reference, 11m28s). **2026-08-03:** validator now reads the real DATAPOOL (was blind to every file in it — see C2 below); all 7 PAGENET sessions validate clean; `$U` provisioned from a repo gold standard; `USER.CPU` maxjobs 2→11. **PAGENET_DLY.PCF blocker CLEARED** — captured 2026-08-05 (`4e82eaa`), verified 2026-08-12 (5.4 format, 0 dangling WAITs). **2026-08-06: LUZON reprocessed 30/30 days unattended in 2h47m**, 5m33s/day, repeatability 2.8/3.0/10.9 mm. **2026-08-12:** MATLAB velocity step ported to Python (171/171 components exact); PHIVOLCS scripts + `offsets` catalog captured into git. Parallel multi-session (SUPERBPE) tested and FAILED — PCF not session-independent; remedy is one campaign per session. Plan in `bernese_orchestrator_r740_readiness.md` |
| 1.4 | Public Data Portal and API | ⏳ | Q4 2026 | Depends on 1.3, 2.4. Strategic target: AusPos-equivalent for PH (300-station network, 27yr archive) — needs NAMRIA partnership for PRS92 datum |
| 3.1 | Centralized Documentation Portal | ⏳ | Q3 2026 | MkDocs + GitHub Pages; low-risk, can start any time |
| 3.2 | Automated Processing Documentation | ⏳ | Q4 2026 | Depends on 3.1 |

---

## Near-Term Work Items

> Full ticket list with priorities, sizes, and dependency graph: [`ticket_backlog.md`](ticket_backlog.md)

**DONE since last update (2026-04/05):** IGS-001, BRN-002, BRN-003, BRN-004, BRN-005, BRN-006,
ING-001/002/003 — see `bernese_workflow_status` memory + commits `bead683`→`c002a88`.

**Critical path (P0 — R740 orchestrator hardening; blocks unattended production):**
> Source: `bernese_orchestrator_r740_readiness.md` (14 gaps found in NAMRIA training week, 2026-06).
> The core orchestrator is built; these close the un-happy paths before R740.
1. ✅ **Per-session RINEX station validator** — targets DATAPOOL not empty RAW; runs per session. **Completed 2026-08-03**, but note what "complete" concealed: on first contact with the real DATAPOOL it found **zero** files. `_is_rinex_obs()` matched on `path.suffix`, and every archive file is `.gz` or `.Z`; Hatanaka `.26d`/`.crx` were missing from the accepted set too. Under the default `require_stations=False` it returned a **passing** report having read nothing. All 128 tests passed throughout, because the fixtures used a filename space that does not occur in production. Fixed with the real encodings plus an integration test against the live archive.
2. ✅ **Parameterize backends.run()** — PCF_FILE/campaign/CPU_FILE; MAXPAR sized from station count (gaps #3, #10).
3. ✅ **prepare_campaign() adds GEN/ + SESSIONS.SES** (gap #2).
4. ✅ **Panel/script sanitizer** — `\`→`/`, strip dangling WAIT PIDs, reject hardcoded sessions (gaps #8, #14). **Wired into provisioning 2026-08-03** via `scripts/provision_gpsuser.py`, so no un-sanitized panel can reach `$U`.
5. ✅ **BRN-001** — **DONE 2026-07-29.** Bernese 5.4 on the R740; EXAMPLE campaign 0.0000 mm vs reference. Easier than the T420 as predicted: AVX-512 present, so no ISA `objcopy` patch.

**NEW P0 — blocks the acceptance test:**
5a. ~~**Capture `PAGENET_DLY.PCF` from the T420**~~ — **DONE 2026-08-05** (`4e82eaa`), verified 2026-08-12: on `main`, installed to `$U/PCF/`, 52/52 rows in 5.4 format, 0 dangling WAITs. **Also now out of scope:** PAGENET is NAMRIA's network and existed only for the June training. Its eight `PGN_*` OPT directories are absent here, which matters only if a NAMRIA pipeline is run again. The PHIVOLCS equivalent, `LUZON_DLY.PCF`, is derived and has processed 30/30 days. *(The reasoning against re-deriving any PCF still holds: truncating RNX2SNX at PID 514 leaves `599 DUMMY` waiting on `522`, a dangling WAIT that hangs the BPE forever rather than failing — the provisioner now refuses it.)*
5b. **Resolve PLG2.** Contrary to the previous note, the validator does *not* prevent the PLG2 hard-abort — it **detects** it. PLG2 is absent from all five `PGN.*` reference files and its data sits hand-quarantined in `DATAPOOL/PGN/.excluded_plg2/`. `scripts/add_station_to_campaign.py` generates the records (dry-run verified); the velocity a priori needs a geodesist's sign-off before applying.

**Production deployment (P1 — before R740 go-live):**
6. **CODSPP-QC + tropo auto-recovery gates** (gaps #9, #11) — cheapest auto-fix in the pipeline.
7. 🔄 **Final-solution clustering tuning** (gap #13) — the 502 GPSCLU_P single-cluster bottleneck. **Half done 2026-08-03:** `USER.CPU` maxjobs was still the T420's `2`, so the 12-core R740 was using two of them; now 11. The readiness doc's "24 physical cores" was the *logical* count — 24 would have oversubscribed the FPUs 2×. **`V_CLUFIN` still untuned** and needs a real run to measure; all 72 stations remain in one cluster.
8. **VAD-001** — TimescaleDB compression + retention (DL-012; drives fill without this).
9. **DA-001** — drive-archaeologist GNSS-classification validation on a REAL legacy GNSS drive (currently only mock/synthetic; scanner mechanics proven on a media drive only).
10. **VAD-002** — TCPAdapter NTRIP handshake for Leica GR50.

---

## Recently Completed

| Date | Item | Detail |
|------|------|--------|
| 2026-08-03 | `$U` provisioned from a repo gold standard (P1-H) | `config/bernese/gpsuser/` + `scripts/provision_gpsuser.py`. Found `$U/OPT`, `PCF`, `SCRIPT`, `PAN` **byte-identical to the `$C/USER` template** — nothing PHIVOLCS-specific had ever been deployed. Panels sanitized with MAXPAR sized from station count; `SCRIPT/` copied verbatim (a Perl backslash is an escape); PCFs refused if they carry a dangling WAIT. `PAN/USER.CPU` generated from detected hardware, never versioned |
| 2026-08-03 | C2 — validator could not see the real DATAPOOL | `_is_rinex_obs()` matched on `path.suffix`; all 3,010 archive files are `.gz`, 20 are `.Z`, and Hatanaka `.26d`/`.crx` were unrecognised. Needed no Hatanaka decoding — CRINEX stores the RINEX header verbatim, so decompression alone suffices. Tests 128 → 189 |
| 2026-08-03 | `USER.CPU` maxjobs 2 → 11 | The R740 was running the T420's value: 2 of 12 physical cores, against a known 40-min single-threaded bottleneck. Set via `cpu_config.compute_maxjobs()` |
| 2026-07-29 | **BRN-001** — Bernese 5.4 installed + verified on the R740 | EXAMPLE campaign 0.0000 mm vs reference (max abs diff 20 nm), 11m28s. Storage provisioned (4 TB GPSDATA, 20 TB archive, 1 TB scratch); GPSDATA migrated with a three-way census; all 16 RAID members brought under smartd |
| 2026-06-26 | NAMRIA Bernese training week — full PAGENET pipeline run headless | Ran Modules 1-14 unattended on live 71-station data via `pagenet_pcs.pl` (parameterized stock `startBPE` driver) + idempotent `run_pagenet_week.sh`. Module 13/14 HELMCHK passed (RMS 8.64mm, 6 fiducials, 0 rejected). Proved the orchestrator execution contract on real data; surfaced 14 R740 gaps |
| 2026-06-26 | R740 orchestrator readiness eval | `bernese_orchestrator_r740_readiness.md` — P0/P1/P2 hardening plan + go-live checklist; commit `cf1cf2a` |
| 2026-05-05 | BRN-002..006 + ING-001/002/003 + IGS-001 built | BPEBackend+LinuxBPEBackend, campaign_builder, rinex_header_validator (BRN-006), pcf_context, velocity hook (BRN-005); commits `bead683`→`c002a88` |
| 2026-04-25 | VADASE director demo — full stack | `run_demo.sh` launcher; BOST Mw 7.6 fast-import replay; ANSI event banner; `--quiet` flag; Python 3.11+ check |
| 2026-04-25 | Grafana dashboard provisioned | `real_time_monitoring.json`: velocity + ENU + event table; 5 s refresh; docker-compose wired |
| 2026-04-25 | TimescaleDBAdapter wired as OutputPort | Migration 011 (`displacement_source`); lazy asyncpg import on dry-run; legacy `DatabaseWriter` deleted |
| 2026-04-25 | `ReceiverMode` state machine | Replaces one-way `manual_integration_active` bool; velocity-gated hysteresis; `GOOD_THRESHOLD=30` for Philippine scintillation — commit `a74c109` |
| 2026-03-03 | `velocity-reviewer` — PLOT file stripping | `write_cleaned_plots()` in `reader.py`; `POST /api/export` strips PLOT files with `.bak` backup/restore for idempotency; commit `bd743bb` |
| 2026-03-03 | Velocity pipeline primary source verification | PLOT format confirmed from `RUNX_v2.py:137`; offsets format from production file; `vel_line_v8.m` confirmed does NOT read `OUTLIERS.txt`; `00_CRD_*.bat` exclusion logic mapped; teqc commands confirmed from §4.2.3/§4.2.4 |
| 2026-03-03 | INP file diff (5.2 PHIVOLCS vs 5.4 EXAMPLE) | ADDNEQ2, MAUPRP, RNXGRA, RXOBV3, CODSPP compared; minimal Jinja2 strategy confirmed (3 parameters differ: RNXGRA MINOBS/MAXBAD, ADDNEQ2 MAXPAR) |
| 2026-03-02 | Migration 008 — field ops schema | `staff` table, `logsheet_observers` junction, campaign/continuous logsheet columns |
| 2026-03-02 | Migration 007 — `offset_events` table | Feeds velocity pipeline; replaces manual `offsets` flat file |
| 2026-02-27 | `velocity-reviewer` tool (initial) | Web-based GNSS outlier review UI; replaces Windows-only `outlier_input-site.py` |
| 2026-02-27 | Bernese orchestration explainer | Staff-facing document at `docs/bernese_orchestration_explainer.md` |
| 2026-02-26 | Bernese 5.4 installed + verified (T420) | RNX2SNX BPE, solutions ≤0.09 mm from reference. ("47-step" as previously written matches no count in 5.4's RNX2SNX.PCF — 64 PIDs, 51 unique scripts, 50 PIDs ≤514 excluding DUMMY. It may be right for the PHIVOLCS 5.2 PCF; unverified, so the figure is dropped rather than guessed at) |
| 2026-02-26 | BPE phase map + INP settings documented | Memory files: `bernese_bpe_phases.md`, `bernese_inp_settings.md`, `velocity_pipeline.md` |
| 2026-02-24 | Phase 1B-i ingestion consolidation | PR #32 merged |
| 2026-01-30 | Phase 0 database foundation | commit `bafa06b` |
