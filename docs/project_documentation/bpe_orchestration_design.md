# BPE orchestration: a design for zero AI dependence

*2026-08-29. Written during the PHREF 2025 year run, against the failure that
run started with.*

## The constraint that shapes everything

Claude Code's role here is **temporary and bounded**: running BSW processing
experiments on the R740 and iterating toward optimal configuration. The endgame
is **mechanical automation with no AI in the loop** — a system PHIVOLCS staff
run, extend and debug without an assistant.

That is not a limitation to work around. It is a hard design constraint, and it
rules out a whole class of otherwise-attractive designs:

- **No LLM at runtime.** Not for log triage, not for error classification, not
  for "explain this failure".
- **Knowledge lives in data files, not in code and not in prose.** A file Cass
  can edit without programming, under version control, that a test can read.
- **Unknown input must halt, not improvise.** An unrecognised error stops the
  run and presents evidence. It does not guess. Guessing is the one thing an
  LLM does that a rule table cannot, and it is precisely what we do not want in
  a pipeline whose failure mode is silent wrong numbers.

The corollary: **every diagnosis reached by an assistant must end up in the
knowledge base as a machine-readable entry**, or it evaporates when the
assistant does. This session produced five such diagnoses (below). They are
currently prose in a session log. That is the gap.

## Part 1 — the run model: a plan and a ledger, not a loop

`scripts/run_*_year.sh` is a loop that derives its state by counting files on
disk. That is why nine hours of total failure looked like slow progress: 0
solutions is indistinguishable from "not finished yet" when solutions-on-disk is
the only state you keep.

Replace it with five phases.

| phase | responsibility | the failure it exists for |
|---|---|---|
| **Plan** | enumerate sessions; derive exclusions **from the data**; compute the resource envelope; select the preflight session | LUZON's exclusion list was nearly inherited into PHREF, silently discarding two usable days |
| **Preflight** | run the **worst-case** session. The plan is not authorised until it passes | DOY 200 was the easiest day of the year and certified a configuration that failed on all 359 |
| **Execute** | N-way parallel; every attempt appended to the ledger before and after | — |
| **Ledger** | append-only record per attempt: session, outcome, **error signature**, duration, station count, config hash | status derived from disk could not distinguish "broken" from "slow" |
| **Verify** | full-population check: every expected session present, station counts and sizes in band | four recorded instances in this project of a sample reported as a population |

### The circuit breaker is the first thing to build

**K consecutive attempts sharing one error signature halts the run.**

It encodes a distinction neither the shell driver nor the service currently
represents: *a per-session failure is data; N identical failures are
configuration.* Today's run failed 24 times over nine hours with one signature.
With K=3 it would have cost twenty minutes.

It is small, it needs no Bernese to test, and it converts the most expensive
failure mode observed so far into a cheap one. Build it first.

### The resource envelope, computed not discovered

Today's failure was `ADDNEQ2 MAXPAR`, a panel value of 1000 against a
requirement above it. **This was predictable without running anything.** The
station count per session is known at staging time; the parameter count is a
function of it; the panel value is readable. A plan-phase check compares the
envelope against the configuration and refuses to start.

Note that `roadmap.md` has listed "ADDNEQ2 MAXPAR" as one of exactly three
parameters needing an override since **March 2026**. The design knew. The
production path had nowhere to put the knowledge, so it was rediscovered at a
cost of nine hours. That is the argument for this whole document.

## Part 2 — diagnostics: two different problems, two different tools

The instinct was "AST-driven troubleshooting". Half right, and the half that is
wrong matters, because it points the effort at the wrong artefact.

### Program *output* is a regular language. Use a lexer, not a parser.

Bernese error output is emitted as one fixed literal, `' *** SR '`, from **262
source files** in `SOURCE/LIB/FOR`, followed by a subroutine name and an
uppercase message, then indented key/value continuation lines:

```
 *** SR neqckdim: DIMENSION TOO SMALL
                  Requested num. of parameters:        1001
                  Maximum size of the array   :        1000
```

There is no recursion and no nesting. An AST implies a context-free grammar; log
output is **regular**, and building a tree for it is over-engineering that will
be brittle against the 262 emitters' formatting quirks.

What it needs is a **scanner producing canonical typed records**:

```
ErrorSignature(
    sr      = "neqckdim",
    kind    = "DIMENSION_TOO_SMALL",
    params  = {"requested": 1001, "maximum": 1000},
)
```

