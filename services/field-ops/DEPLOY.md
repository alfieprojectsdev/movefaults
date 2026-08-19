# Deploying Field Ops for the Palawan fieldwork

**Written 2026-08-06.** Target: a URL that field staff can open on their phones
before they leave, and that keeps working when they have no signal.

```text
Vercel        →  the PWA (static build)
Fly / Railway →  FastAPI container (the existing Dockerfile)
Neon          →  Postgres
Cloudflare R2 →  photo blobs
```

**Nothing here creates accounts or handles credentials on your behalf.** Every
step you must do yourself is marked **[you]**. Values go into each platform's
secret store; none of them belong in this repo.

---

## 0. Read this before provisioning anything

Three things were broken for field use and are now fixed. They are worth knowing
because they change what you should test:

| Was | Now |
|---|---|
| **No login screen at all** — `login()` existed but nothing called it; the only way in was to hand-craft a JWT into `localStorage` | Real sign-in form; one account per observer |
| **Offline submissions destroyed the photo** — the blob was never queued, and `reset()` cleared it, while the UI said "Saved offline" | Photo is queued in IndexedDB with the record and uploaded on sync |
| **Photos written to local disk** — fine on a laptop, gone on the next container restart | Configurable backend; **production refuses to start unless it is R2** |

The Queue tab now lists what is on the device and what has synced, so an
operator can confirm their day's work exists before leaving a site.

---

## 1. Neon — Postgres **[you]**

1. Create a project at neon.tech. Region: **Singapore** (`ap-southeast-1`) — the
   closest to Palawan; every extra 100 ms shows up on a weak link.
2. Copy the connection string. It looks like
   `postgresql://user:pass@ep-xxx.ap-southeast-1.aws.neon.tech/neondb?sslmode=require`
3. Keep it in your password manager. It is a credential — do not paste it into
   chat, a commit, or a screenshot.

**Use the pooled endpoint** (Neon shows it as "Pooled connection", host contains
`-pooler`). A container that restarts holds connections open; the direct
endpoint runs out.

`?sslmode=require` and `channel_binding` are stripped automatically — asyncpg
rejects libpq's parameters and the resulting error is not obvious.

### Run the migrations **[you]**

From this repo, with `DATABASE_URL` exported in your shell:

```bash
export DATABASE_URL='postgresql://...'          # from Neon, pooled
uv run alembic -c services/field-ops/alembic.ini upgrade head  # field_ops schema, 3 revisions
uv run alembic upgrade head                                    # core schema, 13 revisions
```

**The field_ops tree runs first.** The two trees keep separate `alembic_version`
tables (the field_ops one lives in the `field_ops` schema) and neither knows
about the other, but they are not independent in practice: root `008` extends
`field_ops.logsheets` and `field_ops.staff`, which `fo001` creates. Run the root
tree first on an empty database and `008` fails with `schema "field_ops" does not
exist`.

This order was documented backwards until 2026-08-11 and had never been run
against a genuinely empty database — every environment that "worked" had the
field_ops schema already in place from an earlier manual step.

A revision must also live in the tree that owns its table. `fo003` alters
`field_ops.logsheet_photos`, so it belongs here; it briefly shipped as root `014`
and failed the same way for the same reason.

Both trees read `DATABASE_URL` and fall back to the discrete `POGF_DB_*`
variables. Until 2026-08-11 they read **only** `POGF_DB_*`, so the sequence above
migrated whatever those pointed at — by default a local container — while the
hosted database stayed empty and `alembic upgrade head` reported success either
way. Confirm you migrated the right database with the `psql` checks below rather
than trusting the exit status.

> **If you already ran the old root `014`** on a database (T420, gps3): it is
> stamped in the root `alembic_version` and the file no longer exists, so the next
> `alembic upgrade head` will fail to resolve it. Run
> `uv run alembic downgrade 013` **before** pulling this change, or
> `uv run alembic stamp 013` after. The column and index it created are harmless
> to leave in place — `fo003` re-creates them, so drop them first if you are
> re-running from a stamped state.

Verify before moving on — a partial migration surfaces as a confusing 500 later:

```bash
psql "$DATABASE_URL" -c "\dt field_ops.*"
psql "$DATABASE_URL" -c "\d field_ops.logsheet_photos"   # needs content_sha256
```

Expect 7 tables: `users`, `logsheets`, `staff`, `logsheet_observers`,
`equipment_inventory`, `logsheet_photos`, `equipment_history`.

### Seed stations and staff **[you]**

The station list is what the observers pick from — it must contain the Palawan
sites they are actually visiting, which the 10 demo rows do **not**.

```sql
INSERT INTO public.stations (station_code, name, municipality, province, monitoring_method, status)
VALUES ('XXXX', 'Site name', 'Municipality', 'Palawan', 'campaign', 'active');

INSERT INTO field_ops.staff (full_name, initials, role, is_active)
VALUES ('Full Name', 'FN', 'field_staff', true);
```

---

## 2. Cloudflare R2 — photos **[you]**

