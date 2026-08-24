# GEO-002 settled: the ambiguity panels' mapping function is a dead field

**Measured 2026-08-24.** Verdict: **the `WET_GMF` / `WET_NIELL` split does not
affect the solution at all.** It is cosmetic. The 2025 national run is not
blocked on it.

Regenerate: `scripts/run_gmf_comparison.sh --setup --run --compare`

## The question

Six GPSEST panels carried three mapping functions. The float and final solves
used one thing; the three ambiguity-resolution steps used another:

| panel | | mapping function (live 5.4 tree) |
|---|---|---|
| R2S_AMB | Melbourne-Wübbena | `COSZ` — correct for MW, never at issue |
| R2S_EDT | float | `WET_GMF3` |
| R2S_FIN | final | `WET_GMF3` |
| R2S_QIF / L53 / L12 | ambiguity resolution | **`WET_NIELL`** |

GEO-002 called the split "unintentional" and left it open. Before committing a
year of national data, it was worth knowing whether it mattered.

## What was done

A variant configuration set the three ambiguity panels to `WET_GMF3`, matching
the final panel, and reprocessed 2025 DOY 121 against **identical inputs** —
the campaign was copied, not re-staged, so the observations, orbits, ERP and
station files are the same bytes.

Isolation: variant OPT dirs, variant PCF, variant driver, variant campaign
(`LZGMF`), variant `V_RESULT`. The baseline 30 days were never written to.

**Control that makes the result meaningful:** the run log carries 176
references to the variant panel directories, and those directories carry
`WET_GMF3`. The experiment ran what it claims to have run — without this check,
"identical" is equally consistent with the change never having taken effect.

## Result: bit-identical

The full SINEX diff is **four lines, all run timestamps**:

```
< %=SNX 2.01 XYZ 26:225:32514 IGS 25:121:00000 ...      (13 Aug, baseline)
> %=SNX 2.01 XYZ 26:236:56904 IGS 25:121:00000 ...      (24 Aug, variant)
< *RNX2SNX_20251210: ... 13-AUG-26 09:01
> *RNX2SNX_20251210: ... 24-AUG-26 15:48
```

Every coordinate, every covariance, every station: identical.

Stronger still, the **intermediate QIF output is also identical**. Comparing
`QIF_20251210_ALGN.OUT` between runs gives ten differing lines, all of them
campaign paths or CPU timing. The mapping function change had zero numerical
effect *at the step where it was changed*.

## Why — the mechanism, not a guess

The ambiguity-resolution panels do not estimate a troposphere. They **introduce**
one. From a fresh QIF output's input-file block:

```
Estimated troposphere    : ${P}/LZGMF/ATM/FLT_20251210.TRP     <- INPUT
```

and the only parameter block estimated is `7. CLOCK PARAMETERS`. The zenith
delays come from the float solution's `.TRP`; the QIF step re-uses them. With
no zenith delay being estimated, there is no mapping function to apply.
`MAPPNG` in those three panels is a field that does nothing.

The contrast is visible in the same run. The final step reports:

```
Troposphere estimates    : ${P}/LZGMF/ATM/FIN_20251210.TRP     <- OUTPUT
Site-specific troposphere parameters        870
```

870 troposphere parameters estimated. **`MAPPNG` is live there and inert in the
ambiguity panels** — which is exactly why changing it upstream changed nothing.

## Consequences

**1. GEO-002 closes as cosmetic.** Set the three panels to `WET_GMF3` for
consistency whenever convenient, or leave them; it changes no number. It is a
tidiness ticket, not a science one. Do **not** record it as "resolved by
choosing GMF3" — record that the field is inert, or someone will later infer
that a mapping function was evaluated on its merits and lose the reason.

**2. The 2025 run is unblocked on this question.**

**3. The related finding is the consequential one.** `MAPPNG` *is* live in
R2S_EDT and R2S_FIN — the 870 parameters above — and that is precisely where
the declared configuration is wrong. `pcf_context.LUZON_TROPOSPHERE` and
GEO-002 both record those panels as `WET_GMF`; the live 5.4 tree runs
`WET_GMF3`. Different functions, both valid 5.4 cards. See PR #125.

So the split that was documented and worried about turns out not to matter, and
the value that was never questioned turns out to be the one acting on the
numbers. Worth remembering the next time a configuration question is ranked by
how obvious it looks.

## Scope

One day (DOY 121), and the result is bit-identical rather than
small — a difference of degree could vary by day, but "no effect via a field
that is not read" does not. The mechanism generalises; the arithmetic does not
need repeating. `DOYS="121 126 131 136 141 146 151"` remains available in the
harness if a broader confirmation is ever wanted.

## Tool fix found by using it

`scripts/compare_solutions.sh` did not strip the `DD-MMM-YY HH:MM` program
header stamp, so any two runs made on **different days** reported DIFFERS even
when bit-identical. That is the normal case for this tool — a baseline and a
variant are rarely produced the same afternoon — so it failed exactly when it
was most likely to be believed. Fixed in the same change.
