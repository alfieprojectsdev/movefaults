# Technical Specification: Centralized Geodetic Database

**Version:** 1.0

**Date:** 2026-01-25

## 1. Introduction

### 1.1. Purpose

This document outlines the technical specifications for the Centralized Geodetic Database, which will serve as the foundation for the Philippine Open Geodesy Framework (POGF). The database will act as the single source of truth for all geodetic data and processed products, ensuring data integrity, accessibility, and long-term preservation.

### 1.2. Scope

This specification covers the database's architecture, schema design, technology stack, and data management policies. It is intended for the engineering team responsible for building and maintaining the POGF infrastructure.

### 1.3. Definitions

- **POGF:** Philippine Open Geodesy Framework
- **GNSS:** Global Navigation Satellite System
- **RINEX:** Receiver Independent Exchange Format
- **PostGIS:** Spatial database extender for PostgreSQL
- **TimescaleDB:** Time-series database extension for PostgreSQL

## 2. System Architecture

The Centralized Geodetic Database is a core component of the POGF, interacting with several other systems:

- **Data Ingestion Pipeline:** This service will be the primary writer to the database, pushing validated and standardized data from various sources.
- **Automated Processing Workflow:** The Bernese automation scripts will read raw data and station metadata from the database and write processed results (e.g., time series, velocity fields) back to it.
- **Public Data Portal & API:** The web front-end and public API will be the primary consumers (readers) of the database, providing data to end-users.

The architecture is centered around a PostgreSQL server enhanced with PostGIS for spatial capabilities and TimescaleDB for efficient time-series data management.

![System Architecture Diagram](https://i.imgur.com/example.png "A high-level diagram showing the database at the center, with arrows indicating data flow from the Ingestion Pipeline and to the Public Portal/API.")

## 3. Database Schema Design

The schema is designed to be relational, normalized, and optimized for common query patterns.

### 3.1. Core Tables

- **`stations`**
  - `id`: `SERIAL PRIMARY KEY`
  - `station_code`: `VARCHAR(10) UNIQUE NOT NULL` - e.g., 'PHIV'
  - `name`: `VARCHAR(255)`
  - `location`: `GEOMETRY(Point, 4326)` - WGS 84 coordinate, managed by PostGIS.
  - `elevation`: `FLOAT`
  - `agency`: `VARCHAR(50)` - e.g., 'PHIVOLCS', 'NAMRIA'
  - `status`: `VARCHAR(50)` - e.g., 'active', 'decommissioned'
  - `date_installed`: `DATE`
  - `metadata_json`: `JSONB` - For storing other relevant station metadata.

- **`rinex_files`**
  - `id`: `BIGSERIAL PRIMARY KEY`
  - `station_id`: `INTEGER REFERENCES stations(id)`
  - `filepath`: `VARCHAR(1024) UNIQUE NOT NULL` - Path in the object storage/file system.
  - `start_time`: `TIMESTAMPTZ NOT NULL`
  - `end_time`: `TIMESTAMPTZ NOT NULL`
  - `sampling_interval`: `FLOAT`
  - `receiver_type`: `VARCHAR(100)`
  - `antenna_type`: `VARCHAR(100)`
  - `hash_md5`: `VARCHAR(32)`
  - `date_added`: `TIMESTAMPTZ DEFAULT NOW()`

- **`timeseries_data`** (This will be a TimescaleDB Hypertable)
  - `time`: `TIMESTAMPTZ NOT NULL`
  - `station_id`: `INTEGER REFERENCES stations(id)`
  - `north_mm`: `FLOAT`
  - `east_mm`: `FLOAT`
  - `up_mm`: `FLOAT`
  - `sigma_n_mm`: `FLOAT`
  - `sigma_e_mm`: `FLOAT`
  - `sigma_u_mm`: `FLOAT`
  - `solution_id`: `VARCHAR(50)` - Identifier for the processing run that produced this data.
  - `PRIMARY KEY (time, station_id)`

- **`velocity_products`**
  - `id`: `SERIAL PRIMARY KEY`
  - `station_id`: `INTEGER REFERENCES stations(id)`
  - `vel_north_mm_yr`: `FLOAT`
  - `vel_east_mm_yr`: `FLOAT`
  - `vel_up_mm_yr`: `FLOAT`
  - `solution_id`: `VARCHAR(50)`
  - `date_computed`: `TIMESTAMPTZ`

### 3.2. Entity-Relationship Diagram

(A textual description of the ERD, showing relationships between tables, e.g., one-to-many from `stations` to `rinex_files` and `timeseries_data`.)

## 4. Technology Stack

- **Database:** PostgreSQL 15+
  - **Justification:** Robust, open-source, and has a rich ecosystem of extensions. It provides the stability and feature set required for a mission-critical data store.
- **Spatial Extension:** PostGIS 3+
  - **Justification:** The de-facto standard for spatial data in open-source databases. It is essential for storing station locations and performing geographic queries.
- **Time-Series Extension:** TimescaleDB 2.5+
  - **Justification:** Provides automatic partitioning, improved write performance, and specialized functions for time-series data, which is crucial for handling the large volume of GNSS time series.

## 5. Data Management

### 5.1. Backup and Recovery

- **Strategy:** Daily full backups and continuous WAL (Write-Ahead Logging) archiving using `pg_basebackup` and `wal-g`.
- **Recovery:** Point-in-Time Recovery (PITR) will be enabled to allow restoration to any point in the last 30 days.

### 5.2. Security and Access Control

- **Access:** Database access will be strictly controlled via user roles. The Ingestion Pipeline will have write access, while the Public Portal will have read-only access. Direct user access will be prohibited.
- **Authentication:** All connections must use SSL/TLS.

### 5.3. Data Retention

- **Policy:** Raw RINEX file metadata and processed time-series data will be stored indefinitely. Stale or superseded processed products may be archived after 5 years.
