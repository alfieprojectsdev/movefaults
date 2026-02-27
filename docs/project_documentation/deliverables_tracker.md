# Deliverables Tracker

**Last updated:** 2026-02-27

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
| 1.1 | Centralized Geodetic Database | ✅ | 2026-01-30 | Alembic 001–006; commit `bafa06b` |
| 2.3 | Digital Field Operations PWA | ✅ | 2026-02-24 | `services/field-ops/`; committed, not pushed to origin |
| 1.2 | Unified Data Ingestion Pipeline | 🔄 | Q2 2026 | 1B-i consolidation done (PR #32); teqc + Trimble step pending |
| 2.1 | drive-archaeologist Integration | 🔄 | Q2 2026 | Scanner works; Trimble profiles + pipeline handoff pending |
| 2.2 | Automated IGS Product Downloader | 🔄 | Q2 2026 | Partial; needs IGS20 naming + mirror fallback chain |
| 2.5 | RINEX QC Module | 🔄 | Q2 2026 | teqc wrapper exists; gfzrnx not yet acquired |
| 1.3 | Automated Bernese Processing Workflow | 🔬 | Q3 2026 | Research complete; awaiting INP files from staff to start Jinja2 templates |
| 2.4 | Geodetic Post-Processing & Modeling Suite | ⏳ | Q3–Q4 2026 | velocity-reviewer is first component; MATLAB port deferred |
| 1.4 | Public Data Portal and API | ⏳ | Q4 2026 | Depends on 1.3, 2.4. Strategic target: AusPos-equivalent for PH (300-station network, 27yr archive) — needs NAMRIA partnership for PRS92 datum |
| 3.1 | Centralized Documentation Portal | ⏳ | Q3 2026 | MkDocs + GitHub Pages; low-risk, can start any time |
| 3.2 | Automated Processing Documentation | ⏳ | Q4 2026 | Depends on 3.1 |

---

## Near-Term Work Items (next 4–6 weeks)

Priority order based on current unblocked state:

1. **Receive INP files from data processing staff** → build Jinja2 templates → `LinuxBPEBackend` (1.3 implementation start)
2. **Install Bernese on R740** — same procedure as T420, no ISA mismatch issue (Haswell = x86-64-v3)
3. **Migration 007** — `offset_events` table (feeds into velocity pipeline / replaces flat `offsets` file)
4. **Parameterise `plot_v2.py`** — replace interactive reference station prompt with `--reference-station` CLI arg (unblocks headless velocity pipeline)
5. **drive-archaeologist: Trimble profiles** — add `.T01`, `.T02`, `.T04`, `.DAT`, `.TGD` file classification
6. **VADASE latch bug fix** — `domain/processor.py:130` one-way latch never resets

---

## Recently Completed

| Date | Item | Detail |
|------|------|--------|
| 2026-02-27 | `velocity-reviewer` tool | Web-based GNSS outlier review UI; replaces Windows-only `outlier_input-site.py` |
| 2026-02-27 | Bernese orchestration explainer | Staff-facing document at `docs/bernese_orchestration_explainer.md` |
| 2026-02-26 | Bernese 5.4 installed + verified (T420) | 47-step BPE, solutions ≤0.09 mm from reference |
| 2026-02-26 | BPE phase map + INP settings documented | Memory files: `bernese_bpe_phases.md`, `bernese_inp_settings.md`, `velocity_pipeline.md` |
| 2026-02-24 | Phase 1B-i ingestion consolidation | PR #32 merged |
| 2026-01-30 | Phase 0 database foundation | commit `bafa06b` |
