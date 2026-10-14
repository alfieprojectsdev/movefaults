# pogf-geodetic-suite

The shared geodesy library: RINEX QC, IGS product download, coordinate
transforms, the ported velocity pipeline, and dislocation modelling without
MATLAB. Status as of 2026-10-14: about 75%, 18 modules, 260 tests.

## Modules

| module | what it does |
|---|---|
| `qc/rinex_qc.py` | `RinexQC`: teqc first, gfzrnx when teqc refuses a RINEX 3 file or is not installed; every result records `tool` and `fallback_reason`. CLI `rinex-qc` |
| `qc/completeness.py` | which days can be processed at all (for example, fewer than three reference stations), run before staging a campaign. CLI `rinex-completeness` |
| `igs_downloader.py` | IGS20 long-name products with mirror fallback. CLI `igs-downloader`. Production fetches use `scripts/fetch_igs_products.sh` instead |
| `modeling/coordinates.py` | coordinate transforms |
| `timeseries/crd_pipeline.py` | Bernese CRD → ENU relative to a reference station (the `RUNX_v2.py` steps 01–03) |
| `timeseries/plots.py`, `timeseries/cli.py` | network filter and PLOT-file writer. CLI `crd-to-plots`; networks in `timeseries/networks/networks.yml` |
| `timeseries/analysis.py` | offset-aware segmented velocities, a port of `vel_line_v8_newvelduetooffset_v4.m`: 161 of 165 components agree with PHIVOLCS' published output to better than 5e-6 mm/yr. Joint step + rate estimation (`estimate_velocity_joint`) |
| `timeseries/offsets_catalog.py` | load (sorted) and validate the `offsets` discontinuity catalog |
| `timeseries/gmt.py` | GMT `psvelo` files; sites whose final interval is under a year are withheld |
| `modeling/disloc.py` | Okada 1985 surface dislocation, replacing `disloc.mexw64` |
| `modeling/dc3d.py`, `modeling/disloc3d.py` | Okada 1992 DC3D and the `disloc3d` calling convention, replacing `disloc3d.mexw64`. No MATLAB binary is left in the modelling chain |
| `modeling/inversion.py` | the 2-D interseismic grid-search inversion (port of `analysis/03 Yu`) |

## Conventions that are settled

- **Decimal year is `year + DOY/365.25`**, so DOY 1 is `year + 0.0027`. It
  matches the `offsets` catalog and every published PLOT file. Do not "correct"
  it (`docs/SETTLED.md` §3; pinned by tests).
- The reference station is always an explicit argument. These velocities are
  relative to one site, not ITRF.
- Outliers are excluded from the fit by default (`exclude_outliers=True`).

## Building and testing

From the repository root:

```bash
uv sync --all-extras
uv run pytest packages/pogf-geodetic-suite/tests
```

`modeling/dc3d.py` and `modeling/disloc.py` compile small C cores
(`_dc3d/*.c`, `_disloc/*.c`) with `cc` on first use into git-ignored `.so`
files, so a C compiler must be installed. Two DC3D tests skip if the quadrant
fix did not build. The RINEX QC tests mock the subprocess, so they need neither
`teqc` nor `gfzrnx`; real QC runs do (on gps3 both are in `~/bin`, see
`docs/tooling/README.md`).

## Related documents

- `docs/project_documentation/automation_stages.md`: stage 3, coordinates → velocities
- `docs/project_documentation/velocity_outlier_policy_delta.md`: what the port found in published velocities
- `docs/project_documentation/inversion_method_decision.md`: which inversion method to port next (awaiting sign-off)
- `docs/project_documentation/gfzrnx_vs_teqc_rinex3_evidence.md`
