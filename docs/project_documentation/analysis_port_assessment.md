# `analysis/` — what to port, what to fix, what to delete

**Assessed 2026-08-25** against every file under `analysis/` (229 files, 1.1 GB),
read alongside `roadmap.md` and `automation_stages.md`.

**Verdict in one line:** the roadmap frames this as *"port legacy MATLAB/Python
into `pogf-geodetic-suite`"*, and that framing is wrong in a way that has kept
the work stalled. Three of the seven things blocking the pipeline are **one-line
fixes or config, not ports** — and the single largest scientific unlock is a C
file nobody has noticed sitting in `08 Bootstrapping/`.

---

## What is actually in there

| kind | count | note |
|---|---|---|
| MATLAB `.m` | 55 | 25 are `vel_line*` — **22 distinct versions of one script** |
| GMT `.gmt` | 32 | mostly data, not code |
| Windows `.bat` | 25 | network filters, teqc drivers, GMT plot drivers |
| Python `.py` | 23 | **18 contain `input()` — 75 prompts total** |
| Windows binaries | 8 | 4 `.exe`, 4 `.mexw64` — no source for 3 of the 4 MEX |

The directory is a **working scientist's desktop**, snapshotted: versions kept
by filename, data beside code, `.exe`s beside their sources, three independent
attacks on the same inverse problem in three folders that do not reference each
other. Treating it as a codebase to port wholesale is the mistake. Most of it
is provenance to preserve, a little of it is production, and a small part is
blocking.

---

## Seven findings, evidence first

