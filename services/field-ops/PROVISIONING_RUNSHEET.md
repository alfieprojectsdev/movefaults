# Field Ops PWA — provisioning run sheet

**Merged from** `services/field-ops/DEPLOY.md` (written 2026-08-06, manual steps)
and `services/field-ops/deploy/deploy.sh` + `preflight.sh` (newer, automated
phases). DEPLOY.md never mentions the scripts and the scripts never mention
DEPLOY.md's section numbers, so the two drifted. This is the single order.

**Work top to bottom.** Every step says who does it, the exact command, what a
pass looks like, and what to do when it doesn't. `[you]` = a platform UI or a
credential; nobody can do it for you.

---

## Stop — three blockers before you touch a platform

These are not style notes. Two of them make a deploy fail outright and one lets
a broken deploy pass every check you would run.

### A. ~~The Dockerfile cannot build from either directory~~ — FIXED 2026-08-18

`services/field-ops/Dockerfile` has two stages that disagree about the build
context:

| Line | Implies context is |
|---|---|
| `COPY frontend/package.json ...` (stage 1) | `services/field-ops/` |
| `COPY pyproject.toml uv.lock ./` (stage 2) | repo root |
| `COPY services/field-ops/src/ ./src/` (stage 2) | repo root |
| `COPY src/db/ ./src/db/` (stage 2) | repo root |

- Build from `services/field-ops/` (what DEPLOY.md §3 tells you to do):
  stage 1 works, **stage 2 fails** — there is no `pyproject.toml` there.
- Build from the repo root: **stage 1 fails** — there is no `frontend/` there.

DEPLOY.md §3 says "The existing `services/field-ops/Dockerfile` builds
unmodified." It does not. Nothing in `docker-compose.yml` builds it either, so
this image has almost certainly never been built.

**Status: done.** `services/field-ops/Dockerfile` has been rewritten in place
(the old one is in git if you want to compare). Two defects were present, not
one — see "Second defect" below. Original analysis kept for the record:

**Fix applied:** deleted stage 1. `main.py` never mounts `StaticFiles`, so
the frontend it builds is copied into the image and then served by nothing —
Vercel serves the PWA. Removing the stage also cuts an `npm ci` from every
deploy.

```dockerfile
FROM python:3.11-slim AS api
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --extra field-ops --no-dev
COPY services/field-ops/src/ ./src/
COPY src/db/ ./src/db/
EXPOSE 8001
CMD ["uv", "run", "field-ops-api"]
```

Then build **from the repo root**, not from `services/field-ops`:

```bash
fly launch --no-deploy --name pogf-field-ops --region sin \
  --dockerfile services/field-ops/Dockerfile
```

*(Alternative, if you ever want the API to serve the PWA: keep stage 1 but
prefix its COPYs with `services/field-ops/`, and add the `StaticFiles` mount
that the Dockerfile comment promises. More work, no benefit for this trip.)*

**This changes DEPLOY.md §3.** `cd services/field-ops` there is wrong.


#### Second defect, found while fixing the first

`pyproject.toml`'s hatch wheel declares `packages`, `services` and `tools` as
wheel roots. So `uv sync --extra field-ops --no-dev` — run in the Dockerfile
*before* any source is copied — tries to build a wheel spanning the whole
monorepo and fails, because none of those trees exist in the image yet.
Copying them in would drag `services/field-ops/frontend/node_modules` along.

The rewritten Dockerfile installs dependencies with `--no-install-project`,
copies only `services/field-ops/src/`, and runs off `PYTHONPATH=/app/src`.
`field_ops` imports nothing outside its own package and its third-party deps,
so that is sufficient — verified by grepping every import in the tree.

It also uses shell-form `CMD` so `${PORT}` expands at runtime. **Keep
`fly.toml`'s `internal_port` at 8001**, or set `PORT` as a Fly secret to match
whatever `fly launch` generates — a mismatch means the health check never
passes and Fly rolls the deploy back.

### B. ~~Two contradictory account schemes~~ — RESOLVED 2026-08-19

