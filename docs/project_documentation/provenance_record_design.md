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

---

## Amendment, 2026-08-13: reprocessing with data found later

Raised in review: *what happens when RINEX files previously assumed missing
turn up, and whole subnetworks are reprocessed with them?*

This is not hypothetical. Retrieving the full PH network from staff computers
is planned work, and the `2024/`/`2025/` layout trap on the file server is
proof that "we have all of it" has already been wrong once. The design above
handles part of this and misses the part that actually bites.

### What the design already handles

**Same filename, different science.** `FIN_20251390.SNX` computed from 4
stations and from 25 stations occupy the same path. Because a record lists its
inputs, the two runs are distinguishable — and the second one does not
retroactively invalidate the first, it simply supersedes it. No change needed.

### Correction to decision 2: manifest lookup is a lookup, never a gate

Decision 2 says "reference the manifest hash for covered inputs, hash directly
otherwise". Correct, but the dangerous implementation of it is:

```python
h = manifest.get(path)          # WRONG
record.inputs.append(h)         # h is None for anything found later
```

Newly-found files are by definition absent from every manifest. **Absence must
trigger a hash, never a null and never a skip.** A record that silently omits
an input is worse than no record: it asserts completeness it does not have.

```python
h = manifest.get(path) or sha256_file(path)   # and mark which one it was
```

Records must also carry *how* each hash was obtained — `from_manifest` versus
`computed` — so a later audit can tell "verified against the archive" from
"trusted at the time".

### The part that bites: a station-set change is an apparent offset

Adding stations changes network geometry, datum realisation, and ambiguity
resolution. **Stations whose own data did not change still move**, typically at
the few-mm level, because the network around them changed.

So reprocessing 2015–2018 with newly-found data while leaving 2019–2025 as it
stands puts a **step in the coordinate series at the reprocessing boundary that
has no physical cause**. It will look exactly like the equipment changes and
earthquakes the `offsets` catalog exists to record, and the honest analyst
looking at it will add a catalog entry for an event that never happened.

That failure is self-concealing: once the offset is in the catalog, the
segmented velocity fit accommodates it, the residuals look fine, and nothing
downstream complains. The velocity delta analysis
(`velocity_outlier_policy_delta.md`) shows the neighbouring hazard is already
real — a catalog edit on 2026-07-29 silently changed five sites' published
velocities and corrupted two of them outright.

**Two mitigations, both cheap:**

1. **Station-set fingerprint per solution.** Sorted 4-character station codes,
   hashed, recorded alongside the solution. Grouping solutions by that
   fingerprint turns "when did the processing configuration change?" into one
   query instead of an archaeology session. It is a dozen lines and it is the
   single highest-value field in the record.

2. **Reprocess a whole span or none of it.** An operational rule, not code: a
   coordinate series must be internally consistent in its station set, because
   a partially-reprocessed series is not comparable to itself. If new data
   justifies reprocessing, it justifies reprocessing the series.

Where a partial reprocess is genuinely unavoidable, the boundary must be
recorded in the `offsets` catalog **as a processing discontinuity, not an
EQ/CE/VE**. The current type codes have no way to say "this jump is ours" —
which means today the catalog cannot distinguish an artefact from an
earthquake. A `PR` (reprocessing) code would fix that, and is worth adding
before the 2025 run rather than after.
