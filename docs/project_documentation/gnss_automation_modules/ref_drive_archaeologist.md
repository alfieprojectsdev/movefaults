# Reference: Drive Archaeologist (for Smart USB Data Ingestion)

**Deliverable originally:** 2.1: Smart USB Data Ingestion System

**Replaced by:** Existing project `/home/finch/repos/drive-archaeologist/`

## Purpose

The "Smart USB Data Ingestion System" deliverable, which aimed to automate the process of collecting, scanning, and organizing data from USB drives, is superseded by the existing `Drive Archaeologist` project. This project already provides a robust solution for excavating data from old hard drives and USBs, including features directly applicable to our needs.

## Drive Archaeologist Overview

The `Drive Archaeologist` project (located at `/home/finch/repos/drive-archaeologist/`) is a cross-platform CLI scanner designed to automatically scan, classify, and organize legacy GNSS data, field notes, and other files. It outputs detailed metadata in JSONL format, supports resuming interrupted scans, and tracks progress.

### Key Features Relevant to Data Ingestion

-   **Cross-platform CLI scanner:** Works on both Windows and Linux, ideal for lab machines.
-   **JSONL output:** Provides structured metadata for all scanned files, which can be easily ingested into our database or other systems for further processing.
-   **Resume capability:** Ensures robustness against interruptions during long scans.
-   **Future USB auto-detection:** The roadmap for `Drive Archaeologist` explicitly includes "Phase 4: USB auto-detection + HTML reports," which directly covers the automatic detection and processing of connected USB drives, a core requirement of the original deliverable.

## Integration

Instead of developing a new "Smart USB Data Ingestion System," the MOVE Faults project will integrate and utilize the `Drive Archaeologist` project. This involves:

1.  **Deployment:** Deploying the `Drive Archaeologist` application on designated lab machines.
2.  **Configuration:** Configuring `Drive Archaeologist` to target relevant data types and output locations according to MOVE Faults project standards.
3.  **Monitoring:** Implementing a process to monitor the output of `Drive Archaeologist` scans (e.g., the `scan_results.jsonl` files) to trigger subsequent ingestion steps into the POGF database for relevant GNSS data.

## Specialization for Site Conditions

As you noted, a key opportunity lies in specializing `drive-archaeologist` to handle legacy "site condition" files. This transforms it from a generic file scanner into a domain-specific analysis tool for geodetic field data.

-   **Goal:** To identify and classify unstructured files like site photos, scanned log sheets, and plain-text field notes, and to associate them with the corresponding GNSS data files.
-   **Implementation:** This will involve developing a custom "profile" or a set of classifiers within (or for) the `drive-archaeologist` project. This profile will use heuristics such as file naming conventions, directory structures, and file types to tag files with semantic meaning (e.g., `{"type": "site_photo", "station": "PHIV"}`).
-   **Complementary Role:** This provides a powerful reactive solution for recovering historical context from legacy data. It perfectly complements the **Digital Field Operations System (Deliverable 2.3)**, which is the proactive solution for creating structured, digital-native site data going forward.

This specialization is a key part of the integration and ensures that the full value of the `drive-archaeologist` tool is leveraged for the MOVE Faults project.