**Decision: random passwords, distributed on paper.** The contradiction below
is closed; both the seeder and DEPLOY.md §5 now describe the same scheme.

`seed_field_accounts.py` generates one random password per person, bcrypt-hashes
it into `field_ops.users`, and writes the plaintext once to a `--slips` file at
mode 600. It **refuses to run without `--slips`**, so it cannot mint passwords
that go nowhere. Format is `k7np-qr4m-vx82` — three lowercase groups from a
31-character alphabet with no `0/O` and no `1/l/i`, chosen for whether a cold
observer types it right first time rather than for entropy (it carries 59 bits
regardless).

The `--surnames` path still exists for an instance that is genuinely
unreachable from the internet, and warns loudly when used.

#### Why the old scheme had to go

`seed_field_accounts.py` used to set each password to the holder's surname, and
its docstring was honest about the condition that made that defensible:

> "It is only defensible while the API is not reachable from the open internet."

That condition is now false. The API deploys to a public `*.onrender.com` URL
behind a public Vercel frontend; the repository is public and names PHIVOLCS
staff, so `staff.csv` supplied the username half and a colleague's name the
other. The three options previously listed here (seed-then-reset, follow §5
manually, or add an allowlist) are superseded — the seeder now does the right
thing by default, which was option 2's outcome without option 1's per-person
manual step.

#### Verified end to end, 2026-08-19

Against the Neon `development` branch and the real container image:

- 13 accounts created, roles from `staff.csv` (5 admin / 3 data_processor /
  5 field_staff)
- slips file written mode 600, 13 lines, gitignored by `*credentials*`
- a generated password authenticates: `POST /api/v1/token` → 200, and
  `GET /api/v1/me` returns the right username and role
- a wrong password is rejected with 401

**Still to do before the Palawan deployment:** print the slips, hand them out at
the briefing, then `shred -u field_credentials.txt`. And note the accounts above
exist on the **development** branch — a production deployment needs its own run.

### C. `deploy.sh verify` passes with the wrong station list

`FIELD_RUNBOOK.md` §6: all 138 seeded stations are **continuous CORS**, no
campaign sites, and Palawan coverage is `PLWN` only (no coordinates).
DEPLOY.md §1 says the list must contain the Palawan sites being visited, as
`monitoring_method='campaign'`.

`phase_verify` checks only `stations > 10`. With 138 continuous stations and
zero Palawan campaign sites it passes — and the observer opens the dropdown at
the monument and their site is not in it. Silent, and discovered too late.

**Add the check that matters** (`deploy.sh`, in `phase_verify`, after the
existing station count):

```bash
local campaign
campaign=$(psql "$DATABASE_URL" -tAc \
  "select count(*) from public.stations
    where province='Palawan' and status='active'")
step "active Palawan stations: $campaign"
(( campaign > 0 )) || stop "No Palawan stations — observers cannot select their sites."
```

And confirm by eye before you send anyone the URL:

```bash
psql "$DATABASE_URL" -c \
  "select station_code, name, municipality, monitoring_method, status
     from public.stations where province='Palawan' order by station_code"
```

---

## Phase 0 — Take stock [you]

You said some accounts already exist. Establish which, and whether the *hosted*
database has been migrated — not the local container. Run from the repo root:

```bash
cd /mnt/ssd/home/ltpt420/repos_finch/movefaults_clean

echo "── tooling ──"
for t in uv psql fly flyctl vercel npx rclone; do
  printf '%-8s %s\n' "$t" "$(command -v $t || echo MISSING)"
done

echo "── platform logins ──"
fly auth whoami 2>&1 | head -1
vercel whoami  2>&1 | head -1

echo "── fly app ──"
fly apps list 2>&1 | head -20
fly secrets list -a pogf-field-ops 2>&1 | head -20   # names only, no values

echo "── vercel ──"
vercel projects ls 2>&1 | head -20

echo "── repo ──"
git status --porcelain | head -20
grep -c REPLACE-WITH-BACKEND-HOST services/field-ops/frontend/vercel.json
ls -la data/network_inventory/ 2>&1 | head
```

