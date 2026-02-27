# Session Log: Bernese 5.4 Installation, Verification & Orchestration Design (2026-02-26)

## Overview

Two major threads this session:

1. **Bernese 5.4 installation completed and verified on T420** — full end-to-end run of the EXAMPLE campaign through BPE; solutions numerically match reference at ≤0.09 mm.
2. **Orchestrator design research** — non-interactive BPE API confirmed, BPE phase map documented, PHIVOLCS-specific INP file settings extracted from processing manuals via NotebookLM RAG.

---

## 1. Bernese 5.4 Installation (T420)

### What was done
- Completed setup.sh option sequence: 1 → (exit+source LOADGPS) → 5 → 2 → 4 → 3 → 6 → 7
- Resolved all T420-specific installation blockers (see below)
- Installed CRX2RNX (GSI Japan) into `$EXE`
- Generated `DE421.EPH` from JPL ASCII files via `ASC2EPH`, installed to `$MODEL/`
- Created DATAPOOL reference symlinks (`EXAMPLE.CRD_REF → EXAMPLE.CRD` etc.)
- Ran `perl $U/SCRIPT/rnx2snx_pcs.pl 2023 0100` — **47 BPE steps, all OK**
- Verified SINEX output against SAVEDISK reference solutions: differences ≤0.09 mm

### T420-specific blockers resolved

| Problem | Fix |
|---------|-----|
| conda-forge gfortran 15.2.0 builds binaries requiring x86-64-v3; T420 Sandy Bridge is x86-64-v2 | `objcopy --remove-section=.note.gnu.property` on all 88 `$EXE/*` binaries after compile |
| Qt `/Qt4.8.7` prefix hardcoded in qmake by Docker build | `sudo ln -s ~/Qt4.8.7 /Qt4.8.7` |
| Qt X11R6 path hardcoded | `sudo mkdir -p /usr/X11R6 && sudo ln -s /usr/lib/x86_64-linux-gnu /usr/X11R6/lib` |
| X11 `-dev` packages uninstallable (PPA version conflict) | 7 manual `.so` symlinks in `/usr/lib/x86_64-linux-gnu/` |
| `EXAMPLE.CRD`/`.VEL`/`.ABB` missing from DATAPOOL (only `_REF` variants exist) | `ln -s EXAMPLE.CRD_REF EXAMPLE.CRD` etc. |
| Option 6 before Option 3 → $U/SCRIPT/ lost | Re-ran Option 6 after Option 3 created $U |
| `$U/BPE/` not found | Bernese 5.4 uses `$U/PCF/` (not BPE/) for PCF files |

### Full procedure documented
`memory/bernese_install.md` — complete verified procedure including all symlinks, gfortran workaround, objcopy patch, DE421 generation, and R740 replication plan.

---

## 2. Non-Interactive BPE API (confirmed)

