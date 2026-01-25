# Technical Specification: Automated IGS Product Downloader

**Version:** 1.0

**Date:** 2026-01-25

## 1. Introduction

### 1.1. Purpose

This document details the technical specifications for the Automated IGS Product Downloader. This is a crucial utility designed to reliably download the various data products from the International GNSS Service (IGS) and other public data centers that are required for high-precision GNSS data processing.

### 1.2. Scope

This specification covers the tool's features, architecture, command-line interface, and technology stack. The tool is designed as a standalone command-line application to be run on a schedule.

## 2. Architecture

The system is a standalone Python application intended to be executed via a scheduler (e.g., `cron`) or manually from the command line. It operates based on a configuration file that defines the products to be downloaded, their remote sources (including mirrors), and the local storage structure. Its architecture is simple, robust, and focused on a single task: populating a local repository with external products.

## 3. Features

### 3.1. Product Support

The tool will be configurable to download a wide variety of standard GNSS products, including but not limited to:
- Precise orbits (`.sp3`)
- Satellite clock files (`.clk`)
- Earth Rotation Parameters (`.erp`)
- Ionosphere models (`.ion`, `.bsx`)
- Differential Code Biases (`.bsx`)
- Station coordinates (`.snx`)

### 3.2. Resilient Downloading

- **Retry Logic:** If a download from a specific URL fails due to a transient network error (e.g., timeout, 5xx server error), the tool will automatically retry the download. The number of retries and the delay between them will be configurable (e.g., exponential backoff).
- **Mirror Fallback:** The configuration allows for a list of mirror URLs for each product type. If a download fails from the primary URL after all retries are exhausted, the tool will automatically attempt to download from the next mirror in the list.

### 3.3. Data Integrity

- **Checksum Validation:** If a data center provides checksum files (e.g., `.md5`, `.sha256`), the tool will be able to download the checksum and verify the integrity of the downloaded product file. The download will be marked as failed if the checksum does not match.
- **Intelligent Downloading:** Before attempting a download, the tool will check if the target file already exists in the local repository. If it exists and is valid (e.g., non-zero size, or passes a checksum re-validation), the download will be skipped to save bandwidth. This can be overridden with a `--force` flag.

### 3.4. Local Storage

- **Directory Structure:** The tool will save the downloaded files into a clean, logical, and configurable directory structure. The default structure will be based on product type, year, and day-of-year (DOY).
- **Example:** `/data/igs/products/{YYYY}/{DOY}/codg{GPS_WEEK}{DOW}.sp3.Z`

## 4. Command-Line Interface (CLI)

The tool will be driven by a simple and intuitive CLI, built using a library like `click` or `argparse`.

- **`igs-downloader --date YYYY-MM-DD [--product-type <type>]`**
  - Download products for a specific calendar date. Can be limited to one product type (e.g., `final`, `rapid`).

- **`igs-downloader --days-ago <n> [--product-type <type>]`**
  - A convenience command to download products for `n` days before the current date.

- **`igs-downloader --gps-week <wwww> --gps-dow <d>`**
  - Download products for a specific GPS week and day of the week.

- **`igs-downloader --config <path/to/config.toml>`**
  - Specify a custom configuration file.

- **`--force`**
  - A flag to force re-downloading of all files, even if they already exist locally.

## 5. Technology Stack

- **Language:** Python 3.11+
- **HTTP/FTP Communication:** `requests` library.
  - **Justification:** It provides a simple, high-level interface for making HTTP and FTP requests, with built-in support for connection pooling, session management, and robust error handling.
- **CLI Framework:** `click`.
  - **Justification:** A modern and easy-to-use library for creating beautiful and composable command-line interfaces.
- **Configuration:** TOML file.
  - **Justification:** Provides a clear and structured way to define the complex list of products and their mirror URLs.

## 6. Error Handling

- The tool will gracefully handle common network errors (timeouts, DNS failures, HTTP error codes).
- All actions, including successful downloads, failed attempts, retries, and checksum mismatches, will be logged to `stdout` (and optionally to a file) with clear, informative messages.
- The tool will exit with a non-zero status code if any of the requested products could not be successfully downloaded and validated, making it easy for scheduling systems like `cron` to detect failures.
