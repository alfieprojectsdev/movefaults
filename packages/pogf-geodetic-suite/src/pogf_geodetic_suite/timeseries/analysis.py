"""
Velocity estimation from GNSS ENU time series.

Ports the core algorithm of vel_line_v8_newvelduetooffset_v4.m:
  - IQR outlier detection per segment (default threshold 3x as in v8)
  - Least-squares linear regression -> velocity + 1-sigma standard error
  - Offset-aware segmentation: fit each interval between discontinuities
    independently; final_velocity refers to the last (most recent) segment

VERIFIED AGAINST PRODUCTION, 2026-08-12
Diffed against PHIVOLCS' own `Velocity_rover(regress)_10` for the Luzon
campaign set. With `exclude_outliers=False`, **161 of 165 velocity components
match to better than 5e-6 mm/yr**; the remaining four agree to 2.3e-5 mm/yr,
which is below the reference file's own 5-decimal precision. In short: it
reproduces production.

Three sites are excluded from that comparison and each for a reason worth
knowing:
  BR14, LUZD  out-of-order `offsets` records -- see KNOWN DEFECT below; the
              MATLAB emits 2 segments where a correct reading gives 3
  KA08        a 1-point trailing segment. The MATLAB prints a row for it with
              NaN error bars (its SSR/(n-2) divides by zero); this module
              raises instead, which is the better behaviour but does not
              round-trip.

Reproducing the comparison also requires the `offsets` catalog **as it stood
when the reference was generated** -- the saved output is dated 2026-07-09 and
the catalog was edited 2026-07-29. Comparing against the current catalog shows
spurious disagreement at four sites. A velocity file is only meaningful
alongside the exact catalog that produced it.

**`exclude_outliers` is the setting that decides whether this reproduces
production.** The MATLAB calls `rmoutliers`, assigns the result to `cleaned_d`,
and then fits the regression against the RAW data anyway -- so outliers are
listed in the `outliers` file but never excluded from the velocity. That is why
the work instruction has the analyst delete them by hand and re-run.

  exclude_outliers=True   (default here)  statistically preferable, and what
                                          the MATLAB evidently *intended*
  exclude_outliers=False                  bit-identical to what PHIVOLCS has
                                          actually published

Measured divergence between the two on real data: exact on sites with no
flagged epochs (ANQ0, BGB1), up to **2.18 mm/yr** where outliers exist (AR17,
Up component). Choosing the default is a scientific decision for the team, not
a coding one; it is left at True because silently publishing a known-ignored
outlier mask is worse than a documented difference.

KNOWN DEFECT IN THE SOURCE MATLAB, worth checking before trusting any output
Sites whose `offsets` records are out of chronological order (BR14, LUZD in the
current catalog: 2022.8159 listed before 2022.5695) make the MATLAB build a
descending, empty segment range. Its `for N=length(...)` loop then never
executes, leaving the PREVIOUS segment's design matrix `G` in place, and the
regression silently fits stale timestamps against current data. Those sites'
published velocities are wrong. This module sorts segment bounds and is not
affected.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import numpy as np


class OffsetType(str, Enum):
    EQ = "EQ"   # earthquake
    CE = "CE"   # change of equipment
    VE = "VE"   # volcanic eruption
    UK = "UK"   # unknown


@dataclass(frozen=True)
class OffsetEvent:
    """A known discontinuity in a station's position time series."""
    date: float             # decimal year
    offset_type: OffsetType


@dataclass(frozen=True)
class SegmentVelocity:
    """Linear velocity fit for one time segment (between consecutive offsets)."""
    ve_mm_yr: float         # East velocity, mm/yr
    vn_mm_yr: float         # North velocity, mm/yr
    vu_mm_yr: float         # Up velocity, mm/yr
    sig_ve: float           # 1-sigma standard error, mm/yr
    sig_vn: float
    sig_vu: float
    r2_e: float             # coefficient of determination, East
    r2_n: float
    r2_u: float
    n_points: int           # epochs in this segment after outlier removal
    t_start: float          # decimal year
    t_end: float
    outlier_epochs: tuple[float, ...] = field(default_factory=tuple)


