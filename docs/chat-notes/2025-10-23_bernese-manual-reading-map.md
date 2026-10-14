# Bernese manual reading map (2025-10-23)

*Condensed from an AI chat. See [README](README.md).*

A prioritised reading order for the Bernese GNSS Software 5.2 manual
(`DOCU52`), chosen for automating the processing workflow. The page ranges are
as the assistant read them from the manual's index; check them against the copy
on gps3 (`~/bernese-docs/`) before relying on one.

| priority | section | pages | why |
|---|---|---|---|
| 1 | 22 Bernese Processing Engine (BPE) | 479–530 | the automation system itself: components (22.3), the PCF (22.5), user scripts (22.6), error handling (22.11) |
| 1 | 6 Data preprocessing | 127–168 | RINEX-level preprocessing, clock synchronisation, cycle slips |
| 1 | 24 Data structure | 679–774 | file formats and naming; station files (STA, CRD, ABB, …) in 24.7 |
| 2 | 4 Import and export of external formats | 73–106 | RINEX observation import (4.2) |
| 2 | 21 Menu system | 451–478 | menu variables (21.6), program output and errors (21.7) |
| 2 | 5 Earth orientation, orbits, satellite clocks | 107–125 | the external product dependencies |
| 3 | 7 Parameter estimation | 169–190 | GPSEST output |
| 3 | 9 Combination of solutions | 209–240 | NEQ stacking |
| 3 | 10 Station coordinates and velocities | 241–272 | |
| 4 | 8, 11, 12–15, 23 | | ambiguities, FODITS time-series analysis, atmosphere and biases, processing examples |

Chapter 9 later mattered directly: it is the NEQ combination behind the weekly
stacking and the `MAXPAR` limit (`docs/bernese_maxpar_limit.md`).
