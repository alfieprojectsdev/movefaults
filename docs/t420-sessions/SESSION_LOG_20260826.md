# T420 session log — 2026-08-25/26

**Why this file exists separately from `docs/gps3-sessions/`.** That log is the
R740 session's record — its §24 opens *"For the T420: this is the state of the
R740…"*, so it is written **by** that machine **for** this one. Writing T420
work into it would take over someone else's record. Same reasoning as
`config/bernese/gpsuser52-luzon/PROVENANCE.md`: relay corrections, do not
commit into another session's file.

**Machine:** T420, PHIVOLCS WLAN. **Counterpart:** R740 (gps3), reachable and
reviewing.

---

## 1. What landed

**Twelve PRs merged (#142–#153)**, `main` at `3ade5a6`. Three open at the time
of writing: #154, #155, #156.

Test counts after, measured not carried forward:

| component | tests |
|---|---|
| `pogf-geodetic-suite` | **253** (was 144 at session start) |
| `bernese-workflow` | 228 + 1 skip |
| `services/field-ops` | 59 on `main`; **77** on the #155 branch |
| `drive-archaeologist` | 133 |
| `vadase-rt-monitor` | 51 |

### The `analysis/` Sequence — all ten items

Assessed in #139, implemented across #142–#150.

- **#142** — `msvcrt` removed from four files. Windows-only, imported, never
  used; its only in-body reference was already commented out. Four coseismic
  displacement scripts now run on Linux.
- **#144** — `rinex-completeness`, run **before** staging. The 2025 run lost
  six days to too-few-reference-stations, each discovered by failing a BPE run;
  the datapool could have answered that in seconds. Also fixed `rinex-qc` and
  `igs-downloader`, which could not start after a plain `uv sync` because
  `click` was in an optional extra and `requests` was undeclared.
- **#143** — decimal year settled as `DOY/365.25`.
- **#146** — `crd-to-plots`. The ported library became runnable by a person for
  the first time; three `.bat` network filters became one YAML.
- **#147** — Okada dislocation without MATLAB.
- **#148** — offsets validator wired to the real catalog.
- **#149** — `05`/`07`/`09` archived; the 22 `vel_line` versions mapped.
- **#150** — grid search ported and vectorised; method decision recorded.
- **#151** — dc3dm registered; **finding 5 corrected**.
- **#145, #152** — BERN52 inventory, then its CSV export.
- **#153** — DC3D and `disloc3d`. **The last MATLAB binary in the modelling
  chain is gone.**

---

## 2. Findings worth keeping

### The decimal year was one day off, in merged code

`RUNX_v2.py` uses `DOY/365.25`; the merged `crd_pipeline.py` used
`(DOY-1)/365.25`. Inverting three real `offsets` entries lands on whole DOYs
under the legacy rule, so the catalog is written in it — and
`parse_offsets_file` reads those years verbatim.

**Why the 5e-6 mm/yr verification missed it:** that comparison ran
`analysis.py` against MATLAB using PLOT files the *legacy* script produced.
`crd_pipeline` was never in the loop. **Both halves of the port were verified
against the incumbent and neither against the other.**

**Why the tests missed it:** `abs=0.01`, nearly four times the 0.002738
difference. A test too loose to distinguish two candidate answers is not a test
of which one you have.

### `i=i++` — undefined behaviour that only worked by luck

In `disloc.c`. gcc leaves `i` unchanged: infinite loop. The `.mexw64` everyone
depended on worked **only because MSVC happened to increment**. That binary was
one compiler away from hanging and nothing recorded it. The regression test
passes *three* dislocations, because with one the loop exits on the bound and
the bug stays invisible.

### The grid search was never expensive

The Green's function depends on geometry alone; `block_motion` enters as a
shift applied to the **data**. The innermost 41 iterations were recomputing a
constant. **560,511 dislocation calls → 13,671**, before any parallelism. A
property of the loop order, not of the method.

### Finding 5 of my own assessment was wrong

I claimed the MCMC had only ever run on Taiwanese data, from `06 Ku-en`'s
committed inputs — 39 site codes, zero overlap with our catalog. A background
agent reached the same conclusion from the same evidence, which **reinforced
the reading rather than testing it**.

`analysis/07 Dislocation Model/` settles it: `inversion and monte carlo` at
**900,000 samples** is the newest column for Central Luzon, Masbate and Leyte.
**Two independent passes over the repository could not find an answer that was
never in the repository.**

### DC3D verified against an independent port

`disloc3d.mexw64` cannot run here — that is the premise — so there was no
reference output. Instead: DC3D at `z=0` must reproduce the 1985 surface
solution, and `disloc.c` is a different author's C from a different original.
**1.6e-15 across five strikes, three dips and tensile opening.** Plus the
analytic arctan, to 0.04%.

### A convention that fails by returning zeros

Okada's `AL1/AL2` are **positive distances**, not signed offsets. Passing
`(-L/2, L/2)` makes all four corner terms identical; they cancel to **exactly
zero** — a plausible "no deformation" answer with nothing raised. Cost an hour.
`AW` reversed gives the surface-breaking **complement**, which is a different
physical problem rather than a broken one, and also looks like a plausible
arctan. Both pinned.

### The licence question was narrower than the package's licence

`dc3omp.f` is EPL 1.0 because Bradley added a fix — but that fix is **only
`MQ1`/`MQ2`, eighty lines**. The kernel is Okada's and carries no copyleft.
Splitting by *authorship* and making the split a **file boundary** turned "we
cannot take this" into "take the kernel freely, isolate the rest".

---

## 3. Process

### The inter-session loop worked, and it worked for one reason

PR comments as the channel (SOP, this session). R740 reviewed #138–#141 and
#150; every finding worth having came from **asymmetric access, not a second
opinion**:

- R740 found the §24.1 block-table fault **from run logs I could not see**, and
  the `grep 'import msvcrt'` trap — it searched the obvious way, got zero hits,
  and would have been entitled to call the finding wrong.
- I found the PDL-1.0 licence problem by going **outside the document** to
  GSI's actual terms.

Neither would have caught the other's. Same model on both machines, so
agreement between us is weak evidence; **disagreement and new evidence are the
signal.**

### Two git hazards, recorded in #154

`--delete-branch` on a **stack base auto-closes** the dependent PR, and a
closed PR can be neither reopened nor retargeted until the branch exists again.
Recovery meant pushing the merge commit back under the deleted name first.

`MERGEABLE/UNSTABLE` shortly after a push usually means a check is **still
running**. My first version of that entry said "ignore it" — asserted from
`gh pr checks` showing three passes without checking what was outstanding.
Every context was `success`; the state had simply not settled. **"Ignore it"
would have taught the next session to merge over a genuinely failing check.**
Recorded with its correction rather than quietly replaced.

### Mistakes caught before review

- **CRLF→LF on four `analysis/` files**, turning a 4-line change into 2,246.
  Fifth occurrence in this project. Redone at byte level.
- **`git add -A analysis/`** swept three untracked paths into the index; later
  `git add archive/` did the same with a planner directory. Explicit paths now.
- **A test I wrote was wrong, not the code.** Synthetic data built from the
  infinite-dislocation form against a finite-width fault recovered
  `slip = -94.46` where truth was `30`. `-94.46 ≈ -30π` looked like a damning
  sign-and-scale bug. The port was right.

---

## 4. Also this session

**FO-001 / issue #118** — backend for in-app station creation (#155). The
report called the station list stale; it is worse. `seed_network_inventory.py`
says campaign occupations "must be seeded from another source" and no such
source exists, so **campaign sites have never had an ingest path**. Refreshing
the export more often would have fixed nothing.

**VADASE vendor-neutrality** (#156). NTRIP and NMEA are transport and payload,
not alternatives. The parser accepts only `$GNLVM`/`$GNLDM`, which are **Leica
proprietary** — and the deeper reason a Trimble parser would not help is that
**VADASE is an algorithm Leica runs on board**. The service consumes
displacement it did not compute. Vendor-neutrality is an algorithm we do not
have, not a parser nobody wrote.

Measured while investigating: `stations.yml` holds **4** stations, not the 35+
`CLAUDE.md` claims twice, all on `192.168.1.10x` — a placeholder subnet. No
NTRIP credentials. The ingestor is not a compose service. **Nothing alerts.**

---

## 5. State at the time of writing

| | |
|---|---|
| `main` | `3ade5a6`, local synced |
| Open PRs | #154, #155, #156 — none merged |
| MATLAB in modelling | **none** — both `.mexw64` replaced and cross-verified |
| Uncommitted | `uv.lock`, `packages/CORS-dashboard` (both pre-existing) |

**Open questions belonging to people, not code:**

1. **Who reconciles station proposals, and how often?** (#118 / #155.) The
   endpoints exist; a reconcile step nobody runs is the same as not having one.
2. **Is real-time displacement Leica-only by decision?** (#156.) If not, it is
   a research deliverable, not a parser enhancement.
3. **Which inversion method to port** was answered by
   `dislocation_model_results.md`; the draft questions at
   `temp/DRAFT-cass-dane-inversion-method.md` are now largely moot and remain
   **unsent**.
