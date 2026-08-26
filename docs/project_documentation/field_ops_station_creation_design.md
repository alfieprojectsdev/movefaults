# Creating a station from inside the field app — design for review

**Status: DRAFT 2026-08-23 — design for review. Nothing is built.**
**Source:** [issue #118](https://github.com/alfieprojectsdev/movefaults/issues/118),
reported from the field-ops group.
**Ticket:** FO-001 in [`ticket_backlog.md`](ticket_backlog.md).

---

## The question it answers

> *An observer is standing at a monument that is not in the Station picker.
> What now?*

Today: nothing. They cannot file a sheet for it. Somebody back at the office has
to add the site to the source list before the team leaves, and that fails
whenever a visit is decided late.

## Why this is not what the report says it is

The report calls the station list *stale* — "the list came from an earlier
export and hasn't been updated since". That reading is close enough to act on
but wrong in a way that changes the design, so it is worth being exact.

The list is not drifting behind an authoritative source. **It never contained
these sites and no process would ever have added them.** `public.stations` is
seeded from `data/network_inventory/stations.csv` — 138 rows, every one of them
`monitoring_method = continuous`. The seeder says so in its own docstring:

> **No campaign sites.** All 135 rows are continuous CORS. Campaign occupations
> — including the Palawan sites — are not in this spreadsheet and must be
> seeded from another source.
>
> — `scripts/seed_network_inventory.py`

(That docstring says 135; the CSV holds 138. The figure drifted, the claim did
not — all 138 are `continuous`, verified by parsing the file. Worth correcting
in passing, and a reminder that counts in this repo rot as fast as line
numbers.)

`FIELD_RUNBOOK.md` §6 already lists this as a known gap teams must resolve
before departure. So the missing sites are not a maintenance lapse; there is a
whole category of station — campaign occupations, the entire reason the campaign
half of the form exists — with **no ingest path at all**.

That matters because "keep the export fresher" is not a fix, and any design that
amounts to a better sync of the same spreadsheet solves nothing.

## Two things in the report that are already fine

Both were listed as risks. Neither is one, and building guards for them would be
wasted work.

**1. "New sites created offline need to survive sync without being refused for
an unknown station code."** They already do. `field_ops.logsheets.station_code`
is a loose `VARCHAR(10)` — no foreign key, no lookup. `models.py` labels it
`# loose ref to public.stations`, and the reason is recorded there: cross-schema
FKs were avoided deliberately, matching VADASE's denormalised pattern. The
submit-time `@model_validator` in `routers/logsheets.py` checks antenna models,
slant counts and equipment-change pairs, and **never mentions `station_code`**.
A sheet naming a station that does not exist is accepted with a 201 today.

The damage from an unknown code is therefore not rejection. It is silence: the
sheet lands, and the site is absent from the picker, from the `/sheets` view's
joins, and from `equipment_history`. Nobody is told anything is wrong.

**2. Offline availability.** Worth knowing before designing an offline create
path: the station list is **not** in IndexedDB, despite the docstring at the top
of `routers/stations.py` claiming it is. It is a Workbox
`StaleWhileRevalidate` HTTP cache with `maxAgeSeconds: 86400`
(`frontend/vite.config.ts`). After a day offline the entry expires and a cold
start already shows *"Stations unavailable (offline?)"* — this is a pre-existing
24-hour cliff, not something this feature introduces. But it does constrain it:
a locally-created station kept only in that cache would evaporate the same way.
See *Fix the 24-hour cliff in the same ticket*, below.

While correcting that docstring, note it also says "35 stations" — which
disagrees with `StationPicker.tsx` (138) and a comment further down the same
file (140).

---

## Decision 1 — proposals live in `field_ops`, not `public.stations`

**App-created stations are written to a new `field_ops.station_proposals`
table. They are never inserted straight into `public.stations`.**

`public.stations` is the master record for three consumers, not one:
VADASE-rt-monitor reads `host`/`port` for its TCP streams, bernese-workflow
links `station_code` to `.STA` info, and field-ops reads the picker list.
Putting unverified rows in that table puts them in front of all three.

field-ops also declines to own it. `routers/stations.py` reads the table through
raw SQL with `ST_Y`/`ST_X` rather than importing the ORM model, and says why:

> the ORM model for public.stations lives in src/db/models.py, not here, so we
> use a text query rather than importing across service boundaries.

A separate proposals table respects that, and three further things fall out of
it for free:

- **"Unverified" becomes structural.** An unreconciled station is not a row with
  a flag somebody might forget to filter on. It is in a different table. You
  have to go and get it.
- **The migration lands in the low-risk alembic tree.** field-ops has its own
  chain (`fo001`…`fo006`) whose `env.py` keeps `alembic_version` inside the
  `field_ops` schema. The root tree cannot even reach head on Neon —
  `DEPLOY.md` records revision `012` failing on a TimescaleDB feature the
  licence rejects. A new field-ops revision `fo007` avoids that entirely.
- **The seeder stays safe.** `seed_network_inventory.py` upserts with
  `ON CONFLICT (station_code) DO UPDATE ... COALESCE(...)`, and the comment
  beside it explains the COALESCE is there so a hand-corrected coordinate is
  not reverted to NULL by a later re-seed. A proposal in a separate table cannot
  collide with that logic at all.

`GET /api/v1/stations` — already raw SQL — becomes a UNION over both tables,
every row carrying an `origin` of `inventory` or `field`. The picker shows
proposals alongside inventory stations, visibly marked.

### The alternative, and why not

Writing into `public.stations` with a `verified` boolean is simpler to read (no
UNION) and was the obvious first thought. It was rejected because it inverts the
safety property: the default becomes "visible to everything, trusted, unless
someone remembers to filter", and it forces a migration into the tree that
cannot currently migrate. The reconcile step then has to be built as discipline
rather than as a state transition, which is exactly the failure the report
warned about.

## Decision 2 — any signed-in observer may propose one

**No role gate on creation.** The person blocked is the observer at the
monument; requiring `admin` reintroduces the office round-trip this whole
feature exists to remove, and an observer in the field has no admin present.

Safety comes from the row being a *proposal* until reconciled, not from
restricting who may file it. This is the same argument the codebase already
accepted once — `routers/stations.py` used to filter the picker to
`status = 'active'` and stopped, on the grounds that *"an observer standing at a
monument that is not in the picker cannot file a sheet at all."*

`require_role` (`routers/auth.py`) — built alongside the roles and still
deliberately unused, waiting for "the first genuinely privileged endpoint" — is
therefore **not** the gate on `POST /stations`. It is the gate on the reconcile
endpoints. That is its first real consumer.

---

## The proposal record

One row per proposed site, in `field_ops.station_proposals`.

| Field | Why |
|---|---|
| `id` | surrogate PK |
| `client_uuid` | minted on the handset, the idempotency key — same contract as `logsheets.client_uuid`, so a retried sync cannot double-insert |
| `station_code` | `VARCHAR(10)` to match both `public.stations.station_code` and `logsheets.station_code`; canonically 4 characters |
| `name` | free text, as on the monument's plate or in the tasking |
| `location` | PostGIS `POINT` SRID 4326, built `ST_SetSRID(ST_MakePoint(lon, lat), 4326)` — same construction the seeder uses. Nullable: see open questions |
| `monitoring_method` | `campaign` \| `continuous`. The expected value here is `campaign` — that is the category with no ingest path |
| `status` | defaults `active`; a proposed site is one being visited |
| `municipality`, `province`, `region` | mirrors `public.stations` so promotion is a straight copy, not a mapping |
| `created_by` | FK to `field_ops.users` — who proposed it, for the reconciler to ask |
| `created_at` | server time |
| `proposed_at` | handset time at creation, which may be days earlier offline. Keep both; they answer different questions |
| `reconciled_at` | NULL until promoted or rejected. **This column is the state machine** |
| `reconciled_by` | FK to `field_ops.users` |
| `reconciled_station_id` | the `public.stations.id` it became, NULL if rejected |
| `rejected_reason` | free text; a rejected proposal is not deleted |
| `notes` | observer's free text — "monument found, no plate", etc. |

**Why `reconciled_at` rather than a status enum:** the partial unique index
below keys off `reconciled_at IS NULL`, and one nullable timestamp that also
records *when* beats an enum plus a separate timestamp. This mirrors how the
provenance work treats time-stamped facts over derived flags — see
[`provenance_record_design.md`](provenance_record_design.md).

---

## The duplicate guard, in three layers

The report is right that this is the load-bearing risk: a typo'd code creates a
shadow station that looks real. Three layers, because the database one is not
reachable from the field.

1. **On the handset, before submit.** `useStations()` already holds the whole
   list in memory. Reject an exact collision outright, and *warn* on a near
   miss — same code in different case, a transposition, or an existing code
   whose name does not resemble what the observer typed. A warning, not a
   block: the observer is the one looking at the monument.
2. **On the server, at create.** Reject a code already present in
   `public.stations` **or** in an unreconciled proposal → `409`. The shape to
   copy is `POST /api/v1/inventory` in `routers/equipment.py`, which uses
   `on_conflict_do_nothing(index_elements=["qr_code"])` and returns 409.
3. **In the schema.** A unique index on `station_proposals(station_code)`
   **partial on `reconciled_at IS NULL`**. Partial, so that a code can be
   proposed again after an earlier proposal was promoted or rejected — a plain
   unique index would permanently burn every code ever typed, including typos.

**The hole this leaves, stated plainly:** an observer who has been offline for
two days cannot consult layers 2 or 3. Two teams can independently propose the
same code, and both proposals sync successfully. That is unavoidable — the
alternative is refusing to let people work offline — and it is precisely why
promotion must be a human decision rather than an automatic upsert. Reconcile is
not a tidying step; it is where this class of collision is actually resolved.

---

## Offline path

**Do not build a second queue.** `useOfflineQueue.ts` already carries the parts
that were expensive to get right, several of them from real field failures:

- the single-flight `flushInFlight` lock, cleared in `finally` so a rejection
  cannot wedge it;
- `withTimeout` on every IndexedDB call, because a hung open must not look like
  an empty queue;
- the permanent-vs-transient split on `ApiError.isPermanent` (4xx except 401,
  408, 429), with `flushIndividually` quarantining a bad record to
  `_status: "error"` so one rejection cannot block the day's other sheets;
- `storageHeadroom()` refusing a write that would not fit.

Extend it: `DB_VERSION` 3 → 4, adding a `station_queue` store, and generalise
`runFlush()` over both stores. Reimplementing any of the above in a parallel
queue means reimplementing the bugs too.

**Flush order is a new requirement.** A proposal must reach the server *before*
any sheet naming it, so the station exists when the sheet lands. Sheets today
have no ordering constraint between records at all — this is the first one, and
it needs to survive the `flushIndividually` path as well as the batch path.

**The proposal must appear in the picker immediately**, long before it syncs.
`StationPicker` reads React Query, which is in-memory with no persister, so
pending proposals have to be merged into `useStations()` output on the client.
They should be visibly distinguishable in the list — the picker already groups
by status with `<optgroup>`, so a fourth group ("Added here — not yet
confirmed") fits the existing shape.

### Fix the 24-hour cliff in the same ticket

Persist the fetched station list to IndexedDB rather than relying on the Workbox
`maxAgeSeconds: 86400` entry. Without this, the feature ships onto a list that
disappears after a day offline — a team on a week-long campaign would lose both
the inventory list and the context needed to duplicate-check their own new
sites. It is a small change and it is a precondition, not a follow-up.

---

## Reconcile

Two endpoints, both `require_role("admin", "data_processor")`:

- `GET /api/v1/station-proposals` — unreconciled first, with each proposal's
  sheet count, so the reviewer can see whether it is already carrying data.
- `POST /api/v1/station-proposals/{id}/promote` — inserts into
  `public.stations` using the same `ON CONFLICT (station_code) DO UPDATE ...
  COALESCE(...)` shape as the seeder (so promotion cannot null out a field the
  spreadsheet later fills), then stamps `reconciled_at`, `reconciled_by` and
  `reconciled_station_id`.
- Rejection is the same endpoint's sibling: stamp `reconciled_at` and
  `rejected_reason`, leave `reconciled_station_id` NULL. **The row is kept.**
  A rejected proposal with sheets attached is a data-quality finding, not
  garbage.

Promotion is the one place field-ops writes to `public.stations`. Keep it in
one function, and keep it raw SQL for the same boundary reason as the read path.

---

## The largest hidden cost: none of this is testable today

This deserves to be read before anyone estimates the ticket.

`services/field-ops/tests/conftest.py` runs on **in-memory SQLite** with
`schema_translate_map={"field_ops": None}`, and its own docstring notes that
SQLite cannot exercise Postgres-specific behaviour. `public.stations` is not in
`FieldOpsBase.metadata`, so `create_all` never creates it, and SQLite has no
`ST_Y`/`ST_X`. That is why there is **no `tests/test_stations.py` and zero
coverage on `GET /api/v1/stations`** — not an oversight, an inability.

Everything proposed here is PostGIS-touching. So the ticket needs, as a
prerequisite:

- **a Postgres integration fixture** against the docker-compose TimescaleDB on
  5433 (which bundles PostGIS), behind the `@pytest.mark.integration` marker
  that `conftest.py` already anticipates in its docstring and that nothing
  currently uses; or
- a station-lookup seam that can be dependency-overridden, keeping the routing
  and validation tests on SQLite and confining PostGIS to a thin adapter.

The first is more honest and unblocks the existing untested endpoint too.

Note also that every `station_code` in the current tests is a bare literal
(`"PBIS"`, `"BOST"`, `"BTU2"`) that need not exist anywhere. Those tests are
fine as-is under this design — nothing here adds validation to the sheet-submit
path — but they would all break if anyone later decides an unknown code should
be rejected on submit. Two changes, two tickets; do not bundle them.

Frontend testing is in better shape: `fake-indexeddb/auto` is already wired in
`src/test/setup.ts`, and `useOfflineQueue.test.ts` is the pattern to copy —
including its `IDBObjectStore.prototype.put` spy for asserting write counts,
which is what will catch a station queue accidentally rewriting photo blobs.
There are currently no tests for `StationPicker` or `useStations`; a create
form would be the first.

---

## Open questions

Not answered here. Answer them before building, not during.

1. **Must a proposal carry coordinates?** `useDeviceLocation` and
   `distanceMetres` can prefill from the handset, but handset accuracy is
   metres — fine for sorting a picker by proximity, meaningless as a monument
   position. Options: require them and accept they are approximate and clearly
   labelled; or allow NULL and let the picker's nearby-radius feature simply not
   apply. Note `PLWN` already exists in the inventory with no coordinates, so
   NULL is not unprecedented.
2. ~~**Who reconciles, and how often?**~~ **ANSWERED 2026-08-26.**

   > *"We can always discuss over the group chat (live) what the site name or
   > code will be going forward."*

   That is a real answer, and it splits the question in two.

   **The hard half is resolved socially, and quickly.** Adjudicating a
   collision and agreeing the canonical code needs people who know the
   network; no schema does it. If the field-ops group chat settles the code
   the same day it is created, collisions surface in hours rather than being
   discovered weeks later by someone reading a queue.

   **That deflates the duplicate-guard anxiety recorded above.** The three
   layers still stand and the partial unique index is still right, but the
   scenario they were sized for — two teams colliding and nobody noticing
   until a reviewer works through a backlog — is not the operating model. The
   queue stays short and each decision is easy because it was already made in
   chat.

   **The mechanical half remains: somebody must press promote.** That is
   bookkeeping after the decision, not the decision. Cadence recorded as:
   *reconciled by group-chat consensus on the code, promoted by whoever is at
   a laptop.*

   **Two consequences for the build**, neither yet actioned:

   - Promotion should be **low-friction and low-ceremony**. It is a click
     confirming something already agreed.
   - **Reconsider `require_role` on promote.** It was chosen when reconcile
     looked like an adjudication needing authority. If the adjudication
     happens in chat, the role gate guards a bookkeeping step and mostly
     guarantees the promote does not happen while the one admin is in the
     field. Left as-is in the first implementation, deliberately — loosening
     a gate is a smaller change than adding one, and this should be decided
     after watching it run rather than now.
3. **Does a promoted proposal keep its row?** Recommended yes — it is the only
   record of who proposed the site and when — but it means `station_proposals`
   grows without bound and needs an explicit retention answer.
4. **What happens to sheets already filed against a rejected code?** They exist
   and are valid observations of *something*. Reassigning them to the correct
   code is a data edit with no current endpoint.
5. **Does this path fix `PLWN`'s missing coordinates**, or is that a seed
   correction? Related: `PPPC`, `PNDO` and `PKLY` are NAMRIA's and have no
   `equipment_history` rows at all.

---

## Scope summary

| Piece | Where | Size |
|---|---|---|
| `fo007` migration — `station_proposals` + partial unique index | `services/field-ops/migrations/versions/` | S |
| `POST /stations`, UNION into `GET /stations` | `routers/stations.py` | M |
| Reconcile endpoints behind `require_role` | `routers/stations.py` | M |
| Postgres integration fixture (**prerequisite**) | `tests/conftest.py` | M |
| `station_queue` in the existing offline queue, `DB_VERSION` 4, flush ordering | `hooks/useOfflineQueue.ts` | M |
| Create-station form + picker integration | `components/` | M |
| Persist station list to IndexedDB (**precondition**) | `hooks/useStations.ts` | S |
| Fix the stale `stations.py` docstring and its station count | `routers/stations.py` | S |