Then, **only if you have the Neon string in your shell**:

```bash
export DATABASE_URL='postgresql://...-pooler...'   # pooled endpoint
psql "$DATABASE_URL" -c '\dt field_ops.*'
psql "$DATABASE_URL" -tAc "select count(*) from public.stations"
psql "$DATABASE_URL" -tAc "select count(*) from field_ops.users"
psql "$DATABASE_URL" -tAc "select version()"
```

`fly secrets list` prints names and digests only — safe to paste back.
`psql` output above contains no credentials — safe to paste back.
**The connection string itself is not.** Never paste it anywhere.

---

## Phase 1 — Neon Postgres [you]

Skip if it exists. Otherwise, DEPLOY.md §1:

- [ ] Project at neon.tech, region **Singapore `ap-southeast-1`**
- [ ] Copy the **pooled** connection string — host contains `-pooler`.
      The direct endpoint runs out of connections when a container restarts.
- [ ] Store it in your password manager. Never in the repo, a commit, a
      screenshot, or a chat window.

```bash
export DATABASE_URL='postgresql://user:pass@ep-xxx-pooler.ap-southeast-1.aws.neon.tech/neondb?sslmode=require'
```

`?sslmode=require` and `channel_binding` are stripped automatically by
`dburl.to_asyncpg_url` — asyncpg rejects libpq's parameters — and the TLS
requirement is carried across as a verifying `SSLContext`. You do not need to
strip them by hand.

**Check:** `./services/field-ops/deploy/deploy.sh preflight`

Expect a `!` warning on `vercel.json` (placeholder still present — fine at this
stage) and failures on the R2 variables (not created yet). The database section
must be green: *remote host* and *connection succeeds*.

---

## Phase 2 — Migrations

**Order is load-bearing.** field_ops tree first: root `008` extends
`field_ops.logsheets` and `field_ops.staff`, which `fo001` creates. Root first
on an empty DB fails with `schema "field_ops" does not exist`. This was
documented backwards until 2026-08-11.

```bash
./services/field-ops/deploy/deploy.sh db --dry-run    # read the plan
./services/field-ops/deploy/deploy.sh db
```

**Pass:** `field_ops tables: 7` (or more) and `photo idempotency column present`.

**If you previously ran the old root `014`** on this database (T420 or gps3):
it is stamped in root `alembic_version` and the file is gone, so
`alembic upgrade head` cannot resolve it.

```bash
uv run alembic stamp 013     # after pulling; or downgrade 013 before pulling
```

`fo003` re-creates the column and index `014` made, so drop those first if
re-running from a stamped state.

**Do not trust the exit status.** Both trees fall back to `POGF_DB_*` when
`DATABASE_URL` is unset — that is how a "successful" migration once landed on a
local container while the hosted DB stayed empty. The script's own `psql`
verification is the proof, not alembic's output.

---

## Phase 3 — Seed stations, equipment, observers

```bash
./services/field-ops/deploy/deploy.sh seed --dry-run
./services/field-ops/deploy/deploy.sh seed
```

Then **resolve Blocker C.** The seeder loads the 138 continuous CORS stations.
The Palawan campaign sites are not in PHIVOLCS' inventory and must be inserted
by hand — one row per site the team is actually visiting:

```sql
INSERT INTO public.stations
  (station_code, name, municipality, province, monitoring_method, status)
VALUES ('XXXX', 'Site name', 'Municipality', 'Palawan', 'campaign', 'active');
```

- [ ] Every site on the itinerary is in that table
- [ ] `monitoring_method='campaign'` — this is what makes the form ask for
      antenna model, slant heights and session times instead of power/battery
- [ ] `status='active'`

---

## Phase 4 — Cloudflare R2 [you]

- [ ] R2 → Create bucket, e.g. `pogf-field-ops`. Location hint **APAC**.
- [ ] **Keep it private.** Reads go through the API. Site photos show equipment,
      access routes, sometimes people.
- [ ] Manage API Tokens → **Object Read & Write**, scoped to that one bucket
- [ ] Record: account ID, access key ID, secret access key, bucket name.
      **The secret is shown once.**

