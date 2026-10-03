# EQ vs EPB residual discriminator — research spike

**Purpose:** measure what a raw per-satellite stream would add over the
station-level data we receive today, for telling an earthquake from an
equatorial plasma bubble (EPB). The physics check: under a quake one rigid
motion fits every line of sight, so the post-fit residual of the per-epoch
velocity solve stays at noise level; under a bubble, extra range-rate error on a
subset of satellites shows up in the residual.

Synthetic data only. Nothing here touches `services/vadase-rt-monitor`, and no
recorded station data, coordinates or captures are committed (the repo is
public). Every figure is reproducible from a seed and a config.

## Task 0 — what the code and stream actually provide (2026-10-03)

1. **Per-satellite data: none in the live stream.** The `$GNLVM` sentence our
   parser reads carries station-level values only: velocity ENU, its 3x3
   variance-covariance, `cq` (3-D quality, m/s) and `n_sats`. `$GNLDM` adds
   displacement with covariance, `cq`, `n_sats`, `reset_indicator`, and epoch and
   overall completeness. There are no per-satellite residuals, lines of sight or
   time-differenced phase, so **this residual test cannot run on live data as
   is**. The receivers do push raw observations to GNSS Spider on gps1 (Leica
   binary, sensor "Passive LB2"); those carry per-satellite carrier phase, so a
   TDCP velocity solve with real residuals could be computed downstream if a raw
   stream were exposed. Not done; out of scope here.
2. **Rate 1 Hz** (Spider's streaming data rate). Constellations and single vs
   dual frequency used by the receiver's VADASE engine are not in the stream:
   **[VERIFY]** from the receiver configuration.
3. **Current detector** (`src/domain/processor.py`): horizontal speed
   `hypot(vE, vN)` in mm/s against `threshold_mm_s` (15 mm/s per station in
   `config/stations.yml`). The vertical is not used. Plus the receiver-mode
   state machine and a leaky integrator for displacement. Station-level only.
4. **Recorded streams:** `services/vadase-rt-monitor/tests/fixtures/sample_{lvm,ldm}.nmea`
   (tiny, committed); untracked captures on gps3 and finch, and gps1's NMEA logs.
   All station-level, and all stay local.
5. **Conventions:** Python 3.11+, `uv`, pytest with `--import-mode=importlib`,
   ruff (settings in the root `pyproject.toml`). A suite runs in `uv run pytest`
   only if its path is listed in `testpaths`; this one is.

## Layout

```
epb/geometry.py   sky, line-of-sight vectors, design matrix, weights
epb/signals.py    quake velocity pulse, bubble range-rate noise, single-satellite glitch
epb/scenario.py   Config + build(label): truth + noise + labels, and LVM-style station outputs
epb/residual.py   WLS, chi2/dof, Baarda normalized residuals, MDB, leakage, station_level()
plot_epoch.py     session 1 figure (quake vs bubble), writes PNG + config JSON
tests/            statistics against theory, scenarios, reproducibility
NOTES.md          state at each stopping point
```

## Model

Per epoch, satellite i: `y_i = -u_i . v + b + d_i + e_i`, with `u_i` the
receiver-to-satellite unit vector in ENU, `v` the station velocity, `b` the
clock drift (m/s), `d_i` unmodelled per-satellite error (zero under the null;
bubbles and glitches live here), `e_i ~ N(0, (sigma0 / sin el_i)^2)`. Design
matrix rows `[-u_e, -u_n, -u_u, 1]`; redundancy `N - 4`.

**Placeholders, to calibrate from a quiet recorded day:** `sigma0` = 3 mm/s,
bubble RMS 10 mm/s, quake peak (50, 30, 10) mm/s over 20 s. See `Config`.

## Run

```
uv run pytest analysis/epb_discriminator/tests
uv run python analysis/epb_discriminator/plot_epoch.py --seed 42
```
