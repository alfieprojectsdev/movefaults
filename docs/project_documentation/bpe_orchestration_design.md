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

### What is genuinely absent

Searched for and not found: **any catalogue mapping an error message to a cause
or a remedy.** §22.11.2 is titled *"Where to Find Error Messages"*; it lists
which files to open. It does not say what any message means.

| capability | AIUB | us |
|---|---|---|
| error lexical format | specified (`***` / `###`) | scan it |
| PCF logical checks | built, **GUI-only** | headless equivalent |
| error → diagnosis → remedy | **nothing** | the knowledge base |

### Why the expertise is siloed

`neqckdim: DIMENSION TOO SMALL` reads identically to a beginner and an expert.
The manual adds nothing to it. The entire difference is whether the reader has
seen it before — so the diagnostic knowledge was never designed to be
transmissible, and PHIVOLCS, NAMRIA and CAAP each rediscover the same failures
independently.

The knowledge base is therefore not compensating for an oversight. It is
building the artefact AIUB's operating model never needed, and the one a
zero-AI-dependence endgame requires: *"ask someone who has seen it"* is exactly
the dependency being removed.

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
