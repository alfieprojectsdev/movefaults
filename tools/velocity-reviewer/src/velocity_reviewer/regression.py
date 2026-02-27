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
    Returns timestamps of points whose residuals exceed threshold × IQR.

    Operates on the combined 3D residual magnitude across E, N, U so that a
    point is flagged if it is an outlier in *any* component.
    """
    if len(residuals) < 4:
        return []
    q1, q3 = np.percentile(residuals, [25, 75])
    iqr = q3 - q1
    if iqr == 0.0:
        return []
    mask = np.abs(residuals) > threshold * iqr
    return [float(ts) for ts in t[mask]]


def process_site(
    t: np.ndarray,
    e: np.ndarray,
    n: np.ndarray,
    u: np.ndarray,
) -> dict:
    """
    Full processing pipeline for one site: demean → cm → regression → IQR detection.

    Returns a dict ready for JSON serialisation by the FastAPI endpoint.
    """
    e_cm = (e - e.mean()) * 100
    n_cm = (n - n.mean()) * 100
    u_cm = (u - u.mean()) * 100

    e_fit, ve = fit_segment(t, e_cm)
    n_fit, vn = fit_segment(t, n_cm)
    u_fit, vu = fit_segment(t, u_cm)

    # Use combined 3D residual magnitude for outlier detection so that
    # a spike in any single component gets flagged.
    combined_res = np.sqrt((e_cm - e_fit) ** 2 + (n_cm - n_fit) ** 2 + (u_cm - u_fit) ** 2)
    auto_outliers = iqr_outliers(t, combined_res)

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
