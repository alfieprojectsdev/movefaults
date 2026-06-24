# Session Log — 2026-06-22

**Context:** Onboarding on Bernese changes (May 2026 session info lost) + pre-NAMRIA-training
local Bernese readiness check. Bernese Training: 22–26 Jun 2026, NAMRIA Boardroom, bring this T420.

---

## 1. Bernese track onboarding (memory was stale)

Memory froze ~Phase 1B planning. Since then the **whole Bernese track was built + merged**
(last commit 2026-05-05). All tickets DONE except R740 install:

| Ticket | Status | Commit |
|---|---|---|
| BRN-002+003 (BPEBackend + LinuxBPEBackend + PHIVOL_REL PCF) | DONE | `bead683` |
| BRN-004 (campaign file pipeline + Trimble class) | DONE | `e11a135` |
| BRN-006 (pre-BPE RINEX header validator — RXOBV3 drop fix) | DONE | `e1f2de2` |
| BRN-005 (RUNX_v2 --reference-station + velocity hook) | DONE | `c0b23ca` |
| ANA-001 (port RUNX_v2 + vel_line_v8 to pogf-geodetic-suite) | DONE | `7f79174` |
| IGS-001, ING-001/002/003 | DONE | — |
| **BRN-001 (R740 Bernese install)** | **OPEN, P0, critical path** | — |

Code deep-read confirmed claims match implementation (55 tests in bernese-workflow).
Service layout at `services/bernese-workflow/src/bernese_workflow/`: backends, campaign_builder,
campaign_models, orchestrator, pcf_context, rinex_header_validator.

**Stale docs flagged:** CLAUDE.md maturity table still says bernese-workflow ~10% / "not active" —
**NOT fixed this session** (user deferred). Fix when convenient.

---

## 2. T420 Bernese install — VERIFIED READY for training

Checked live (not assumed):
- BERN54 tree + 88 EXE_GNU Fortran bins; RXOBV3 runs (normal OPNERR, no SIGILL → ISA objcopy patch holds)
- `menu` GUI: all libs resolve, DISPLAY=:0.0 active
- `startBPE.pm` syntax OK; perl 5.40.1; libgfortran.so.5 present; python 3.13
- CRX2RNX, DE421.EPH, DATAPOOL REF54 symlinks intact, license perpetual

**Dependency verdict: NO updates. Do NOT `apt upgrade` before/during training** (newer libgfortran/Qt
could break verified install; zero upside).

### EXAMPLE BPE end-to-end run (full verification)
- `perl $U/SCRIPT/rnx2snx_pcs.pl 2023 0100`
- Runtime **09:33:58 → 09:54:38 = 20m40s** (matches ~20-min benchmark)
- All phases clean, `SCRIPT ENDED`; FIN SINEX + NQ0 written
- `.ERR` = benign EXAMPLE header warnings (missing GLONASS COD/PHS/BIS), not station drops
- **SINEX diff vs reference** (`$SAVEDISK/RNX2SNX/2023/SOL/FIN_20230100.SNX.gz_REF`):
  **0.0000 mm max 3D across all 18 stations** — better than Feb-2026 (0.001–0.09 mm)

---

## 3. Artifacts created this session

**Repo docs (NOT committed):**
- `docs/project_documentation/bernese_monitoring_cheatsheet.md` — files/folders to watch during a BPE run
- `docs/project_documentation/bernese_dependencies.md` — build-time vs runtime dep manifest + T420 fixes + R740 deltas

**Memory updated:**
- NEW `bernese_workflow_status.md` — full Bernese build status + module map
- `MEMORY.md` — index line, marks Phase 1B plan + CLAUDE.md maturity as superseded
- `bernese_install.md` — re-confirmed 2026-06-22, 0.0000 mm, deps-frozen note, correct reference path

**Run logs:** `~/bpe_dryrun_logs/example_20230100.log`

---

## 4. Next actions (post-training / post-harness-upgrade)

1. **BRN-001** — R740 Bernese install (only open critical-path item). Deltas documented in
   `bernese_dependencies.md` §6. Skip ISA objcopy patch on R740.
2. Fix CLAUDE.md maturity table (bernese ~10% → built).
3. ANA-002 (dislocation models → suite), ING-004, DOC-002.
4. Possible orchestrator var mismatch: `backends.py` uses env `X` for bernese_root, but real Bernese
   uses `$C` (install path); `$X`/`$XG` differ. Verify before R740 wiring.

---

## State at logout
- Uncommitted: 2 new docs + this session log + earlier untracked files (see git status). Nothing staged.
- lite-xl open with BPE outputs + the two new docs.
- Logging out to upgrade Claude harness.