The correct orchestration API for Bernese 5.4 is `startBPE.pm`, not the NONIA flag (which doesn't exist in 5.4).

```perl
# $BPE/startBPE.pm — driver pattern from $U/SCRIPT/rnx2snx_pcs.pl
my $bpe = new startBPE();
$bpe{PCF_FILE}     = "RNX2SNX";
$bpe{CPU_FILE}     = "USER";
$bpe{BPE_CAMPAIGN} = "EXAMPLE";
$bpe{YEAR}         = "2023";
$bpe{SESSION}      = "0100";
$bpe{SYSOUT}       = "RNX2SNX";
$bpe{STATUS}       = "RNX2SNX.RUN";
$bpe{TASKID}       = "RS";
$bpe->resetCPU();
$bpe->run();
```

Python orchestrator calls this via `subprocess.run(["perl", driver_script, year, session], env=bern_env)`.

---

## 3. BPE Phase Map

NotebookLM analysis of `RNX2SNX.OUT` produced a full PID→process mapping (stored in `memory/bernese_bpe_phases.md`). Key findings for orchestrator:

- **`_P` suffix scripts** run in parallel on multiple CPUs — BPE manages this internally, orchestrator does not
- **RXOBV3_P (PID 221/222)** silently drops stations with bad `.STA` headers — orchestrator must check station count before/after
- **ADDNEQ2 runs three times** with different roles: float solution (341), final fixed (511), size-reduced NQ0 for velocity stacking (521)
- **HELMCHK (513)** is a secondary seismic sensor — reference station displacement flagged here before it shows up in time series
- **Output files**: `*.SNX` (final coords), `*.NQ0` (normal equations for velocity stacking), `R2S*.PRC` (human-readable report)

---

## 4. PHIVOLCS INP File Settings (from RAG)

NotebookLM queries against PHIVOLCS processing manuals confirmed exact parameter values for all key INP files (stored in `memory/bernese_inp_settings.md`). Summary:

### GPSEST — three configurations (one per processing stage)
| Stage | PID | Frequency | Ambiguity pre-elim | SIP |
|-------|-----|-----------|-------------------|-----|
| Float solution | 321/322 | L3 | PRIOR TO NEQ SAVING | No |
| QIF ambiguity resolution | 431/432 | **L1&L2** | — | **EVERY EPOCH** |
| Final fixed | 501/502 | L3 | AS SOON AS POSSIBLE | No |

The QIF L1&L2 + SIP EVERY EPOCH is the Philippine ionosphere handling — it's the physically correct treatment for equatorial scintillation.

### Other confirmed values
- **HELMR1**: 3-parameter (XYZ translations only), 12 IGS reference stations (AIRA, ALIC, BTNG, CUSV, DAEJ, DARW, GUUG, MCIL, NTUS, PIMO, PNGM, TNML)
- **MAUPRP**: 181s window, 10-cycle slip threshold, 0.002 sigma, 400%/30% ionosphere change — AIUB defaults, no Philippine-specific adjustments
- **ADDNEQ2 stacking**: minimum constraints, translations-only, outlier thresholds 15/15/30 mm (residual) and 10/10/20 mm (RMS)
- **CODSPP**: L3, no ionosphere model, GMF troposphere
- **Sampling**: 180s, 24h sessions

### INP template strategy
Only 7 Jinja2 template variables needed per run (campaign ID, year, session, HOI file, reference frame, orbit prefix, antenna model). All physics settings are hardcoded constants. Three GPSEST INP variants can be handled by a single template with a `mode` flag.

---

## 5. Velocity Reviewer Tool (tools/velocity-reviewer/)

Built a web-based replacement for `analysis/02 Time Series/Outliers-input name.py` — the
Windows-only, interactive matplotlib GUI used to manually flag outlier epochs in GNSS time series.

### Why it was needed
- Original script uses `msvcrt` (Windows-only), has no CLI interface, and requires a running display
- Blocks headless automation of the velocity pipeline on Linux (R740, CI)
- Right-click GUI is fragile and produces no audit trail of what was flagged or why

### What was built
```
tools/velocity-reviewer/src/velocity_reviewer/
  cli.py          — argparse CLI; launches uvicorn + auto-opens browser
  app.py          — FastAPI; 6 endpoints; module-level session state
  reader.py       — parsers for PLOT, 123, offsets; writer for OUTLIERS.txt
  regression.py   — numpy least-squares + IQR outlier detection (ported from reference)
  static/index.html — Plotly.js SPA (dark theme, keyboard shortcuts)
```

### Key design decisions
- **Module-level session state** (no DB) — correct for a single-session CLI tool; state lives exactly as long as the process
- **IQR auto-outliers pre-loaded as pre-selected (orange)** — operator de-selects false positives rather than hunting from scratch; faster review
- **Single-file HTML** with Plotly.js from CDN — no npm/Vite build step required
- **Keyboard shortcuts**: `→`/`Enter` = Accept & Next, `←` = Prev, `Esc` = Clear selection

### Usage
```bash
uv run velocity-reviewer --plots-dir /path/to/PLOTS
# browser opens at http://localhost:8765
# click points to toggle red; Accept & Next; Export OUTLIERS.txt
```

### pyproject.toml additions
- Entry point: `velocity-reviewer = "velocity_reviewer.cli:main"`
- Optional dep group: `velocity-reviewer = ["fastapi>=0.110.0", "uvicorn[standard]>=0.27.0"]`
- Hatch source: `"tools/velocity-reviewer/src" = ""`

### Smoke test result
```
Sites: ['BOST', 'PIMO']
Offsets: {'BOST': [(2022.5, 'EQ')]}
IQR outliers detected; OUTLIERS.txt written in correct format (matches original script)
All 6 FastAPI routes registered and responding correctly
```

---

## 6. Pending Actions

| Action | Owner | Notes |
|--------|-------|-------|
| Request working INP files from data processing staff | finch | OPT_DIR: `R2S_GEN`; 12 files covering all AP scripts |
| Install Bernese on R740 | finch | See `memory/bernese_install.md` R740 plan; no ISA mismatch, no PPA issues |
| Build Jinja2 INP templates from received files | next session | Block on receiving files from data processing staff |
| Migration 007 — `offset_events` table | next session | Phase 1B work item |
| Add Trimble raw file class to drive-archaeologist `profiles.py` | next session | `.T01`, `.T02`, `.T04`, `.DAT`, `.TGD` |
| Fix one-way latch bug in `domain/processor.py:130` | backlog | VADASE PR #1 remediation |

---

## Files Updated This Session

- `memory/bernese_install.md` — complete rewrite with all T420 fixes + verification status
- `memory/bernese_bpe_phases.md` — new file: full PID→process mapping
- `memory/bernese_inp_settings.md` — new file: confirmed INP parameter values
- `memory/MEMORY.md` — updated Bernese section, added pointers to new files