10 GB free ≈ 3,300 phone photos at ~3 MB. A week in Palawan is nowhere near it.

---

## Phase 5 — Backend on Fly [you]

**Blocker A must be fixed first**, or this fails at `fly deploy`.

From the **repo root**:

```bash
fly launch --no-deploy --name pogf-field-ops --region sin \
  --dockerfile services/field-ops/Dockerfile
```

Secrets via a file, never as arguments — `fly secrets set K=v` puts every value
into your shell history and into the process table where any other user on the
machine can read it:

```bash
umask 077
cat > /tmp/field-ops.env <<'ENV'
FIELD_OPS_PRODUCTION=1
DATABASE_URL=...
FIELD_OPS_STORAGE_BACKEND=r2
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=pogf-field-ops
ENV

printf 'FIELD_OPS_JWT_SECRET=%s\n' \
  "$(uv run python -c 'import secrets; print(secrets.token_hex(32))')" \
  >> /tmp/field-ops.env

fly secrets import < /tmp/field-ops.env
shred -u /tmp/field-ops.env
```

`uv run python`, not system `python3` — the project dependencies are not on the
bare interpreter.

**Do not set `FIELD_OPS_DEV`.** It re-enables every weak default. Production
mode is now *inferred* from a non-local `DATABASE_URL`, so forgetting
`FIELD_OPS_PRODUCTION` no longer silently disables the gate — but `FIELD_OPS_DEV`
still overrides everything.

```bash
fly deploy
curl https://pogf-field-ops.fly.dev/health      # {"status":"ok",...}
```

**If it refuses to start,** read the logs — `_assert_deployable` names every
missing variable at once and never prints a value. It checks: JWT secret not
default and ≥32 chars, storage backend is `r2`, all four R2 variables present,
`DATABASE_URL` set. The R2 variables are validated at *startup*, not at first
upload, precisely so a typo'd `R2_BUCKET` fails here rather than 500-ing on
every photo for a week.

> **Gap worth knowing:** `preflight.sh check_backend_env` reads *your local
> shell*, not Fly's secret store. A clean preflight says nothing about what Fly
> actually has. `fly secrets list` (names only) is the real check. Consider
> adding that comparison to `preflight.sh`.

---

## Phase 6 — Observer accounts

Blocker B is resolved: random passwords, distributed on paper (see above).

```bash
./services/field-ops/deploy/deploy.sh accounts --dry-run
./services/field-ops/deploy/deploy.sh accounts --slips field_credentials.txt
```

One random password per person, bcrypt-hashed into `field_ops.users`, plaintext
written once to the slips file at mode 600. The phase refuses to run without
`--slips` rather than mint passwords that go nowhere.

**Print it, cut it up, hand each person their line at the briefing, then:**

```bash
shred -u field_credentials.txt
```

Per-person replacement, printed once:

```bash
uv run python scripts/seed_field_accounts.py --reset ARP
```

Re-running `accounts` never rewrites an existing password (someone may have
changed theirs), so it issues no slip for anyone who already has an account. It
*does* update roles from `staff.csv`. Both are deliberate.

Sessions last 8 hours: a full shift without re-entering anything.

---

## Phase 7 — Frontend on Vercel [you]

Nothing to run. Vercel builds from the repository, the same way Render builds
the API from `render.yaml`; merging to `main` redeploys both.

1. Import `alfieprojectsdev/movefaults` in Vercel.
2. **Root directory: `services/field-ops/frontend`.**
3. Deploy. Note the URL.

`vercel.json` already points the `/api` rewrite at
`pogf-field-ops-api.onrender.com`, which keeps the API same-origin — no CORS
preflight, and `FIELD_OPS_CORS_ORIGINS` stays empty.

> `deploy.sh frontend --backend-host HOST` was retired 2026-08-19. It edited
> the working tree and pushed from a laptop, so only that machine could deploy
> and nothing in git recorded what was deployed — and once the placeholder had
> been substituted, `--backend-host` was silently ignored, so a run aimed at
> staging would have deployed production.


