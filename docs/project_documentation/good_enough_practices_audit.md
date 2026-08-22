# Audit: POGF against *Good Enough Practices in Scientific Computing*

**Date:** 2026-08-22
**Standard:** Wilson, Bryan, Cranston, Kitzes, Nederbragt & Teal (2017),
[*Good Enough Practices in Scientific Computing*](https://swcarpentry.github.io/good-enough-practices-in-scientific-computing/),
PLOS Computational Biology 13(6).
**Scope:** the six practice areas and their ~35 numbered recommendations,
measured against this repository at `d2d1cef`+.
**Output:** documentation only. Nothing in this audit changes code.

---

## Summary

The project scores well on the practices that are hardest to retrofit —
version control discipline, dependency management, testing, data provenance —
and has gaps in the ones that are cheapest to fix.

The single most valuable finding is a five-minute job:

> **`pyproject.toml` declares `license = "MIT"`, `README.md` tells the reader to
> "see the `LICENSE` file", and there is no LICENSE file.** GitHub reports the
> licence as `NONE` on a repository that is **public**. Under default copyright
> that means nobody may legally reuse this work — the opposite of the stated
> intent, and of the "Open" in Philippine Open Geodesy Framework.

| Area | Verdict |
|---|---|
| Data Management | **Strong**, with one deliberate deviation and one blocked item |
| Software | **Strong** |
| Collaboration | **Weakest area** — 3 of 5 items missing |
| Project Organization | **Good**, deviates from the paper's layout for defensible reasons |
| Keeping Track of Changes | **Strongest area** |
| Manuscripts | Partially applicable; the applicable half is done |

---

## 1. Data Management

| # | Practice | Status |
|---|---|---|
| 1a | Save the raw data | ✅ **Deliberately outside the repo** |
| — | Raw data backed up in more than one location | ✅ |
| 1b | Create the data you wish to see in the world | ✅ |
| 1c | Create analysis-friendly (tidy) data | ✅ |
| 1d | Record all steps used to process data | ✅ |
| 1e | Multiple tables, unique identifier per record | ✅ |
| 1f | Submit data to a DOI-issuing repository | ⛔ **Blocked on policy, correctly** |

**1a — the deviation is right.** The paper says save raw data in the project.
This project does not, and should not: `CLAUDE.md` states plainly that
`\\192.168.48.99` is the system of record, "not this repo and not gps3". 476 GiB
of GNSS observations do not belong in git. What the repo holds instead is
**fixity**: `docs/archive-manifests/` carries 5 tracked, gzipped sha256 manifests
covering **560,644 files** across the legacy archive, datapool and processed
products (counted directly from the manifests for this audit; earlier notes
say 560,636 — the manifests are authoritative). That is the intent of 1a satisfied by a means the paper did not
anticipate — and it is stronger than a copy, because it detects silent
corruption rather than merely duplicating it.

**Backup in more than one location** is genuinely met and was hard-won: the
DOSTB evacuation (2026-07-04/16) after the Backup Plus drive was found to
corrupt fresh writes, plus 20 TB of RAID 5 on gps3. Documented in `RESUME_NEXT.md`.

**1d is the project's quiet strength.** The processing chain is recorded end to
end in `CLAUDE.md`'s "How components connect", and `provenance_record_design.md`
goes further than the paper asks — per-invocation tool name, self-reported
version, argv, and input/output hashes. `fiducial_set.py` (PR #112) implements
the first piece of it.

**1e is met** — `client_uuid` on logsheets, `station_code` throughout,
`content_sha256` on photos, all with real uniqueness constraints.

**1f is blocked, and the analysis is already written.** `RESUME_NEXT.md` §"Tier 3"
records the intent to deposit with IGS / EarthScope-UNAVCO / a DOI repository and
names the two blockers: PAGENET is NAMRIA's under MOU, and agency data-release
policy sits above project level. It also notes derived products are easier to
release than raw observations. **No action — this is correctly parked**, and the
reasoning is better than most projects manage.

---

## 2. Software

| # | Practice | Status |
|---|---|---|
| 2a | Explanatory comment at the start of every program | ⚠️ **72%** (112/156 modules) |
| 2b | Functions no more than ~60 lines | ✅ **94%** (29/460 over) |
| 2c | Be ruthless about eliminating duplication | ✅ |
| — | Search for well-maintained libraries | ✅ |
| — | Test libraries before relying on them | ✅ |
| 2f | Meaningful names | ✅ |
| 2g | Make dependencies explicit | ✅ |
| 2h | Do not comment/uncomment to control behaviour | ✅ |
| 2i | Provide example or test data | ✅ |
| 2j | Submit code to a DOI-issuing repository | ⛔ Same policy block as 1f |

**2a — the gap is real but concentrated.** 44 modules lack a docstring, and the
list is informative: `packages/CORS-dashboard/` (explicitly forensic reference
material, not our code), `vadase-rt-monitor/scripts/*` (three runnable entry
points — these are the ones the paper cares about, since 2a asks specifically
for *how the program is used*), and two library modules,
`igs_downloader.py` and `modeling/coordinates.py`. Where docstrings do exist
they are exceptional: `rinex_qc.py` and `analysis.py` explain *why*, record
retracted claims, and name the evidence.

**2b is comfortably met** at 6% over the line, and the outliers are honest
rather than sloppy — `estimate_velocity_joint` (218) is a single mathematical
routine, `submit_logsheets` (148) is one transactional endpoint.

**2c is met and enforced.** The duplicate-elimination history is documented:
`src/ingestion/` removed, `src/stream/` and `src/sources/` consolidated in
vadase, the MATLAB velocity step ported once rather than reimplemented per
caller.

**2g is met thoroughly** — `pyproject.toml` with pinned lower bounds, `uv.lock`
committed, extras per service, `docker-compose.yml` for infrastructure.

**2i is met** — 31 tracked fixture/sample files, plus `mock_drive/`, a mock NTRIP
caster and replay tooling.

---

## 3. Collaboration — **the weakest area**

| # | Practice | Status |
|---|---|---|
| 3a | Create an overview of your project | ✅ `README.md` |
| 3b | Create a shared to-do list | ✅ `ticket_backlog.md` + issue templates |
| 3c | Decide on communication strategies | ❌ **Not documented** |
| 3d | Make the license explicit | ❌ **Declared but absent — see below** |
| 3e | Make the project citable | ❌ **No CITATION file** |

### 3d — the finding that matters

Three sources disagree:

| Source | Says |
|---|---|
| `pyproject.toml:10` | `license = "MIT"` |
| `README.md:115` | "see the `LICENSE` file for details" |
| The filesystem | **No LICENSE file exists** |
| GitHub API | `"license": "NONE"` |

The paper's wording is exact: *"Lack of an explicit license does not mean there
isn't one; rather, it implies the author is keeping all rights and others are
not allowed to re-use or modify the material."*

This repository is **public**. A geodesist who wants to reuse the velocity
estimator, or a partner agency wanting to build on the RINEX QC, currently has
no legal permission to do so. The intent is documented in two places; only the
file that carries legal weight is missing.

**Fix:** add a standard MIT `LICENSE` at the repository root with the correct
copyright holder. One consideration worth raising rather than assuming: the
copyright holder for work produced as a PHIVOLCS employee may be **PHIVOLCS/DOST
rather than an individual**. That is a question for the Director, not a
judgement call for this audit — but it should be settled before the file is
written, because getting it wrong is harder to undo than leaving it absent.

### 3e — citation

No `CITATION.cff`. For a project whose outputs are meant to be cited in
geodetic literature — and whose author is a co-author on Tobita et al. (2015) —
this is a real gap. GitHub renders `CITATION.cff` as a "Cite this repository"
button automatically. Blocked on the same copyright-holder question as 3d, and
on 1f/2j if a DOI is ever minted.

### 3c — communication

Nothing states how a newcomer asks a question or reports a problem *about the
project as a whole*. Note the partial exception: the field-ops issue templates
(`.github/ISSUE_TEMPLATE/01-app-problem.yml`, `02-app-suggestion.yml`) do exactly
this for the PWA's users, and the quick guide explains them in plain language.
That model just has not been extended to the repository.

**Lowest-value item in this audit.** The project has one active developer and a
git history that records decisions unusually well.

---

## 4. Project Organization

| # | Practice | Status |
|---|---|---|
| 4a | Each project in its own directory, named after it | ✅ |
| 4b | Text documents in `doc/` | ✅ `docs/` |
| 4c | Raw data in `data/`, generated files in `results/` | ⚠️ **Deviates, defensibly** |
| 4d | Source code in `src/` | ⚠️ **Deviates, defensibly** |
| 4e | Compiled programs in `bin/` | n/a |
| 4f | Name files to reflect content or function | ✅ |

**4c and 4d deviate because the paper describes a single-analysis project and
this is a monorepo of deployable services.** `packages/` / `services/` / `tools/`
each carry their own `src/`, which is correct for Python packaging and is what
`pyproject.toml`'s hatch mappings expect. There is no `results/` because
generated products live on the file server and gps3, consistent with 1a.

One genuine wart, already documented in `CLAUDE.md`: the **repo-root `src/`** is
down to `src/db/` (4 files), so anything pointed at it — coverage, mypy — measures
nearly nothing. The file already warns about this. Not worth moving; worth not
forgetting.

**4f is well met.** `bernese54_luzon_reprocessing_runbook_20260806-1837.md`,
`006_username_case_insensitive_unique.py` — the naming carries content *and*
date where date matters. The paper's specific prohibition on `result1.csv`-style
sequential names is not violated; the numeric prefixes in `analysis/` and
`migrations/` encode genuine ordering.

---

## 5. Keeping Track of Changes — **strongest area**

| # | Practice | Status |
|---|---|---|
| 5a | Back up everything human-created, as created | ✅ |
| 5b | Keep changes small | ✅ **median 3 files/commit** (last 60) |
| 5c | Share changes frequently | ✅ |
| 5d | Maintain a checklist for saving and sharing changes | ✅ **Unusually thorough** |
| 5e | Mirror the project off the working machine | ✅ |
| 5f | `CHANGELOG.txt` in docs | ⚠️ Superseded, see below |
| 5g | Copy the whole project on significant change | n/a — manual-versioning alternative |
| 5h | Use a version control system | ✅ |

437 commits, 5 contributors, median 3 files per commit, mirrored to GitHub.

**5d is where this project exceeds the standard.** `CLAUDE.md`'s Branching &
Merge Policy is exactly the checklist the paper asks for, and it is enforced:
branch → commit → PR → merge → delete; a one-week branch lifetime with the
27-day drift incident recorded as the reason; `git pull --rebase` before every
push; never `>/dev/null` a gated git operation; verify `origin/main` actually
advanced after every merge. The paper suggests a checklist. This is a checklist
with an incident report attached.

**5f — no `CHANGELOG.txt`, and that is defensible.** 5f and 5g are the paper's
*manual versioning* alternative, offered for people not using version control.
This project uses git and writes commit messages that carry the reasoning 5f
asks for. `RESUME_NEXT.md` additionally functions as a dated,
reverse-chronological project log — 5f in substance under a different name.

Worth noting honestly: `RESUME_NEXT.md` is now 1,819 lines. It works, but a
newcomer meets the whole project history before the current state. Splitting
older entries into `docs/session-logs/` would preserve the record and shorten
the on-ramp. Cosmetic, not urgent.

---

## 6. Manuscripts

Partially applicable — no journal manuscript is in preparation in this repo.

| # | Practice | Status |
|---|---|---|
| 6a | Online tools with change tracking | n/a |
| 6b | Plain text under version control | ✅ |

Everything textual here is Markdown under git: runbooks, handovers, decision
logs, the GEONET strategy brief, the presentation kits. The GeoCon 2026 abstract
is drafted in Markdown (`temp/`, gitignored by design — it is unsent
correspondence).

One observation rather than a finding: the **field-ops quick guide is a `.docx`**,
generated by a Python script from screenshots. The `.docx` is the deliverable
because its readers open it on a phone, but the generator makes it reproducible.
That is 6b's spirit — plain-text source, generated output — arrived at
independently.

---

## Recommended actions, in order

1. **Add a `LICENSE` file** (3d). Blocking on the copyright-holder question:
   PHIVOLCS/DOST or individual? *Ask the Director.* Everything else in this list
   is optional; this one changes whether the work is legally reusable at all.
2. **Add `CITATION.cff`** (3e). Same copyright question. Enables GitHub's
   "Cite this repository".
3. **Module docstrings for the 3 vadase entry-point scripts** (2a) — the paper
   asks specifically for *how the program is used*, and these are the runnable
   ones. Then `igs_downloader.py` and `coordinates.py`.
4. **A short "how to reach us" section in `README.md`** (3c). Lowest value here;
   include it when the README is next touched.

**Explicitly not recommended:** restructuring to the paper's `src/`/`results/`
layout (4c/4d), or adding a `CHANGELOG.txt` (5f). Both would trade a working
monorepo convention for conformance to a single-analysis template, and the paper
itself is explicit that these are *good enough* practices, not requirements.

## What this audit did not check

Reproducibility end to end — whether a clean checkout plus the documented
commands actually reproduces a published velocity field. That is the question
the paper is ultimately aimed at, and it needs a machine with Bernese and the
file server, not a static read of the tree.
