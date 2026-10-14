# Philippine Open Geodesy Framework: the November 2025 proposal

*Condensed from an AI chat of 2025-11-11 that drafted a 2–3 year program
proposal, then a tone revision of it. See [README](README.md). This is where the
name "POGF" comes from.*

## Read this first

The draft was written by an AI assistant from planning notes and a draft
Fulbright application. **Its context numbers were not verified and should not be
quoted**: about 250 continuous GNSS stations across four agencies (PHIVOLCS
100+, NAMRIA 50+, DPWH 20+, CAAP 15+), ₱5–15 million a year in licences
avoidable, 1,500 staff hours a year saved, a ₱11.8 million three-year budget.
For numbers the project has measured, see `docs/SETTLED.md`. For example, about
107 stations have 2025 RINEX 2 in the local datapool, and PAGENET is NAMRIA's
network.

Personal sections of the draft (the author's career, motivation and family
circumstances) are left out.

## The proposal in brief

**Aim.** Turn the Philippines' fragmented GNSS monitoring into one open,
sustainable national deformation-monitoring system, modelled on Japan's GEONET:
a unified processing strategy, automated quality control, open data, and a
processing strategy that keeps improving.

**Fit with national policy**, as the draft argued it: the Philippine Space Act
(RA 11363), the DRRM Act (RA 10121), and DOST's emphasis on open, interoperable
systems.

**Three tiers.**

1. Ingestion and preprocessing: drive and USB import, product downloads, RINEX
   quality checks, equipment metadata.
2. Processing: automated Bernese BPE runs, multi-agency network solutions,
   real-time paths (PPP, VADASE), time series and velocities.
3. Access and decision support: dashboards, a REST API, assisted outlier
   detection, an expert system.

**Phases.**

| period | phase | main deliverables |
|---|---|---|
| Year 1 | Foundation | geodetic database; USB hot-drop monitor; BPE wrappers; digital logsheet PWA and equipment tracking; OCR pilot on paper logsheets; automated daily processing; dashboard v1; quantitative QC |
| Year 2 | Integration | NAMRIA stations in the same processing; inter-agency data-sharing agreements and a steering committee; a combined velocity field; assisted outlier and equipment-change detection; public API, versioned data releases with DOIs |
| Year 3 | Scale | DPWH and CAAP data; near-real-time processing; dislocation modelling with GNSS and InSAR; training and documentation portal; ASEAN collaboration and a sustainability plan |

A Fulbright placement was described as a way to accelerate Year 1, not a
prerequisite.

**Governance as proposed.** A steering committee chaired by PHIVOLCS, co-chaired
by NAMRIA, with DPWH, CAAP, PhilSA and DOST-ASTI; working groups for processing
and QC, field operations, data access, and research.

**Data access tiers as proposed.** Public (processed coordinates, velocities,
station metadata); registered researchers (RINEX, QC reports); partner agencies
(real-time streams, equipment history); restricted (case by case).

## Where it stands (2026-10-14)

The repository's roadmap (`docs/project_documentation/roadmap.md`) keeps the
proposal's deliverable numbering. Measured state:

| proposal item | now |
|---|---|
| Geodetic database (1.1) | built (PostgreSQL, TimescaleDB, PostGIS); nothing writes solutions into it yet |
| Ingestion pipeline (1.2) | about 30%, not in the production loop |
| Automated Bernese processing (1.3) | production runs through `scripts/` on Bernese 5.4; `services/bernese-workflow` is built and tested but has run no production month |
| Public portal and API (1.4) | not started |
| Drive and USB import (2.1) | `tools/drive-archaeologist`, about 60% |
| IGS downloader (2.2) | partial; production uses a mirror fetch script |
| Digital logsheets (2.3) | deployed, used on a real handset; the equipment QR scanner is not built |
| Post-processing and modelling (2.4) | velocities verified against PHIVOLCS' MATLAB output; Okada and disloc ported; bootstrapping not ported |
| RINEX QC (2.5) | teqc first, gfzrnx fallback; the draft's RINGO was not adopted |
| Documentation portal and auto-docs (3.1, 3.2) | not started |
| Multi-agency integration, ML outlier detection, real-time processing | not started. "No LLM in the processing path" is settled (`docs/SETTLED.md` §3), and outlier review stays human-in-the-loop |
| Cluster partitioning on the GEONET model | deliberately not done at ~107 stations (`docs/SETTLED.md` §3) |