1. Cloudflare dashboard → R2 → **Create bucket**, e.g. `pogf-field-ops`.
   Location hint: **APAC**.
2. **Keep it private.** Site photos can show equipment, access routes and
   occasionally people. Reads go through the API, not a public bucket URL.
3. R2 → **Manage API Tokens** → Create token, permission **Object Read & Write**,
   scoped to that one bucket.
4. Note four values: account ID, access key ID, secret access key, bucket name.
   The secret is shown **once**.

Free tier is 10 GB — roughly 3,300 phone photos at ~3 MB. A week in Palawan will
not come close.

---

## 3. Backend container **[you]**

The existing `services/field-ops/Dockerfile` builds unmodified. Fly.io shown;
Railway and Render are equivalent.

```bash
cd services/field-ops
fly launch --no-deploy --name pogf-field-ops --region sin
```

Set secrets — **names here, values from your password manager**:

Write them into a file and pipe it in, rather than passing them as arguments:

```bash
cat > /tmp/field-ops.env <<'ENV'
FIELD_OPS_PRODUCTION=1
DATABASE_URL=...
FIELD_OPS_JWT_SECRET=...
FIELD_OPS_STORAGE_BACKEND=r2
R2_ACCOUNT_ID=...
R2_ACCESS_KEY_ID=...
R2_SECRET_ACCESS_KEY=...
R2_BUCKET=pogf-field-ops
ENV

# generate the JWT secret with the project interpreter, straight into the file
printf 'FIELD_OPS_JWT_SECRET=%s\n' \
  "$(uv run python -c 'import secrets; print(secrets.token_hex(32))')" \
  >> /tmp/field-ops.env

fly secrets import < /tmp/field-ops.env
shred -u /tmp/field-ops.env      # or: rm -P  /  srm
```

`fly secrets set KEY=value` on the command line puts every one of those values
into your shell history and, while it runs, into the process table where any
other user on the machine can read it. `import` reads stdin instead, so nothing
sensitive is ever an argument.

Generate with `uv run python`, not the system `python3` — bcrypt and the rest
are project dependencies, and the bare interpreter will not have them.

A **fail-closed** startup check refuses to boot if the JWT secret is the shipped
default or under 32 characters, if storage is not R2, or if `DATABASE_URL` is
missing.

That check exists because this repo is **public**. With the default secret,
anyone who reads it can mint a valid token for your URL and post logsheets as
any user. A service that boots happily in that state is worse than one that
refuses, because nobody finds out.

`FIELD_OPS_PRODUCTION=1` used to be what switched that check on — which meant
forgetting one variable silently disabled the whole thing, in exactly the
situation it was written for. It is now **inferred**: any `DATABASE_URL` whose
host is not local puts the process in production mode. Setting the variable is
still fine and still documented above, but it is no longer load-bearing.

The one way out is `FIELD_OPS_DEV=1`, for deliberately running a local build
against a remote database. It skips the checks and warns loudly on startup.
**Never set it on a deployed instance** — it re-enables every weak default.

```bash
fly deploy
curl https://<your-app>.fly.dev/health     # {"status":"ok",...}
```

If it will not start, read the logs — the refusal message names every missing
variable at once, and never prints a value.

---

## 4. Frontend on Vercel **[you]**

Vercel builds from the repository, the same way Render builds the API from
`render.yaml`. There is no deploy command to run from a laptop, and nothing to
edit at deploy time — merging to `main` redeploys both halves.

1. Import `alfieprojectsdev/movefaults`. **Root directory:
   `services/field-ops/frontend`.**
2. Deploy. Note the URL.

That is the whole procedure. `vercel.json` already points the `/api` rewrite at
the deployed backend:

```json
{ "source": "/api/:path*", "destination": "https://pogf-field-ops-api.onrender.com/api/:path*" }
```

**The rewrite keeps the API same-origin**, so the browser never makes a
cross-origin request and there is no CORS preflight — one fewer round trip on
one bar of signal. It also means **`FIELD_OPS_CORS_ORIGINS` stays empty**;
setting it changes nothing while the rewrite is in place. Only a cross-origin
deployment needs it, together with `VITE_API_BASE_URL` at build time.

### If you fork this, or move the backend

`scripts/check-deploy-config.mjs` fails the build when `vercel.json` still
contains `REPLACE-WITH-BACKEND-HOST`, but **only when `VERCEL=1`** — local and
Docker builds never read that file, so they are not blocked by it. A rewrite
destination is not validated at build time, so without that check a deploy
that forgot this step would build, load, render and install perfectly, and only
the API calls would fail — which an offline-capable PWA shows as "no signal"
rather than "misconfigured". Better to break the build where someone is
watching.

> **`deploy.sh frontend` was retired 2026-08-19.** It substituted the
> placeholder in the working tree and pushed with `vercel deploy --prod`, which
> meant only the machine that ran it could deploy and nothing in git described
> what was deployed. It also had a trap: once the placeholder was substituted,
> the `sed` silently no-opped and `--backend-host` was ignored, so a re-run
> aimed at staging would deploy production. Git integration removes both.

