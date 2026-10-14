# VADASE Real-Time Monitor Documentation

Welcome to the technical documentation for the VADASE Real-Time Monitor. This documentation is tailored for STEM graduate students with a background in Python and an interest in GNSS geodesy and seismology.

## Table of Contents

1.  **[Onboarding](ONBOARDING.md)**: The codebase file by file, and the order to read it in. For the architecture notes that span files (receiver mode, import paths, the `src` namespace package), see the "VADASE-RT-Monitor: Deep Architecture" section of `CLAUDE.md` at the repo root.
2.  **[Domain Logic & Processing](DOMAIN_LOGIC.md)**: The `ReceiverMode` state machine, the leaky integrator, and event detection.
3.  **[NMEA Parsers](PARSERS.md)**: LDM/LVM sentence parsing and checksum validation.
4.  **[NMEA Specification](NMEA_SPEC.md)**: The Leica LVM/LDM sentence formats.
5.  **[Data Ingestion & Ports](INGESTION_SYSTEM.md)**: Input adapters, queues and playback strategies.
6.  **[Database Schema](DATABASE_SCHEMA.md)**: The `vadase_*` tables, their TimescaleDB policies, and how the adapter writes.
7.  **[Developer & Researcher Guide](DEVELOPER_GUIDE.md)**: Extending the system and using the scripts for analysis.
8.  **[GEOCON 2025 poster notes](GEOCON_2025_POSTER_NOTES.md)**: The poster's case studies and the reasons for moving off SpiderQC.
9.  **Validation:** what the detector does on real earthquakes is measured in the repo-root `docs/project_documentation/vadase_detection_validation.md` and `vadase_threshold_evidence.md`.

`Architectural Refactor Plan.md` and `../tree.md` are pre-implementation proposals, kept for history.

## Target Audience

This service is designed for researchers and engineers at PHIVOLCS. We assume familiarity with:
- **Python 3.11+**: Specifically `asyncio`, `protocols`, and `type hinting`.
- **GNSS Concepts**: Velocity vs. Displacement, NMEA 0183 standard, and 1Hz sampling rates.
- **Seismology**: Understanding earthquake wave arrivals and horizontal magnitude calculation ($vH = \sqrt{vE^2 + vN^2}$).

## Core Repositories

- Ingestion Engine: `src/`
- Configuration: `config/`
- Recorded captures: `data/` in a working clone, git-ignored (field data, not in the repository)
- Operational Scripts: `scripts/`
- Database migrations: repo-root `migrations/versions/` 010–012
