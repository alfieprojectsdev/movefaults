# Session Log — 2026-07-02

**Context:** Continue R740 orchestrator hardening. Ship RH-002, adopt a PR-per-major-commit +
git-worktree workflow, start RH-003. PAGENET weekly batch (087–090) running detached in the background.

---

## 1. PAGENET weekly batch — 087→090 launched detached
`~/run_pagenet_week.sh --detach` launched to finish the week. Confirmed reparent to init (runner
PPID=1, BPE server live), session **0870** started and advanced past ORBGEN → RNXGRA. Logout-safe
(`setsid nohup`), idempotent (skips the 084/085/086 already banked), PLG2 pre-stashed so DOY 088 won't
hard-abort. Not harness-tracked, so no auto-notify — poll via `~/run_pagenet_week.log` or
`~/watch_runner.sh` (keyed on `FIN_20260870/0880/0890/0900.NQ0`).

## 2. RH-002 — parameterize `backends.run()` (`e544492`)
Closes readiness gaps #3 (PCF/CPU parameterization) and #10 (MAXPAR sizing).
- `LinuxBPEBackend` constructor now takes `pcf_file` (default `RNX2SNX`), `cpu_file` (default `USER` —
  the shipping `USER.CPU`, **not** the phantom `PCF.CPU` the stub carried), `driver_script`, `max_par`.
  `run()` exports the parameterized `PCF_FILE`/`CPU_FILE`/`BPE_CAMPAIGN` and passes the PCF as `argv[2]`
  for `pagenet_pcs.pl`-style drivers (stock `rnx2snx_pcs.pl` ignores it). Defaults reproduce the prior
  stock contract, so nothing existing breaks.
- `compute_maxpar(n_sta) = max(1000, n_sta*4 + 500)` + `_count_crd_stations()`; `run()` auto-sizes
  MAXPAR from the campaign CRD (or the `max_par` override) and exports it as a BPE variable. Left unset
  when uncomputable so the panel default stands. **MAXPAR is exported, not yet injected into the
  ADDNEQ2 panel template** — that wiring is RH-004 / readiness task B; flagged in the backlog so the
  boundary isn't lost.
- `test_backends.py` +10 (maxpar bounds, CRD count, env-var flow, default preservation). 75 pass,
  ruff + mypy clean. Backlog RH-002 marked DONE.
- Consumer gap: `BerneseOrchestrator` still builds the backend with defaults — threading
  `pcf_file`/`max_par` through it is a small follow-up, out of RH-002 scope.

## 3. Workflow change — PR per major commit
Starting today, major (code/ticketed) commits are posted as pull requests rather than pushed straight
to a shared branch. First PR drafted for `docs/bernese-training-notes → main`: it batches RH-001
(`1e3c952`) + RH-002 (`e544492`) + the training-week docs (12 commits). **RH-002 could not be a
standalone PR** — its `backends.py` changes sit directly on top of RH-001's, which is unmerged;
isolating it would conflict or require rewriting pushed history. Going forward, each major ticket
starts on its own branch so one ticket = one focused PR. (`gh pr create` was sandbox-denied on the
network write; body staged, user to run/approve.)

## 4. Workflow change — git worktrees (`.trees/`)
Adopting the `.trees/` hidden-worktree protocol (per global CLAUDE.md) instead of in-place feature
branches. `.trees/` added to `.gitignore`. RH-003 developed in `.trees/rh-003-gen-sessions` on branch
`feat/rh-003-gen-sessions`, branched off the current tip (so it inherits RH-001/RH-002 and avoids
phantom `backends.py` conflicts against a bare `main`).

## 5. RH-003 (in progress) — `prepare_campaign()` adds GEN/ + SESSIONS.SES (gap #2)
`_SUBDIRS` omitted `GEN`; no session table was generated → BPE dies (the exact gap that blocked the
manual run in training). Work: add `GEN` to `_SUBDIRS`; generate/stage a daily `SESSIONS.SES`
(`???0` session template). See the RH-003 worktree branch.

## State at end of session
- **Committed** (branch `docs/bernese-training-notes`): `e544492` RH-002 + this session log.
- **PR:** drafted for `docs/bernese-training-notes → main` (RH-001+RH-002+docs); create pending
  user run/approve.
- **Background:** PAGENET 087–090 running detached; 3 of 7 dailies banked at session start.
- **In progress:** RH-003 in `.trees/rh-003-gen-sessions`.
