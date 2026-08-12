# Session Log — 2026-07-31: `ugt` handover from R740 context, and solver repair

**Machine:** T420 (`finch`)
**CWD:** `movefaults_clean` — but **the work product is in `ugt`.** See §6.
**Scope:** build a context handover for continuing the `ugt` project on the
R740, using this repo's session logs as the evidence base; then fix the
defects that survey turned up.

Nothing in this repo's code or Bernese state was touched. This log lives here
because this is where the source material is, and because §3 is a finding
about *this* repo.

---

## 1. What was produced

| artifact | where | state |
|---|---|---|
| R740 context handover for `ugt` | `ugt/docs/R740_HANDOVER_20260731.md`, ~480 lines | **untracked on purpose** — see §3 |
| Solver fixes | `ugt` branch `fix/solver-numerics-headless` @ `aa549dc` | committed, **not pushed** |
| This log | `session_log_20260731.md` | untracked |

---

## 2. Method — and its one deliberate constraint

The R740 was **not** reachable and was **not** contacted. The T420 sits on
`192.168.1.0/24`; the server is on another subnet with no route. Every
statement about the machine was therefore derived from documents, and the
handover tags each claim as LOGGED (observed by a session with a shell on the
box), UNCONFIRMED (asserted, never checked), or VERIFIED (checked here today).
That tagging is the point of the document; do not flatten it when editing.

**Scoped to the last 7 days on request**, which turned out to be the entire
lifetime of Claude Code sessions on that server — 07-28 (install verified),
07-29 (the on-machine storage/RAID session), 07-30 (smartd, mirror, branch
reconciliation). `docs/BERNESE_GPS3_HANDOVER.md` (07-22/23, reconstructed from
phone photos, central diagnosis wrong) was deliberately excluded rather than
merely caveated.

**Transcripts were mined as well as the markdown.** Searched the session
`.jsonl` files for `lscpu`, `free`, `nvidia` output. **There is none.** The
"24 physical cores / 48 threads" figure that two documents rely on has never
been confirmed by a command, after three days of sessions on the box. It is
tagged UNCONFIRMED in the handover, with the command to settle it.

---

## 3. Finding about THIS repo — disclosed, acknowledged, unremediated

`alfieprojectsdev/movefaults` is a **public** repository. `RESUME_NEXT.md` is
tracked in it, and states that `R740_PASS` equals `gps3` — i.e. the sudo
password of a PHIVOLCS server, published alongside its hostname, its IPv4
address, the login user, and the Cockpit port.

`scripts/deploy_r740.secrets` is correctly gitignored. **The disclosure is in
the prose, not the file.**

The machine is LAN-only, so this is not remotely exploitable today. It is
still a live credential in a public index, and git history means deleting the
line does not retract it.

**The user was told and has acknowledged and accepted this.** No remediation
was performed this session. If it is ever actioned, the order is: change the
password first, then scrub the prose, and treat the old one as burned
regardless of history rewriting.

Consequence carried into the handover: `ugt` is **also** a public repo, so
that document deliberately omits the host address, management URL, and any
credential detail. Accepting the exposure here is not a reason to duplicate it
there.

---

## 4. `ugt` findings — reading was not enough

The survey found three defects by reading. **Running the code found a fourth
that fires first, and it invalidates the other three's ordering:**

```
jax.errors.ConcretizationTypeError: The `length` argument to `scan` expects a
concrete `int` value ... depends on the values of the arguments total_steps
and norm_interval
```

Both scripts carry a plain `@jit`, which traces the step counts, while
`lax.scan` needs `length` as a concrete Python int. **Neither script had ever
run.** Fixed with `partial(jit, static_argnums=...)`.

Behind it: `batch_lle(...).block_until_ready()` called on the tuple `vmap`
returns; float32 default; `plt.show()` on a machine that will be headless.

**The float32 claim was asserted in the survey, then measured.** Over the
committed 200-point sweep, float32 vs float64:

| | |
|---|---|
| max abs difference | **0.0588** |
| LLE range (float64) | −0.0357 … 0.0738 |
| difference as fraction of range | **54%** |
| points changing **sign** | **3 of 200** |

Sign is the chaos / no-chaos verdict. float32 was not adding noise, it was
changing the answer at three points on exactly the boundary the thesis argues
about. Verification ran the **full committed sweep**, not a reduced one:
200 params × 50 000 steps, 3.73 s, dtype float64, figure written. ruff 15 → 12
findings, all pre-existing.

**Unexpected result worth acting on:** that sweep takes **3.7 s on this
2-core laptop**. The R740 buys nothing for the current workload. It starts to
matter only for a 2D (R × ω) sweep or far longer integrations. Decide that
before moving anything.

---

## 5. Gotchas

- **Cross-repo work from the wrong CWD.** All of §1's output lives in `ugt`
  while the shell sat in `movefaults_clean`. Every git call used
  `git -C <abs path>`, and the identity check ran first and printed *both*
  remotes for contrast. A bare `git commit` here would have been silent and
  wrong — the exact failure the global rule describes.
- **Reading a script is not running it.** Four defects, three found by
  reading, and the one that actually fires first found in seconds by
  `.venv/bin/python lle_solver.py`. The survey would have shipped an ordered
  list that was wrong at the top.
- **`plt.show()` needs the backend chosen before pyplot is imported.** In
  `ugt`, `plt` is re-exported from `sprott_solver` so import ordering cannot
  silently defeat it — isort would otherwise reorder it into breakage.

---

## 6. State at end / open decisions

**This repo:** untouched except this log (untracked). No background jobs.

**`ugt`:** on `fix/solver-numerics-headless` @ `aa549dc`, one commit ahead of
`main`, **unpushed**. Uncommitted `main.tex` (+25/−2, the 2026 literature
review — never committed, so no clone anywhere has it). Untracked
`docs/R740_HANDOVER_20260731.md` and `.claude/` (a checkout of
`solatis/claude-config`; do not `git add`). `figures/` now gitignored. A
`.venv` was created there with jax/ruff.

Open, all needing the user:

| decision |
|---|
| push `ugt` branch / open PR |
| commit `ugt/main.tex` — **the server has no copy of that work** |
| `ugt` defects 4–6: `setup_env.sh` markdown-mangled curl URL, `[tool.ruff] select` → `lint.select`, `\section\*` + `[Author, 2024]` in `main.tex` |
| whether to commit this log and the handover, and with what scrubbing |
| §3 remediation |
