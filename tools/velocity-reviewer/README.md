# velocity-reviewer

A browser-based reviewer for GNSS time-series outliers. It replaces the
Windows-only `outlier_input-site.py` GUI from the PHIVOLCS velocity workflow.
It works, but has **no tests** and is not in `testpaths`.

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

For each site: an interactive ENU plot (Plotly), automatic suggestions (points
whose residual from the linear fit exceeds 3 × IQR) as a starting point, and
point-and-click marking by the analyst.
Exporting writes `OUTLIERS.txt` and strips the marked epochs from the PLOT files.
The original is backed up as `<SITE>.bak` the first time, and every later export
restores from that backup before stripping, so exporting twice gives the same
result.

The regression and IQR logic is a straight port of
`analysis/02 Time Series/Outliers-input name.py` (mean-centred, in cm), so the
outlier suggestions match the legacy tool. The velocity numbers PHIVOLCS
publishes come from `pogf_geodetic_suite.timeseries.analysis`, not from this
tool.

## Limits

- Single session: state lives in the server process, so one analyst at a time.
- The page loads Plotly from `cdn.plot.ly`, so it needs internet access.
- No tests.
