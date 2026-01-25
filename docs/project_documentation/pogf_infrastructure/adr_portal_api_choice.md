# ADR-004: Technology Stack for the Public Data Portal and API

**Date:** 2026-01-25

**Status:** Proposed

## Context

The POGF project requires a public-facing component to fulfill its "Open" mandate. This component must provide both a user-friendly web interface for exploration and a robust, well-documented API for programmatic access to **processed, historical, non-real-time** geodetic data. The system needs to be performant, scalable, and maintainable, presenting potentially large and complex datasets (maps, time series) in an intuitive way.

**Note:** Real-time GNSS displacement monitoring and earthquake detection are handled by the separate `vadase-rt-monitor` project. This Public Data Portal will focus on the comprehensive long-term archive and analysis of processed data.

## Decision

We will build a decoupled frontend/backend system to provide access to **processed, historical, non-real-time geodetic data**, complementing real-time monitoring systems like `vadase-rt-monitor`. The primary technologies will be:

1.  **Backend: FastAPI (Python)**
    - **Reasoning:** FastAPI is a modern, high-performance Python web framework ideal for building APIs. Its key advantages include:
      - **Performance:** One of the fastest Python frameworks available, comparable to Node.js.
      - **Automatic Documentation:** It automatically generates interactive OpenAPI (Swagger) and ReDoc documentation from code, which is critical for a public API.
      - **Data Validation:** Uses Pydantic for type-hint-based data validation, reducing boilerplate and bugs.
      - **Python Ecosystem:** Allows us to stay within the Python ecosystem, enabling code and skill sharing with the data processing parts of the project.

2.  **Frontend: React**
    - **Reasoning:** React is the leading JavaScript library for building user interfaces.
      - **Component Architecture:** Its component-based model is perfect for building a complex, maintainable UI with reusable parts (e.g., a "time series plot" component).
      - **Rich Ecosystem:** A vast ecosystem of libraries and tools is available (e.g., for mapping, plotting, state management).
      - **Large Talent Pool:** It is easier to find developers with React experience.

3.  **API Specification: OpenAPI**
    - **Reasoning:** This is the industry standard for REST API specifications. By using FastAPI, we get compliance and documentation for free, ensuring our API is easy for third parties to understand and integrate with.

## Alternatives Considered

### 1. Monolithic Framework (e.g., Django, Ruby on Rails)

- **Description:** Using a single framework to handle both backend logic and server-side rendering of HTML templates.
- **Pros:** Can be faster to develop for simpler, content-focused sites. Single codebase.
- **Cons:** For highly interactive applications with maps and plots, a server-rendered approach can feel slow and clunky, requiring full page reloads for updates. It tightly couples the frontend and backend, making it harder to evolve them independently.

### 2. Other Backend Frameworks

- **Flask (Python):** A solid microframework, but it requires more plugins and boilerplate to achieve the features FastAPI provides out-of-the-box (e.g., data validation, async support, OpenAPI docs).
- **Node.js (Express/NestJS):** Very performant and a popular choice for APIs. However, this would introduce JavaScript/TypeScript as a primary backend language, increasing the project's technology sprawl and reducing opportunities for code/skill reuse from the Python-based data-processing components.

### 3. Other Frontend Frameworks

- **Vue.js:** An excellent, modern framework often praised for its gentle learning curve. It is a perfectly valid alternative to React. However, React currently has a larger community, a more extensive library ecosystem, and a larger talent pool, making it a slightly safer choice for a long-term project.
- **Angular:** A full-featured, opinionated framework by Google. It is powerful but can be more complex and rigid than React or Vue, making it better suited for large, enterprise-scale applications where its strong opinions are a benefit.

## Consequences

### Positive

- **Clear Separation of Concerns:** The decoupled architecture allows frontend and backend teams to work independently. The API serves as a clear contract between them.
- **Complements Real-time Monitoring:** By focusing on historical data, this portal avoids duplicating effort with `vadase-rt-monitor` and instead provides a comprehensive view of both past and present.
- **Modern & Performant User Experience:** An SPA built with React can provide a fast, fluid, and highly interactive user experience, which is essential for data exploration.
- **Excellent API Discoverability:** The auto-generated OpenAPI documentation makes the API easy for external developers to learn and use.
- **Scalability:** The frontend (as static files) can be served efficiently from a CDN, and the stateless FastAPI backend can be easily scaled horizontally.

### Negative

- **Increased Development Complexity:** Requires expertise in two distinct technology stacks (Python/FastAPI and JavaScript/React) and the interface between them (REST, CORS).
- **Initial Load Time & SEO:** SPAs can have a larger initial bundle size, leading to a longer first-page load time compared to server-rendered pages. They can also be more challenging for search engine crawlers, though this can be mitigated with techniques like Server-Side Rendering (SSR) if SEO becomes a major requirement (at the cost of added complexity).
