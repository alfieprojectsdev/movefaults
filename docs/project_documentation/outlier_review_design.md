# Outlier review in the BSW console

**Status: proposal, 2026-11-05; the review view and the decision record were
built the same day** (`6405d2a`, `c076a61`: `bsw_console/outliers.py` and the
Time series page's plot). The rest of this document has not been re-checked
against the code since, so read "what exists today" below as of the proposal.
It designs the step
`docs/bernese_orchestration_explainer.md` calls "manual outlier removal stays
human": a person looks at each station's time series, confirms or overrides the
automatic outlier flags, and the decision is recorded with their name, *not* by
editing PLOT files. The explainer marks it "Not built yet: it is a later stage
of the browser console."

## What exists today

| | Automatic flags | Person decides | Where the decision goes |
|---|---|---|---|
| Legacy (`outlier_input-site.py`, Windows GUI; the copy in this repo is `docs/bern52/.../Outliers-input name.py`) | none in the GUI: it plots the linear fit. Automatic detection was the MATLAB's `rmoutliers` in `vel_line_v8`, whose mask the fit then ignored | right-click to mark | appends the epoch to `OUTLIERS.txt`; the work instruction then has the analyst delete those points by hand and re-run (`velocity_outlier_policy_delta.md`) |
| `tools/velocity-reviewer` (web) | its own addition: Tukey fences (Q1/Q3 ± 3×IQR) on each component's residuals from a linear fit (mean-centred, cm), drawn as suggestions. Until 2026-11-13 it compared the 3-D residual magnitude with 3×IQR alone, which flagged about 10% of clean daily data | click to mark | strips the marked epochs from the PLOT files in place (first `.bak` kept, refreshed when the PLOT file was regenerated) and writes `OUTLIERS.txt`. No name recorded, one analyst at a time, Plotly loaded from a CDN, 44 tests |
| Console Time series page (#335, #337) | `pogf_geodetic_suite.timeseries.status`: 3×IQR per segment, on **raw values**, any of E/N/U | **nothing**: read-only | shows counts and the mode only |

What the console already has. `station_status` returns every epoch's
`e_mm`/`n_mm`/`u_mm` with its flag, segment and fit membership, the fitted line
per segment, and the offsets. So a plot needs no new science, only drawing.
(The console's own TypeScript type declares only part of `series` today, and
the page draws no chart yet.)

Two things to keep in view:

- **The two automatic rules disagree.** velocity-reviewer flags on residuals
  from a linear fit; `status` flags on raw values. On a fast-moving site a
  strong trend widens the raw spread, so a horizontal outlier can sit inside
  the raw fences. `status`'s own docstring names this as an inherited weakness,
  and `automation_stages.md` (stage 3, item 1) proposes iterative detection on
  residuals.
- **The fit question is still open.** `docs/SETTLED.md` §6 records whether a
  confirmed outlier is excluded from the published velocity fit as an open team
  decision. `status` defaults to `record`, which reproduces PHIVOLCS' published
  velocities, while `analysis.estimate_velocity` defaults to excluding.
  `velocity_outlier_policy_delta.md` explains why the manual step existed at
  all: the MATLAB computed the outlier mask and then fitted the raw data anyway.

## Proposal

### 1. A review view on the Time series page

For the chosen station and reference:

- One chart each for East, North and Up against time.
- Automatically flagged epochs are highlighted, the catalogue's offsets drawn as
  vertical lines, and the fitted line drawn per segment, all from
  `station_status` as returned.
- Clicking an epoch opens a small form: **outlier** / **not an outlier** /
  **clear my decision**, and a reason. The reason is required when the decision
  goes against the automatic flag.
- Epochs with a recorded decision are drawn distinctly, with who decided and
  when on hover.
- Charting: a library loaded from cdnjs, or plain SVG. Nothing loads at run time
  from a host gps3 cannot reach.

### 2. The decision record

An append-only JSON Lines file in the console's state directory,
`<BSW_CONSOLE_STATE>/outlier_decisions.jsonl`. One line per decision; the latest
line for a (station, epoch) is the current decision, and the earlier lines are
its history.

```json
{"v": 1, "ts": "2026-11-05T09:12:00+08:00",
 "station": "LORE", "epoch": "2025-218", "decimal_year": 2025.5969,
 "decision": "outlier" | "not_outlier" | "cleared",
 "by": "abc", "reason": "multipath after the antenna swap",
 "reference": "MONT", "auto_flag": true,
 "rule": {"method": "iqr", "factor": 3.0, "scope": "per_segment", "on": "raw_values"},
 "source": {"crd_dir": "/home/gps3/GPSDATA/SAVEDISK/PHREF/2025/STA",
            "file": "FIN_20252180.CRD", "sha256": "..."}}
```

- **`epoch` is the session date (`YYYY-DDD`), not the float.** The daily final
  CRD's name carries it (`FIN_YYYYDDDS.CRD`, S the sub-session), and the decimal
  year is derived from it (`year + DOY/365.25`, settled), so matching on the
  float would invite rounding errors.
- **`reference` is stored because an apparent outlier can be the reference's
  bad day**, which shows up at every station at once. A decision made relative
  to one reference is shown, labelled with that reference, when another is
  chosen. It is not silently reused.
- **`source.sha256` ties the decision to the CRD file it was made on.** If that
  day is reprocessed, as PHREF 2025 was this week, the page marks the decision
  "made on a superseded solution" instead of carrying it over unseen.
- **Writing a decision needs a signed-in user,** the same identity as stage 3
  (the Caddy login, `X-Remote-User`). Recording is reversible and runs nothing,
  so any signed-in user may record. Operators aren't required. Until accounts
  exist, the form is off and the page says why.
- **No CRD, PLOT or SAVEDISK file is ever modified.**

### 3. What the decisions change

Until SETTLED §6 is decided: **nothing published.** The page shows the
published fit (`record`). Beside it, clearly labelled as not published, it shows
the fit with the confirmed outliers left out, so the effect of the decisions is
visible before the team decides.

That second fit needs one small change in the timeseries package:
`estimate_velocity` / `series_status` taking an explicit exclusion mask (the
confirmed epochs), alongside today's `exclude_outliers` flag, which excludes
what the statistic flagged. The fitting itself is unchanged.

Once §6 is decided, the published velocity (`make_velocity_field.py`) reads the
same decision file. It never reads PLOT files edited by hand.

### 4. Where velocity-reviewer goes

It stays usable for the legacy PLOT workflow until the console view exists and
has been used on one real campaign. Then it's retired, and its README points to
the console. The decision file can be exported in the legacy `OUTLIERS.txt`
format if any downstream step still wants that file. The export is generated
from the decisions and never written by hand.

## Decisions needed

Each with a recommendation; open until the project lead accepts or changes it.

1. **SETTLED §6: are confirmed outliers excluded from the published fit?**
   **Recommended:** decide it after a month of recorded decisions, using the
   side-by-side fits. Until then, keep `record`. This is the existing open
   question, not a new one.
2. **Which automatic rule pre-flags.**
   **Recommended:** move `status` to residuals from the segment fit (iterative,
   as `automation_stages.md` proposes) in a separate PR, measured against
   velocity-reviewer's flags on PHREF 2025 before it ships. The review view
   doesn't depend on which rule is used.
3. **Who may record a decision.**
   **Recommended:** any signed-in user, named on every line. Operators gate
   runs, not judgement.
4. **Decisions per reference or per station-day.**
   **Recommended:** store the reference, show it, and never reuse a decision
   silently across references (section 2).
5. **velocity-reviewer.**
   **Recommended:** retire it after the console view has been used on one real
   campaign (section 4).

## Not proposed

- Removing an epoch from any file, ever.
- Changing the published velocity before §6 is decided.
- Automatic acceptance of the statistic's flags without a person.

## Size

About two PRs:

1. **Timeseries package:** the explicit exclusion mask, with tests against the
   MATLAB-verified fit unchanged when the mask is empty.
2. **Console:** the charts, the decision file and its endpoint behind the
   signed-in gate, the side-by-side fit, the "superseded solution" and "other
   reference" labels, and tests.

The rule change (decision 2) and the retirement (decision 5) are separate.
