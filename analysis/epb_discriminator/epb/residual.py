"""Weighted least squares and the RAIM-style residual statistics.

All functions take W as the weight VECTOR (diagonal weights), and y as either
one epoch (N,) or many (T, N). Units are whatever y is in (m/s here).

Vocabulary is Baarda's: the global test (chi2 of the residuals), data snooping
(normalized residual w_i), minimal detectable bias (MDB). Same mathematics as
receiver autonomous integrity monitoring (RAIM).
"""

from __future__ import annotations

import numpy as np
from scipy import stats


def _normal(H, W):
    N = H.T @ (W[:, None] * H)
    return np.linalg.inv(N)


def wls(H: np.ndarray, W: np.ndarray, y: np.ndarray):
    """Returns (x_hat, r, Qx). x_hat is (4,) or (T, 4); r matches y; Qx is (4, 4)."""
    Qx = _normal(H, W)
    G = Qx @ H.T * W  # (4, N): x_hat = G @ y
    x_hat = y @ G.T
    r = y - x_hat @ H.T
    return x_hat, r, Qx


def chi2_norm(r: np.ndarray, W: np.ndarray, dof: int):
    """sum(w r^2) / dof, ~ chi2(dof)/dof under the null. Scalar or (T,)."""
    return (r**2 @ W) / dof


def residual_cofactor(H: np.ndarray, W: np.ndarray) -> np.ndarray:
    """Q_r = W^-1 - H Qx H^T, the covariance of the residuals (N, N)."""
    return np.diag(1.0 / W) - H @ _normal(H, W) @ H.T


def normalized_resid(H: np.ndarray, W: np.ndarray, r: np.ndarray):
    """Baarda's w_i = r_i / sqrt(Q_r,ii). N(0,1) per satellite under the null."""
    return r / np.sqrt(np.diag(residual_cofactor(H, W)))


def mdb(H: np.ndarray, W: np.ndarray, alpha: float = 0.001, power: float = 0.8):
    """Minimal detectable bias per satellite (1-dof w-test), same units as y. (N,).

    MDB_i = delta0 / sqrt(w_i^2 Q_r,ii), delta0 = z(1-alpha/2) + z(power).
    A satellite whose residual cofactor is near zero has an MDB near infinity:
    its bias is absorbed by the solution and cannot be seen.
    """
    delta0 = stats.norm.ppf(1 - alpha / 2) + stats.norm.ppf(power)
    qr = np.diag(residual_cofactor(H, W))
    with np.errstate(divide="ignore"):
        return delta0 / np.sqrt(W**2 * qr)


def leakage(H: np.ndarray, W: np.ndarray) -> np.ndarray:
    """(N, 4): solution error [vE, vN, vU, clock] per unit bias on satellite i.

    This is where a bubble fakes a quake: the part of a bias the residual does
    not show goes into the velocity.
    """
    return (_normal(H, W) @ H.T * W).T


def station_level(H: np.ndarray, W: np.ndarray, y: np.ndarray, dof: int):
    """What an LVM-style stream would carry for the same epochs.

    Velocity ENU, its 3x3 covariance scaled by the a-posteriori variance factor,
    a 3-D quality cq = sqrt(trace), and the satellite count. No per-satellite
    information survives, which is the point of the comparison.
    """
    x_hat, r, Qx = wls(H, W, y)
    s2 = chi2_norm(r, W, dof)
    cov = np.multiply.outer(s2, Qx[:3, :3])
    return {
        "v": x_hat[..., :3],
        "cov": cov,
        "cq": np.sqrt(np.trace(cov, axis1=-2, axis2=-1)),
        "n_sats": np.full(np.shape(s2), H.shape[0]),
    }
