# Domain Logic & Processing

The heart of the monitor resides in `src/domain/processor.py`. This component handles the transformation of raw GNSS measurements into actionable displacement time-series and earthquake alerts.

## 1. VADASE Core Concept

VADASE (Variometric Approach for Displacement Analysis Stand-alone Engine) calculates instantaneous velocity and displacement from high-frequency GNSS observations without requiring a reference station.
- **LVM (Leica Velocity Measurement)**: Instantaneous velocity ($m/s$).
- **LDM (Leica Displacement Measurement)**: Integrated displacement ($m$).

## 2. Horizontal Magnitude Calculation

For seismic monitoring, we focus on the horizontal plane. The monitor calculates the horizontal magnitude ($vH$) for every epoch:

$$vH = \sqrt{vE^2 + vN^2}$$

where $vE$ is the velocity in the East-West direction and $vN$ is the velocity in the North-South direction.

## 3. "Smart Integration" (Leaky Integrator)

Some legacy GNSS receivers fail to provide stable LDM (displacement) sentences, outputting zero or identical-to-velocity values. To solve this, the monitor implements a **manual integration** fallback.

### The Algorithm
When displacement data is detected as "bad" (i.e., identical to velocity), the system switches to integrating the velocity stream:

$$d_{t} = (d_{t-1} \times \lambda) + (v_{t} \times \Delta t)$$

- $d_t$: Calculated displacement at time $t$.
- $v_t$: Instantaneous velocity.
- $\Delta t$: Time delta between epochs (nominally 1 second).
- $\lambda$: **Decay Factor** (nominally 1.0). A factor $< 1.0$ implements a high-pass filter to prevent long-term drift (Brownian motion).

### Automatic Latching
The system uses a "Streak" mechanism to detect bad data:
- **Bad Streak**: If $v_E = d_E$ for 5 consecutive epochs, the system "latches" into manual integration mode.
- **Good Streak**: If $v_E \neq d_E$ for 10 consecutive epochs, the system "unlatches" and returns to using the receiver's proprietary LDM data.

## 4. Earthquake Event Detection

The monitor maintains an internal state machine for each station to track seismic events.

1.  **Detection**: If $vH > \text{threshold}$ (nominally 15 mm/s), an event is marked as **Active**.
2.  **Peak Tracking**: During an active event, the monitor tracks the `peak_velocity` and `peak_displacement`.
3.  **Termination**: When $vH$ stays below the threshold for a period, the event is closed, and a summary record is written to the `event_detections` table.

## 5. Quality Filtering

The monitor respects the VADASE quality flags:
- `min_completeness`: LDM sentences with an `overall_completeness` below 50% are discarded to prevent "jumps" during signal re-acquisition.
- `delta_t` limit: Integration only occurs if the time gap between velocity samples is $< 5.0$ seconds. This prevents massive displacement spikes after a communication outage.
