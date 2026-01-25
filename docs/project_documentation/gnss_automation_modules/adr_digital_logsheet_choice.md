# ADR-007: Architecture for the Digital Field Operations System

**Date:** 2026-01-25

**Status:** Proposed

## Context

Current field operations for GNSS station maintenance rely on paper-based log sheets. This manual process has several critical drawbacks:
- **Data Quality:** Handwriting can be illegible, and forms can be incomplete.
- **Data Timeliness:** Paper forms must be physically transported back to the office and manually transcribed, leading to significant delays.
- **Data Loss:** Paper is easily damaged by weather or lost in transit.
- **Inefficiency:** Manual transcription is a waste of time and a source of error.

We need a digital solution that is robust, easy for field engineers to use, and, most importantly, functions reliably in environments with intermittent or non-existent internet connectivity.

## Decision

We will build a **Progressive Web App (PWA)** for the frontend, supported by a dedicated **Python/FastAPI backend**.

1.  **Frontend Architecture: Progressive Web App (PWA)**
    - **Reasoning:** This is the most critical architectural decision. A PWA offers the best of both web and native applications for this specific use case:
      - **Offline-First Capability:** Using a Service Worker, the application can cache its UI and data, making it fully functional offline. New log sheets can be created, saved locally (in IndexedDB), and queued for synchronization. This is a non-negotiable requirement for field use.
      - **Cross-Platform by Default:** A single codebase (HTML, CSS, JavaScript) runs on all modern mobile browsers (iOS and Android), drastically reducing development and maintenance effort compared to native apps.
      - **No App Store:** The application is accessed via a URL and can be "installed" to the device's home screen, bypassing the complex and lengthy submission processes of the Apple App Store and Google Play Store.

2.  **Backend Architecture: FastAPI and a Dedicated PostgreSQL Database**
    - **Reasoning:**
      - We will reuse the same backend technology stack (FastAPI, SQLAlchemy) chosen for other components of the project for consistency and to leverage existing expertise.
      - This system requires its own database to manage stateful, user-centric data (user accounts, equipment inventory, log sheet entries) that is distinct from the primary POGF geodetic data store. A dedicated PostgreSQL instance provides a clean separation of concerns.

## Alternatives Considered

### 1. Native Mobile App (Swift for iOS, Kotlin for Android)

- **Pros:** Offers the best possible performance and the deepest integration with device hardware and OS features.
- **Cons:**
  - **High Cost:** Requires developing and maintaining two completely separate codebases, effectively doubling the development effort.
  - **Slow Deployment:** Updates must be submitted to and approved by app stores, which can take days.
  - **Overkill:** The core features required for this project (forms, camera access, offline storage) are all well-supported by modern PWAs, making the extra complexity of native development unnecessary.

### 2. Commercial Off-the-Shelf (COTS) Field Data Collection Platforms

- **Examples:** Esri Survey123, Fulcrum, KoboToolbox.
- **Pros:** These are mature, feature-rich platforms that provide form builders and offline capabilities out-of-the-box.
- **Cons:**
  - **Subscription Costs:** They incur ongoing licensing fees.
  - **Customization Limits:** It may be difficult or impossible to customize them to our exact workflow, particularly the deep integration with our own equipment inventory and QR code system.
  - **Data Integration Challenges:** Getting data out of these platforms and into our own database in real-time can be complex and may rely on proprietary APIs. Building our own solution gives us full control over the data.

### 3. A Standard Web App (Online Only)

- **Pros:** The simplest and quickest of all alternatives to build.
- **Cons:** **Not a viable option.** The lack of offline support is an absolute deal-breaker for a tool intended for use in remote field locations where internet connectivity cannot be guaranteed.

## Consequences

### Positive

- **Solves the Core Problem:** The PWA's offline-first design directly addresses the most critical challenge of field data collection.
- **Efficient Development:** A single, cross-platform codebase for the frontend is vastly more efficient than native development.
- **Improved Data Quality & Timeliness:** Structured digital forms eliminate transcription errors, and data is synced to the central server as soon as a connection is available.
- **Full Control:** We have complete control over the features, workflow, and data, now and in the future.

### Negative

- **Complexity of Offline State Management:** Building a truly robust offline-first application is significantly more complex than a standard CRUD web app. It requires careful management of local data storage (IndexedDB), synchronization logic, and conflict resolution (though conflicts are unlikely in this single-user-per-device model).
- **PWA Limitations:** While powerful, PWAs have some limitations compared to native apps (e.g., less access to background processes, some hardware APIs). However, for the features specified in this project, PWAs are entirely sufficient.
