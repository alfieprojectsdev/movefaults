# ADR-002: Technology Stack for the Unified Data Ingestion Pipeline

**Date:** 2026-01-25

**Status:** Proposed

## Context

The POGF requires an automated data ingestion pipeline to handle data from various sources and in various formats. The pipeline must be:
- **Reliable:** Able to recover from transient failures.
- **Scalable:** Able to handle a growing number of data sources and a high volume of data.
- **Maintainable:** Easy to configure for new data sources and to update its logic.
- **Asynchronous:** Able to perform I/O-bound tasks (like downloading files or writing to the database) without blocking the entire system.

## Decision

We will build the pipeline in Python using a combination of the following key libraries:

1.  **Celery:** For managing the entire ingestion process as a distributed task queue. Each stage of the pipeline (Validation, Standardization, Loading) will be a Celery task.
2.  **SQLAlchemy:** As the ORM for all interactions with the PostgreSQL database.
3.  **A configuration-driven approach:** Using TOML files to define data sources, validation rules, and other parameters, decoupling the pipeline's logic from its configuration.
4.  **Pandas:** For in-memory data manipulation and validation where complex, tabular operations are needed.

## Alternatives Considered

### 1. Simple Python Scripts with Cron

- **Pros:** Very simple to implement for a single data source. Low overhead.
- **Cons:** Becomes brittle and difficult to maintain as complexity grows. Offers poor parallelism, no built-in retry mechanisms, and no easy way to monitor the status of tasks. It is not scalable.

### 2. Logstash / Fluentd

- **Pros:** Excellent, battle-tested tools for data collection and processing, especially for logs.
- **Cons:** Primarily designed for log-like data streams. While they can be adapted, they are not a natural fit for the multi-stage, stateful validation and standardization required for scientific data formats like RINEX. The configuration can become complex for non-log data.

### 3. Apache NiFi

- **Pros:** A very powerful and flexible platform for building data-flow automation. Provides a graphical UI for designing pipelines.
- **Cons:** Has a steep learning curve. The graphical, flow-based programming model can be cumbersome for implementing complex, imperative logic (like detailed RINEX validation). Can be heavyweight and overkill for the currently defined scope.

## Consequences

### Positive

- **Robustness & Scalability:** Celery provides a production-ready foundation with support for retries, rate limiting, and scaling out workers to handle increased load.
- **Maintainability:** The combination of Python's readability, SQLAlchemy's abstraction, and TOML configuration files makes the system easy to understand and extend.
- **Python Ecosystem:** We can leverage the rich Python ecosystem for scientific data processing (e.g., `georinex` for RINEX parsing) and other tasks.
- **Decoupling:** Celery decouples the task submission from the execution, making the system more resilient.

### Negative

- **Operational Overhead:** Requires managing a message broker (like RabbitMQ or Redis) for Celery, which adds a component to the infrastructure that needs monitoring and maintenance.
- **Learning Curve:** While Python is common, Celery has its own concepts and requires a learning curve to use effectively and debug issues.
- **Complexity for Simple Cases:** For a very small number of simple, reliable data sources, a Celery-based architecture might be considered over-engineered. However, given the project's long-term vision, starting with a scalable architecture is a strategic advantage.
