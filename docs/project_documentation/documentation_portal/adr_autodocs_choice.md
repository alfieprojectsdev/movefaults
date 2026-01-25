# ADR-011: Strategy for Automated Processing Documentation

**Date:** 2026-01-25

**Status:** Proposed

## Context

A significant portion of our project's "configuration" is not just in `.toml` files, but is also defined implicitly by things like the command-line arguments our tools accept or the custom file formats we use. Manually creating and, more importantly, *maintaining* documentation for this is tedious and highly error-prone. It's almost guaranteed that manual documentation will become outdated as the project evolves.

We need a strategy to automatically generate this reference documentation directly from the source of truth (the code and config files themselves) as part of our "Docs as Code" approach.

## Decision

Our strategy will be to create a set of **small, targeted Python scripts** that are executed as a **pre-build step** in our documentation CI/CD pipeline. Each script will be responsible for generating one specific piece of documentation.

1.  **Strategy: Custom Generation Scripts**
    - **Reasoning:** Instead of adopting a large, monolithic "autodoc" framework, we will write our own simple scripts. For example:
      - A script to parse our `config.toml` files and generate a Markdown page describing the parameters.
      - A script to execute our command-line tools with the `--help` flag and capture the output into a CLI reference page.
      - A script to parse a central YAML definition of file types and generate a glossary.
    This approach is highly flexible, gives us complete control over the final Markdown output, and avoids adding complex new dependencies to our project.

2.  **Execution: Pre-build Step in CI/CD**
    - **Reasoning:** The generation scripts will be run as part of the existing GitHub Actions workflow for building our documentation. The command will be changed from `mkdocs build` to something like `python scripts/generate_docs.py && mkdocs build`. This ensures that the documentation is *always* regenerated from the very latest source code and configuration files just before the main site is built.

## Alternatives Considered

### 1. Manual Documentation Only

- **Pros:** Requires no initial development effort.
- **Cons:** **This is the core problem we are solving.** Manual documentation is brittle, gets outdated, and is a drain on developer time. It is not a sustainable solution.

### 2. Using Sphinx `autodoc`

- **Pros:** `autodoc` is the standard tool for generating comprehensive API documentation from Python docstrings. It is very powerful.
- **Cons:**
  - We have already decided against Sphinx in favor of MkDocs/Markdown for our main documentation portal (see ADR-010), as it's simpler and more aligned with our needs. Using `autodoc` would require us to adopt the entire Sphinx ecosystem.
  - `autodoc` is designed primarily for generating API reference documentation from docstrings. It is not well-suited for our specific, non-API tasks, such as creating a file glossary or parsing command-line help text.

### 3. Using Third-Party MkDocs "autodoc" Plugins

- **Pros:** Several community plugins attempt to bring `autodoc`-like functionality to the MkDocs ecosystem.
- **Cons:** These plugins are often less mature and less flexible than Sphinx's `autodoc`. More importantly, they are still focused on API documentation. For our very specific, targeted needs (parsing TOML files, capturing `--help` text), writing a small, dedicated Python script is often simpler, faster, and more direct than trying to bend a complex plugin to our will.

## Consequences

### Positive

- **Documentation is Always Accurate:** The generated reference documentation will never be out of sync with the application's actual behavior, as it is generated from the same source.
- **Reduces Manual Toil:** Developers are freed from the boring and error-prone task of manually updating reference documentation. They can add a new CLI flag or config parameter, and the documentation will be updated automatically on the next build.
- **Full Control over Output:** Because we are writing the generation scripts ourselves, we have complete control over the formatting of the final Markdown. We can ensure it is clean, readable, and consistent with our manually written documentation.
- **Simplicity:** The chosen approach of small, targeted scripts is easy to understand, implement, and maintain.

### Negative

- **Custom Script Maintenance:** We are now responsible for creating and maintaining these documentation generation scripts. This is a new, albeit small, piece of code in our project. If we significantly change how our configuration or CLI tools work, these scripts may also need to be updated. This is a minor and acceptable cost for the benefits gained.