The canonical `(sr, kind)` pair is the deduplication key. It is what makes 24
failures collapse to one fact, and it is what the circuit breaker counts.

**Design note learned today:** parameters are evidence, not conclusions.
`requested=1001` is the *first request that overflowed*, not the requirement.
The signature must carry the raw numbers and the knowledge base must state what
they mean, because the obvious reading is wrong.

### Program *input* has a grammar. That is where parsing earns its keep.

The PCF **is** a graph: `PHREF_DLY.PCF` has **64 steps and 70 edges**
(`WAIT=`, `NEXTJOB=`). Panel `.INP` files are structured key/value with typed
values and widget metadata. These are genuine parse-and-analyse targets, and
static analysis over them catches whole failure classes *before a run starts*:

- **dangling references** — a `WAIT=` or `NEXTJOB=` to a deleted step.
  §24.7 of the session log records four attempts lost to a checker that
  covered `WAIT=` and not `NEXTJOB=`. A real graph walk covers both by
  construction, because it walks *edges*, not one keyword.
- **unreachable steps** and **cycles**
- **resource sizing** — read `MAXPAR` from the panel, compare against the
  envelope from the plan
- **panel/PCF agreement** — every option directory a step names must exist and
  contain the panel that step's program needs

So: **AST and graph analysis on the inputs; scanning and signature matching on
the outputs.** Effort spent building a parser for log files is effort not spent
on the artefact that actually has structure.

## Part 2b — what AIUB already specified, and where they put it

Checked against the 5.2 manual (`DOCU52`) rather than assumed. The answer is not
"AIUB did not think of this". They did, and documented it. The question is
*where they put it*.

### They specify the error format lexically — which validates the scanner choice

§21.7:

> "An error message starts with three star–characters (`***`) ... A warning
> message starts with three hash characters (`###`)."

AIUB define errors by a **three-character prefix**, not by grammar. The scanner
design above is not a workaround for a missing capability; it targets the
contract AIUB wrote down. §24.11.2 repeats it for the `.MSG` files: "Errors are
indicated with a string `***`, warnings with a string `###`."

### They built PCF static analysis — in the GUI

§22.11.1, item 4:

> "Already before actually starting the BPE server the menu program checks
> several things (particularly the Process Control File) for **logical errors
> (e.g., required waiting for a non–existing script etc.)**. A number of checks
> are already performed when editing a PCF file using
> `Menu>BPE>Edit process control file (PCF)`."

That is precisely the dangling-`WAIT` check, implemented by AIUB. It lives in
the **interactive menu program**. The same paragraph states the assumed
operating model outright:

> "Before running any new BPE in non-interactive mode, try the interactive mode
> first. The error messages in both modes are the same but in non-interactive
> mode **one has to know where to find them**. In interactive mode the menu
> program tries to display the error messages automatically."

A headless pipeline — the only kind that can process 359 days — gets none of it.
This is a single-analyst-at-a-workstation model, not an absence of engineering.

### What is absent from the manual — and what is on the website instead

**Correction (same day, after checking the website).** The claim first written
here was "no catalogue mapping an error message to a cause or a remedy exists".
That is true of the **manual** — §22.11.2 is titled *"Where to Find Error
Messages"* and lists which files to open, not what any message means — but it
**overstated the case**, because AIUB publish exactly such a catalogue on the
web.

