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

| | `03 Yu` grid search | `08 Bootstrapping` | MCMC |
|---|---|---|---|
| method | deterministic grid | resampling around the grid | Metropolis, proper posterior |
| produced published numbers | **yes** | **yes — wraps the grid search** | **yes — the newest runs** |
| Philippine segments | many | many | Central Luzon, Masbate, Leyte |
| driver | MATLAB | Python → `matlab.engine` | MATLAB |
| uncertainty output | none alone | 95% CI, 1,000 samples | full posterior, 900,000 samples |

> **Correction, 2026-08-26.** An earlier version of this section said the MCMC
> **had never been run on Philippine data** and was therefore not a peer
> option. **That was wrong**, and the recommendation below is weaker for it.
>
> `analysis/07 Dislocation Model/Dislocation Model (Compilation of Results).docx`
> records the method for every modelled Philippine segment, and
> `inversion and monte carlo` at **900,000 samples** appears as the *newest*
> column for **Central Luzon (LUZA), Masbate (SIBI) and Leyte (CEB1)**.
>
> The error was specific: I inspected `06 Ku-en`'s **committed inputs**, found
> them Taiwanese — 39 site codes, zero overlap with our `offsets` catalog — and
> generalised from *what was committed* to *what exists*. A background agent
> reached the same conclusion from the same evidence, which reinforced rather
> than checked it. The answer was in the workbooks, not the repository.
>
> What survives: `06 Ku-en`'s **committed example** is Taiwanese, so that
> particular code path has no Philippine inputs in the tree. What does not
> survive: the claim that the method has not been applied here. See
> [`dislocation_model_results.md`](dislocation_model_results.md).

### Uncertainty is already published, and the bootstrap already wraps the grid

Every published parameter carries an interval — `Locking depth 40 (35-45)`,
`Backslip 27.97 (14.08-29.67)`, 1,000 samples, 95% CI. So "which method gives
uncertainties" is not an open question either; all three do, by different
routes. `bootstrap_v2.py`'s hardcoded `VIGN` reference station appears in the
results table as the reference for the first two Central Luzon runs, tying the
script directly to the published record.

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

Whether it bit the published 900,000-sample runs is checkable and has not been
checked. The fix is one line either way:

```matlab
accept = log(rand) < (DET2-DET1) + (g2-g1);
```

**A biased-but-plausible posterior is worse than an obviously broken one.**
Since the method is already in use rather than merely a candidate, this is not
a precondition for evaluating it — it is a defect in a method that has already
produced published intervals, and worth checking against those runs.

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
5. **The MCMC is already in use and is the methodologically strongest option.**
   It is the newest method applied to Central Luzon, Masbate and Leyte, so this
   is a recommendation about *porting order*, not about scientific merit. The
   `metropolis_log` overflow should be fixed before any further MCMC run,
   whoever does it.

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
