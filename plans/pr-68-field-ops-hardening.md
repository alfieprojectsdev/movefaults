# PR #68 field-ops hardening plan

PR: https://github.com/alfieprojectsdev/movefaults/pull/68  
Scope: address the outstanding CodeRabbit findings while preserving the PR's primary objectives: reliable offline photo capture, deployable R2-backed storage, and a safe field PWA. Do not introduce unrelated line-ending normalization or broad UI redesign.

## Goals

- Ensure a mandatory field photo is never silently lost and a storage-full error leaves the operator able to retry.
- Keep offline queue, authentication, and connectivity state consistent across all mounted frontend consumers.
- Make production startup, CORS, upload limits, R2 behavior, and database TLS fail closed.
- Make deployment and retention guidance operationally safe for real field data.
- Add focused frontend and backend tests for the repaired behavior, especially measurement calculations and failure paths.

## 1. Fix the form's photo-failure and status-message paths

File: `services/field-ops/frontend/src/components/LogSheetForm.tsx`

Actions:

1. In the online-logsheet-success/photo-upload-failure branch, wrap `addToQueue(record, photo)` in the same queue-storage-error handling used by offline and network-failure paths.
2. If queue persistence fails, transition out of `saving`, retain the form and selected photo, and show an actionable error that the log is saved but the photo was not queued. Do not reset the form in this case.
3. Use the status state reserved for a server-saved record with a queued photo, and render its explanatory message through the appropriate outcome branch. Keep `queued` exclusive to genuinely offline saves.
4. Make photo-required feedback mutually exclusive: offline users see the offline guidance only; online users see the red validation message only after an appropriate interaction/submit attempt, not on initial render.
5. Remove the now-empty inline `inputStyle` and `readonlyStyle` objects and their attributes so `field.css` is the sole style source.

Tests:

- Mock photo upload failure plus successful queue persistence: assert the form resets and reports that a queued photo will sync.
- Mock photo upload failure plus `QueueStorageError`: assert the form stays populated, the photo remains selected, the submit control is re-enabled, and an actionable error is shown.
- Assert initial, online, and offline no-photo messaging produces exactly the intended single message.

## 2. Establish shared frontend session and queue state

Files:

- `services/field-ops/frontend/src/App.tsx`
- `services/field-ops/frontend/src/services/api.ts`
- `services/field-ops/frontend/src/hooks/useOfflineQueue.ts`
- `services/field-ops/frontend/src/components/QueueView.tsx`

Actions:

1. Introduce one shared authentication source of truth (for example, an external store or React context) rather than initializing `App` authentication only once from `getToken()`.
2. Have `clearToken()` notify that source, so a 401 from either ordinary API calls or photo upload immediately switches the application to the login screen.
3. Refactor queue state to one shared external store/context. A queue mutation from the form must update the badge/count and Queue view without requiring another component to remount.
4. Put all queue flushing behind one module-level in-flight promise. Concurrent callers must await the same flush; clear the guard only after work and count refresh finish, including failures.
5. Use the existing reactive `useOnline` hook in QueueView for its manual-sync button state and label; do not read `navigator.onLine` directly.

Tests:

- A mocked 401 clears auth and causes `App` to render LoginScreen.
- Two hook consumers observe the same pending-count update after `addToQueue`.
- Concurrent manual/automatic flush triggers result in one set of record/photo uploads.
- QueueView button transitions reactively between offline and online, while respecting the busy state.

## 3. Add field-critical measurement tests and wire them into deployment checks

Files:

