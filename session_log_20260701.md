# Session Log — 2026-07-01

**Context:** Post-NAMRIA-training consolidation + first R740-hardening code. BPE weekly-batch resume,
project-doc reconciliation, and P0 #1 (per-session RINEX validator).

---

## 1. PAGENET weekly batch — resume + PCF-var bug fix
Resumed `run_pagenet_week.sh` (finishes 087-090). Caught a real bug by running it in-session:
sourcing `LOADGPS.setvar` exports Bernese's own `$PCF` (the PCF *directory* path), which clobbered the
script's `PCF="PAGENET_DLY"` → malformed path → FATAL. Renamed the script var to `PCFNAME`. Fix
committed `4068688` (late 06-27) + synced to repo copy. Idempotent runner skips 084/085/086, restarts
at 087. Later stopped the run cleanly (user paused for the night); 3 dailies (084/085/086) banked.

## 2. Roadmap + tracker reconciliation (`d24b1ff`)
The roadmap (2026-03-03) was 3-4 months stale on the biggest deliverable. Corrected:
- **Bernese 1.3**: 🔬 "~15%, research starting" → 🔄 **core built (BRN-002..006), R740-hardening is
  the frontier**; linked the readiness eval + 14-gap plan.
- Critical path: marked IGS-001/BRN-002..006/ING-001..003 done; replaced with R740 P0 items.
- RINEX QC 2.5: added the gfzrnx-vs-teqc migration decision + licensing.

## 3. drive-archaeologist testing gap (DA-001, memory `drive_archaeologist_test_gap`)
User's nag ("not tested on a real filesystem") CONFIRMED and sharper than expected. `artifacts.db`
shows the scanner ran on a REAL mounted drive — but a **DOST movies drive**
(`/run/media/finch/DOSTB20150918`), NOT GNSS data. So scanner *mechanics* (walk/dedup/checkpoint) have
real-FS exercise, but the **GNSS-classification path** (RINEX/Trimble/Hatanaka profiles — the tool's
whole purpose) has only mock/synthetic coverage. A movies drive tests everything except the domain
logic. → **DA-001** (P1): validate classification on a real legacy GNSS drive before trusting
excavation output.

## 4. P0 #1 — per-session RINEX validator (`1e3c952`) — the first R740-hardening code
Closes two readiness gaps found in training:
- **Gap #1 (vacuous pass):** validator read the campaign `RAW/`, empty until RNX_COP stages data
  *inside* BPE → 0 stations → `report.ok` vacuously True. Added `rinex_source_dir` (= `$D/$V_RNXDIR`)
  so pre-flight reads RINEX where it lives before the run, + a `no_rinex_found` guard
  (`require_stations`) so empty/wrong source fails loudly.
- **Gap #12 (per-session):** a DATAPOOL source holds all DOYs; intermittent stations (PLG2, present
  only some days) must be validated against the session being processed. Added year/session DOY
  filtering across RINEX2/RINEX3/RXO names. The exact PLG2 hard-abort from day 086 is now caught
  pre-BPE by `LinuxBPEBackend`.
- Backward compatible (filter + guard opt-in via `rinex_source_dir`; legacy RAW/ path untouched).
  65 tests pass (6 new), ruff + mypy clean.

## 5. Ticket backlog reconciliation (`cff603d`)
Third doc in the trio (roadmap/tracker updated ~6h earlier, backlog was still 2026-05-04). Marked
BRN-004/ING-002 done; added the **R740 Orchestrator Hardening** section (RH-001..006 from the 14-gap
readiness eval — RH-001 done, RH-002 = next); added DA-001; refreshed the dependency graph.

## 6. RH-007 added to backlog (`47d4e9a`) — FTP_DWLD vs igs_downloader reconciliation
Found the Option-B pipe half-built: template `basic_processing.pcf.j2` still ships `000 FTP_DWLD`,
`campaign_builder.download_igs_products` is defined but never called, yet the production PAGENET PCF
already has no download step. RH-007 = strip FTP_DWLD from template, wire the pre-download into
`prepare_campaign()`, add pre-flight product-existence check. Option B (pre-download via igs_downloader)
is architecturally better for orchestration: separation of concerns, pre-flight-validatable,
reproducible vintage, CDDIS/IGN/BKG mirror fallback, endpoint-change resilience.

## 7. gfzrnx vs teqc — RINEX 3 evidence (migration trigger MET, not pending)
Cass (MOVE Faults COS staff, DOST-PHIVOLCS — NOT NAMRIA; corrected earlier mis-slot) provided gfzrnx
2.2.0 binaries + manual (`~/Downloads/gfzrnx/`); has run it as a teqc substitute with manual BPE for
years. Ran a head-to-head on an on-disk PAGENET fiducial (CUSV 2026/087, RINEX 3.04, GPS+GLO+GAL+QZS+
BeiDou-3):
- **teqc `2019Feb25` HARD-REFUSES it**: `must be RINEX Version <= 2.11 ... exiting` — 0 observations read.
- **gfzrnx 2.2.0** QC'd all constellations in 14 s (48 MB file).
Every IGS fiducial is RINEX 3.04 → teqc only "works" today because the PAGENET CORS subset still emits
RINEX 2. The migration trigger ("first RINEX 3/4 teqc can't process") is **met NOW**, not months away.
Evidence doc `docs/project_documentation/gfzrnx_vs_teqc_rinex3_evidence.md` (reproducible). Memory
`gfzrnx_teqc_decision` + tracker 2.5 updated. Licensing corrected: intra-PHIVOLCS (not third-party);
free scientific covers current manual use; automated pipeline still needs commercial campus license.

## State at end of session
- **Committed + pushed** (branch `docs/bernese-training-notes`): `d24b1ff` roadmap/tracker,
  `1e3c952` validator, `cff603d` backlog, `47d4e9a` RH-007, `3b73e1f` session log, + this session-log
  update + gfzrnx evidence doc. All in sync with origin.
- **Machine idle** — BPE stopped, nothing running.
- **Next code:** RH-002 (parameterize `backends.run()` PCF/campaign/CPU + MAXPAR sizing) — small,
  highest-value P0.
- **Async (user):** send GFZ license inquiry + internal cover note (now stronger — cite existing
  manual gfzrnx use + the RINEX-3 evidence); rotate `deploy_r740.secrets` OAuth token; run
  `~/run_pagenet_week.sh --detach` to finish 087-090.