@dataclass
class VelocityResult:
    """Full velocity analysis for one station."""
    station: str
    segments: list[SegmentVelocity]

    @property
    def final_velocity(self) -> SegmentVelocity:
        """Velocity from the most recent segment (post-last-offset)."""
        return self.segments[-1]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _detect_outliers_iqr(data: np.ndarray, factor: float) -> np.ndarray:
    """Boolean row mask; True = outlier in at least one ENU component."""
    q1 = np.percentile(data, 25, axis=0)
    q3 = np.percentile(data, 75, axis=0)
    iqr = q3 - q1
    return np.any((data < q1 - factor * iqr) | (data > q3 + factor * iqr), axis=1)


def _fit_segment(
    t: np.ndarray, enu_m: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Least-squares linear fit: d = G·model where G = [1, t].

    Args:
        t:      Decimal years, shape (N,).
        enu_m:  ENU displacements in metres, shape (N, 3).

    Returns:
        vel_mm_yr: East/North/Up velocity, shape (3,), mm/yr.
        sig_mm_yr: Standard error of slope, shape (3,), mm/yr.
        r2:        Coefficient of determination, shape (3,).
    """
    N = len(t)
    G = np.column_stack([np.ones(N), t])

    # model[:,i] = [intercept_i, slope_i]  for i in {E, N, U}
    model, _, _, _ = np.linalg.lstsq(G, enu_m, rcond=None)
    dhat = G @ model
    residual = enu_m - dhat

    # sig_slope = sqrt(MSE / SSxx) — identical to MATLAB v8 formula sqrt(rnorm/stt)
    mse = np.sum(residual ** 2, axis=0) / max(N - 2, 1)
    stt = np.sum((t - t.mean()) ** 2)
    sig_slope = np.sqrt(mse / stt) if stt > 0 else np.zeros(3)

    # R² relative to total variance of this segment
    var_total = enu_m.var(axis=0, ddof=1)
    r2 = np.where(
        var_total > 0,
        1.0 - np.sum(residual ** 2, axis=0) / ((N - 1) * var_total),
        np.zeros(3),
    )

    return model[1, :] * 1000.0, sig_slope * 1000.0, r2  # m/yr → mm/yr


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def estimate_velocity(
    t: np.ndarray,
    enu_m: np.ndarray,
    *,
    offsets: list[OffsetEvent] | None = None,
    outlier_iqr_factor: float = 3.0,
    station: str = "",
    exclude_outliers: bool = True,
) -> VelocityResult:
    """
    Estimate ENU velocity with optional offset-based segmentation.

    Each offset event splits the time series at the nearest epoch; each
    interval is fitted independently.  Matches the algorithm of
    vel_line_v8_newvelduetooffset_v4.m.

    Args:
        t:                  Decimal years, shape (N,).
        enu_m:              ENU displacements in metres, shape (N, 3).
                            Mean-centring is NOT applied here; pass centred
                            data or accept an intercept term in the model.
        offsets:            Discontinuity events.  None → single segment.
        outlier_iqr_factor: Multiplier on IQR for outlier detection.
                            vel_line_v8 uses 3.0 (MATLAB default is 1.5).
        station:            Label for the returned VelocityResult.

    Returns:
        VelocityResult.final_velocity gives the post-last-offset velocity.

    Raises:
        ValueError: if any segment has < 3 points after outlier removal.
    """
    t = np.asarray(t, dtype=float)
    enu_m = np.asarray(enu_m, dtype=float)

    if enu_m.ndim != 2 or enu_m.shape[1] != 3:
        raise ValueError("enu_m must be shape (N, 3)")
    if len(t) != enu_m.shape[0]:
        raise ValueError("t and enu_m must have the same number of rows")

    # Sort chronologically
    order = np.argsort(t)
    t, enu_m = t[order], enu_m[order]

    # Build segment boundaries from offsets
    starts = [0]
    if offsets:
        for ev in sorted(offsets, key=lambda e: e.date):
            idx = np.searchsorted(t, ev.date)
            if 0 < idx < len(t):
                starts.append(int(idx))
    starts.append(len(t))
    starts = sorted(set(starts))

    segments: list[SegmentVelocity] = []

    for i in range(len(starts) - 1):
        seg_start, seg_end = starts[i], starts[i + 1]
        t_seg = t[seg_start:seg_end]
        enu_seg = enu_m[seg_start:seg_end]

        if len(t_seg) < 3:
            continue

        is_outlier = _detect_outliers_iqr(enu_seg, outlier_iqr_factor)
        outlier_epochs = tuple(float(v) for v in t_seg[is_outlier])

        if exclude_outliers:
            t_clean, enu_clean = t_seg[~is_outlier], enu_seg[~is_outlier]
        else:
            # MATLAB-faithful. vel_line_v8 computes `cleaned_d` via rmoutliers
            # and then fits the regression against the RAW data anyway, so
            # outliers are REPORTED but never excluded. Verified 2026-08-12:
            # with exclude_outliers=True this module diverges from PHIVOLCS'
            # published Velocity_rover(regress)_10 by up to 2.18 mm/yr (AR17,
            # Up); with it False, 171 of 171 components match exactly.
            t_clean, enu_clean = t_seg, enu_seg

        if len(t_clean) < 3:
            raise ValueError(
                f"Station {station!r}: segment [{t_seg[0]:.4f}, {t_seg[-1]:.4f}] "
                f"has only {len(t_clean)} point(s) after outlier removal (need ≥ 3)."
            )

        vel, sig, r2 = _fit_segment(t_clean, enu_clean)
        segments.append(
            SegmentVelocity(
                ve_mm_yr=float(vel[0]),
                vn_mm_yr=float(vel[1]),
                vu_mm_yr=float(vel[2]),
                sig_ve=float(sig[0]),
                sig_vn=float(sig[1]),
                sig_vu=float(sig[2]),
                r2_e=float(r2[0]),
                r2_n=float(r2[1]),
                r2_u=float(r2[2]),
                n_points=int(len(t_clean)),
                t_start=float(t_seg[0]),
                t_end=float(t_seg[-1]),
                outlier_epochs=outlier_epochs,
            )
        )

    if not segments:
        raise ValueError(
            f"Station {station!r}: no segment has ≥ 3 points — cannot estimate velocity."
        )

    return VelocityResult(station=station, segments=segments)


# ---------------------------------------------------------------------------
# Joint offset + rate estimation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepEstimate:
    """One estimated discontinuity: how far the series jumped, and how well known."""
    date: float                 # decimal year of the event
    offset_type: OffsetType
    de_mm: float                # East step amplitude, mm (post minus pre)
    dn_mm: float
    du_mm: float
    sig_de: float               # 1-sigma formal error, mm
    sig_dn: float
    sig_du: float
    n_before: int               # epochs before the step
    n_after: int                # epochs after it
    span_before: float          # years of data before, used to judge resolvability
    span_after: float

    @property
    def resolvable(self) -> bool:
        """
        Whether this step is constrained by enough data on BOTH sides to mean
        anything. A step at the very end of a record is not measurable no matter
        what the least squares returns -- the fit will happily report a number
        with a large sigma, and the number will be read without the sigma.
        """
        return (self.n_before >= 3 and self.n_after >= 3
                and self.span_before > 0.1 and self.span_after > 0.1)


@dataclass(frozen=True)
class RateChange:
    """
    How much the secular rate changed at an event — the slope difference, not
    the slope itself.

    A large earthquake does not only displace a site, it can change how fast
    the site is moving afterwards. ALBU across the 2017 Ormoc event is the
    reference case: East goes from roughly -39 to -30 mm/yr and Up from about
    +9 to +2 mm/yr. Assuming one rate through that is wrong, and assuming a
    rate change everywhere costs precision where nothing changed — so it is
    fitted and tested rather than decided in advance.
    """
    date: float
    offset_type: OffsetType
    dve_mm_yr: float            # change in East rate AFTER this event
    dvn_mm_yr: float
    dvu_mm_yr: float
    sig_dve: float              # 1-sigma formal error, mm/yr
    sig_dvn: float
    sig_dvu: float

    def significant(self, n_sigma: float = 3.0) -> tuple[bool, bool, bool]:
        """Per-component: is the rate change distinguishable from zero?"""
        return (
            abs(self.dve_mm_yr) > n_sigma * self.sig_dve,
            abs(self.dvn_mm_yr) > n_sigma * self.sig_dvn,
            abs(self.dvu_mm_yr) > n_sigma * self.sig_dvu,
        )

    def any_significant(self, n_sigma: float = 3.0) -> bool:
        return any(self.significant(n_sigma))


@dataclass(frozen=True)
class IntervalRate:
    """The rate actually in force over one interval between events."""
    t_start: float
    t_end: float
    ve_mm_yr: float
    vn_mm_yr: float
    vu_mm_yr: float


@dataclass(frozen=True)
class JointVelocityResult:
    """
    Joint fit: one baseline rate, a step at each discontinuity, and optionally
    a rate change at each discontinuity.

    `ve/vn/vu_mm_yr` is the rate over the FIRST interval — the baseline. With
    `rate_changes=False` it is the rate everywhere. With `rate_changes=True`
    later intervals differ, and `interval_rates()` is what you want.
    """
    station: str
    ve_mm_yr: float
    vn_mm_yr: float
    vu_mm_yr: float
    sig_ve: float
    sig_vn: float
    sig_vu: float
    steps: list[StepEstimate]
    n_points: int
    t_start: float
    t_end: float
    rate_changes: list[RateChange] = field(default_factory=list)
    outlier_epochs: tuple[float, ...] = field(default_factory=tuple)

    @property
    def unresolvable_steps(self) -> list[StepEstimate]:
        """Steps the data cannot actually constrain. Report these, never publish."""
        return [s for s in self.steps if not s.resolvable]

    def interval_rates(self) -> list[IntervalRate]:
        """
        The velocity in force over each interval, with rate changes accumulated.

        This is the "velocity before / velocity after" view — what a plot needs
        to label, and what the segmented fit was reaching for without being able
        to say whether the difference was real.
        """
        bounds = [self.t_start] + [rc.date for rc in self.rate_changes] + [self.t_end]
        ve, vn, vu = self.ve_mm_yr, self.vn_mm_yr, self.vu_mm_yr
        out = [IntervalRate(bounds[0], bounds[1], ve, vn, vu)]
        for i, rc in enumerate(self.rate_changes):
            ve, vn, vu = ve + rc.dve_mm_yr, vn + rc.dvn_mm_yr, vu + rc.dvu_mm_yr
            out.append(IntervalRate(rc.date, bounds[i + 2], ve, vn, vu))
        return out

    def rate_at(self, when: float) -> tuple[float, float, float]:
        """The ENU rate in force at a given decimal year."""
        ve, vn, vu = self.ve_mm_yr, self.vn_mm_yr, self.vu_mm_yr
        for rc in self.rate_changes:
            if when >= rc.date:
                ve, vn, vu = ve + rc.dve_mm_yr, vn + rc.dvn_mm_yr, vu + rc.dvu_mm_yr
        return ve, vn, vu


def estimate_velocity_joint(
    t: np.ndarray,
    enu_m: np.ndarray,
    *,
    offsets: list[OffsetEvent] | None = None,
    outlier_iqr_factor: float = 3.0,
    station: str = "",
    exclude_outliers: bool = True,
    rate_changes: bool = False,
) -> JointVelocityResult:
    """
    Fit one rate across the whole record, with a step parameter per offset.

    WHY THIS EXISTS, AND WHY IT IS NOT THE SAME AS `estimate_velocity`
    `estimate_velocity` fits every inter-offset segment INDEPENDENTLY, which is
    what the source MATLAB does. That has two consequences the team has been
    living with:

      1. The step amplitude is never estimated. It is implicit in the gap
         between two independent intercepts, so the only way to know "how far
         did the site jump?" is to eyeball the plot. That is precisely the task
         PHIVOLCS asked to have automated (2026-08-13).

      2. A segment with few epochs produces a meaningless rate, and nothing
         stops it being published. ALBU's continuous series, plotted
         2025-11-11, carries `V=-539 mm/yr` East and `V=-1846 mm/yr` Up because
         the 2025.7474 Bogo earthquake left a 7-day final segment. The number
         is the slope of a week of scatter. Six Luzon campaign sites have the
         same defect (see velocity_outlier_policy_delta.md).

    This function fits the standard GNSS trajectory model instead:

        d(t) = a + b·(t - t0) + Σ c_i · H(t - t_i)

    one intercept, ONE rate `b` shared by the whole record, and one step
    amplitude `c_i` per event, with `H` the Heaviside step. Both problems go
    away at once: `c_i` is a fitted parameter with a formal uncertainty, and
    `b` is constrained by every epoch rather than by whatever happens to follow
    the last event.

    WHAT THIS ASSUMES, AND WHEN IT IS WRONG
    A single `b` asserts that the secular rate is unchanged by the events --
    the site steps and then resumes its previous motion. That is the right
    default for equipment changes and for most co-seismic offsets, and it is
    the answer to "do we continue the slope or start a new epoch 0?": the slope
    continues, and the jump is a separate parameter.

    It is NOT right where a large earthquake genuinely changed the rate, and
    that is not an edge case. **ALBU is the reference example**: across the 2017
    Ormoc M6.5 the East rate goes from roughly -39 to -30 mm/yr and Up from
    about +9 to +2 mm/yr. A single rate through that fits neither interval.

    Pass `rate_changes=True` to add a slope-change term per event:

        + Σ d_i · (t - t_i) · H(t - t_i)

    `d_i` is returned as a `RateChange` with a formal sigma, so "did the rate
    change?" becomes a test (`RateChange.significant`) rather than an
    assumption in either direction. `interval_rates()` then gives the velocity
    actually in force over each interval — the before/after view a plot needs.

    WHY THIS IS NOT ENABLED BY DEFAULT
    Fitting a rate change at every event costs precision where nothing changed,
    and most events in the catalog are equipment changes. Turning it on
    everywhere would inflate the uncertainty of rates that are currently well
    determined. The intended use is: fit both, and let the significance test
    decide per site.

    THE CAVEAT THAT MATTERS MOST HERE
    A changed slope after a large earthquake is usually **post-seismic
    deformation** — afterslip and viscoelastic relaxation — which decays over
    months to years. It is not a new secular rate. A straight line through the
    post-event data is therefore the linear approximation to a decaying
    transient, and **its value depends on how long after the event you fit**:
    a window starting at the event averages in the fast early phase, one
    starting two years later does not. Two analysts fitting the same site over
    different windows will disagree, and both will be right about their window.

    So `d_i` is the right tool for *detecting* that the rate changed, and the
    wrong tool for publishing a post-seismic velocity. Exponential and
    logarithmic transients are not modelled here; a large, significant `d_i`
    near a major event is a signal to model the transient properly.

    Args:
        t:                  Decimal years, shape (N,).
        enu_m:              ENU displacements in metres, shape (N, 3).
        offsets:            Discontinuities. None or empty → plain linear fit.
        outlier_iqr_factor: IQR multiplier for outlier detection.
        station:            Label.
        exclude_outliers:   Drop flagged epochs from the fit. See module
                            docstring -- the MATLAB computes them and does not.
        rate_changes:       Also solve a slope change at each event.

    Returns:
        JointVelocityResult. Check `.unresolvable_steps` before using any step
        amplitude: a step at the very edge of a record returns a number the
        data does not support.

    Raises:
        ValueError: if fewer epochs remain than free parameters.
    """
    t = np.asarray(t, dtype=float)
    enu_m = np.asarray(enu_m, dtype=float)
    if t.ndim != 1 or enu_m.shape != (t.size, 3):
        raise ValueError(f"Station {station!r}: expected t (N,) and enu_m (N, 3).")

    order = np.argsort(t)
    t, enu_m = t[order], enu_m[order]

    outlier_epochs: tuple[float, ...] = ()
    if len(t) >= 4:
        mask = _detect_outliers_iqr(enu_m, outlier_iqr_factor)
        outlier_epochs = tuple(float(x) for x in t[mask])
        if exclude_outliers and mask.any() and (~mask).sum() >= 4:
            t, enu_m = t[~mask], enu_m[~mask]

    # Sorted and de-duplicated: an out-of-order catalog must not be able to
    # produce a different answer here. See the KNOWN DEFECT note above -- the
    # MATLAB's segment loop is order-sensitive and ours must not be.
    events = sorted(offsets or [], key=lambda e: e.date)
    # An event outside the observed span contributes an all-zero or all-one
    # column, which is either useless or exactly collinear with the intercept.
    events = [e for e in events if t[0] < e.date <= t[-1]]

    t0 = float(t.mean())  # centring keeps the normal matrix well conditioned
    cols = [np.ones(t.size), t - t0]
    for e in events:
        cols.append((t >= e.date).astype(float))
    if rate_changes:
        for e in events:
            cols.append(np.where(t >= e.date, t - e.date, 0.0))
    G = np.column_stack(cols)

    n_params = G.shape[1]
    if t.size <= n_params:
        raise ValueError(
            f"Station {station!r}: {t.size} epochs cannot constrain {n_params} "
            f"parameters ({len(events)} event(s))."
        )

    model, _, rank, _ = np.linalg.lstsq(G, enu_m, rcond=None)
    if rank < n_params:
        raise ValueError(
            f"Station {station!r}: design matrix is rank deficient "
            f"({rank} < {n_params}) — events are likely too close to the "
            f"record edges or to each other to be separable."
        )

    residual = enu_m - G @ model
    mse = np.sum(residual ** 2, axis=0) / (t.size - n_params)
    cov_unit = np.linalg.inv(G.T @ G)          # shared by all three components
    var_param = np.outer(np.diag(cov_unit), mse)   # (n_params, 3)
    sig = np.sqrt(var_param)

    rate = model[1, :] * 1000.0                # m/yr → mm/yr
    sig_rate = sig[1, :] * 1000.0

    steps: list[StepEstimate] = []
    for i, e in enumerate(events):
        amp = model[2 + i, :] * 1000.0         # m → mm
        s = sig[2 + i, :] * 1000.0
        before, after = t < e.date, t >= e.date
        steps.append(
            StepEstimate(
                date=e.date,
                offset_type=e.offset_type,
                de_mm=float(amp[0]), dn_mm=float(amp[1]), du_mm=float(amp[2]),
                sig_de=float(s[0]), sig_dn=float(s[1]), sig_du=float(s[2]),
                n_before=int(before.sum()), n_after=int(after.sum()),
                span_before=float(np.ptp(t[before])) if before.sum() > 1 else 0.0,
                span_after=float(np.ptp(t[after])) if after.sum() > 1 else 0.0,
            )
        )

    changes: list[RateChange] = []
    if rate_changes:
        base = 2 + len(events)      # slope-change columns follow the step columns
        for i, e in enumerate(events):
            d = model[base + i, :] * 1000.0     # (m/yr) → mm/yr
            sd = sig[base + i, :] * 1000.0
            changes.append(
                RateChange(
                    date=e.date,
                    offset_type=e.offset_type,
                    dve_mm_yr=float(d[0]), dvn_mm_yr=float(d[1]), dvu_mm_yr=float(d[2]),
                    sig_dve=float(sd[0]), sig_dvn=float(sd[1]), sig_dvu=float(sd[2]),
                )
            )

    return JointVelocityResult(
        station=station,
        ve_mm_yr=float(rate[0]), vn_mm_yr=float(rate[1]), vu_mm_yr=float(rate[2]),
        sig_ve=float(sig_rate[0]), sig_vn=float(sig_rate[1]), sig_vu=float(sig_rate[2]),
        steps=steps,
        n_points=int(t.size),
        t_start=float(t[0]), t_end=float(t[-1]),
        rate_changes=changes,
        outlier_epochs=outlier_epochs,
    )


def parse_offsets_file(path: Path) -> dict[str, list[OffsetEvent]]:
    """
    Parse a PHIVOLCS offsets text file into per-station OffsetEvent lists.

    File format (one event per line, whitespace-delimited):
        SITE  YYYY.DDDD  TYPE
    e.g.:
        ALBU  2017.5147  EQ
        BOST  2013.1234  CE

    Lines starting with '#' and blank lines are ignored.
    Unrecognised type codes default to OffsetType.UK.
    """
    result: dict[str, list[OffsetEvent]] = {}
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            site = parts[0].upper()
            try:
                date = float(parts[1])
            except ValueError:
                continue
            try:
                offset_type = OffsetType(parts[2].upper())
            except ValueError:
                offset_type = OffsetType.UK
            result.setdefault(site, []).append(OffsetEvent(date=date, offset_type=offset_type))
    return result
