# GEOCON 2025 VADASE poster: discussion notes

*Condensed 2026-10-14 from a chat export of 2–4 December 2025, which replaced
the raw HTML export kept here until then. The export also held a full
conversation about scaffolding this service (repository layout, `uv` setup,
starter parser code); that part is omitted because the service itself has
superseded it.*

Poster: Bacolcol, T., et al. (2025). *Real-time measurement of GNSS motions
using VADASE: Application to recent earthquakes in the Philippines.* GEOCON 2025.

## Read this before quoting a number

The figures below are **as stated on the poster**, transcribed through the chat.
They have not been re-measured here, and where the repository has measured the
same event it does not always agree:

- The poster's "2023 Mw 7.4 Surigao del Sur" event (PBIS, BOST, 2 December 2023)
  is the one `docs/project_documentation/vadase_threshold_evidence.md` lists as
  **USGS M7.6**. Agency and USGS magnitudes differ; say which you are quoting.
- Detection here means the receiver's VADASE threshold logic as seen in Leica
  SpiderQC, not this service's detector. For how this service's 15 mm/s
  threshold behaves on real captures, use the two evidence notes in
  `docs/project_documentation/` (`vadase_detection_validation.md`,
  `vadase_threshold_evidence.md`).

## The network (July 2025)

- 35 VADASE-capable CORS under the MOVE Faults project, supplemented by selected
  NAMRIA PAGeNet stations.
- Leica GR50 receivers with AR20 antennas; real-time streaming through routers.
- Data flow at the time: receiver → VADASE on the receiver → SpiderQC
  visualisation → NDRRMC dashboard.

## Case studies on the poster

| event | first detection | farthest detection | peak horizontal velocity | peak horizontal displacement |
|---|---|---|---|---|
| 2022 Mw 7.0 Northwest Luzon | 64 s after origin (PAPI, Aparri) | 443 km (PGM2, Gumaca) | 14.2–24.5 mm/s | 28.4–73.7 mm |
| 2023 Mw 7.4 Surigao del Sur | 13 s (PBIS, Bislig, 38 km) | — | 83.49 mm/s (PBIS) | 290.70 mm (PBIS); BOST 129.31 mm |
| 2023 Mw 6.8 Sarangani (63 km deep) | 23 s (MASM, Maasim) | 397 km (BTU2, Butuan) | 8.3–57.8 mm/s | — |
| 2022-08-15 Mw 5.5 Magsaysay, Davao del Sur (smallest detected) | 11 s (DGOS, 24 km; the only station) | — | 33.01 mm/s | 33.35 mm |

Points the poster supports:

- Near-field stations resolve events as small as Mw 5.5; the Magsaysay event
  was seen by one station because southern Mindanao was sparsely instrumented.
- Detection time follows epicentral distance: 11–13 s near the source, about a
  minute at PAPI for the Northwest Luzon event.
- The case for densification, especially in the Visayas and Mindanao.

## Why move off SpiderQC

The reason this service exists, as stated at the start of the conversation:

1. **Licensing** constraints on SpiderQC access.
2. **Latency** between receiver, SpiderQC and the browser.
3. **Cluttered visual layouts** for event review.

Leica documents the LVM and LDM sentences, so the service parses a published
format rather than a reverse-engineered one (`NMEA_SPEC.md`). At the time, new
receiver firmware could email an alert when the VADASE thresholds were exceeded.
The suggestion then was to keep that as an independent backup alert while this
service provides the analysis and dashboards. Whether it was ever configured is
not recorded here.

## Questions to expect, with answers grounded in this repository

- **How does VADASE relate to Bernese processing?** VADASE gives seconds-scale
  displacement for situational awareness; Bernese gives the precise daily
  coordinates behind interseismic velocities and coseismic offsets.
- **Can it detect slow slip or creep?** No. VADASE integrates velocity over
  seconds to minutes; slow processes need daily solutions.
- **What about false alarms?** A threshold on horizontal velocity, measured
  against a quiet-time noise floor of about 0.9 mm/s and against a real
  non-seismic spike at TUA2: see `vadase_threshold_evidence.md`.
- **What happens in a communication outage?** The real-time alert is lost;
  data logged at the receiver can be recovered afterwards.
