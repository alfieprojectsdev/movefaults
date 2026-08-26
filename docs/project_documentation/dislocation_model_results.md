# Dislocation model results — what has actually been run

**Extracted, not vendored.** Source is
`analysis/07 Dislocation Model/Dislocation Model (Compilation of Results).docx`
(~62 MB of .pptx/.docx in that directory, deliberately not committed —
opaque to `git diff`, not greppable on the R740, and bulk binary).

Regenerate with:

```bash
uv run --with python-docx python scripts/extract_dislocation_results.py
```

This file settles a question that two sessions got wrong from the
repository alone. See the correction in
[`analysis_port_assessment.md`](analysis_port_assessment.md) finding 5.


## Methods actually applied

| method | segments / runs |
|---|---|
| `Elastic half-space model and grid search` | PF: Central Luzon / Bacolcol et al. (2012), PF: Guinayangan Fault / Bacolcol et al. (2012), PF: Lianga Fault / 1st modeling results (2021), PF: Masbate / Bacolcol et al. (2012), PF: Surigao Fault / Bacolcol et al. (2012), PF: West Compostela Valley Fault / Bacolcol et al. (2012) |
| `Elastic half-space model, and grid search` | PF: Southern Leyte Fault / Bacolcol et al. (2012) |
| `Elastic half-space model, grid search` | PF: Northern Leyte Fault / 2nd modeling results (2023) |
| `Elastic half-space model, grid search, and bootstrap` | Ambuklao Fault / 1st modeling results (2024), PF: Central Luzon / 1st modeling results (2021), PF: Central Luzon / 2nd modeling results (2023), PF: Central Luzon / Yu et al. (2011), PF: Eastern Mindanao / 1st modeling results (2021), PF: Guinayangan Fault / 1st modeling results (2021) (+14 more) |
| `Inversion and monte carlo` | PF: Central Luzon / 3rd modeling results (2023), PF: Masbate / 3rd modeling results (2023) (Figure 4), PF: Northern Leyte Fault / 3rd modeling results (2023) |
| `Relative GPS velocities between GPS stations` | PF: Eastern Mindanao / Aurelio (2020) |
| `Trilateration/GPS geodetic network` | PF: Northern Leyte Fault / Duquesnoy et al. (1994) |

**All three candidate methods are in production use on Philippine data.**
The MCMC is not a method awaiting evaluation — it is the newest one
applied. Any claim that it has only run on Taiwanese data is wrong and
came from reading `06 Ku-en`'s committed example rather than the record.


## Segments modelled

| segment | runs | reference stations | methods |
|---|---|---|---|
| (methods reference) | 2 | — | — |
| Ambuklao Fault | 1 | BLNA | Elastic half-space model, grid search, and bootstrap |
| PF: Central Luzon | 10 | IBAZ, LUZA | Elastic half-space model and grid search; Elastic half-space model, grid search, and bootstrap; Inversion and monte carlo |
| PF: Eastern Mindanao | 2 | CDOC, PUER (Puerto Princesa, Palawa) | Elastic half-space model, grid search, and bootstrap; Relative GPS velocities between GPS stations |
| PF: Guinayangan Fault | 4 | SIBB | Elastic half-space model and grid search; Elastic half-space model, grid search, and bootstrap |
| PF: Hapap Fault | 4 | BLNA, VIGN | Elastic half-space model, grid search, and bootstrap |
| PF: Infanta Fault | 1 | CNTA | Elastic half-space model, grid search, and bootstrap |
| PF: Lianga Fault | 1 | SOMF | Elastic half-space model and grid search |
| PF: Masbate | 5 | BALU, SIBI | Elastic half-space model and grid search; Elastic half-space model, grid search, and bootstrap; Inversion and monte carlo |
| PF: Northern Leyte Fault | 4 | CEB1 | Elastic half-space model, grid search; Elastic half-space model, grid search, and bootstrap; Inversion and monte carlo; Trilateration/GPS geodetic network |
| PF: San Manuel Fault | 2 | MABN | Elastic half-space model, grid search, and bootstrap |
| PF: Southern Leyte Fault | 2 | ISAB | Elastic half-space model, and grid search; Elastic half-space model, grid search, and bootstrap |
| PF: Surigao Fault | 2 | NOMA | Elastic half-space model and grid search; Elastic half-space model, grid search, and bootstrap |
| PF: West Compostela Valley Fault | 2 | SOMF | Elastic half-space model and grid search; Elastic half-space model, grid search, and bootstrap |

## Uncertainties are published

91 published parameter values carry an explicit interval.
So "which method gives uncertainties" was never the open question —
all of them do, by different routes.


Examples:

- **PF: Hapap Fault** / Yu et al. (2011) — Locking depth (km): `15 (6-17)`
- **PF: Hapap Fault** / Yu et al. (2011) — Dip Angle (degrees): `85 (79-90)`
- **PF: Hapap Fault** / Yu et al. (2011) — Slip Rate (mm/yr): `24 (20-25)`
- **PF: Hapap Fault** / Yu et al. (2011) — Backslip Rate (mm/yr): `22 (17-35)`
- **PF: Hapap Fault** / 1st modeling results (2021) — Top depth (km): `0 (0-5)`
- **PF: Hapap Fault** / 1st modeling results (2021) — Locking depth (km): `37 (32-43)`
- **PF: Hapap Fault** / 1st modeling results (2021) — Dip Angle (degrees): `85 (81-88)`
- **PF: Hapap Fault** / 1st modeling results (2021) — Slip Rate (mm/yr): `19 (17-20)`

## What is still open
- The `metropolis_log.m` overflow (`exp(a)*exp(b)` rather than
  `exp(a+b)`) is a defect in a method that has **already produced
  published intervals**. Whether it affected the 900,000-sample runs is
  checkable and has not been checked.
- `bootstrap_v2.py` hardcodes reference station `VIGN`, which appears in
  the table as the reference for the first two Central Luzon runs. The
  script is tied to a specific published run rather than parameterised.


---

Full long-format extraction: [`dislocation_model_results.csv`](dislocation_model_results.csv)

