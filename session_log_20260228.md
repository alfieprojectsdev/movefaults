# Session Log: Documentation Revision & Staff Communication Strategy (2026-02-28)

## Overview

Short session following context compaction from 2026-02-26. Focus: committing pending
documentation, revising the orchestration explainer for accuracy, and planning what to
share with processing and field ops staff.

---

## 1. Committed Pending Documentation

The following files from the 2026-02-26 session had not yet been committed:

- `docs/project_documentation/roadmap.md` — updated with per-deliverable status symbols,
  Bernese research milestones, velocity-reviewer, VADASE remaining work items
- `docs/project_documentation/deliverables_tracker.md` — new; quick-reference status table
  with near-term work items and recently completed entries
- `docs/bernese_orchestration_explainer.md` — new; staff-facing orchestration explainer

Commit: `docs: update roadmap, add deliverables tracker, revise orchestration explainer`

---

## 2. Orchestration Explainer Revisions

Four corrections made before sharing with processing staff:

### 2a. Title
Changed from `From Manual BPE Runs to Reproducible Science: A Proposal for GNSS Pipeline
Orchestration` to `GNSS Pipeline Orchestration: What We're Building for Our Processing
Workflow`. Removed "Proposal" framing — inappropriate given author's seniority; reframes
as collaborative update rather than pitch seeking approval.

### 2b. Knowledge Concentration Section (§2)
Previous text: *"the full processing procedure exists primarily in the heads of the people
who do it regularly... none of this is written down."* — factually wrong; a work instruction
document exists.

Rewritten to: documents drift silently from practice, code fails loudly — that's the actual
argument. The work instruction is not deprecated; it becomes the **exception-handling
reference** when the orchestrator flags something that needs human judgment. For new staff:
orchestrator handles the routine, work instruction teaches the reasoning.

### 2c. Scale Numbers (§3)
Corrected from "35+ CORS stations" to the accurate figures from the MOVE Faults technical
paper:
- **~270 active stations** nationwide as of December 2024 (CORS + campaign combined)
- **300+ GPS sites** contributing data since 1995 (historical total, includes decommissioned)
- **35 CORS** with VADASE for real-time monitoring

Distinction preserved: 270 is the operational load argument; 300+ is the archive depth
argument. Both appear in the explainer for different purposes.

### 2d. New Section: The Workstation Problem (§4)
Added: BPE currently ties up a desktop for the duration of a run. With the orchestrated
pipeline on the R740, staff submit a job and their workstation is immediately free.
Prerequisite before this becomes current fact: Bernese installed and operational on R740.

---

## 3. Staff Communication Strategy

### Processing Staff
- **Share now**: `docs/bernese_orchestration_explainer.md` — written for them, stands alone
- **Follow-up**: `docs/project_documentation/deliverables_tracker.md` — shows timeline and
  the specific ask (R2S_GEN INP files, USER.CPU, RUNBPE.INP)
- **Hold**: roadmap, tech specs, session logs (wrong audience)

### Field Ops Staff
- **Documentation gap identified**: no user-facing guide for the PWA logsheet exists yet
- **Needed before sharing**: (1) one-pager "why the digital logsheet" covering offline-first
  behaviour; (2) field-use quick guide explaining IndexedDB queue + sync
- **Can share now**: the "What Stays in Your Hands" table from the orchestration explainer
  gives useful project context for buy-in
- **Hold everything else**: too technical for field ops audience

---

## 4. Pending Actions (carried forward)

| Action | Notes |
|--------|-------|
| Request INP files from processing staff | R2S_GEN OPT_DIR, USER.CPU, RUNBPE.INP (5.2 format) |
| Install Bernese on R740 | Same procedure as T420; no ISA mismatch; no objcopy step |
| Migration 007 — `offset_events` table | Feeds velocity pipeline; replaces flat `offsets` file |
| Parameterise `plot_v2.py` | Replace interactive reference station prompt with `--reference-station` CLI arg |
| drive-archaeologist Trimble profiles | `.T01`, `.T02`, `.T04`, `.DAT`, `.TGD` |
| Write field ops PWA user guide | One-pager + quick guide; prerequisite for sharing with field staff |
| VADASE latch bug fix | `domain/processor.py:130` |

---

## Files Updated This Session

- `docs/bernese_orchestration_explainer.md` — title, §2 rewrite, §3 scale numbers, new §4
- `docs/project_documentation/roadmap.md` — committed (written 2026-02-27)
- `docs/project_documentation/deliverables_tracker.md` — committed (written 2026-02-27)
- `memory/MEMORY.md` — corrected network scale (~270 active / 300+ historical)
- `session_log_20260228.md` — this file