The [FAQ](https://www.bernese.unibe.ch/faq) carries ~28 entries, **11 of them
specific error messages**, each with a cause and a remedy. It is a small
knowledge base of precisely the kind described in Part 3.

**And today's nine-hour failure is entry 3 of that list.**
`NEQCKDIM: DIMENSION TOO SMALL`, with AIUB's remedy being the one reached
independently at cost: adjust *"Maximum number of parameters in combined NEQ"*
in panel *ADDNEQ2 3.1: Options 1*.

That is the argument of this document in one fact. The knowledge existed, was
public, was correct, and was **not anywhere the pipeline or its operator could
reach at the moment of failure.** A knowledge base that lives on a website is
not in the loop.

What AIUB still do not supply: **a method for choosing the value.** The FAQ says
only that the number "must be adjusted to the size of the normal equations".
The observation that the reported figure is ceiling+1 rather than the
requirement is not there, and remains ours.

### `CHKMAX` shows AIUB solved this problem elsewhere in the same program suite

The FAQ entry for `CHKMAX: Dimension for parameter "MAXzzz" exceeded` describes
a genuinely different design:

> dimensions "are adjusted from the input files and input options", bounded by
> built-in defaults; up to **2×** the built-in limit the run proceeds with a
> warning that it is "an extreme run"; beyond 2× it stops.

So BSW already contains **adaptive dimensioning with a soft and a hard limit**.
GPSEST sizes itself from its input. ADDNEQ2's `MAXPAR` is the inconsistent
case — a hand-set panel value in a suite that elsewhere computes the same thing
automatically. That inconsistency is what cost the nine hours, and it makes the
plan-phase envelope check in Part 1 a re-implementation of a pattern AIUB
already established rather than an invention.

Also worth carrying forward: for an oversized network AIUB's own stated remedy
is **"you may split the network into clusters"** — the same answer GEONET
reached, and directly relevant to PHNAT at 102 stations.

### Our install is unpatched

Release `2024-11-11` publishes **7 fixes**; our install has **none** of them.
Verified rather than assumed: `IONOSP2.f90` carries `IGRF10`–`IGRF13` and not
`IGRF14` (B_33), and `O_RXOWRAP.f90` is dated Oct 2023, predating B_34.

B_34 reduces `RNXGRA` runtime by a factor of 5–6, and `PHREF_DLY` runs RNXGRA
once per session. B_38 touches `TRPSTORE.f90`, which is on the GPSEST/ADDNEQ2
path. Neither is a correctness risk for work already done, but an unpatched
install is a standing item, not a neutral state.

| capability | AIUB | us |
|---|---|---|
| error lexical format | specified (`***` / `###`) | scan it |
| PCF logical checks | built, **GUI-only** | headless equivalent |
| adaptive dimension sizing | built for GPSEST (`CHKMAX`), **not** for ADDNEQ2 `MAXPAR` | envelope check in the plan phase |
| error → diagnosis → remedy | **FAQ: 11 entries, on the website** | machine-readable, in the loop, extensible |

### Why the expertise is still siloed, despite the FAQ

The FAQ exists, is correct, and did not help — because nothing in the pipeline
consults it and the operator has to already suspect the answer to search for it.
11 entries also cannot cover a suite of 262 error-emitting source files; the
five diagnoses this session produced include four that are **not** in the FAQ
(BLQ column alignment, ATL fiducial coverage, ATL trailing-blank terminator, the
seven mandatory `$D/REF54` types).

So the knowledge base is not compensating for an AIUB oversight, and it is not
duplicating the FAQ either. It is doing two things the FAQ structurally cannot:
being **in the loop at the moment of failure**, and being **extensible by the
people who hit the failures**. PHIVOLCS, NAMRIA and CAAP each rediscover the
same problems because there is no mechanism for one of them to write down what
they learned in a form the others' pipelines can execute.

The mailing-list archive (<https://www.bernese.unibe.ch/bswmail.php>) is the
closest existing approximation, and it has the same defect in sharper form: the
knowledge is there, in prose, searchable only by someone who already knows what
to ask.

For the zero-AI endgame this is the whole point. *"Ask someone who has seen it"*
— whether that someone is a colleague, a mailing list, or an assistant — is
exactly the dependency being removed. Seeding the base from the FAQ's 11 entries
is a legitimate start, provided the entries are **re-derived and re-worded**
rather than copied (see the licence note in `external-sources/README.md`).

## Part 3 — the knowledge base is a data file

A table mapping signature → diagnosis → remedy, as data:

```yaml
- sr: neqckdim
  kind: DIMENSION_TOO_SMALL
  diagnosis: >
    ADDNEQ2's parameter array is smaller than the combined normal equation
    needs. `requested` is the FIRST request that overflowed, not the total
    requirement -- it will read as maximum+1 regardless of the true need.
  remedy: >
    Raise MAXPAR in the option directory used by the ADDNEQ2 step. Do not size
    it from `requested`.
  confirm: a session completes and writes a solution
  scope: configuration          # -> trips the circuit breaker
```

`scope: configuration` versus `scope: session` is the field that drives the
breaker: configuration errors are systematic and must halt; session errors are
data-dependent and may be skipped.

Entries this session produced, currently prose in `SESSION_LOG` §25:

| signature | scope | remedy |
|---|---|---|
| `neqckdim / DIMENSION_TOO_SMALL` | configuration | raise `MAXPAR`; do not size from `requested` |
| `GTOCNL / *` on a station present in the BLQ | configuration | BLQ block indented one column left; re-align |
| `GTATML / *` on a fiducial | configuration | station absent from the campaign `.ATL` |
| ATL `ERROR READING` on the last block | configuration | file needs a trailing blank line terminator |
| missing `.ABB` / `.CLU` in `$D/REF54` | configuration | all seven reference types are mandatory |

Five entries is not a knowledge base. It is a start, and the point is that the
mechanism for growing it exists: **every failure diagnosed from here adds a row,
and the row is what survives.**

### Testing without Bernese

Keep a corpus of captured `.PRT` / `.LOG` files, each with its expected
signature and diagnosis. The scanner and the rule table are then unit-testable
with no BSW installation, which is what makes the diagnostic layer maintainable
by someone who is not standing in front of the R740.

## Part 4 — what stays human, permanently

Consistent with `automation_stages.md` and the standing direction that this is
**decision support, not autonomy**: the test is *"if it is wrong, does a human
find out?"*

- **Unknown signature → halt and present.** Never a guess, never a default
  remedy. An unrecognised error is the case the system is least entitled to
  act on.
- **Outlier review at the velocity stage stays human.** Unchanged.
- **Remedies are proposed, not applied.** The system diagnoses and prints the
  change; a person makes it. Auto-applying a config change is how a silent
  wrong number gets into production.

Automate the orchestration hard. Leave the judgement alone.

## Part 4b — where an LLM may and may not sit

Recorded because the question will be reopened, and it should not be reopened
without the safety argument attached. Prompted 2026-09-01 by a proposal to run
`llama.cpp` on the R740's CPU.

### The test any AI component must pass

**The pipeline must behave identically whether the model is present, broken, or
absent.** Anything that fails this is not a candidate, however useful it looks.

### The one slot that passes

Part 1 halts on an unrecognised error signature and presents raw evidence. A
human then diagnoses it from nothing. That human step is the expensive one.

A local model may, **at that halt and only there**, draft a candidate knowledge
base entry — proposed `(sr, kind)`, diagnosis, remedy — for a person to accept,
edit or bin. The committed artefact is still the human-approved YAML row.

It passes the test because it runs only on halt, never in the processing path;
its output is text for review, never a config change or a resume decision; and
removing it changes nothing except how long the human takes.

### Prohibitions, stated so they are not re-litigated

An LLM must never: choose `MAXPAR` or any other resource bound; decide whether
to skip or retry a session; classify an error as benign; write a panel, a PCF
or any campaign file; or gate a run in either direction.

### Why "fallback" is the wrong word

Asked about `*** SR GTOCNL`, a small model will not say it does not know. It
will produce fluent, confident, wrong prose about ocean loading. **That is
strictly worse than silence here**, because an articulate wrong diagnosis is
far more likely to be acted on than a blank screen — and this pipeline's
failure mode is silent wrong numbers.

The actual cause on 2026-08-28 was a BLQ block indented one column left. No
model infers that; every model will cheerfully offer an alternative.

So a local model is **not a fallback for diagnostic reasoning**. It is a
drafting aid at a point where a human is already required. Collapsing that
distinction reintroduces exactly the dependency the zero-AI endgame exists to
remove.

### Where a model is simply the wrong tool

IGSMAIL (23 MB), BSWMAIL (1.8 MB) and both manuals are held locally. The
instinct is retrieval-augmented generation; the correct tool is `grep`.
Searching BSWMAIL for the MAXPAR failure returned a clean and *correct negative*
in milliseconds. A model asked the same question would have produced something.

Use BM25 or ripgrep for lookup. Reserve generation for drafting.

---

## Part 4c — where learned models may and may not sit

Companion to 4b. Same test applies: **the pipeline must behave identically
whether the model is present, broken, or absent.** Prompted 2026-09-01 by the
observation that the R740's AVX-512 VNNI unit is unused.

### "Idle VNNI" is real, and it is not free compute

VNNI is idle even during a full BPE, because Bernese is float64 geodesy and
VNNI is an **int8** dot-product unit — BSW never issues a VNNI instruction.

But VNNI is a unit **inside a core**, not a separate device. It cannot be
reached without occupying the core it sits in. So idleness here does not mean
spare capacity; it means that *if* a core is spent, int8 work extracts more per
cycle than Bernese does. Any deployment needs cpuset pinning, with the BPE
owning a fixed set of cores and the model the remainder — the same reasoning
that keeps bulk transfers off the machine during a run.

The question is therefore not "what runs for free" but **"what is worth cores"**.

### VNNI only pays for waveform-shaped problems

| problem shape | right tool | does VNNI help? |
|---|---|---|
| tabular (predict which station-days resolve badly, from baseline length, obs count, geometry) | gradient-boosted trees | **no** — seconds on one core, quantization meaningless |
| sequence / waveform (1 Hz displacement streams) | small 1-D CNN, int8 | **yes** — this is VNNI's shape |

**Do not pick a model to justify the silicon.** Only waveform data makes VNNI
relevant at all, and that filter removes most candidates immediately.

### The one candidate worth the cores: VADASE artefact discrimination

It is the only sequence-shaped problem in the repository, and it is a real gap
rather than one invented to fit the hardware. `CLAUDE.md` records the third
receiver state — *anomalous spikes* — as **"empirically unconfirmed"**. Current
logic is thresholds plus a leaky integrator plus the `ReceiverMode` state
machine: good engineering, but separating real displacement from receiver
artefact is a classification problem wearing a threshold's clothes.

Task, stated narrowly: **given a window of 1 Hz E/N/U displacement, classify
seismic / receiver-artefact / quiet.** Streaming, CPU-only and latency-bound
across 35+ stations — exactly where int8 throughput matters.

### Two things that would sink it, and one is a blocker today

**Labels — this is the actual blocker.** The event catalogue holds **88
offsets**, and they are *daily* coordinate offsets, not 1 Hz waveform events.
46 MB of real `.rtl` exists (48 files) but is unlabelled. A training set
requires PHIVOLCS' seismic catalogue joined to the VADASE archive by time and
station. **Establish whether that join is possible before writing any model
code.** If it is not, this is unbuildable and should be dropped rather than
approximated.

**Error asymmetry.** A missed earthquake and a false alarm are not equally
costly, and a learned detector that *suppresses* a real event is the worst
outcome this project can produce. Therefore: a model may **raise** a candidate
the thresholds missed; it must never **clear** one the thresholds raised.
Augment, never veto.

That constraint also makes deployment cheap — a detector that can only add
candidates needs no trust to be useful, and its absence changes nothing.

### Ruled out, with reasons

- **Learning anything from the weekly comparison residuals.** 1,979
  station-weeks with **18** positives. There is no supervised problem here; the
  East-dominated signature was found by counting, and counting was correct.
- **Replacing outlier rejection in the velocity pipeline.** The existing
  statistics are auditable and reproduce published output. A learned
  replacement would break comparability for no gain.
- **RINEX QC classification.** teqc and gfzrnx already answer it
  deterministically.

### The rule

**VNNI is a reason to implement on this machine. It is never a reason to choose
a problem.** On current evidence there is one candidate, and it is blocked on
data rather than on compute.

---

## Part 5 — migration: strangle, do not rewrite

`scripts/` has produced 358 complete days (LUZON) and is mid-run on PHREF.
`services/bernese-workflow` has produced none. The service's `backends.py`
correctly invokes `startBPE.pm`; that part is not the problem and should not be
touched.

The service takes over the **decision layer only**, in this order:

1. **Signature scanner + golden corpus.** No Bernese needed. Pure win.
2. **Circuit breaker** over the scanner. Converts the worst observed failure
   mode from nine hours to twenty minutes.
3. **Ledger.** Replaces disk-scanning as the source of run state; makes the
   status reporter honest.
4. **Plan phase** — exclusions derived from data, envelope computed, worst-case
   preflight selected.
5. **PCF/panel static analysis.** Catches dangling references and resource
   mis-sizing before launch.
6. Only then, if ever, move BPE invocation itself.

Each step is independently useful and independently testable, and the pipeline
keeps running on `scripts/` throughout. Nothing in this list requires an AI to
build or to operate, which is the point.

## Measured, and relevant

At `MAXSESS=6` on 24 cores the R740 is **53% idle** (load 10.9, `%idle 53.0`
sustained). `roadmap.md` says RH-006 clustering tuning is "gated on measurement,
not hardware". This is the measurement: there is roughly a factor of two
available in parallelism alone. Worth taking before optimising anything subtler.
