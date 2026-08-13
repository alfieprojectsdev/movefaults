# Provenance record — design for review

**Status: DECIDED 2026-08-13 — the open questions below are answered. Ready to
build; nothing is built yet.**
**Drafted:** 2026-08-13

---

## The question it answers

> *Which tool, at which version, with which inputs, produced this file?*

That is what a reviewer asks about a coordinate series, and what a successor
asks in 2031. Today the honest answer for most of our outputs is "we think we
know."

## Why this is not hypothetical

Three failures **this month**, each of which a provenance record would have
turned from an investigation into a lookup:

1. **The velocity file that could not be reproduced.** PHIVOLCS' published
   `Velocity_rover(regress)_10` was written 2026-07-09; the `offsets` catalog
   it consumes was edited 2026-07-29. Comparing a new implementation against
   it showed disagreement at four sites and looked like a porting bug for
   about an hour. Neither file records which version of the other it used.

2. **A tool substitution nobody would have seen.** teqc is not installed on the
   R740, so RINEX QC now falls back to gfzrnx. Two results computed a week
   apart could come from different binaries reporting different quantities,
   and nothing in the output would say so. (This is why `RINEXQCResult` now
   carries `tool` — a first instance of the pattern proposed here.)

3. **The a priori that moved underneath a comparison.** Solutions are only
   comparable if the reference frame files, station list, and event catalog
   match. We currently establish that by remembering.

## What a record must contain

Per **step**, not per pipeline run — the unit is one invocation of one tool.

| Field | Why |
|---|---|
| `tool` | name as invoked |
| `version` | **self-reported by the binary**, never assumed. gfzrnx ships a manual labelled 2.0-8219 alongside a 2.2.0 binary; believing the docs would misattribute behaviour |
| `argv` | the exact argument vector, not a prose summary |
| `inputs[]` | path + sha256 + size for every file read |
| `outputs[]` | path + sha256 + size for every file written |
| `started`, `finished`, `exit_code` | wall time and outcome |
| `host`, `user` | two machines contribute to this project |
| `notes` | free text — e.g. a fallback reason |

**Checksums are the point.** A record naming `LUZON.CRD` is nearly worthless;
`LUZON.CRD` at a known hash is definitive. This also composes: an output hash
in one step matches an input hash in the next, so a chain reconstructs without
anyone designing a chain format.

## Where it goes

**One JSON Lines file per campaign-session**, beside the solution:

```
$S/<CAMPAIGN>/<year>/PROV/<CAMPAIGN>_<yyyyddd>.jsonl
```

One object per line, appended as steps complete. Rationale:

- **Append-only** survives a crash mid-run; a partial record is still valid.
- **JSONL** greps and streams; no parser needed to read it by eye.
- **Beside the data** so it travels with a copy — but see the caveat below.

## The unavoidable weakness, stated plainly

**A provenance record stored only beside the data cannot prove anything if that
disk is what went wrong.** Exactly the argument that put the archive manifests
into git.

The honest resolution: the record is *evidence*, not *proof*. To make it
proof, a digest of each session's record should be committed to git — small,
text, and independently timestamped by the commit. Proposed:

```
docs/provenance-digests/<CAMPAIGN>-<year>.tsv     # session, sha256 of jsonl, n_steps
```

A few hundred bytes per session. If the array is later suspect, the digest in
git says whether the record on disk is the one that was written.

## What I recommend *against*

- **A database.** TimescaleDB is in `docker-compose.yml` and nothing writes to
  it. Adding a service dependency to the step that is supposed to be the most
  reliable thing in the pipeline inverts the risk. Files first; ingest into a
  database later if querying demands it.
- **Capturing everything automatically via a wrapper.** Tempting, and it
  produces records nobody reads because they contain mostly noise. Instrument
  the steps whose provenance is actually disputed: external binaries, and
  anything consuming the `offsets` catalog or reference-frame files.
- **Retrofitting history.** We cannot honestly reconstruct provenance for runs
  already completed. Start from the next run; leave the past as it is.

## Proposed scope for a first implementation

Deliberately small enough to finish and be judged:

1. A `provenance.py` in `pogf-geodetic-suite` — a context manager that records
   one step and appends one line.
2. Wire it into **three** places, chosen because each has already caused a real
   problem: `RinexQC.run_qc` (tool substitution), the velocity estimation
   (catalog drift), and `scripts/run_luzon_month.sh`'s per-day BPE invocation
   (frame/station-file drift).
3. A `verify_provenance.py` that re-hashes recorded inputs and outputs and
   reports what no longer matches.

Explicitly **not** in scope for the first pass: the git digest file, database
ingestion, and instrumenting every script.

## Decisions (2026-08-13)

**1. Granularity — per external-binary invocation.** Not per BPE step. A
session runs ~50 BPE steps, and recording all of them produces a file nobody
reads. The boundary worth recording is where control leaves our code and
enters someone else's binary.

**2. Hashing — reference existing manifests; compute only what they do not
cover.**

The question as originally posed ("always, or only when small or changed?")
was badly framed, and both alternatives were wrong:

- *Only if small* is backwards. A large input that changes silently is exactly
  the case worth catching; a size threshold skips precisely that.
- *Only if changed* is better, but rests on mtime+size — a heuristic a
  same-size edit defeats. Fine for a cache, not for a fixity claim.

**The cost has largely evaporated since the question was written.** As of
2026-08-12 every archived file carries a sha256 committed to git —
**560,636** across the legacy archive, the datapool, and `processed/`. So:

- **Inputs covered by a manifest**: record the manifest's hash and cite which
  manifest. No re-read. If the file on disk has since diverged, manifest
  verification catches it — duplicating that check inside every run buys
  nothing.
- **Inputs not covered** (freshly staged products, generated PCFs, the
  `offsets` catalog): hash directly. Small, and `offsets` is the one whose
  drift has already caused a real problem.
- **Outputs**: always hash. New by definition, and small next to the
  observations.

This also makes records *composable*: an output hash in one step is the input
hash of the next, and a disagreement between a provenance record and an
archive manifest becomes the alarm rather than something to guard separately.

**3. Home — `services/bernese-workflow`.** It is orchestration, and that
service is the destination. One design consequence worth stating:
`pogf-geodetic-suite` must not import it, so library code cannot call the
recorder. Libraries **return** what they did — as `RINEXQCResult` already does
with `tool` and `fallback_reason` — and the orchestrator records it. Better
boundary regardless: the library computes, the orchestrator remembers.

**4. Retention — indefinite**, matching the solutions. A record is a few KB
against a solution set of hundreds of MB, and a coordinate series outliving its
provenance is the exact situation this exists to prevent.

## Revised first implementation

1. `services/bernese-workflow/src/bernese_workflow/provenance.py` — a context
   manager recording one external-binary invocation as one JSONL line,
   resolving input hashes from `docs/archive-manifests/` where possible.
2. Wire into the three call sites that have already caused real problems, via
   returned metadata rather than library-side calls:
   - the BPE invocation in `backends.py` (reference-frame / station-file drift)
   - `RinexQC.run_qc` (tool substitution — already returns `tool`)
   - velocity estimation (catalog drift)
3. `verify_provenance.py` — re-hash recorded outputs, cross-check recorded
   input hashes against the archive manifests, report divergence.

Out of scope for the first pass: the git digest file, database ingestion, and
instrumenting every script.
