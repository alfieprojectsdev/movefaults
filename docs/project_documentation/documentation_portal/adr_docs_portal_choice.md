# ADR-010: Technology Stack for the Centralized Documentation Portal

**Date:** 2026-01-25

**Status:** Proposed

## Context

A successful and sustainable project requires high-quality, accessible documentation. Currently, project knowledge is fragmented across various documents, formats, and locations. This makes it difficult for new team members to get up to speed and for existing members to find the information they need. We need a "single source of truth" that is easy to maintain, version-controlled, and always available. This approach is often called **"Docs as Code"**.

## Decision

We will adopt a "Docs as Code" strategy and build a static documentation website using the following technologies:

1.  **Static Site Generator: MkDocs with the Material for MkDocs theme**
    - **Reasoning:**
      - **Simplicity and Speed:** MkDocs is extremely simple to configure (a single YAML file) and builds very quickly.
      - **Python-Native:** As a Python-based tool, it fits perfectly within our existing technology stack and developer workflows.
      - **Material Theme is a Killer Feature:** The Material for MkDocs theme is a powerful, feature-rich frontend that comes for free. It provides a modern, responsive design, excellent navigation, and, most importantly, a fantastic client-side search function. Building a comparable frontend from scratch would be a significant undertaking.
      - **Markdown-Based:** It uses standard Markdown, a format every developer already knows.

2.  **Deployment Pipeline: GitHub Actions for CI/CD and GitHub Pages for Hosting**
    - **Reasoning:**
      - **Seamless Integration:** This entire pipeline can be configured to live and run within our existing GitHub repository.
      - **Fully Automated:** The GitHub Actions workflow will automatically build and deploy the site on every push to the `main` branch, ensuring the documentation is never out of date.
      - **Zero Cost and Low Maintenance:** For a public repository, this solution is free and requires no server provisioning, security patching, or maintenance on our part. GitHub manages the entire hosting infrastructure.

## Alternatives Considered

### 1. Wiki-Based Systems (e.g., Confluence, Notion, GitHub Wiki)

- **Pros:** Offer a very low-friction editing experience through a web UI, which can be good for non-technical contributors.
- **Cons:**
  - **Separation from Code:** The primary drawback. The documentation content lives in a separate system's database, not in our Git repository. This makes it impossible to review documentation changes in pull requests alongside the code changes they relate to.
  - **No Versioning Parity:** It's difficult to see what the documentation looked like for a specific version (e.g., `v1.2.0`) of the software.
  - **Cost/Lock-in:** Commercial solutions like Confluence and Notion incur subscription costs.

### 2. Other Static Site Generators

- **Docusaurus:** A very popular and powerful tool from Facebook, built on React. It's an excellent choice, but it would introduce a Node.js/JavaScript dependency into our project's tooling. MkDocs keeps us within a pure Python environment.
- **Sphinx:** The traditional standard for documenting Python projects. It is extremely powerful and extensible but is also far more complex to configure than MkDocs. It uses reStructuredText (rST) by default, which is less common and arguably less intuitive than Markdown. For our needs, the simplicity of MkDocs is a significant advantage.
- **Jekyll / Hugo:** Also excellent static site generators, but they are written in Ruby and Go, respectively. Again, MkDocs aligns best with our existing Python stack.

### 3. Self-Hosting the Website

- **Pros:** Full control over the server environment.
- **Cons:** Unnecessary operational overhead. We would be responsible for provisioning a server, configuring a web server (like Nginx), setting up TLS certificates, and handling security and maintenance. For a simple static site, this is a solved problem that services like GitHub Pages handle for us.

## Consequences

### Positive

- **Docs are Treated Like Code:** The "Docs as Code" approach means documentation will be subject to the same review, versioning, and CI/CD processes as our application code, leading to higher quality.
- **Excellent Developer Experience:** Writing documentation in Markdown within a code editor is a natural workflow for developers.
- **Single Source of Truth:** All project documentation will be centralized, searchable, and easily accessible to everyone.
- **Zero-Cost, Zero-Maintenance Infrastructure:** The combination of GitHub Actions and GitHub Pages provides a robust, enterprise-grade deployment pipeline for free.

### Negative

- **Learning Curve for Non-Developers:** Contributors who are not familiar with Git and the pull request workflow may find it more difficult to update documentation compared to a simple web-based editor. This is a trade-off we accept for the benefits of versioning and review. We can mitigate this by providing clear contribution guidelines.