The `/api` rewrite keeps the API same-origin, so there is no CORS preflight —
one fewer round trip on one bar of signal. `check-deploy-config.mjs` fails the
build if the placeholder survives, but *only when `VERCEL=1`* — a local
`npm run build` merely warns. Don't read a clean local build as confirmation.

If you deploy cross-origin instead, set `VITE_API_BASE_URL` at build time and
add the Vercel URL to `FIELD_OPS_CORS_ORIGINS` on Fly. Wildcards are rejected
by design.

- [ ] Commit the `vercel.json` change — the `sed` edits your working tree

---

## Phase 8 — Verify

```bash
export FIELD_OPS_URL=https://<your-vercel-url>
./services/field-ops/deploy/deploy.sh verify
```

`401` from `/api/v1/stations` is the **pass** — it proves the API is reachable
through the rewrite *and* requires auth. `200` means the endpoint is open and
the script stops. `000` means the rewrite is wrong.

Then the part no script can do. **On a real phone, not a desktop browser:**

- [ ] Open the URL, sign in with a real observer account
- [ ] Station dropdown lists the **Palawan** sites (Blocker C)
- [ ] Add to Home Screen; it opens without browser chrome
- [ ] **Airplane mode.** Full campaign sheet + photo, submit.
      Expect *"Saved offline — including the photo."* Queue tab: **photo held**
- [ ] Signal back on — the queue drains by itself, record moves to synced
- [ ] `logsheet_photos` has a row with an `r2://` path
- [ ] Open that object in the R2 dashboard — it is the right image
- [ ] Force-quit between queueing and syncing, reopen — the sheet is still there
- [ ] **Install, airplane mode, cold open from the home screen.** The service
      worker path has never been exercised on a handset (FIELD_RUNBOOK §6)

**If the airplane-mode step fails, stop.** That is the path they will use most
and its failure mode is silent — the app says "Saved offline" either way.

---

## Phase 9 — Brief the staff

Send them `FIELD_RUNBOOK.md`. Say these three out loud anyway:

1. **Sign in once while you still have signal.** First login needs a connection.
2. **Never clear browsing data. Never use private/incognito.** Queued sheets
   live in browser storage; clearing it destroys unsynced work permanently.
3. **Check the Queue tab before leaving a site.** Pending is normal; it should
   reach zero once back in signal.

Add, given the untested arithmetic: **write the four raw slant measurements in
the paper log as well.** The slant→RH computation has no test behind it and a
wrong answer looks plausible on screen.

Also tell them free tiers sleep — a slow first load after idle is not a failure.

---

## After the fieldwork

```bash
pg_dump "$DATABASE_URL" --schema=field_ops --schema=public -Fc \
  -f palawan-$(date +%Y%m%d).dump

DEST="./palawan-photos-$(date +%Y%m%d)"
rclone copy --dry-run r2:pogf-field-ops "$DEST"
rclone copy r2:pogf-field-ops "$DEST"
```

**`copy`, never `sync`.** `sync` deletes whatever the source no longer has —
pointed at an archive directory it removes the previous export. Dated
destination per run, `--dry-run` first.

Then the project rule: `sha256sum` manifest committed to git, not just the
files. Fingerprints stored only beside the data prove nothing if that disk is
what failed.

---

## Open items to fold back into the repo

- [x] ~~Fix `services/field-ops/Dockerfile`~~ (Blocker A) — done 2026-08-18
- [ ] Correct DEPLOY.md §3: it still says `cd services/field-ops` before
      `fly launch`, which is the wrong build context
- [ ] Decide the account scheme (Blocker B); make DEPLOY.md §5 and
      `seed_field_accounts.py` agree, or delete the claim about a control that
      does not exist
- [ ] Add the Palawan station assertion to `phase_verify` (Blocker C)
- [ ] `preflight.sh`: compare `fly secrets list` names against the required set
- [ ] DEPLOY.md should point at `deploy/deploy.sh` — right now a reader follows
      the manual path and never learns the scripts exist
