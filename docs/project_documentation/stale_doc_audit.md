# Stale documentation audit

`scripts/audit_doc_references.py`, run 2026-09-05.

## What it checks, and what it cannot

Prose claims are not mechanically checkable. **File references are.** A live
document citing `scripts/foo.py` when no such file exists is stale by
construction, and that is the cheapest reliable staleness signal available.

A path that *does* exist proves nothing about the sentence around it. This
audit finds a lower bound on staleness, not its extent.

## Historical documents are not stale

A session log recording that a file existed in August is **correct** after the
file is deleted. Dated records — session logs, `CR-*` briefs, handovers — are
counted separately and must not be "fixed": rewriting them to match the present
destroys the record, which is the opposite of the point.

**24 historical documents** contain dead references and are excluded from
what follows.

## Results

| | |
|---|---:|
| markdown files tracked | 166 |
| path-like references checked | 1,739 |
| **live documents with dead references** | **53** |
| dead references in them | 272 |

## Where it concentrates

| document | dead refs |
|---|---:|
| `docs/CODE_REVIEW_VADASE_INGESTION.md` | 16 |
| `docs/project_documentation/documentation_portal/tech_spec_autodocs.md` | 16 |
| `docs/national_network_subnetwork_prep_plan.md` | 13 |
| `docs/project_documentation/bernese_dependencies.md` | 12 |
| `tools/drive-archaeologist/docs/TAILORED_IMPLEMENTATION_PLAN.md` | 12 |
| `docs/bernese54_luzon_reprocessing_runbook.md` | 12 |
| `docs/drive-archaeologist/docs/TAILORED_IMPLEMENTATION_PLAN.md` | 12 |
| `README_FOR_GPS3_CLAUDE.md` | 10 |
| `docs/bsw54_patch_plan.md` | 9 |
| `CLAUDE.md` | 8 |
| `docs/project_documentation/ticket_backlog.md` | 8 |
| `docs/bernese_linux_setup_primer.md` | 7 |

## The three causes, which need different responses

**1. Aspirational specs.** `tech_spec_autodocs.md` cites `generate_docs.py` and
`generate_glossary.py`, which were never written. The document describes an
intention, not a system. It is not wrong so much as **mislabelled** — a reader
cannot tell a spec from a description. Fix by marking status, not by deleting.

**2. Post-refactor rot.** `CODE_REVIEW_VADASE_INGESTION.md` cites
`src/database/writer.py`, `filters/validator.py` and others removed when
`src/stream/` and `src/sources/` were consolidated — a change `SETTLED.md`
already records as complete. This is the dangerous class: the document reads as
current and describes a structure that no longer exists. This is exactly what
`CLAUDE.md`'s "Corrections to earlier versions" block was added for.

**3. Moved, not deleted.** Several references are correct but relative to a
different directory. Cheap to fix, low consequence.

## What was actually corrected in this pass

`docs/bern52/crd_catalog.md` stated the want-list acceptance figure of
**190 / 271** "could not be reproduced". True when written; the T420
subsequently ran it against the real list and reported **259 / 271**, and
revision 2 of the brief confirms it. Corrected.

## What was deliberately not done

The other {nlive} documents were **not** mass-edited. Most dead references sit
in documents that are historical in spirit — a code review of a past state, a
backlog of tickets partly completed — and bulk-editing them would destroy more
context than it repairs. The audit's value is the classification; acting on it
is a per-document judgement.

## Re-running

```bash
scripts/audit_doc_references.py                       # live documents only
scripts/audit_doc_references.py --include-historical  # everything
```

Exit status is non-zero when any live document has a dead reference, so it can
gate CI once the backlog is worked down.

