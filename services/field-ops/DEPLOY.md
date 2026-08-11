# Deploying Field Ops for the Palawan fieldwork

**Written 2026-08-06.** Target: a URL that field staff can open on their phones
before they leave, and that keeps working when they have no signal.

```
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
uv run alembic upgrade head                                    # core schema, 13 revisions
uv run alembic -c services/field-ops/alembic.ini upgrade head  # field_ops schema
```

The two trees are independent — separate `alembic_version` tables (the field_ops
one lives in the `field_ops` schema), no shared ordering. A revision must live in
the tree that owns its table, or the order above cannot work: `fo003` alters
`field_ops.logsheet_photos`, which `fo001` creates, so it has to run in the second
command. It briefly shipped as root `014` and broke exactly this way on a fresh
database.

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

```bash
fly secrets set \
  FIELD_OPS_PRODUCTION=1 \
  DATABASE_URL='...' \
  FIELD_OPS_JWT_SECRET="$(python3 -c 'import secrets; print(secrets.token_hex(32))')" \
  FIELD_OPS_STORAGE_BACKEND=r2 \
  R2_ACCOUNT_ID='...' \
  R2_ACCESS_KEY_ID='...' \
  R2_SECRET_ACCESS_KEY='...' \
  R2_BUCKET='pogf-field-ops'
```

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

1. Import the repo. **Root directory: `services/field-ops/frontend`.**
2. Edit `vercel.json` first — replace `REPLACE-WITH-BACKEND-HOST` with your
   backend hostname:

```json
{ "source": "/api/:path*", "destination": "https://pogf-field-ops.fly.dev/api/:path*" }
```

The rewrite keeps the API same-origin, so there is no CORS preflight — one
fewer round trip on one bar of signal. If you deploy cross-origin instead, set
`VITE_API_BASE_URL` at build time and add the Vercel URL to
`FIELD_OPS_CORS_ORIGINS` on the backend.

3. Deploy. Note the URL.

---

## 5. Create the observer accounts **[you]**

One per person, so `submitted_by` records who filed each sheet. There is no
sign-up screen by design.

```bash
python3 -c "import bcrypt,secrets; pw=secrets.token_urlsafe(9); \
print('password:', pw); print('hash:', bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode())"
```

```sql
INSERT INTO field_ops.users (username, hashed_password, role)
VALUES ('surname', '<hash>', 'field_staff');
```

Give each person their own password **through a private channel**, not a group
chat. Sessions last 8 hours — a full shift without re-entering anything.

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
rclone sync r2:pogf-field-ops ./palawan-photos/     # or the R2 dashboard
```

Then follow the project's own rule: the archive needs a `sha256sum` manifest
committed to git, not just the files. Fingerprints stored only beside the data
prove nothing if that disk is what failed.
