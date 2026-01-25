# Technical Specification: Automated Processing Documentation

**Version:** 1.0

**Date:** 2026-01-25

## 1. Introduction

### 1.1. Purpose

This document outlines the specifications for a set of scripts designed to automatically generate reference documentation from the project's source code and configuration files. The goal is to reduce manual effort and ensure that key reference material is always up-to-date.

### 1.2. Scope

This specification covers the architecture of the generation scripts, the specific types of documentation to be generated, and the method of integration into the main documentation portal's build process.

## 2. System Architecture

The system is composed of a set of small, single-purpose Python scripts. These scripts are not part of the main application runtime; they are development tools used only during the documentation build phase.

A master script, `generate_docs.py`, will orchestrate the execution of the individual generator scripts. This master script will be called as a pre-build step before the static site generator (`mkdocs`) is run.

![Auto-Doc Architecture](https://i.imgur.com/example6.png "Diagram showing a GitHub Actions workflow that first runs `generate_docs.py`. This script produces Markdown files, which are then consumed by `mkdocs build` to create the final HTML site.")

## 3. Features / Generated Documents

### 3.1. Glossary of File Formats

- **Generator Script:** `generate_glossary.py`
- **Input:**
  1.  A manually curated YAML file (`file_formats.yaml`) that maps file extensions to descriptions.
  2.  The script will also scan the project's source and configuration files to find any extensions in use that are *missing* from the YAML file, flagging them as undocumented.
- **Process:** The script parses the YAML file and generates a Markdown file, `glossary.md`, containing a formatted table of all defined file extensions and their descriptions.
- **Output (`glossary.md`):**
  ```markdown
  # File Format Glossary

  | Extension | Description |
  |-----------|-------------|
  | `.sp3`    | Precise satellite orbit file from the IGS. |
  | `.clk`    | Satellite clock correction file. |
  ...
  ```

### 3.2. Command-Line Tool Reference

- **Generator Script:** `generate_cli_reference.py`
- **Input:** A list of the project's command-line entry points (e.g., `igs-downloader`, `timeseries-analyzer`).
- **Process:** The script iterates through the list of tools. For each tool, it executes it with the `--help` flag using the `subprocess` module and captures the output. It then formats this captured text into a Markdown file, `cli_reference.md`, with each tool's help text in a formatted code block.
- **Output (`cli_reference.md`):**
  ```markdown
  # Command-Line Tool Reference

  ## igs-downloader

  ```
  Usage: igs-downloader [OPTIONS]
  ...
  ```

  ## timeseries-analyzer

  ```
  Usage: timeseries-analyzer [OPTIONS]
  ...
  ```
  ```

### 3.3. Configuration File Reference

- **Generator Script:** `generate_config_reference.py`
- **Input:** Paths to the default `config.toml` files for the various project components.
- **Process:** The script parses the TOML files. It iterates through each section and parameter, extracting the parameter name, its default value, and any descriptive comments associated with it. It formats this information into a Markdown file, `config_reference.md`.
- **Output (`config_reference.md`):**
  ```markdown
  # Configuration Reference

  ## ingestion_pipeline.toml

  ### [logging]

  **level**
  : Log level for the application.
  : *Default: "INFO"*

  ...
  ```

## 4. Integration with MkDocs

The automated generation process will be integrated into the main documentation build as a pre-build step.

- **Master Script:** A `generate_docs.py` script will call the individual generator functions in the correct order.
- **Build Command:** The GitHub Actions workflow responsible for building the documentation will be modified to run this script before calling MkDocs.
  - **Example Workflow Step:** `run: python docs/tools/generate_docs.py && mkdocs build`
- **Navigation:** The generated Markdown files (`glossary.md`, `cli_reference.md`, etc.) will be explicitly listed in the `nav` section of the `mkdocs.yml` configuration file so they appear in the portal's navigation menu.

## 5. Technology Stack

- **Language:** Python 3.11+
- **File Parsing:** Standard Python `pathlib` and `re` modules, plus the `toml` library for parsing `.toml` files.
- **Process Execution:** `subprocess` module for capturing CLI help text.
- **Orchestration:** A simple, top-level Python script.
