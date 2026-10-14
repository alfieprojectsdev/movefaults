# Chat notes, October to December 2025

Before this repository existed, much of the project's early planning happened in
AI chat sessions. Ten of them were committed on 2026-01-26 as raw HTML exports
of the chat page (1.5–2.8 MB each). Besides the conversation, each export
carried the whole chat interface: the sidebar list of the account's other,
unrelated conversations, the account email, and the assistant's asides about
the author's career and personal life.

On 2026-10-14 they were replaced by the notes below. Each keeps only what is
specific to this project and still useful, and says where the conversation's
output now lives in the repository. **Figures in these notes were produced by
an AI assistant in 2025 and were not verified then**; where the project has
since measured or decided something, the note says so and the repository wins.

The HTML files remain in git history up to the commit that removed them.

| date | conversation | kept as |
|---|---|---|
| 2025-10-22 | Work instructions document overview | [work-instructions-overview.md](2025-10-22_work-instructions-overview.md). Its two outputs are `docs/gnss_automation_roadmap.md` and `docs/work_instructions_review.md` |
| 2025-10-23 | Bernese software documentation extraction | [bernese-manual-reading-map.md](2025-10-23_bernese-manual-reading-map.md) |
| 2025-10-23 | GNSS automation development effort estimation | [effort-estimate-and-matlab-decision.md](2025-10-23_effort-estimate-and-matlab-decision.md) |
| 2025-10-23 | GNSS data processing automation roadmap | Here only: revisions folded into `docs/gnss_automation_roadmap.md`. Reading list: DOCU52 §22 (BPE), the data collection team's orientation deck, Wilson et al. 2016 *Good Enough Practices in Scientific Computing* (now `docs/project_documentation/good_enough_practices_audit.md`), Kawamoto et al. 2023 *RINGO*, Takamatsu et al. 2023 on the GEONET F5 strategy (`[TAK23]` in `geonet_bernese_strategy_research.md`). The assistant's first answer was written after it failed to open the uploaded PDFs, and said so only when asked |
| 2025-10-29 | Git diff notation explanation | [proposing-edits-to-work-instructions.md](2025-10-29_proposing-edits-to-work-instructions.md) |
| 2025-10-29 | Smart USB data ingestion system | Here only: the design is `tools/drive-archaeologist/docs/Smart USB data ingestion system.md`, and the tool is `tools/drive-archaeologist/`. Requirements set in the chat and carried into the tool: scans may run for hours or days on old drives; drives mix GNSS data with two decades of personal files; archives (zip, gz, tar.gz, …) must be opened, not just listed; `uv` for packaging; developed on Linux Mint, deployed on a Debian server, OS-independent for staff machines |
| 2025-11-11 | Philippine Open Geodesy Framework proposal | [pogf-proposal.md](2025-11-11_pogf-proposal.md) |
| 2025-11-11 | POGF proposal revision for institutional tone | Not kept: editorial advice on removing second-person and personal framing from the proposal draft. The condensed proposal above is already written institutionally |
| 2025-12-17 | Volcano-specific rules in har-automation evaluation | Not kept: about a different repository (hazard assessment report automation), not this one |
| undated | Google Gemini: docling | Not kept: general advice on parsing PDF manuals with screenshots (LlamaParse, Docling, unpdf), and Docling's likely performance on the T420 and R740. The project settled on `pdftotext` plus `grep`/BM25 (`docs/SETTLED.md` §3) |

The GEOCON 2025 VADASE poster conversation was condensed the same way, to
`services/vadase-rt-monitor/docs/GEOCON_2025_POSTER_NOTES.md`.
