# VADASE Physics Engine: Drift Control & Integration

## 1. The Challenge (Velocity Drift)
The VADASE system receives **Velocity** data ($v$) at 1Hz or 10Hz and must calculate **Displacement** ($d$).
Mathematically, displacement is the integral of velocity:
$$d(t) = \int_{0}^{t} v(\tau) d\tau$$

In a discrete real-time system, this is a cumulative sum:
$$d_{t} = d_{t-1} + (v_t \times \Delta t)$$

### The Problem: Random Walk
All GNSS velocity solutions contain **zero-mean noise** (white noise). However, the **integral of white noise is a random walk (red noise)**.
Even tiny sensor biases ($0.001 m/s$) accumulate indefinitely over time ($3.6 m/hr$), causing the calculated displacement to wander far from zero, making long-term monitoring impossible.

## 2. Solution: The Leaky Integrator (High-Pass Filter)
To counteract this drift, we implement a **Leaky Integrator**. This acts as a High-Pass Filter, allowing transient events (earthquakes) to pass while suppressing low-frequency drift (DC bias).

### The Formula
Instead of pure integration, we apply a `decay_factor` ($0 < \lambda < 1$) to the accumulated displacement at every step:

$$d_{t} = (d_{t-1} \times \lambda) + (v_t \times \Delta t)$$

*   **$\lambda = 1.0$**: Pure Integration (Drifts indefinitely).
*   **$\lambda = 0.99$**: Weak Filter (Suitable for 10Hz).
*   **$\lambda = 0.95$**: Strong Filter (Maximum centering force, suitable for detecting strong motion in 1Hz data).

This "leak" ensures that in the absence of new velocity input, the displacement asymptotically returns to zero.

## 3. Vector Component Integration (Avoiding "Odometer Effect")
A critical aspect of the physics engine is **Component-Based Integration**.

### The "Odometer Effect" Bug
Initially, the system calculated the Scalar Speed ($|v|$) and integrated it.
Since Speed is strictly positive ($|v| \ge 0$), the integral effectively became an odometer—only adding distance, never subtracting it. This caused the displacement to rise monotonically regardless of the decay factor.

### The Fix: Coordinate Splitting
We must integrate each spatial component independently to allow positive and negative velocities to cancel each other out (oscillation).

1.  **Parse Vectors**: Extract signed components $v_{East}$, $v_{North}$, $v_{Up}$.
2.  **Integrate Separately**:
    *   $d_{East} \leftarrow (d_{East} \times \lambda) + (v_{East} \times \Delta t)$
    *   $d_{North} \leftarrow (d_{North} \times \lambda) + (v_{North} \times \Delta t)$
    *   $d_{Up} \leftarrow (d_{Up} \times \lambda) + (v_{Up} \times \Delta t)$
3.  **Compute Magnitude**:
    Only *after* integration do we calculate the scalar magnitude for event detection:
    $$D_{total} = \sqrt{d_{East}^2 + d_{North}^2}$$

This approach ensures that an oscillation (e.g., ground shaking East then West) results in a net displacement near zero, accurately representing the physical event physics.
