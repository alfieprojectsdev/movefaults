# Technical Specification: Unified Data Ingestion Pipeline

**Version:** 1.0

**Date:** 2026-01-25

## 1. Introduction

### 1.1. Purpose

This document describes the technical specifications for the Unified Data Ingestion Pipeline. The pipeline is responsible for automatically collecting, validating, standardizing, and loading geodetic data from various partner agencies into the Centralized Geodetic Database.

### 1.2. Scope

This specification covers the pipeline's architecture, its core stages, the technology stack, and its error handling and configuration mechanisms.

## 2. System Architecture

The pipeline is a service-oriented system designed for modularity and scalability. It runs independently of other POGF components but communicates with the Centralized Geodetic Database.

The architecture consists of four main logical components orchestrated by a task queue:

1.  **Scanner:** Detects new data files from configured sources (e.g., FTP servers, local directories).
2.  **Validator:** Performs integrity and format checks on the incoming data.
3.  **Standardizer:** Processes and reformats the data and metadata to conform to the POGF standard.
4.  **Loader:** Inserts the standardized data and metadata into the Centralized Geodetic Database.

These components are implemented as tasks within a Celery distributed task queue, allowing for parallel processing, retries, and scalability.

![Ingestion Pipeline Architecture](https://i.imgur.com/example2.png "Diagram showing data flowing from sources (FTP, HTTP) to the Scanner, which places tasks in a queue. Workers (Validator, Standardizer, Loader) pick up tasks and interact with the Database.")

## 3. Pipeline Stages

The ingestion process for a given data file proceeds through the following stages:

### 3.1. Stage 1: Scanning

- **Responsibility:** To discover new data files from heterogeneous sources.
- **Implementation:** A set of source-specific scanners will run on a schedule (e.g., every 15 minutes). For local file systems, `watchdog` can be used for real-time detection. For remote sources (FTP, S3), the scanner will list remote files and compare them against a list of already-processed files.
- **Output:** A "new file found" event is published to the task queue, triggering the validation stage.

### 3.2. Stage 2: Validation

- **Responsibility:** To ensure data quality and integrity before processing.
- **Implementation:** This task consumes "new file found" events. It performs the following checks:
  - **File Integrity:** Verifies file checksums (MD5/SHA256) if provided.
  - **Format Validation:** Uses a tool like `gfzrnx` or an equivalent library to check for valid RINEX 2/3/4 format.
  - **Metadata Consistency:** Checks that the filename and RINEX header information (station code, date) are consistent.
- **Output:** If validation succeeds, the task is passed to the Standardization stage. If it fails, the file is moved to a quarantine directory, and an error is logged.

### 3.3. Stage 3: Standardization

- **Responsibility:** To convert data into a consistent, project-wide format.
- **Implementation:** This task performs the following actions:
  - **File Naming:** Renames files to the standard POGF naming convention (e.g., `SSSSDDDY.YYo`).
  - **Metadata Extraction:** Parses the RINEX header to extract key metadata (receiver type, antenna type, sampling interval, etc.).
  - **Data Structuring:** Creates the data records to be inserted into the database tables (`rinex_files`, etc.).
- **Output:** A structured data object is passed to the Loader stage.

### 3.4. Stage 4: Loading

- **Responsibility:** To load the standardized data and metadata into the database.
- **Implementation:** This task consumes the structured data object from the Standardizer. It uses SQLAlchemy to perform the following database operations within a single transaction:
  - Insert a new record into the `rinex_files` table.
  - Update the `stations` table if new station information is discovered.
- **Output:** A success or failure log message. On failure (e.g., database connection error), Celery's retry mechanism will be triggered.

## 4. Technology Stack

- **Language:** Python 3.11+
- **Task Queue:** Celery with RabbitMQ or Redis as the message broker.
  - **Justification:** Provides a robust, scalable, and asynchronous architecture for handling long-running I/O-bound tasks.
- **Database Interaction:** SQLAlchemy 2.0 (Core and ORM).
  - **Justification:** A mature and powerful library that provides a consistent, high-level API for database interactions, abstracting away SQL dialects.
- **Data Manipulation:** Pandas.
  - **Justification:** Useful for handling and validating tabular metadata if extracted in bulk.
- **Configuration:** TOML files.
  - **Justification:** A clear and unambiguous format for defining data sources, validation rules, and other pipeline parameters.

## 5. Error Handling and Logging

- **Logging:** All pipeline stages will log detailed information, including file paths, actions taken, and timing, using Python's standard `logging` module.
- **Quarantine:** Files that fail the validation stage will be moved to a designated quarantine directory for manual inspection.
- **Retries:** I/O-bound tasks that may fail due to transient issues (e.g., network errors, database deadlocks) will be configured with an exponential backoff retry policy in Celery.

## 6. Configuration

The pipeline will be configured via a `config.toml` file, allowing operators to manage its behavior without code changes.

```toml
# Example config.toml

[logging]
level = "INFO"
file = "/var/log/ingestion_pipeline.log"

[[sources]]
name = "phivolcs_ftp"
type = "ftp"
host = "ftp.phivolcs.dost.gov.ph"
user = "anonymous"
path = "/pub/gnss/rinex/daily"
# ... other source-specific settings

[[sources]]
name = "local_usb_drop"
type = "local"
path = "/mnt/usb_data_drop"
# ...
```
