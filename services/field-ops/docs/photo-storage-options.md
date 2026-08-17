# Photo storage on the phone — why it copies, and what to do about it

**Written 2026-08-17**, after a real handset session where submitting a sheet
froze on "Saving…", nothing reached the queue, and the phone raised a
low-memory toast while taking photos.

Immediate faults from that session are fixed in `08a3f6f` (timeouts so the save
can no longer hang, batch photos, file browser restored, form survives a tab
switch). This file records the storage question underneath them, which is not
fixed and needs a decision.

---

## The question

> Instead of copying photo bytes into the app, can the PWA keep a *reference*
> to the image in the phone's own filesystem, and have sync read it from there?
> The camera and file manager already do this work.

The instinct is right — it is how a native app would do it. The web platform
will not allow it on a phone.

## Why not

**A `File` is already a lazy reference, but it dies with the page.** A `File`
from `<input type="file">` does not load bytes into memory until something
reads them. What it cannot do is outlive the document. Close the app, reload,
or reboot, and the reference is gone. There is no way to persist it.

**The API that gives durable handles is desktop-only.** File System Access
(`showOpenFilePicker()` → `FileSystemFileHandle`) returns a handle that *can*
be stored in IndexedDB and reopened in a later session. It is not available on
Chrome for Android or Safari on iOS — the two platforms this app targets.

**Putting a `File` in IndexedDB copies the bytes.** It reads like a reference
and is not one; the browser writes a snapshot into its own storage.

**Nothing exposes a stable path into the camera roll.** Even the filename is
frequently useless — iOS commonly supplies generic names.

**And the requirement forbids it anyway.** The queue exists so a sheet survives
the app being killed at a monument. A reference that dies with the page cannot
do that. Referencing and offline durability are mutually exclusive here.

## What already avoids the copy

When there is signal, the photo is uploaded straight from the `File` and
**never touches IndexedDB** (`LogSheetForm.onSubmit`, the online branch). No
copy, minimal memory.

The copy happens only on the offline path — the one case where it cannot be
avoided.

---

## Options

Ordered cheapest first. 1 and 2 are safe now; 3 is the real fix; 4 is a
judgement call about evidence.

### 1. Cap photos per sheet

Refuse past a threshold — say six, or a total megabyte budget — with a message
naming the limit. One condition in `addToQueue`, no downside beyond the cap
itself. Bounds the worst case without addressing the mechanism.

### 2. One IDB record per photo, not one array

**Do this regardless.** Today `addToQueue` writes the record with
`_photos: Blob[]` in a single `db.put`, so every photo in the batch is live in
one transaction — precisely the spike that froze the submit.

Writing each photo as its own keyed record (`<client_uuid>#<index>`) and
storing only the count on the sheet lowers peak memory to one photo at a time.
No image is altered, nothing is lost, and the flush already uploads
sequentially, so the read side barely changes.

Cost: a store change and a migration path for records queued under `_photos`.
Those must be read and never rewritten — they are unsynced fieldwork.

### 3. OPFS instead of IndexedDB blobs

The Origin Private File System (`navigator.storage.getDirectory()`) is a better
backend for large binaries. Same durability, but a file can be *streamed* in
via `createWritable()` rather than handed to IndexedDB whole. That targets the
peak-memory spike directly rather than working around it.

**Verify before committing.** Safari on iOS has historically lagged on
`createWritable()`, favouring `createSyncAccessHandle()`, which is Worker-only.
If that is still true, iOS needs the sync-handle path inside a Worker, which is
a materially bigger change than the Chrome path. This has not been tested on
iOS from this project.

Sequence: confirm iOS support on a real handset → if `createWritable()` is
available on both, migrate the blob store to OPFS and keep IndexedDB for the
sheet metadata → if not, decide whether a Worker is worth it or fall back to
option 2.

### 4. Downscale before storing

Roughly a tenfold reduction at ~1920px on the long edge, and the largest single
saving available.

It also alters the image the camera recorded. A site photo is evidence — of
equipment condition, of access, of damage being reported — and the person who
took it did not choose to reduce it. Worth doing only as a deliberate decision,
with the resolution written into `FIELD_RUNBOOK.md` so field staff know what is
kept. Do not do it silently.

---

## Recommendation

Option **2** now: strictly better, no tradeoff, addresses the mechanism that
actually failed.

Then investigate **3** on a real iPhone and a real Android handset before
touching **4**. Option 4 should be a decision someone makes about the record,
not a performance fix that happens to change the evidence.

## Related

- `services/field-ops/FIELD_RUNBOOK.md` — what field staff are told about photos
- `services/field-ops/frontend/src/hooks/useOfflineQueue.ts` — the store itself
- `08a3f6f` — the handset session that prompted this
