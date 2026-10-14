# Work instructions overview (2025-10-22)

*Condensed from an AI chat. See [README](README.md) for what was kept and why.*

The conversation reviewed `Work_Instructions_ao20251017.docx.pdf`, PHIVOLCS'
manual for processing MOVE Faults GNSS data, and produced the two documents now
in the repository:

- `docs/gnss_automation_roadmap.md`: automation opportunities around the
  existing workflow.
- `docs/work_instructions_review.md`: a section-by-section technical review of
  the manual, with proposed edits in diff notation.

## The workflow as the manual described it (October 2025)

1. **Data conversion (manual §4).** Trimble `.T01`/`.T02` or Leica `.m00` raw
   files → `runpkr00.exe` and `teqc` → RINEX (`.YYo`). Batch conversion by the
   custom `campaign_v5.py` / `continuous_v5.py`; `fixdatweek.exe` for GPS week
   rollover.
2. **Bernese 5.2 processing (manual §5).** One-time campaign setup, including
   the eight station metadata files; then routine daily processing through the
   BPE against IGS stations, giving daily ITRF14 coordinates.
3. **Time series (manual §6).** Daily `F1_YYDDD0.CRD` → Python filtering and
   conversion to ENU relative to a reference station (S01R at the time) →
   MATLAB `vel_line_v8.m` for plots, outliers and velocities.

Supporting tools named: Perl (BPE scripting), gzip and Hatanaka compression,
Notepad++ for file edits, FileZilla or Total Commander for IGS downloads,
`plot_v2.py` and `outlier_input-site.py`.

## Constraints the author set in the conversation

- **Bernese stays** for core processing. Only the work around it was open to
  change.
- Contract staff had run day-to-day processing for about ten years, using tools
  and conventions the author built or institutionalised.
- Watching for new raw data (`inotify`/`watchdog`) was a long-standing wish.
  It became `tools/drive-archaeologist/` and `services/ingestion-pipeline/`.

## What has happened since

The October 2025 picture is history now. Bernese 5.4 runs on gps3, production
goes through `scripts/`, and `vel_line_v8.m` is ported to Python and verified
against PHIVOLCS' output (`pogf_geodetic_suite.timeseries.analysis`). See
`CLAUDE.md`, "How components connect", and
`docs/project_documentation/automation_stages.md`.
