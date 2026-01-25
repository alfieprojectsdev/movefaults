# ADR-001: Choice of Database Technology for the POGF Centralized Geodetic Database

**Date:** 2026-01-25

**Status:** Proposed

## Context

The Philippine Open Geodesy Framework (POGF) requires a centralized database to store and manage a large and growing volume of geodetic data. This includes:
- Station metadata (location, equipment, etc.).
- Time-series position data from GNSS processing (e.g., daily solutions).
- Pointers to raw observation files (e.g., RINEX).
- Processed data products like velocity fields.

The chosen database must be robust, scalable, open-source, and capable of handling both spatial and time-series data efficiently.

## Decision

We will use a combination of three open-source technologies, built on top of each other:
1.  **PostgreSQL:** As the core relational database management system.
2.  **PostGIS:** As an extension for handling spatial data types and queries (e.g., station locations).
3.  **TimescaleDB:** As an extension for partitioning and managing time-series data (e.g., daily position measurements).

## Alternatives Considered

### 1. MySQL with Spatial Extensions

- **Pros:** Widely used, well-documented.
- **Cons:** Its spatial extensions are generally considered less mature and feature-rich than PostGIS. It lacks a native, well-integrated time-series extension equivalent to TimescaleDB.

### 2. NoSQL Databases (e.g., InfluxDB, MongoDB)

- **InfluxDB:**
  - **Pros:** Highly optimized for time-series data, excellent write performance.
  - **Cons:** Not a general-purpose database. It lacks the relational capabilities needed for managing station metadata and complex relational queries. Joining data between time-series and metadata is difficult.
- **MongoDB:**
  - **Pros:** Flexible schema, good for storing document-like data (like station metadata).
  - **Cons:** Not designed for time-series data and lacks the robust geospatial features of PostGIS. Performing complex relational queries can be inefficient.

### 3. Proprietary Solutions (e.g., Oracle Spatial)

- **Pros:** Commercially supported, mature feature set.
- **Cons:** High licensing costs, risk of vendor lock-in, and less flexibility compared to open-source solutions. This is contrary to the "Open" in POGF.

## Consequences

### Positive

- **Powerful & Integrated:** Provides a single, integrated system with best-in-class support for relational, spatial, and time-series data.
- **Open-Source:** No licensing costs, avoids vendor lock-in, and aligns with the project's open philosophy.
- **Extensible:** PostgreSQL has a vast ecosystem of extensions that can be leveraged for future needs.
- **Strong Community:** Benefits from a large, active community for support and future development.

### Negative

- **Operational Complexity:** Requires expertise in managing PostgreSQL, PostGIS, and TimescaleDB, including tuning and backup strategies for all three.
- **Resource Intensive:** Running all three components on a single server may require significant RAM and CPU resources. Careful capacity planning is needed.
