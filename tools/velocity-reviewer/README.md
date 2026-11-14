# velocity-reviewer

A browser-based reviewer for GNSS time-series outliers. It replaces the
Windows-only `outlier_input-site.py` GUI from the PHIVOLCS velocity workflow.
It is interim: `outlier_review_design.md` (section 4) retires it once the
console's review view has been used on one real campaign.

## Run it

From the repository root:

```bash
uv run velocity-reviewer --plots-dir /path/to/PLOTS          # port 8765 by default
uv run velocity-reviewer --plots-dir /path/to/PLOTS --port 9000
```

The PLOTS directory holds the inputs the legacy workflow already uses:

| file | format |
|---|---|
| `123` | master site list, one 4-character code per line |
| `<SITE>` PLOT files | `decimal_year east_m north_m up_m` |
| `offsets` | `SITE decimal_year TYPE` (EQ, CE, VE, UK), drawn as event lines |

## What it does

For each site: an interactive ENU plot (Plotly), automatic suggestions as a
starting point, and point-and-click marking by the analyst.

The suggestions are points whose residual from the linear fit, in any one
component, falls outside the Tukey fences Q1 − 3·IQR and Q3 + 3·IQR: the same
fences as MATLAB's `rmoutliers` and `pogf_geodetic_suite.timeseries.analysis`,
applied to residuals instead of raw positions. The legacy GUI had no automatic
suggestions; only its fit (mean-centred, in cm) is a port of
`analysis/02 Time Series/Outliers-input name.py`.

Exporting writes `OUTLIERS.txt` and strips the marked epochs from the PLOT files:

- The first export copies each PLOT file to `<SITE>.bak`.
- Every export rebuilds the PLOT file from `<SITE>.bak` minus the current
  selection, so exporting twice gives the same file and clearing a site's
  selection restores it.
- If a PLOT file has rows its backup lacks, it was regenerated after the last
  export (new epochs, or reprocessed coordinates). It becomes the new backup
  before stripping, so the new rows are kept.
- After an export, the page draws the site from `<SITE>.bak` and starts with
  the stripped epochs selected, so a later session keeps earlier decisions
  instead of undoing them. `OUTLIERS.txt` also lists them for sites not opened
  in the current session.
- One case it can't tell apart: a regenerated PLOT file whose rows are all in
  the old backup (a shorter span, nothing else changed) looks like an earlier
  export, and the old rows come back. Delete `<SITE>.bak` after regenerating
  over a shorter span, or after deleting rows from a PLOT file by hand. The velocity numbers PHIVOLCS
publishes come from `pogf_geodetic_suite.timeseries.analysis`, not from this
tool.

## Limits

- Single session: state lives in the server process, so one analyst at a time.
- The page loads Plotly from `cdn.plot.ly`, so it needs internet access.
- A site the `123` file doesn't list can't be selected or exported.
