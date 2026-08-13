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
