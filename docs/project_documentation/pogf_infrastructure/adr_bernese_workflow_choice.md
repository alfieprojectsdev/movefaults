# ADR-003: Architecture for the Automated Bernese Processing Workflow

**Date:** 2026-01-25

**Status:** Proposed

## Context

The Bernese GNSS Software is a central part of the project's data processing chain. It is a powerful but complex suite of tools, traditionally used in an interactive, desktop environment. To achieve the goals of the POGF, we must automate its execution in a way that is reliable, repeatable, and scalable.

The automation system must handle the entire lifecycle of a processing run: gathering inputs, generating configuration files, executing the Bernese Processing Engine (BPE), and parsing the results.

## Decision

We will implement the automation workflow using Python, orchestrated by Celery. The key architectural decisions are:

1.  **Python as the primary scripting language:** To write the business logic for the entire workflow.
2.  **Celery for orchestration:** To manage each Bernese processing run as a single, long-running, asynchronous task. This allows the system to handle multiple runs concurrently (if resources permit) and to manage failures gracefully.
3.  **Jinja2 for configuration templating:** To dynamically generate the various Bernese input files (e.g., PCF, STA) based on data queried from the central database.
4.  **Direct BPE execution via `subprocess`:** The Python workflow will call the Bernese command-line executable (`BPE.exe` or equivalent) directly. This is a simple and direct integration method.

This implies that the Celery worker designated for this task must run on a machine (or in an environment) where a licensed copy of the Bernese GNSS Software is installed and configured.

## Alternatives Considered

### 1. Wrapping Bernese in a Dedicated Web Service

- **Pros:** Creates a clean API boundary around Bernese, completely decoupling it from the workflow orchestrator.
- **Cons:** Introduces significant overhead. We would need to build, document, and maintain a separate web service just for this purpose. The communication between the orchestrator and this new service would also need to be managed.

### 2. Using a General-Purpose Workflow Engine (e.g., Airflow, Prefect)

- **Pros:** These tools are purpose-built for creating complex, multi-step data pipelines and offer excellent UI for monitoring and scheduling.
- **Cons:**
  - **Increased Technology Sprawl:** Introduces another major technology to the stack that needs to be learned, managed, and maintained.
  - **Potential Overkill:** While Bernese processing is multi-step internally, from the orchestrator's point of view, it can be seen as a single, monolithic task ("run Bernese"). The complexity of Airflow/Prefect might be more than is needed.
  - **Reusing Celery:** Since Celery is already part of the stack for the ingestion pipeline, reusing it for this workflow simplifies the overall architecture.

### 3. Using Proprietary Automation Tools or GUI Automation

- **Pros:** Might offer record-and-playback features for automating GUI interactions.
- **Cons:** Extremely brittle. Any change in the Bernese UI would break the automation. Not suitable for a headless, server-based environment. Introduces licensing costs and vendor lock-in.

## Consequences

### Positive

- **Reduces Technology Sprawl:** Reusing Celery and Python from the ingestion pipeline simplifies the project's technology stack.
- **Flexibility and Control:** Python provides fine-grained control over the entire process, from file manipulation to error handling. Jinja2 is a powerful tool for handling the complexity of Bernese configuration.
- **Direct Integration:** The `subprocess` approach is simple and has minimal overhead.

### Negative

- **Tightly Coupled Environment:** The Celery worker(s) for this task are tightly coupled to the Bernese installation environment. They are not generic workers and must be provisioned and managed specifically for this purpose.
- **"Black Box" Execution:** The system treats the BPE as a black box. If the BPE's command-line interface, input file formats, or output file formats change in a future version, our automation scripts may break. This is an accepted risk, as Bernese is a mature and stable software package.
- **State Management:** The state of the workflow is managed within the Python script. For very complex, multi-day workflows, a more formal workflow engine might provide better state management and recoverability. However, for typical daily/hourly runs, this approach is sufficient.
