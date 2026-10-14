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

## 3. Receiver mode and the leaky integrator

Leica receivers behave in three ways, and the monitor has to tell them apart:

1. **Quiet time:** velocity is the default output and the displacement fields
   echo the velocity values (`vel == disp`). This is normal receiver behaviour,
   not a fault.
2. **Event time:** the receiver's internal threshold is crossed and it sends a
   real integrated displacement (`vel != disp`).
3. **Anomalous spikes:** how the receiver behaves during a non-seismic
   excursion is not established empirically.

So for every LDM epoch, `IngestionCore` compares it with the latest LVM epoch
and classifies the pair (`_classify_signal`):

| signal | condition |
|---|---|
| `IDENTICAL` | `vE == dE` and `vN == dN` (to 1e-9) |
| `HIGH_VEL_NEQ` | different, and horizontal velocity is at or above the station's threshold |
| `LOW_VEL_NEQ` | different, and horizontal velocity is below the threshold |

### The state machine (`ReceiverMode`, in both directions)

Two modes: **RECEIVER** (use the receiver's displacement) and **MANUAL**
(integrate velocity ourselves). Streak counters drive the transitions
(`_update_mode`):

| from | to | after | why |
|---|---|---|---|
| RECEIVER | MANUAL | `STREAK_THRESHOLD` = **5** consecutive `IDENTICAL` | quiet time: the displacement fields are echoes |
| RECEIVER | MANUAL, integration **frozen** | `SUSPECT_THRESHOLD` = **3** consecutive `LOW_VEL_NEQ` | displacement disagrees with velocity while nothing is moving: treated as scintillation |
| MANUAL | RECEIVER | `GOOD_THRESHOLD` = **30** consecutive `HIGH_VEL_NEQ` | the receiver is reporting a real event displacement |

While integration is frozen, velocity epochs do not accumulate into the
integrated displacement. A `HIGH_VEL_NEQ` or `IDENTICAL` epoch unfreezes it.

Each displacement row records which decision produced it in
`displacement_source`: `INTEGRATOR` (MANUAL mode), `RECEIVER_SUSPECT` (RECEIVER
mode with a suspect streak in progress) or `RECEIVER`.

`--force-integration` on the replay scripts, or `force_integration=True`,
starts a station in MANUAL instead of RECEIVER.

### The integrator

In MANUAL mode the displacement written is the integrated velocity:

$$d_{t} = (d_{t-1} \times \lambda) + (v_{t} \times \Delta t)$$

- $\lambda$ is `decay_factor`. It **defaults to 1.0**, which is no leak at all
  (pure integration). A value below 1 is a high-pass filter that bleeds off
  accumulated drift; it is opt-in per station through `filter: {enabled: true,
  decay: 0.99}` in `stations.yml`.
- Integration happens only when $0 < \Delta t < 5$ s, so an outage cannot
  inject a step. The last velocity time still updates, so the next gap is
  measured correctly.

## 4. Event detection

Per station, on every **velocity** epoch (`check_event_threshold`):

1. **Start:** horizontal velocity above `threshold_mm_s` (15.0 mm/s for every
   configured station) opens an event, and records its start time and peak.
2. **Peaks:** while it is open, the peak horizontal velocity and (from LDM
   epochs) the peak horizontal displacement are tracked.
3. **End:** the **first** velocity epoch at or below the threshold closes it.
   There is no hold-off period. The summary goes to `write_event_detection`
   (the `vadase_events` table).

What this threshold does and does not separate on real data is measured in
`docs/project_documentation/vadase_detection_validation.md` and
`vadase_threshold_evidence.md` at the repo root.

## 5. Quality filtering

- **Completeness:** an LDM sentence whose `overall_completeness` is below
  `min_completeness` (0.5) is dropped before any processing.
- **Gap limit:** the 5-second integration window above.
- **Checksums:** a sentence that fails the XOR checksum raises
  `NMEAChecksumError`; the core logs `checksum_error` and skips it.