- Frontend test configuration and package scripts (select the repository's established runner; otherwise add a minimal Vitest + Testing Library setup).
- Tests adjacent to `LogSheetForm.tsx` or its extracted calculation helper.
- `services/field-ops/DEPLOY.md`

Actions:

1. Extract the slant-to-RINEX-height/average-slant calculation into a small pure helper if necessary, keeping form behavior unchanged.
2. Write TDD-style tests covering every supported antenna model, normal values, zero/near-boundary values, invalid values, and partial inputs.
3. Assert the values actually submitted in the payload, not only values displayed on screen.
4. Add a package test command and include it in the documented pre-deployment verification sequence.

## 4. Harden backend production configuration and network behavior

Files:

- `services/field-ops/src/field_ops/config.py`
- `services/field-ops/src/field_ops/main.py`
- `services/field-ops/src/field_ops/storage.py`

Actions:

1. Normalize `FIELD_OPS_PRODUCTION` by trimming and case-folding it; accept documented truthy values such as `1` and `true`. Unrecognized values must not bypass production validation.
2. When R2 is selected, require non-empty account ID, access key ID, secret access key, and bucket name. Accumulate all missing-setting diagnostics and fail before serving traffic.
3. Preserve TLS intent when normalizing `DATABASE_URL`: capture `sslmode`, remove only unsupported URL parameters, and configure `asyncpg` with a suitable SSL context for required/certificate-verifying modes. Keep `channel_binding` removal. Where TLS enforcement cannot be represented safely, emit a non-secret diagnostic and fail rather than silently downgrade to plaintext.
4. Restrict localhost CORS origins to non-production mode; retain explicitly configured non-wildcard origins in all environments.
5. Construct the R2 boto3 client with explicit, bounded connect/read timeouts and a small retry limit, leaving endpoint, credentials, and region behavior intact.

Tests:

- Table-test production flag normalization and every production-gate failure, including each missing R2 credential.
- Test CORS origin construction in development and production.
- Test database URL/connection options for `sslmode=require`, certificate-verifying modes, absent `sslmode`, and channel binding removal; verify TLS is never silently weakened.
- Mock boto3 client construction and assert the explicit timeout/retry config.

## 5. Enforce upload limits before object storage

File: `services/field-ops/src/field_ops/routers/logsheets.py`

Actions:

1. Reject a known oversized request before reading it by checking trustworthy metadata such as `Content-Length` where available.
2. Independently enforce the same limit while streaming/chunk-reading the upload, because per-part metadata can be missing or malicious.
3. Stop reading and return the existing size-limit error before calling storage for an over-limit upload.
4. Preserve the current ordering for valid uploads: bytes must be saved successfully before the database reference is committed.

Tests:

- Oversized declared content length is rejected without calling storage.
- Oversized stream with no useful declared size is rejected before storage.
- Boundary-size valid upload reaches storage and retains the current response/storage-ref behavior.

## 6. Guard frontend deployment configuration

Files:

- `services/field-ops/frontend/vercel.json`
- Frontend CI/pre-deploy script or workflow

Actions:

1. Add a validation script that reads `vercel.json` and fails if any API rewrite destination still includes `REPLACE-WITH-BACKEND-HOST`.
2. Run it in CI and document/run it before deployment, while preserving the intentional manual replacement workflow.

Tests:

- Fixture/config test fails for the placeholder and passes for a valid HTTPS backend host.

## 7. Make deployment, retention, and archive guidance safe

File: `services/field-ops/DEPLOY.md`

Actions:

1. Mark generic fenced diagnostic/example blocks as `text` to satisfy Markdownlint MD040.
2. Replace credential-bearing shell arguments with Fly's protected secret-import/standard-input workflow. Ensure examples avoid placing `DATABASE_URL`, R2 access key ID, or R2 secret in shell history, process arguments, or committed files.
3. Run password-generation commands through `uv run python` so declared dependencies, including bcrypt, are available.
4. Replace destructive `rclone sync` archival guidance with a dated-destination `rclone copy` workflow. Require `--dry-run` review before the actual copy.
5. Define a retention period, access control, deletion approval/procedure, and audit record for both R2 objects and `field_ops.logsheet_photos` rows.
6. Require exports to be encrypted and access-controlled, then securely cleaned up after authorized use. Replace the existing indefinite-retention guidance.

Validation:

- Review commands for secret exposure and destructive behavior.
- Run Markdown linting and validate all command snippets for shell syntax without executing credentialed/deployment operations.

## 8. Resolve review hygiene and verify the release candidate

1. Add concise docstrings to newly introduced backend public functions where they contribute to the configured coverage gate; do not add boilerplate solely to manipulate metrics.
2. Run backend tests, frontend unit/component tests, typecheck, production build, style/Markdown linting, and the Vercel placeholder check.
3. Exercise the phone-focused manual acceptance path in `DEPLOY.md`: login, airplane-mode photo submission, recovery/sync, and a forced storage-full/queue failure simulation.
4. Reconcile the final diff against all 17 CodeRabbit findings, including the outside-diff form failure, and resolve only comments proved by code and tests.
5. Keep line-ending normalization as a separate, explicitly reviewed follow-up, as stated in the PR description.

## Completion criteria

- No path can report an offline or queued photo as safe when it was neither uploaded nor durably stored.
- A 401 reliably ends the authenticated frontend session; queue counts and flushes behave correctly with multiple consumers.
- Production cannot start with incomplete R2 configuration, weak/ambiguous production mode, insecure CORS defaults, or downgraded database TLS.
- Oversized photos do not reach object storage, and R2 failures return quickly enough for client retry.
- Deployment documentation avoids secret exposure and destructive archives, and specifies governed retention/deletion for both database and object-store photo data.
- Automated tests cover the repaired paths, including all supported antenna calculations and submitted payload values.

---

# Session record — 2026-08-11 (T420)

Two commits on `feat/field-ops-styling`, both pushed:

| Commit | Covers |
|---|---|
| `c1a1e9d` | The six findings from the third `/code-review` pass |
| `9413192` | Two deploy-path defects found while *verifying* `c1a1e9d` |

## Why there was no fourth review run

Three `/code-review` passes have run against this branch. Every one found a
defect that made a primary path silently non-functional, and every one died on
the session usage limit before its synthesis step, so nothing was ever reported
through `ReportFindings`. Run 3's six confirmed findings were still sitting
unfixed in the working tree.

Three passes is the convergence signal. A fourth would have spent the same limit
re-deriving findings already in hand, so the decision was to fix rather than
re-review. If an independent pass is still wanted, run it against the *fixed*
tree, where it verifies rather than re-discovers.

Worth knowing for next time: run 3's result payload read
`"level":"high","target":"medium 68"`. The argument parser swallowed `medium`
into the target string, so the run that was meant to be cheaper actually
executed at `high` — which is part of why it hit the limit. The target goes
first: `/code-review 68 medium`.

## `c1a1e9d` — the six findings

1. **The production gate was opt-in.** `_assert_deployable()` returned early
   unless `FIELD_OPS_PRODUCTION=1`, so forgetting one variable on the hosting
   platform silently restored every weak default it exists to catch — including
   the JWT secret published in this public repository, with which anyone can
   mint a token for the deployed URL. `is_production` is now inferred from a
   non-local `DATABASE_URL`; `FIELD_OPS_DEV=1` is the only way out and warns on
   startup. TLS now keys on remoteness rather than the production flag.
2. **Observers were validated after the logsheets were committed.** A stale
   `staff_id` — ordinary after a week offline — raised an FK error *after* that
   commit and surfaced as a 500. The client cannot recover: the flush leaves
   everything pending and replays the same doomed batch forever, so the queue
   wedges permanently and the only symptom is a Sync button that appears to do
   nothing. Validation moved ahead of the write; the 422 names the offending
   record. The test pins the real contract — **zero rows written** on refusal.
3. **A rejected batch was invisible.** `runFlush()` logged to the console and
   returned, right for a network failure and wrong for a 4xx that will fail
   identically forever. `ApiError` now carries the status; a permanent rejection
   falls back to per-record submission so good sheets get through, and the
   offender is marked with the server's own message and shown in QueueView with
   a retry action. Its photo blob is deliberately kept.
4. **Losing the photo dedupe race orphaned an R2 object.** Storage backends
   gained `delete()`, called best-effort — the operator's upload has already
   succeeded, and a failed cleanup must not turn that into an error.
5. **Migration `014` was in the root alembic tree**, but the table it alters is
   created by `fo001` in the field-ops tree. Moved to `fo003`.
6. **The photo-failure path reported the wrong thing.** With a full device, the
   unguarded `addToQueue` fallback ended up reporting "Could not save offline"
   for a logsheet that was already on the server — wrong in the direction that
   sends someone back to a site for nothing.

## `9413192` — what verification turned up

Running the plan's own verification step, once docker was back, found two more
defects. Both made `alembic upgrade head` print success while doing the wrong
thing, which is why neither had been noticed.

- **Neither alembic tree read `DATABASE_URL`.** Both built their URL from the
  discrete `POGF_DB_*` variables, defaulting to `localhost:5433/pogf_db`.
  DEPLOY.md tells the operator to export `DATABASE_URL` and run both trees — so
  following it would have migrated the laptop and left Neon empty, with the
  first symptom being a 500 from the deployed API *after* the field team had the
  URL.
- **The two trees were documented in the wrong order.** Root `008` extends
  `field_ops.logsheets` and `field_ops.staff`, which `fo001` creates, so root
  first on an empty database fails with `schema "field_ops" does not exist`.
  Backwards since `008` landed; it survived because every environment that
  "worked" already had the schema from an earlier manual step. **field-ops tree
  first, then root.**

Connection-string handling moved to `field_ops/dburl.py`, shared by the app and
both migration environments. It cannot live in `config.py`: importing that
module instantiates `Settings` and runs the deployment gate, and an operator
migrating a hosted database from a laptop has no reason to hold a production JWT
secret or R2 credentials.

## Verified

- Fresh scratch database, created empty: field-ops tree → `fo003`, then root →
  `013`, with `content_sha256` and its partial unique index present on
  `field_ops.logsheet_photos`. Scratch database dropped afterwards.
- `uv run pytest services/field-ops/tests/` — 10 passed (was 7; three new).
- `tsc --noEmit` clean; `npm run build` clean (which also runs
  `frontend/scripts/check-deploy-config.mjs` — note that is its real path, not
  `services/field-ops/scripts/`).
- `ruff check` clean on all 17 changed files. The four pre-existing findings in
  `main.py`, `auth.py`, `stations.py`, and `conftest.py` were left alone.
- Production gate exercised directly: a remote `DATABASE_URL` with no other
  configuration raises and names the weak JWT secret; the same command with
  `FIELD_OPS_DEV=1` imports cleanly and warns.

## Open before merging #68

- **Manual acceptance on a phone** (§8.3 above): login, airplane-mode photo
  submission, recovery/sync, forced storage-full. Nothing here substitutes for
  it, and Palawan is next week.
- The branch is **24 commits behind `origin/main`** — all bernese/docs work from
  gps3 (PRs #61, #67, #69), with **zero file overlap**. A merge is clean but not
  required for correctness.
- Line endings still have no `.gitattributes`; the repo is mixed CRLF/LF and
  every edit this session had to preserve CRLF by hand. Deliberately still a
  separate change.
- No frontend tests. The slant → RINEX-height computation remains untested.
