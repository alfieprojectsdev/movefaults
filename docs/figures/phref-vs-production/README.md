# PHREF 2025 vs PHIVOLCS production — selected time series

Six of 38 stations, chosen to carry the findings. The full set is regenerable
(below) and deliberately not committed: 38 plots is 5.4 MB of derived output
that a minute of compute reproduces.

All figures: **our 360 daily solutions** (BSW 5.4 on the R740, release
`2024-11-11` **unpatched**) against **PHIVOLCS production weeklies** (BSW 5.2).
Both sides pass through the *same* `crd-to-plots` chain, referenced to **PIMO**,
means removed. A difference here is therefore a difference in the solutions,
not in how they were turned into series.

Median agreement across all 38: **E +3.96, N −2.98, U −13.40 mm**.

| figure | why it is here |
|---|---|
| `ALAB.png` | the typical case — the two series sit on top of each other |
| `VIGN.png` | typical, with a longer record |
| `TGDN.png` | **the one genuine outlier**, 16.7 mm horizontal. Flagged independently by the weekly Helmert comparison as one of three East-dominated stations. Also carries two failed days (2025.5503, 2025.7036, up to 4.6 m) — annotated at the frame edge, not deleted |
| `LGYE.png` | 11 episodic East excursions ending mid-July. Sign alternates, so neither a coordinate offset nor deformation. Beside Mayon, which makes a volcanic story attractive and unsupported |
| `CLAV.png` | **31 epochs, not 360.** CLAV has 31 days of RINEX in 2025; before `read_crd_file` learned to skip a priori carry-through, this plotted as a flat 360-day line with a 31-day step that looked exactly like a real displacement |
| `MARK.png` | 70 of 360 days ours, 12 of 53 weeks hers — a station whose apparent offset was mostly unequal sampling |

## Reading the axes

Y-limits are robust (8×MAD). Points outside are kept and counted in the corner
annotation rather than dropped — a handful of failed days would otherwise set
the scale and flatten the real signal into a line.

## Regenerating, including the other 32

```bash
# our dailies and, after scripts/sinex_to_crd.py, her weeklies
crd-to-plots $S/PHREF/2025/STA -r PIMO -n PIVS -o ~/ts-compare/ours-daily

scripts/plot_series_overlay.py TGDN \
    --series "ours daily (BSW 5.4, unpatched):$HOME/ts-compare/ours-daily" \
    --series "PHIVOLCS weekly (BSW 5.2):$HOME/ts-compare/hers-weekly" \
    --detrend -o TGDN.png
```

Full method and the numbers behind these pictures:
[`../../phref_vs_production_comparison_results.md`](../../phref_vs_production_comparison_results.md).
