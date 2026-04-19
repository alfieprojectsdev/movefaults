# VADASE Real-Time Monitor Documentation

Welcome to the technical documentation for the VADASE Real-Time Monitor. This documentation is tailored for STEM graduate students with a background in Python and an interest in GNSS geodesy and seismology.

## Table of Contents

1.  **[System Architecture](ARCHITECTURE.md)**: High-level overview of the hexagonal architecture and async ingestion pipeline.
2.  **[Domain Logic & Processing](DOMAIN_LOGIC.md)**: Detailed breakdown of the VADASE algorithm, "Smart Integration," and earthquake detection thresholds.
3.  **[NMEA Parsers](PARSERS.md)**: Technical specification of the LDM/LVM sentence parsing and checksum validation.
4.  **[Data Ingestion & Ports](INGESTION_SYSTEM.md)**: How the system handles 35+ concurrent TCP streams using asynchronous programming.
5.  **[Database Schema](DATABASE_SCHEMA.md)**: TimescaleDB optimizations for high-frequency (1Hz) time-series data storage.
6.  **[Validation & Verification](VALIDATION_GUIDE.md)**: Reproduction steps for historical earthquake events.
7.  **[Developer & Researcher Guide](DEVELOPER_GUIDE.md)**: Guide on extending the system and using scripts for data analysis.

## Target Audience

This service is designed for researchers and engineers at PHIVOLCS. We assume familiarity with:
- **Python 3.11+**: Specifically `asyncio`, `protocols`, and `type hinting`.
- **GNSS Concepts**: Velocity vs. Displacement, NMEA 0183 standard, and 1Hz sampling rates.
- **Seismology**: Understanding earthquake wave arrivals and horizontal magnitude calculation ($vH = \sqrt{vE^2 + vN^2}$).

## Core Repositories

- Ingestion Engine: `src/`
- Configuration: `config/`
- Historical Data: `data/`
- Operational Scripts: `scripts/`
