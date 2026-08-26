# Which inversion method — a decision record awaiting sign-off

**Status: RECOMMENDATION, NOT A DECISION.** The choice is PHIVOLCS'. This
records the evidence, the recommendation, and what changed once the three
candidates were actually inspected rather than compared on description.

Sequence item 6 of [`analysis_port_assessment.md`](analysis_port_assessment.md).
Item 7 — porting the chosen method — depends on this.

---

## The three candidates, and how the question changed

`analysis_port_assessment.md` finding 5 presented three peer methods. **They are
not peers.** Inspecting the inputs changed the question:

| | `03 Yu` grid search | `08 Bootstrapping` | `06 Ku-en` MCMC |
|---|---|---|---|
| method | deterministic grid | resampling around the grid | Metropolis, proper posterior |
| produced published numbers | **yes** | unclear — see Q2 | **no** |
| Philippine inputs exist | **yes** | **yes** | **no — Taiwan only** |
| driver | MATLAB | Python → `matlab.engine` | MATLAB |
| uncertainty output | none | parameter spread | full posterior |

### The MCMC has never been run on Philippine data

Its committed inputs are Taiwanese. **39 distinct site codes** across
`vh_cross_A.gmt`, `vp_cross_A.gmt` and `vv_cross_A.gmt` — `G152`, `GS81`,
`GE97`, `J102`, `KHLZ`, `LIAN`, `MITO`, `AKND` — and **zero overlap** with the
station codes in our own `offsets` catalog. The same files sit in the
non-MCMC `2d_model/` too, so **neither Ku-en variant has been exercised on our
data**; both are Kuo-En Ching's Taiwan worked example.

That matters because choosing the MCMC on methodological merit means also
building a Philippine input pipeline that does not exist. It is a larger job
than porting either of the other two, not a smaller one.

### And it carries a defect that must be fixed before it is weighed

`metropolis_log.m` computes the acceptance ratio as **two exponentials
multiplied** rather than summing the exponents:

```matlab
rat = exp(DET2-DET1) * exp(g2-g1);
```

Past ~710 each term overflows independently, so `Inf * 0 = NaN`; both `rat>1`
and `r<rat` are then false and the chain **silently rejects a move it should
always have taken**. Each term only has to exceed the threshold *on its own* —
the sum can be tiny. `logrho = -0.5·χ²`, so with enough data points that is
reachable, especially before the chain finds the mode.

Whether it bites at PHIVOLCS data scale cannot be checked without the inputs —
which is the previous point again. The fix is one line either way:

```matlab
accept = log(rand) < (DET2-DET1) + (g2-g1);
```

**A biased-but-plausible posterior is worse than an obviously broken one**, so
this should be fixed before the MCMC is evaluated, not after.

---

## Recommendation

**Port the grid search now; keep the bootstrap as the uncertainty layer; treat
the MCMC as a separate, later evaluation.**

Reasons, in order of weight:

1. **The grid search produced the published numbers.** Whatever else is
   adopted, this one has to be reproducible or the existing results become
   unverifiable. That argument is independent of which method is best.
2. **It is the only method with Philippine inputs and no known defect.**
3. **Its cost objection has evaporated.** The 560,511-model figure was the main
   argument against it. Most of that was recomputation — see below.
4. **The bootstrap already wraps it** and is already partly refactored, with
   `bootstrap_utils.py` and unit tests. It is the cheapest route to uncertainty
   estimates.
5. **The MCMC remains the methodologically strongest option** and is worth
   evaluating on its merits — after the `metropolis_log` fix and after someone
   builds Philippine inputs for it. Recording it here so it is not quietly
   dropped.

### The cost objection was mostly an artefact

The Green's function depends on geometry — depth, width, dip — and **not on
block motion**, which enters only as a shift applied to the data. So the
innermost 41 iterations were recomputing a constant.

```
560,511 models   ->   13,671 dislocation calls   (41x)
```

The remaining 13,671 are independent and parallelise across the R740's 24
cores. Implemented in `pogf_geodetic_suite.modeling.inversion`; the reduction
is asserted by test rather than claimed.

So "the grid search is too expensive" was never a property of the method. It
was a property of the loop order.

---

## Questions only PHIVOLCS can answer

Ordered by how much they change the recommendation.

1. **Which method produced the numbers in the 2024 GPS Motions report?** If the
   bootstrap did, it is the incumbent rather than the grid search, and its
   `matlab.engine` dependency becomes the priority.
2. **Was the bootstrap meant to replace the grid search, or to wrap it?**
   `bootstrap_v2.py` drives `makeG_2ds_v3_loop.m`, which reads as wrapping —
   but the intent matters more than the call graph.
3. **Does anything downstream consume the uncertainty at all?** If published
   fault parameters carry no error bars, the whole comparison is premature and
   the grid search alone is sufficient.
4. **Is the MCMC's Taiwan-only history correct**, or do Philippine inputs exist
   somewhere outside this repository?

A drafted message asking these sits at
`temp/DRAFT-cass-dane-inversion-method.md`. **It has not been sent.**

---

## What is already implemented against this

`modeling/inversion.py` ports the grid search with the restructuring above. It
is written so the misfit evaluation is reusable by whichever method wins, and
it commits to nothing this document has not argued for.

`modeling/disloc.py` removed the MATLAB dependency underneath **all three**
methods, so that part of the work is not contingent on this decision.

**Not implemented, pending the answer:** the bootstrap's process-pool
parallelism, and any MCMC port.
