"""
Least-squares regression and IQR outlier detection for GNSS time series.

Ports the numpy matrix approach from analysis/02 Time Series/Outliers-input name.py
verbatim, with the same data transformation (mean-centre, convert to cm) applied
before fitting.
"""

import numpy as np


def fit_segment(t: np.ndarray, d: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Least-squares linear fit to one ENU component.

    d must already be mean-centred and in cm.
    Returns (predicted_values, velocity_mm_per_yr).
    """
    if len(t) < 2:
        return np.zeros_like(d), 0.0
    G = np.column_stack([np.ones(len(t)), t])
    model, *_ = np.linalg.lstsq(G, d, rcond=None)
    predicted = G @ model
    velocity_mm_yr = model[1] * 10  # cm/yr → mm/yr
    return predicted, float(velocity_mm_yr)


def iqr_outliers(t: np.ndarray, residuals: np.ndarray, threshold: float = 3.0) -> list[float]:
    """
    Timestamps of points outside the Tukey fences of their residuals.

    `residuals` is (n,) or (n, k), one column per component. A point is flagged
    when any column falls below Q1 - threshold*IQR or above Q3 + threshold*IQR
    of that column: the fences MATLAB's rmoutliers('quartiles') and
    pogf_geodetic_suite.timeseries.analysis use, applied here to residuals from
    the linear fit rather than to raw positions. A column with zero spread flags
    nothing.
    """
    r = np.asarray(residuals, dtype=float)
    if r.ndim == 1:
        r = r[:, None]
    if len(r) < 4:
        return []
    q1, q3 = np.percentile(r, [25, 75], axis=0)
    iqr = q3 - q1
    outside = (r < q1 - threshold * iqr) | (r > q3 + threshold * iqr)
    mask = np.any(outside & (iqr > 0), axis=1)
    return [float(ts) for ts in t[mask]]


def process_site(
    t: np.ndarray,
    e: np.ndarray,
    n: np.ndarray,
    u: np.ndarray,
) -> dict:
    """
    Full processing for one site: demean, convert to cm, fit, suggest outliers.

    Returns a dict ready for JSON serialisation by the FastAPI endpoint.
    """
    e_cm = (e - e.mean()) * 100
    n_cm = (n - n.mean()) * 100
    u_cm = (u - u.mean()) * 100

    e_fit, ve = fit_segment(t, e_cm)
    n_fit, vn = fit_segment(t, n_cm)
    u_fit, vu = fit_segment(t, u_cm)

    # One column per component, so a spike in any single component is flagged.
    residuals = np.column_stack([e_cm - e_fit, n_cm - n_fit, u_cm - u_fit])
    auto_outliers = iqr_outliers(t, residuals)

    return {
        "t": t.tolist(),
        "e": e_cm.tolist(),
        "n": n_cm.tolist(),
        "u": u_cm.tolist(),
        "e_fit": e_fit.tolist(),
        "n_fit": n_fit.tolist(),
        "u_fit": u_fit.tolist(),
        "ve": round(ve, 1),
        "vn": round(vn, 1),
        "vu": round(vu, 1),
        "iqr_outliers": auto_outliers,
    }