*Numbered by how they were found, **not** by priority — see [Sequence](#sequence)
for the order to act in. Finding 6 is live in merged code and comes before
finding 1 there, despite the numbering. (A careful reader took the numbering as
an ordering on first pass, so it is worth saying.)*

### 1. `disloc.c` is present, and it is the whole MATLAB lock-in

`analysis/08 Bootstrapping/disloc.c` — *"Computes surface displacements for
dislocations in an elastic half-space. Based on code by Y. Okada. C version and
mex interface by P. Cervelli."*

Four functions. `Okada()`, `Disloc()`, `GoodModel()` are **pure C with no
MATLAB dependency**. Only `mexFunction()` at line 259 and `#include "mex.h"`
bind it to MATLAB.

This matters more than anything else in this document. Every dislocation model
in `analysis/` — `03 Yu`, `08 Bootstrapping`, and the grid search both depend on
— routes through `disloc.mexw64`, a **Windows-only compiled binary** that
cannot run on the R740 and cannot be rebuilt without MATLAB. That single file
is why fault-parameter modelling still happens on somebody's Windows desktop.

**The source is right there.** Strip `mexFunction`, compile as a shared
library, wrap with `ctypes` or `cffi` — half a day — and the modelling half of
the project moves to Linux with a bit-comparable reference implementation to
verify against. That is the highest-value item on this list and it is not in
either roadmap.

*`disloc3d.mexw64`* (used by `06 Ku-en`) has **no** source in the tree and
neither zip carries one — but it is far less of an unknown than that implies.
Pinned from the call sites in `2d_model/make_G.m`:

```matlab
[U,D,S,flag] = disloc3d(m, x, 1, .25);          % mu = 1, nu = 0.25, always
fault(k,:)   = [5000, seg(1:2), abs(dip)+180, str, seg(4), 0];
m            = [fault(i,:), ss, ds, opening]';  % 10 x 1
```

That is the **Cervelli/Stanford-CDFM `disloc3d` convention** exactly —
`m = [length; width; depth; dip; strike; east; north; strike-slip; dip-slip;
opening]`, a MATLAB wrapper around Okada (1992) `DC3D`. Same author as the
`disloc.c` already sitting in `08 Bootstrapping/`, which is the strongest
available evidence that the matching `disloc3d.c` is obtainable from the same
public source rather than needing reconstruction. `DC3D` itself is published
Fortran (NIED), so a verified reference exists either way.

Three properties narrow the replacement further:

- **Only `U` is ever used.** `D` (displacement gradient) and `S` (stress) are
  computed and discarded at all twelve call sites. A replacement needs the
  displacement half of Okada 1992 and nothing else.
- **`mu = 1`, `nu = 0.25` are hardcoded** at every call — no elastic parameter
  search to support.
- **`length = 5000` is constant**, which is how a 3D engine is being used to
  model a 2D (plane-strain) problem: a fault long enough that along-strike
  effects vanish.

So this is a bounded job — match one signature, one output, fixed elastic
constants — verified against stored `disloc3d.mexw64` output on a known case.
Not the open-ended port the absence of source suggests.

### 2. `msvcrt` is imported and never used — it blocks four scripts from Linux

```
04 Displacement/RUN_ENU_v4.py                        import numpy, os, glob, msvcrt, time
04 Displacement/RUN_ENU_v5_consecutive2EQs_campaign.py
04 Displacement/RUN_ENU_v6_consecutive2EQs_continuous.py
02 Time Series/Outliers-input name.py                import numpy, os, glob, msvcrt
```

**Verifying this has a trap in it.** The import is combined, so the obvious
search finds nothing:

```
grep -rn 'import msvcrt' analysis/  ->  0 hits
grep -rln 'msvcrt'       analysis/  ->  4 files
```

Search the **bare token**. Confirmed independently from the R740 side, which hit
the zero-hit result first and would have concluded the finding was wrong.

`msvcrt` is a Windows-only stdlib module, so the import alone raises
`ModuleNotFoundError` on Linux. Its only appearance in the *body* of any of
these files is **commented out**:

```python
#    if msvcrt.getch() == b'\r':
```

Removing the word from the import line makes all four byte-compile cleanly on
Linux — verified, not assumed. The coseismic displacement tooling — the thing
that produces the numbers on slide 8 of every earthquake briefing — is one
word away from running on the R740.

### 3. The antenna-height constants are right by luck, and the gap is 23 mm

`campaign_v*.py` computes RINEX height from slant height with **one** constant
pair for **all** antennas:

```python
pe1 = math.sqrt(float(pe)*float(pe) - 0.16981*0.16981) - 0.04435
```

Against the per-model constants (`antenna_constants.md`, and implemented
correctly in the field-ops PWA):

| model | error of the shared constants |
|---|---|
| TRM41249.00 | −0.05 mm |
| TRM57971-00 | −0.001 mm |
| TRM115000 | −0.01 mm |
| **TRM22020.00+gp** | **+21 to +28 mm** |

The three antennas the script *offers* share C ≈ 0.1698 and VO ≈ 0.0443, so the
shortcut is harmless — **for those three**. TRM22020.00+gp has C = 0.2334 and
VO = 0.0591, and the script does not offer it at all, so an operator holding
one must pick a wrong option from the menu. A 23 mm vertical error at a
campaign site is enormous against the millimetre precision everything
downstream assumes.

**What is verified and what is not.** The arithmetic above is computed, not
estimated — the constants come from `antenna_constants.md` and the field-ops
PWA's own test file. What is **not** verified, and cannot be from this
repository, is whether a TRM22020.00+gp was ever actually deployed on a
campaign. That is a field-records question, and the R740 review correctly
declined to confirm it from the tree.

So the finding is: *the script cannot express this antenna, and if one was ever
used the error is 21-28 mm.* Whether one was used is the open half. The script
cannot prevent it, cannot record which antenna was actually used beyond the
three-way menu, and nobody would see it afterwards. **The PWA already has this right** — which
is the concrete argument for `automation_stages.md`'s claim that the digital
logsheet is the stage-1 unlock. It is not convenience, it is correctness.

### 4. The grid search is 560,511 forward models, run single-threaded

`03 Yu Interseismic Dislocation/makeG_2ds_v3.m`:

```matlab
for D=0:1:20           %  21
for W=0:1:30           %  31
for dip1=70:1:90       %  21
for block_motion=0:1:40  % 41
```

**21 × 31 × 21 × 41 = 560,511** forward models per inversion, each a `disloc`
call, in serial MATLAB on a desktop. `08 Bootstrapping` then wraps that in
N resampling iterations, driving MATLAB from Python through
`matlab.engine` — a licensed product, over a hardcoded Windows path:

```python
sys.path.append("C:\\Python\\Python38\\Lib\\site-packages\\matlabengineforpython-...")
```

This is embarrassingly parallel and trivially vectorisable in NumPy. The R740
has 24 cores and is idle. **Fault-parameter uncertainty is currently gated by
a single-threaded loop on a Windows laptop** — that is the "actual research"
bottleneck, and it dissolves once finding 1 is done.

### 5. Three independent uncertainty methods exist, and none references the others

| folder | method | status |
|---|---|---|
| `03 Yu` | deterministic grid search | the production path |
| `08 Bootstrapping` | resampling around the grid search | has `bootstrap_utils.py` + unit tests already |
| `06 Ku-en/2d_model_mcmc` | **Metropolis MCMC** (`montecarlo_inversion.m`, `get_log_prob.m`, `metropolis_log.m`) | apparently unused |

The MCMC variant is the methodologically strongest of the three — it yields a
posterior rather than a grid minimum plus a resampling proxy — and it appears
nowhere in either roadmap. It came from Dr. Kuo-En Ching (NCKU, Taiwan), who is
acknowledged in the 2024 report for "providing the programs and scripts".

**Deciding between these three is a scientific decision, not an engineering
one, and it should be made before any of them is ported.** Porting the grid
search because it is the incumbent would spend the effort on the weakest
method.

### 6. The ported decimal year is one day off the legacy one

This one is live, in code that is already merged.

```python
# analysis/02 Time Series/RUNX_v2.py  (legacy, produced every PLOT file in use)
day  = int(allyear[2:5])/365.25          #  year + DOY/365.25
date = int(year)+day

# packages/.../timeseries/crd_pipeline.py  (the port)
return year + (doy - 1) / 365.25         #  year + (DOY-1)/365.25
```

**Exactly one day apart, at every DOY** — 0.002738 yr, constant. Inverting three
real entries from the production `offsets` catalog against the legacy
convention gives whole DOYs, which is the tell:

| catalog entry | DOY under legacy | DOY under the port |
|---|---|---|
| `ALBU 2025.7474 EQ` | 272.99 → **273** | 273.99 |
| `ALBU 2017.5147 EQ` | 187.99 → **188** | 188.99 |
| `AROY 2023.1314 EQ` | 47.99 → **48** | 48.99 |

The catalog was written in the legacy convention. `parse_offsets_file` reads
those decimal years **verbatim** and `estimate_velocity` splits segments on
them, so a series built by `crd_pipeline` puts every offset one day early
relative to its own epochs.

**Why the 5e-6 mm/yr verification did not catch it:** that comparison ran
`analysis.py` against MATLAB using **PLOT files the legacy script had already
produced**. `crd_pipeline` was never in the loop. The two halves of the port
were each verified against the incumbent and never against each other.

Usually one day inside a multi-year segment is noise. It is not noise in
exactly the cases already known to be fragile — the short-final-interval
defects in `velocity_outlier_policy_delta.md`, where ALBU's final segment is
**seven days** and one day is 14% of it, and the epoch that moves across the
break is the coseismic one.

**Neither convention is wrong in itself** — `(DOY-1)/365.25` is arguably the
better definition, putting DOY 1 at year.0000. What is wrong is having both.
Pick one, state it in both modules, and if the port's convention wins, re-base
the `offsets` catalog in the same commit. A silent one-day shift applied to a
hand-maintained catalog is precisely how the last catalog corruption happened.

### 7. The MCMC's Metropolis ratio can overflow to `NaN` and silently reject

`06 Ku-en/2d_model_mcmc/metropolis_log.m`:

```matlab
rat = exp(DET2-DET1) * exp(g2-g1);
```

Two exponentials multiplied, where the whole point of working in logs is to add
the exponents and take **one**. Under IEEE arithmetic (MATLAB included),
`exp(x)` overflows to `Inf` above ~710 and underflows to `0` below ~-745, so
`Inf * 0 = NaN`:

| ΔDET | Δlogrho | `exp*exp` | `exp(sum)` | effect |
|---|---|---|---|---|
| +750 | −750 | **NaN** | 1 | should always accept — **rejected** |
| −750 | +750 | **NaN** | 1 | should always accept — **rejected** |
| +800 | −799 | **NaN** | 2.72 | should always accept — **rejected** |
| +400 | −401 | 0.368 | 0.368 | fine |

With `rat = NaN`, `rat>1` is false and `r<rat` is false, so `accept=0`. The
chain **silently rejects a move it should always have taken**, and nothing
warns. Each term only has to exceed ~710 on its own — the *sum* can be tiny.
`logrho = -0.5·χ²`, so with enough data points that threshold is reachable,
especially early in a chain before it has found the mode.

Whether it bites on PHIVOLCS-scale data depends on the data volume and
weighting, which cannot be checked without the inputs. **The fix is the same
either way and is one line** — `rat = exp((DET2-DET1) + (g2-g1))`, or better,
compare in log space and never exponentiate at all:

```matlab
accept = log(rand) < (DET2-DET1) + (g2-g1);
```

Flagging it here because if the MCMC is chosen in finding 5, this is inherited
along with it, and a biased-but-plausible posterior is worse than an obviously
broken one.

**Related, and it is a cost not a bug:** `forward_slip.m` calls `make_geometry`
then `make_G` on **every likelihood evaluation**, and `get_log_prob` calls
`forward_slip` inside a loop of `numsamples × num_fault_params`. Since the
fault geometry is part of the sampled state, G genuinely must be rebuilt — but
it means the MCMC's cost, like the grid search's, is dominated by dislocation
calls. Both methods land on the same bottleneck, and finding 1 unblocks both.

---

## Port ledger

| dir | verdict | why |
|---|---|---|
| `01 RINEX conversion` | **do not port yet** | `automation_stages.md` is right — the bottleneck is field metadata, not script execution. Fix the antenna-constant gap (#3) at the *PWA* end, which is already done, and let the logsheet obsolete these. |
| `02 Time Series` | **finish the port** | `crd_pipeline.py` covers 01–03. **00 (network filter) and 04 (PLOT files) are not ported, and there is no CLI.** See below. |
| `03 Yu 2D Dislocation` | **port after the method decision** | blocked on #1; do not port the grid search until #5 is settled |
| `04 Displacement` | **one-line fix, then use** | #2. Coseismic ENU + regression; no MATLAB anywhere in it |
| `05 Single Frequency` | **archive** | 4 `.bat` totalling 750 bytes wrapping a frozen `teqc.exe`; u-blox single-frequency side experiment |
| `06 Ku-en` | **evaluate, do not port blind** | contains the MCMC (#5) and `disloc3d` with no source |
| `07 NMEA samples` | **archive as test fixtures** | 8 sample series + 2 scripts already duplicated from `02` — these are *data*, and good VADASE regression fixtures |
| `08 Bootstrapping` | **port — highest value** | #1 and #4 both live here; already partly refactored with tests |
| `09 Kinematic` | **defer** | one driver + a 3 MB spreadsheet; no downstream consumer |
| `10 RINEX Checker` | **port to a CLI — do it early** | see below; it is small and it prevents failures we are currently paying for |

### `02 Time Series` — what "not ported" actually means

`crd_pipeline.crd_directory_to_enu()` returns `StationEpoch` objects in memory.
It does **not**:

- filter the network — that is `00_CRD_{PIVS,NP,NAMRIA}.bat`, three `.bat`
  files whose entire content is one `findstr /V` with **~300 IGS station codes
  inlined into a single line**. This is a config file wearing a script
  costume. Three variants = three networks. It should be one YAML list and one
  `--network` flag.
- write PLOT files — `04_PLOTFILES`, the per-site series that
  `analysis.estimate_velocity` and `make_velocity_field.py` both consume.
- expose a CLI. There is no console entry point for any of it; `pyproject.toml`
  declares `rinex-qc`, `igs-downloader`, `velocity-reviewer`, but nothing for
  the CRD→ENU→PLOT path.

So the ported library **cannot currently be run end-to-end by a person**, which
is why `RUNX_v2.py` is still the thing that gets used. That is the gap, and it
is a day of work, not a port.

Worth reading `RUNX_v2.py` before replacing it, because it encodes decisions:

- **decimal year is `DOY/365.25`**, always, ignoring leap years. The `offsets`
  catalog uses the same convention, so the port must match it *exactly* or
  every offset lands on the wrong day. `crd_pipeline.session_to_decimal_year`
  needs checking against this.
- the two-digit year window is `00–80 → 20xx`, else `19xx` — fine until 2081.
- it **appends** to `XYZ`, `ENU` and per-site files with no truncation, so a
  second run silently doubles every series. Non-idempotent by construction.
- `transform()` re-globs and re-reads every CRD file inside a loop over every
  CRD file — O(n²) file I/O.

### `10 RINEX Checker` — small, and it pays for itself immediately

Kurt's completeness checker lists days with and without RINEX per station.
It is ~8 KB of Python, blocked only by `input()` and a "double-click the .py
file" workflow.

**Why it is worth doing early:** the 2025 national run lost **8 of 365 days**,
and 6 of those were *"fewer than three reference stations — below the minimum
for a Helmert transformation"* (`SESSION_LOG_20260729_storage.md` §24.1). Those
days were discovered **by failing a BPE run**, at ~1.9 min/day of R740 time
plus the analyst attention to work out why.

A completeness scan over the datapool answers that question **before staging**,
in seconds, for the whole year. Same code, moved one step earlier in the
pipeline. That is not a port — it is a re-siting.

---

## Where the roadmaps need amending

**`roadmap.md` Deliverable 2.4** reads *"Port legacy MATLAB/Python scripts from
`analysis/`… Remaining: port `RUNX_v2.py` → Python library; port
`vel_line_v8.m` → Python; dislocation models."*

Two of those three are done or misstated:

- `vel_line_v8.m` **is ported and verified** — `timeseries/analysis.py`, 161 of
  165 components agreeing to 5e-6 mm/yr. `automation_stages.md` records this;
  `roadmap.md` does not.
- `RUNX_v2.py` is **two-thirds ported**; what remains is the network filter,
  the PLOT writer, and a CLI. Listing it as "port `RUNX_v2.py`" hides that the
  remainder is plumbing, which is why it keeps losing to more interesting work.
- "dislocation models" is one line covering the **largest** item, and it does
  not mention that `disloc.c` makes it tractable or that three competing
  methods must first be chosen between.

**Also worth fixing:** `automation_stages.md` contains **two `## Stage 3`
sections** (lines 206 and 393) with overlapping but non-identical content. One
is stale. A document whose purpose is to keep the project honest about its own
status should not have two answers to the same question.

**Missing from both roadmaps entirely:**

1. Preflight validation before staging (the `10 RINEX Checker` re-siting).
2. `disloc.c` as the unlock for Linux-native modelling.
3. The MCMC variant's existence, and the need to choose a method.
4. Anything about `analysis/` provenance — 22 versions of `vel_line`, and no
   record of which produced which published figure.

---

## Sequence

Ordered by value-per-effort, not by tier.

**Now — cheap, unblocking, each independently useful**

1. **Delete `msvcrt` from four import lines.** Minutes. Unblocks all coseismic
   displacement tooling on Linux. Verify each still runs against a known case.
2. **`10 RINEX Checker` → `pogf-geodetic-suite` CLI**, run over the datapool
   *before* `stage_luzon_campaign.sh`. Half a day. Pays for itself on the next
   year-run.
3. **Settle the decimal-year convention (#6) before anything writes a PLOT
   file.** One line in `crd_pipeline.py` either way, but it must be decided
   deliberately and the `offsets` catalog re-based in the same commit if the
   port's convention wins. Doing this *after* generating series is how a
   one-day shift gets baked into published velocities.
4. **Finish the `02` port**: the IGS exclusion list → one YAML per network, a
   PLOT-file writer, and one console entry point covering CRD → ENU → PLOTS.
   A day. This is what lets a person actually use what is already built.

**Next — the scientific unlock**

5. **Build `disloc.c` as a Python extension.** Half a day plus verification
   against `disloc.mexw64` output on a stored case. Everything else in
   modelling is downstream of this.
6. **Decide the inversion method** — grid search, bootstrap, or MCMC — as a
   scientific decision, written down with reasons. Do not skip this by
   defaulting to the incumbent.
7. **Port the chosen method, vectorised.** The 560,511-model grid becomes a
   NumPy array operation; bootstrap iterations become a process pool on the
   R740's 24 cores.

**Then — hygiene that protects the above**

8. **Sort and validate `offsets` in CI.** `offsets_catalog.py` exists and
   reports; nothing runs it. An unsorted catalog has already caused real
   damage (`velocity_outlier_policy_delta.md`).
9. **Archive `05`, `07`, `09` deliberately** — moved to `archive/` with a note
   saying what each was and why it stopped, not deleted and not left to imply
   they are live.
10. **Record which `vel_line` version produced which published figure**, while
   anyone still remembers. 22 versions, one in production, no map between them
   and the papers.

**Not recommended**

- **Porting `01 RINEX conversion`.** Downstream of the logsheet; porting it now
  automates the wrong half and adds a transcription step that can fail
  silently.
- **cron for any of this.** Every stage here is either analyst-initiated or
  already driven by `run_luzon_year.sh`. The one thing that genuinely wants
  scheduling — run status — already has it (`luzon_status.sh`). Adding cron to
  a scientific pipeline whose failure mode is *silent wrong numbers* buys
  nothing and removes the person who would notice.

---

## The through-line

Every finding above is the same shape as the ones in
`SESSION_LOG_20260729_storage.md` §24.7: **a check that looks in the wrong
place**. The antenna menu that cannot express the antenna in your hand. The
`msvcrt` import that never runs. The completeness scan that exists but runs
after the failure instead of before it. The velocity script ported and verified
while the plumbing that feeds it was left as a `.bat`.

The work is not mostly porting. It is mostly moving things one step earlier,
deleting things that were never used, and compiling one C file.
