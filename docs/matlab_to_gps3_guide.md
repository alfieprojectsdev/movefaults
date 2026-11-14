# From MATLAB to gps3: where each step is done now

*For the processing team. 13 November 2026. One page: find the step you run
today, and do it where the second column says.*

Nothing here needs MATLAB, or anything installed on your PC. Steps marked
**console** are on the BSW console's pages (work instruction, section 3, for how
to open it). Steps marked **command** run on gps3 in a terminal, from the
project folder, starting with `uv run`. Ask the maintainer for a gps3 login and
the folder's location. The console will start these commands as jobs later, so
you won't need the terminal then.

| What you run today | Where to do it now | Notes |
|---|---|---|
| `00_CRD_*.bat` (network filter), then `RUNX_v2.py` (CRD → PLOT files) | **console**, Time series page; or **command** `pogf-timeseries plots <CRD folder> -r <reference> -n <NP\|PIVS\|NAMRIA>` | The `-n` choice replaces the three `.bat` files. The command writes PLOT files to `<CRD folder>/PLOTS`; `-o` changes that. Decimal years are `year + DOY/365.25`, the same as yours and as the `offsets` catalogue |
| `outlier_input-site.py` (right-click outliers) | **console**, Time series page (click an epoch); or `uv run velocity-reviewer --plots-dir <PLOTS>` for PLOT files | The console keeps each decision with your name and edits no file. velocity-reviewer edits PLOT files: the first export keeps `<SITE>.bak`, and clearing a site's marks restores it. Its automatic suggestions are a starting point, not a decision |
| `vel_line_v8.m` (velocities, `Velocity_rover(regress)_10`, `outliers`) | **console**, Time series page, one station; or **command** `pogf-timeseries velocities <PLOTS>` for all of them | Same table layout as the MATLAB. Matches production to 5e-6 mm/yr on 161 of 165 components. Default `--outlier-mode record` keeps flagged epochs in the fit, as the MATLAB does. It refuses to run without an `offsets` file unless you pass `--no-offsets`, so a missing catalogue is never silent. `velocities_manifest.json` records which catalogue and settings were used |
| Checking a new result against an old MATLAB one | **command** `pogf-timeseries compare-velocities <new table> <old table>` | "match" means every value prints the same to the table's precision. Lists each site that differs |
| GMT velocity map input | **command** `pogf-timeseries velocities <PLOTS> --crd <one CRD file> -r <reference>` | Also writes `velocities.psvelo` for `psvelo` |
| `velproj_loop.m` (project velocities on a profile) | **still MATLAB** | Being ported next |
| `makeG_2ds_v3_loop.m` and `bootstrap_v2.py` (2-D model, bootstrap) | **still MATLAB** | Being ported next. Default fault geometry and ranges, with sources, are in `project_documentation/fault_model_priors.md`; a geologist hasn't signed them off yet |
| Profile, histogram and combined figures (`combine.m`) | **still MATLAB** | Will be drawn from the saved results, not merged from `.fig` files |
| MCMC (`06 Ku-en`) | **still MATLAB** | Later |

## If something doesn't match

Keep your MATLAB output, run `compare-velocities` against it, and send the
maintainer the command you ran, its output, and the `velocities_manifest.json`.
A difference with a known cause (another reference station, another `offsets`
version, `--outlier-mode exclude`) is expected; the manifest shows which.

## Why the numbers can still differ from older results

- **Reference station.** Velocities are relative to the reference you choose.
  Results against S01R and against a Philippine station can't be compared
  directly (work instruction, section 6).
- **The `offsets` catalogue.** gps3 uses the copy in the repository. The
  continuous stations' catalogue hasn't been copied yet, so a continuous
  station may be fitted straight across a real step.
- **Reprocessed coordinates.** Campaigns reprocessed on gps3 differ slightly
  from older solutions; the CRD files, not the code, are the cause.
