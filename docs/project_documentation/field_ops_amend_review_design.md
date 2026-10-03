# Field Ops: amendments, review, autofill and the filing PDF

*Design note, 2026-10-03 (gps3). Status: **proposed**. Decisions already made by
Alfie are marked **[decided]** with their date; the rest are open and listed at
the end. Nothing here is built.*

Four requests share one form, one table and one history, so they are designed
together and built in an order where each needs only what came before it:

1. **Amend with history**: fix a filed sheet.
2. **Review status**: an admin approves or returns a filed sheet.
3. **Autofill**: start a visit's sheet from what the station already has.
4. **Filing PDF**: print a sheet in the paper logsheet's layout.

Already shipped and assumed here: the check-before-sending step (#261).

---

## 1. Amend with history

**Problem.** A filed sheet cannot be changed: the API is create and read only,
and a resubmission is ignored (`client_uuid` `ON CONFLICT DO NOTHING`). Staff back
at the office find details to fix ("oops, I forgot data X"). Today the only fix
is a direct database edit.

**Decided (Alfie, 2026-09-28):**
- **[decided]** Amend with history, never a plain overwrite. The original stays
  as submitted; every amendment saves the prior full state, who, when, and a
  **required reason**.
- **[decided]** Anyone with a login may amend.
- **[decided]** Every field is editable except keys and system fields: `id`,
  `client_uuid`, `submitted_by` (the original submitter stays; the amender is
  recorded separately), `created_at`, `synced_at`. **Station and date stay
  editable**: they are plain columns, and locking them leaves no fix for a
  wrong pick from the nearby-first station picker. Observers are editable;
  photos can be added or hidden, never deleted or moved.
- **[decided]** Not now: editing sheets still queued on the phone, which would
  race the automatic sync on reconnect.

**Data (migration `fo009`).**

```
logsheet_revisions
  id             pk
  logsheet_id    fk logsheets.id
  revision       int, 1 = as submitted, increments per amendment
  snapshot       jsonb   full prior state, including observers and photo visibility
  changed_fields text[]  which fields this amendment changed
  reason         text not null
  amended_by     fk users.id
  amended_at     timestamptz
logsheets
  + revision     int not null default 1   (optimistic concurrency)
  + amended_at, amended_by                 (null until first amendment)
logsheet_photos
  + hidden_at, hidden_by                   (hide, never delete)
```

The snapshot is the **prior** state, so `logsheets` always holds the current
version and the history reads backwards from it. Revision 1's snapshot is
written on the first amendment, not at submit time, so existing rows need no
backfill.

**API.**

```
PATCH /logsheets/{id}
  body: {fields..., reason, expected_revision}
  409 if expected_revision != current revision (someone amended first)
  422 if a key/system field is present, or reason is empty
GET   /logsheets/{id}/revisions     newest first
```

**Consistency on amend.** Derived fields go stale when what they derive from
changes:

| changed | goes stale |
|---|---|
| station or date | `session_id` (station + DOY, e.g. `BUCA342`) |
| any slant | `avg_slant_m`, `rinex_height_m` |
| antenna model | `rinex_height_m` (the offset depends on the antenna) |

Recommendation (gps3 and finch): **recompute, show old → new on the amend
screen, keep both in the revision**. Open for Alfie (item 1 below). A changed
station must exist. `equipment_history` is reconciled from logsheets and never
written directly, so it follows amendments without extra work.

**UI.** A row in the Sheets table opens the sheet read-only, with **Amend**.
Amend opens the existing form prefilled, with a required "Reason for change"
field. Before saving, a summary lists every changed field, old → new, including
recomputed ones. Revision history appears under the sheet. Needs a connection;
offline, the button explains why it is disabled.

**Safety.** `fo009` is the first migration since #256, so it is also the first
real run of the `/health` schema guard: Render must refuse the new image until
the migration is applied. Run the migration by hand before deploying (DEPLOY.md,
"Run the migrations") and watch `/health` report `current`.

---

## 2. Review status (approve / return)

**Recommendation (2026-10-02):** a status on the synced sheet, **not** a gate
before sync. Holding sheets on the phone until approval leaves the only copy on
a handset that can be lost or reset, and gives the reviewer nothing to review.

**Data (migration `fo010`).**

```
logsheets
  + review_status  text not null default 'pending'   -- pending | approved | returned
  + reviewed_by    fk users.id
  + reviewed_at    timestamptz
  + review_note    text          -- required when returned
```

**Rules.**
- Only `role = 'admin'` can approve or return (the role exists today:
  `field_staff | admin`).
- **Any amendment resets the sheet to `pending`**, so what is approved is what
  is on file. The revision records the status it had.
- *Returned* shows on the submitter's Sheets view with the note; the fix is an
  amendment (section 1), which puts it back to *pending*.
- Downstream consumers read **approved** sheets only: the filing PDF, the
  station-information feed to Bernese, exports. The Looker dashboard shows the
  status as a column rather than hiding pending sheets.

**API.** `POST /logsheets/{id}/review {action: approve|return, note, expected_revision}`;
admin only; 409 on a stale revision, as above.

Depends on 1, because *return* has no fix without amendments.

---

## 3. Autofill from previous visits

**Rule: carry forward description, never measurement.** A measured value copied
from the last visit is indistinguishable from a new measurement, which is the
silent-wrong-number failure this project guards against.

| group | fields | behaviour |
|---|---|---|
| carry forward | `monitoring_method`, `antenna_model`; equipment: last visit's `*_after` → this visit's `*_before` (receiver model, serial, firmware; antenna type, part number, serial, height) | prefilled, tagged "from 12 Sep visit" until touched |
| suggest | observers, `power_notes` | shown as "last time: …", one tap to use |
| never | visit date and times, `utc_start`, `utc_end`, `session_id`, slants, `rinex_height_m`, battery voltage, temperature, weather, bubble centred, notes | always blank |

**Source.** The newest **approved** sheet for the station, falling back to the
newest of any status while review is not yet in use. Since `equipment_history`
is itself reconciled from logsheets, reading the sheet directly gives the same
equipment with fewer moving parts.

**Offline.** The source sheet must already be on the phone when there is no
signal. `useSheets` caches filed sheets for the Today screen; extend it to keep
the newest sheet per station the user has visited or picked.

**Check before sending.** Add one line when carried-forward equipment is
unchanged: "Equipment unchanged since 12 Sep. Correct?"

Depends on 1 (the source is the amended state) and preferably 2 (approved first).

---

## 4. Filing PDF in the paper layout

**Requirement (Alfie, 2026-10-01):** the PDF must keep layout parity with the
original paper logsheets, for filing.

**Needs before design:** a scan or photo of each paper form. Campaign and
continuous probably differ.

**Where it is generated.** Server-side (FastAPI) is the better fit for filing:
one renderer, the approved state, the revision number printed in the footer, and
consistent fonts. On-device generation would work offline but would need the
same template in the PWA, and offline filing is not the use case. Proposed:
server-side, from approved sheets, with "Revision n, approved by …, on …" in the
footer and amendment reasons on a second page.

Depends on 1 and 2.

---

## Build order

| step | migration | depends on | size |
|---|---|---|---|
| 1. Amendments | `fo009` | — | ~2 days |
| 2. Review status | `fo010` | 1 | ~1 day |
| 3. Autofill | none | 1 (2 preferred) | ~1 day |
| 4. Filing PDF | none | 1, 2, paper scans | ~1–2 days |

Each step is its own PR, built test-first, reviewed by the other machine, and
merged on a weekday with someone watching the deploy.

## Open decisions for Alfie

1. **Derived fields on amend:** recompute and show old → new, keeping both in
   the revision (recommended)? Or keep the original and flag it?
2. **Autofill:** automatic when a station is picked, or behind a "Copy from
   last visit" button?
3. **Review:** do the field leads count as admins, or only you? That decides who
   gets the role.
4. **PDF:** scans of the paper forms; confirm server-side generation.
5. **Returned sheets:** may only the original submitter fix them, or anyone (as
   for amendments generally)?