---

## 5. Create the observer accounts **[you]**

One per person, so `submitted_by` records who filed each sheet. There is no
sign-up screen by design.

```bash
uv run python scripts/seed_field_accounts.py --dry-run
uv run python scripts/seed_field_accounts.py --slips field_credentials.txt
```

The seeder reads the roster from `data/network_inventory/staff.csv`, generates
one random password per person, bcrypt-hashes it into `field_ops.users`, and
writes the plaintext ONCE to the `--slips` file at mode 600. It refuses to run
without `--slips` rather than mint passwords that go nowhere.

Passwords look like `k7np-qr4m-vx82` — twelve lowercase characters in three
groups, from an alphabet with no `0/O` and no `1/l/i`. That is not about
entropy (59 bits is far past what this needs); it is about an observer typing
it correctly, one-handed, on a damp phone at a monument.

**Print the slips file, cut it up, hand each person their own line at the
briefing, then destroy it:**

```bash
shred -u field_credentials.txt
```

It is gitignored (`*credentials*`), but treat that as a safety net rather than
a plan. Re-running the seeder does **not** rewrite an existing account's
password, so a second run issues no slip for someone who already has one — use
`--reset INITIALS` for a single replacement, printed once.

> **Earlier versions of this section, and of the seeder, set each password to
> the holder's surname.** That was a deliberate fieldwork trade with one stated
> condition: it held only while the API was unreachable from the open internet.
> Deploying to a public `*.onrender.com` behind a public Vercel URL ends that
> condition, and this repository is public and names the staff — so both halves
> of every credential would have been derivable from `staff.csv`. Decision,
> 2026-08-19: random passwords, distributed on paper. `--surnames` still exists
> for a genuinely unreachable instance and warns loudly when used.

Sessions last 8 hours — a full shift without re-entering anything.

---

## 6. Verify before you send the URL

Do all of this on a real phone, not a desktop browser. **Step 4 is the one that
matters most and the one most likely to be skipped.**

- [ ] Open the URL, sign in with a real observer account
- [ ] Station dropdown lists the **Palawan** sites, not the demo ten
- [ ] "Add to Home Screen" installs it; it opens without browser chrome
- [ ] **Enable airplane mode.** Fill a full campaign sheet, attach a photo,
      submit. Expect *"Saved offline — including the photo."* Check the Queue
      tab shows it as **photo held**
- [ ] Turn signal back on. The queue should drain by itself; the record moves to
      synced
- [ ] Confirm in the DB that the row exists **and** `logsheet_photos` has a row
      with an `r2://` path
- [ ] Open the object in the R2 dashboard and confirm it is the right image
- [ ] Force-quit the app between queueing and syncing, reopen — the queued sheet
      must still be there

If step 4 fails, stop and fix it before anyone travels. That is the path they
will use most, and its failure mode is silent.

---

## 7. Brief the staff on three things

1. **Sign in once while you still have signal.** The app then works offline for
   the rest of the day, but the first login needs a connection.
2. **Do not clear browsing data, and do not use private/incognito.** Queued
   sheets live in the browser's storage; clearing it destroys unsynced work.
3. **Check the Queue tab before leaving a site.** If it shows pending items,
   that is normal — but the count should drop to zero once back in signal.

---

## 8. Known gaps — decide before, not during

- **No frontend tests.** The slant→RH computation is the only real domain
  arithmetic in the UI and has none. A wrong answer there silently corrupts the
  vertical component of every campaign occupation. It is verified by hand for
  `TRM55971-00` only.
- **No password reset.** Locked out means you issue a new hash by hand. For a
  one-week trial that is acceptable; make sure someone with DB access is
  reachable.
- **No admin view.** Reading the data means SQL against Neon.
- **Free tiers sleep.** A Neon or Fly instance idle for hours takes a few
  seconds on first request. Harmless, but tell staff so a slow first load is not
  read as a failure.
- **Photos are never deleted.** No retention policy; at ~3 MB each the 10 GB
  free tier is fine for this trip and will need a decision later.

---

## 9. After the fieldwork

Export before tearing anything down:

```bash
pg_dump "$DATABASE_URL" --schema=field_ops --schema=public -Fc -f palawan-$(date +%Y%m%d).dump

DEST="./palawan-photos-$(date +%Y%m%d)"
rclone copy --dry-run r2:pogf-field-ops "$DEST"   # read the list first
rclone copy r2:pogf-field-ops "$DEST"
```

**`copy`, never `sync`.** `rclone sync` makes the destination match the source
by *deleting* whatever the source no longer has — pointed at an archive
directory, it removes the photos from the previous export. A dated destination
per run means no export can overwrite another, and `--dry-run` first means you
see what is about to move before it moves.

Then follow the project's own rule: the archive needs a `sha256sum` manifest
committed to git, not just the files. Fingerprints stored only beside the data
prove nothing if that disk is what failed.
