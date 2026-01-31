import numpy as np
from typing import Dict, Any, Tuple

class VelocityEstimator:
    """
    Estimates station velocities from time series data using least-squares regression.
    """

    @staticmethod
    def estimate_velocity(t: np.ndarray, d: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Estimates velocity for each component (E, N, U).
        
        Args:
            t: Time array (e.g., in decimal years).
            d: Data array of shape (len(t), 3) for (E, N, U).
            
        Returns:
            Tuple of (model, residual, sig_m)
        """
        if len(t) < 2:
            raise ValueError("Need at least 2 data points for velocity estimation.")

        # Center data (optional, but done in legacy script)
        d_centered = (d - np.mean(d, axis=0)) * 100 # cm if input was meters

        G = np.zeros((len(t), 2))
        G[:, 0] = 1
        G[:, 1] = t
        
        # Least squares: m = (G'G)^-1 G'd
        gT = G.T
        gInv = np.linalg.inv(gT @ G)
        gDotInv = gInv @ gT
        
        model = gDotInv @ d_centered
        dhat = G @ model
        residual = d_centered - dhat
        
        # Uncertainty estimation
        rnorm = np.sum(residual**2, axis=0) / (len(t) - 2)
        sig_m = np.sqrt(gInv[1, 1] * rnorm)
        
        return model, residual, sig_m

    @staticmethod
    def detect_outliers_iqr(d: np.ndarray, factor: float = 1.5) -> np.ndarray:
        """
        Detects outliers using the Interquartile Range (IQR) method.
        """
        q1 = np.percentile(d, 25, axis=0)
        q3 = np.percentile(d, 75, axis=0)
        iqr = q3 - q1
        lower_bound = q1 - (factor * iqr)
        upper_bound = q3 + (factor * iqr)
        
        outliers = (d < lower_bound) | (d > upper_bound)
        return np.any(outliers, axis=1)
