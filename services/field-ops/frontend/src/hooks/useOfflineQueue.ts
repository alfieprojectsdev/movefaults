/**
 * Offline queue backed by IndexedDB.
 *
 * Flow:
 *   1. User submits a logsheet while offline
 *   2. addToQueue() stores the record AND its photo blob, status "pending"
 *   3. On the browser's "online" event, flushQueue() fires
 *   4. Pending records are POSTed as one batch to /api/v1/logsheets
 *   5. Each record's photo is then uploaded against the returned server id
 *   6. A record is marked "synced" only once BOTH steps have succeeded
 *
 * ── Why the photo lives in IndexedDB ────────────────────────────────────────
 *
 * A photo is mandatory to submit. Until v2 of this store, the offline path
 * queued only the text payload — `reset()` then cleared the file input, so the
 * photo was destroyed while the UI reported "Saved offline. Will sync
 * automatically when connected." That sentence was true of the text and false
 * of the photo, and there was no way to recover: the operator had already
 * walked away from the monument.
 *
 * For fieldwork where offline is the normal case rather than the exception,
 * that is data loss on the primary path. The blob is now queued with the
 * record and uploaded on sync.
 *
 * ── Exactly-once, under retry ───────────────────────────────────────────────
 *
 * The logsheet POST is idempotent server-side: ON CONFLICT (client_uuid) DO
 * NOTHING, then a re-fetch by client_uuid, so a retry returns the existing row
 * rather than creating a second one. Photo upload has no such guard — the
 * server would happily store the same image twice.
 *
 * So `_photoUploaded` is tracked separately and persisted *before* the record
 * is marked synced. A crash between the two leaves the record pending with the
 * photo flagged done; the next flush re-POSTs the logsheet (harmless) and
 * skips the photo. Duplicate photos cost R2 storage and muddy provenance —
 * which of two near-identical images was the one the observer meant?
 */

import { openDB, DBSchema, IDBPDatabase } from "idb";
import { useEffect, useState } from "react";
import {
  ApiError,
  LogSheetIn,
  LogSheetOut,
  submitLogSheets,
  uploadLogSheetPhoto,
} from "../services/api";

// ── IDB schema ──────────────────────────────────────────────────────────────

export interface QueueRecord extends LogSheetIn {
  _status: "pending" | "synced" | "error";
  _error?: string;
  /**
   * Photo bytes, held until the record syncs. Absent for online submissions.
   *
   * `_photo`/`_photoName` are the single-photo shape used before batch capture
   * existed. Records queued under it may still be sitting on a device, so they
   * are read on flush and never rewritten — a migration that touched them would
   * risk the one thing this store exists to protect.
   */
  _photo?: Blob;
  _photoName?: string;
  /** Batch shape: several photos for one station visit, in capture order. */
  _photos?: Blob[];
  _photoNames?: string[];
  /**
   * How many of `_photos` have reached the server, counted from the start.
   *
   * A count rather than a flag because a batch can be interrupted halfway on a
   * weak link. Order is stable, so uploading resumes from this index instead of
   * re-sending photos that already landed — the server would dedupe them by
   * content hash, but only after the bytes had crossed the connection, which is
   * the expensive part in the field.
   */
  _photosUploaded?: number;
  /** Legacy single-photo flag. */
  _photoUploaded?: boolean;
  /** Local timestamp, so the queue view can show age without a server call. */
  _queuedAt?: string;
}

/**
 * Upload progress, kept apart from the record it describes.
 *
 * Progress has to be persisted after every photo — that is the difference
 * between resuming at photo four and re-sending all six over a field link. But
 * IndexedDB has no partial update: `put` rewrites the whole value, and a queue
 * record's value contains the photo blobs. Writing progress onto the record
 * therefore rewrote ~18 MB of image data per photo, six times for a six-photo
 * batch — on the same memory-constrained handset whose blob writes are what
 * froze the submit button in the first place.
 *
 * Split out, a progress write is a few dozen bytes. The record itself is
 * written twice per flush regardless of photo count: never during the batch,
 * once when it is marked synced.
 */
interface PhotoProgress {
  client_uuid: string;
  /** Photos uploaded so far, counted from the start of `_photos`. */
  uploaded: number;
}

interface FieldOpsDB extends DBSchema {
  logsheet_queue: {
    key: string; // client_uuid
    value: QueueRecord;
    indexes: { by_status: string };
  };
  photo_progress: {
    key: string; // client_uuid
    value: PhotoProgress;
  };
}

const DB_NAME = "field-ops";
// v1 → v2 adds _photo / _photoUploaded
// v2 → v3 adds the photo_progress store
const DB_VERSION = 3;

/**
 * Nothing in this module may hang forever.
 *
 * IndexedDB has two ways to stall with no error at all: an upgrade blocked by
 * another open tab never fires success, and on a phone under memory pressure a
 * multi-megabyte blob write can simply never settle. Both leave the submit
 * button reading "Saving…" until the app is killed — which is what an observer
 * at a monument actually saw, with the sheet nowhere and the form still full.
 *
 * A rejection is recoverable: the form keeps its values, the message says what
 * happened, and the operator can retry. A hang is not recoverable by anyone.
 */
export class QueueTimeoutError extends Error {
  constructor(what: string, ms: number) {
    super(
      `${what} did not finish within ${Math.round(ms / 1000)}s. ` +
        `This usually means the phone is low on memory. Nothing was saved — ` +
        `close other apps and try again; your entries are still on the form.`
    );
    this.name = "QueueTimeoutError";
  }
}

function withTimeout<T>(p: Promise<T>, ms: number, what: string): Promise<T> {
  return Promise.race([
    p,
    new Promise<never>((_, reject) =>
      setTimeout(() => reject(new QueueTimeoutError(what, ms)), ms)
    ),
  ]);
}

// Opening is fast when it works; when it is blocked it never returns at all.
const DB_OPEN_TIMEOUT_MS = 10_000;
// A write carries the photo, so it is allowed longer — but not forever.
const DB_WRITE_TIMEOUT_MS = 30_000;

let dbInstance: IDBPDatabase<FieldOpsDB> | null = null;

async function getDb(): Promise<IDBPDatabase<FieldOpsDB>> {
  if (!dbInstance) {
    const opening = openDB<FieldOpsDB>(DB_NAME, DB_VERSION, {
      upgrade(db, oldVersion) {
        // v1 records are still valid — the new fields are optional, so the
        // store is carried forward rather than recreated. Destroying it would
        // discard unsynced fieldwork.
        if (oldVersion < 1) {
          const store = db.createObjectStore("logsheet_queue", {
            keyPath: "client_uuid",
          });
          store.createIndex("by_status", "_status");
        }
        if (oldVersion < 3) {
          db.createObjectStore("photo_progress", { keyPath: "client_uuid" });
        }
      },
      blocked() {
        // Another tab holds an older version open. Without this the upgrade
        // waits forever and every queue write hangs with no error — a submit
        // button that silently does nothing, on the offline path.
        console.warn(
          "field-ops: database upgrade blocked by another open tab. " +
            "Close other copies of this app."
        );
      },
      blocking() {
        // We are the old connection holding someone else's upgrade up. Close so
        // the newer context can proceed rather than deadlocking both.
        dbInstance?.close();
        dbInstance = null;
      },
    });

    try {
      dbInstance = await withTimeout(opening, DB_OPEN_TIMEOUT_MS, "Opening local storage");
    } catch (err) {
      // Do not cache a failed open — the next attempt must be able to succeed
      // once the blocking tab is closed or memory is freed.
      dbInstance = null;
      throw err;
    }
  }
  return dbInstance;
}

// ── Shared state ────────────────────────────────────────────────────────────
//
// useOfflineQueue is mounted by three components at once (App for the badge,
// LogSheetForm to queue, QueueView to list and flush). Per-instance state would
// mean three independent `online` listeners firing three concurrent flushes on
// one reconnect. Because `_photoUploaded` is read from a snapshot taken at the
// top of each run and written only after the upload resolves, all three would
// see `false` and upload the same photo — and the photo endpoint, unlike the
// logsheet POST, has no idempotency guard. One observation would end up with
// three R2 objects and three logsheet_photos rows.
//
// So the listener, the in-flight lock and the pending count live at module
// scope, and the hook subscribes to them.

let flushInFlight: Promise<FlushResult> | null = null;
const countSubscribers = new Set<(n: number) => void>();
let lastPendingCount = 0;

function publishCount(n: number): void {
  lastPendingCount = n;
  countSubscribers.forEach((fn) => fn(n));
}

// ── Storage headroom ────────────────────────────────────────────────────────

/**
 * Phone photos run ~3 MB each. Browsers grant IndexedDB a quota that varies by
 * device and free space, and a write past it throws QuotaExceededError — which
 * on the offline path would mean a submission that appears to save and does
 * not. Checked before queuing so the failure is visible while the operator is
 * still standing at the station.
 */
export async function storageHeadroom(): Promise<{
  usage: number;
  quota: number;
  remaining: number;
} | null> {
  if (!navigator.storage?.estimate) return null;
  // estimate() is normally instant, but has been observed to stall on phones
  // under memory pressure. It is only advisory here, so a slow answer is worth
  // less than a fast "unknown" — never let it delay the save it precedes.
  let usage = 0;
  let quota = 0;
  try {
    ({ usage = 0, quota = 0 } = await withTimeout(
      navigator.storage.estimate(),
      3_000,
      "Checking device storage"
    ));
  } catch {
    return null;
  }
  // A zero quota means the browser declined to report one, not that the device
  // is full. Treating it as "no space" would make the guard reject every photo
  // on such a device — blocking the mandatory-photo path entirely, which is a
  // worse failure than the one the guard exists to prevent.
  if (!quota) return null;
  return { usage, quota, remaining: Math.max(0, quota - usage) };
}

export class QueueStorageError extends Error {}

// ── Queue operations (module scope — one copy, whatever mounts the hook) ─────

async function refreshCount(): Promise<QueueRecord[]> {
  const db = await getDb();
  const pending = await db.getAllFromIndex("logsheet_queue", "by_status", "pending");
  publishCount(pending.length);
  return pending;
}

async function addToQueue(record: LogSheetIn, photos: File[] = []): Promise<void> {
  const db = await getDb();

  if (photos.length > 0) {
    const total = photos.reduce((sum, f) => sum + f.size, 0);
    const headroom = await storageHeadroom();
    // Require the batch to fit with room to spare — a queue that fills the
    // quota exactly leaves no space for the next station's sheet.
    if (headroom && headroom.remaining < total * 2) {
      throw new QueueStorageError(
        `Not enough device storage for ${photos.length} photo` +
          `${photos.length === 1 ? "" : "s"} ` +
          `(${(total / 1048576).toFixed(0)} MB needed, ` +
          `${(headroom.remaining / 1048576).toFixed(0)} MB free). ` +
          `Sync pending records, or free space, before continuing.`
      );
    }
  }

  const entry: QueueRecord = {
    ...record,
    _status: "pending",
    _queuedAt: new Date().toISOString(),
    ...(photos.length > 0
      ? { _photos: photos, _photoNames: photos.map((f) => f.name), _photosUploaded: 0 }
      : {}),
  };

  await withTimeout(
    db.put("logsheet_queue", entry),
    DB_WRITE_TIMEOUT_MS,
    "Saving to this device"
  );
  await refreshCount();
}

/**
 * What a flush attempt did, so the UI can say so.
 *
 * The flush used to swallow a network failure into a console.warn and return.
 * That is right about the *data* — records stay pending and retry — but wrong
 * about the operator, who clicks Sync, sees the button settle back, sees the
 * count unchanged, and has no way to tell "still no signal" from "the app is
 * broken". On a weak link that ambiguity is the difference between waiting and
 * driving back to a site.
 */
export interface FlushResult {
  attempted: number;
  synced: number;
  quarantined: number;
  /** Set when the batch could not be delivered at all — transient. */
  error?: string;
}

async function runFlush(): Promise<FlushResult> {
  const db = await getDb();
  const pending = await db.getAllFromIndex("logsheet_queue", "by_status", "pending");
  if (pending.length === 0) return { attempted: 0, synced: 0, quarantined: 0 };

  let server;
  try {
    // Strip local-only fields; the API rejects unknown keys on some paths and
    // a Blob is not JSON-serialisable in any case.
    const payload = pending.map(stripLocalFields);
    server = await submitLogSheets(payload);
  } catch (err) {
    if (err instanceof ApiError && err.isPermanent) {
      // A validation rejection, not a network failure. Retrying the same batch
      // will fail identically forever, and one bad record takes the whole day's
      // work down with it — silently, because nothing here used to record an
      // error and QueueView had nothing to show.
      //
      // Re-submit one at a time so the good records get through, and mark the
      // offender so the operator can see which sheet is blocking and why.
      server = await flushIndividually(db, pending);
      if (server.length === 0) {
        await refreshCount();
        return {
          attempted: pending.length,
          synced: 0,
          quarantined: pending.length,
        };
      }
    } else {
      // Network still down, or auth expired. Records stay pending and retry on
      // the next online event — deliberately no error status here, because a
      // failed flush is the expected case in the field, not a fault.
      console.warn("Offline queue flush failed:", err);
      return {
        attempted: pending.length,
        synced: 0,
        quarantined: 0,
        error: err instanceof Error ? err.message : "Could not reach the server.",
      };
    }
  }

  // Match server rows back to queued records by client_uuid.
  const idByUuid = new Map(server.map((r) => [String(r.client_uuid), r.id]));
  let synced = 0;

  for (const rec of pending) {
    const serverId = idByUuid.get(String(rec.client_uuid));
    if (serverId === undefined) {
      // Server did not return this record — leave pending, do not lose it.
      continue;
    }

    // Re-read immediately before uploading rather than trusting the snapshot
    // taken at the top of this run. Another browsing context (a second tab, the
    // installed PWA alongside the tab it was installed from) can flush the same
    // store concurrently, and the photo endpoint has no idempotency guard.
    const fresh = (await db.get("logsheet_queue", String(rec.client_uuid))) ?? rec;
    if (fresh._status === "synced") continue;

    // Legacy single-photo records, queued before batch capture existed.
    if (fresh._photo && !fresh._photoUploaded) {
      try {
        const file = new File([fresh._photo], fresh._photoName ?? "photo.jpg", {
          type: fresh._photo.type || "image/jpeg",
        });
        await uploadLogSheetPhoto(serverId, file);
        // Persist the flag BEFORE marking synced. If the tab closes here, the
        // next flush re-POSTs the logsheet (idempotent) and skips the photo.
        await db.put("logsheet_queue", { ...fresh, _photoUploaded: true });
      } catch (err) {
        // Text is safe on the server; the photo is not. Stay pending so the
        // photo retries — never drop the blob.
        console.warn(`Photo upload failed for ${fresh.client_uuid}:`, err);
        continue;
      }
    }

    // Batch: upload from where the last attempt stopped.
    if (fresh._photos && fresh._photos.length > 0) {
      const uuid = String(fresh.client_uuid);
      // The progress row is authoritative when present; `_photosUploaded` on
      // the record is the fallback for batches queued before that store
      // existed, and is refreshed on the final synced write.
      const saved = await db.get("photo_progress", uuid);
      let uploaded = saved?.uploaded ?? fresh._photosUploaded ?? 0;
      let stalled = false;

      for (let i = uploaded; i < fresh._photos.length; i++) {
        try {
          const blob = fresh._photos[i];
          const file = new File([blob], fresh._photoNames?.[i] ?? `photo-${i + 1}.jpg`, {
            type: blob.type || "image/jpeg",
          });
          await uploadLogSheetPhoto(serverId, file);
          uploaded = i + 1;
          // Persisted after every single photo, not once at the end of the
          // batch. On a link that drops mid-upload, the difference is between
          // resuming at photo 4 and re-sending all six. Written to the sibling
          // store, not onto the record — see PhotoProgress above for why.
          await db.put("photo_progress", { client_uuid: uuid, uploaded });
        } catch (err) {
          console.warn(
            `Photo ${i + 1}/${fresh._photos.length} failed for ${fresh.client_uuid}:`,
            err
          );
          stalled = true;
          break;
        }
      }

      // Any photo still unsent means the record stays pending. The sheet is
      // already safe on the server; the photos are the part that is not.
      if (stalled) continue;
      fresh._photosUploaded = uploaded;
    }

    // Both halves are on the server. Drop the blob to reclaim device storage;
    // keeping it would fill the quota with data that is already safe.
    //
    // _photoUploaded is set only where a photo actually existed. Setting it
    // unconditionally made QueueView report "photo sent" for records that never
    // carried one — including everything queued under store v1, when the
    // offline path discarded the photo outright. Telling an operator their
    // photo was sent is exactly the false reassurance this rewrite exists to
    // remove, and it hides the one case where returning to the site still helps.
    await db.put("logsheet_queue", {
      ...fresh,
      ...(fresh._photo || fresh._photoUploaded ? { _photoUploaded: true } : {}),
      _status: "synced",
      // Blobs are dropped only now, with everything confirmed on the server.
      // Keeping them would fill the device quota with data that is already safe.
      _photo: undefined,
      _photos: undefined,
    });
    // The progress row described a batch that no longer exists. Left behind it
    // would be read by a later flush of a record queued under the same uuid —
    // which is exactly what a retried submit now is, since client_uuid is
    // stable per sheet — and would skip photos that were never sent.
    await db.delete("photo_progress", String(fresh.client_uuid));
    synced += 1;
  }

  const still = await refreshCount();
  return {
    attempted: pending.length,
    synced,
    // Anything no longer pending and not synced this pass was quarantined.
    quarantined: pending.length - synced - still.length,
  };
}

/**
 * Fallback for a batch the server rejected outright.
 *
 * Submits each pending record on its own, so that one unusable sheet — a stale
 * observer id is the realistic case, after a week offline — cannot hold back
 * every other sheet queued behind it. Records that fail permanently are moved
 * to "error" with the server's own message attached, which takes them out of
 * subsequent batches and puts them in front of the operator in QueueView.
 *
 * Returns the server rows for the records that did go through, in the same
 * shape the batch call would have returned, so the caller's photo-upload pass
 * needs no special case.
 */
async function flushIndividually(
  db: IDBPDatabase<FieldOpsDB>,
  pending: QueueRecord[]
): Promise<LogSheetOut[]> {
  const accepted: LogSheetOut[] = [];

  for (const rec of pending) {
    try {
      const [row] = await submitLogSheets([stripLocalFields(rec)]);
      if (row) accepted.push(row);
    } catch (err) {
      if (err instanceof ApiError && err.isPermanent) {
        // Quarantine. Keep the photo blob — the record may still be repairable
        // (refresh the staff list, re-pick observers) and discarding the only
        // copy of the site photo to tidy up the queue would be the same data
        // loss this store exists to prevent.
        const fresh = (await db.get("logsheet_queue", String(rec.client_uuid))) ?? rec;
        await db.put("logsheet_queue", {
          ...fresh,
          _status: "error",
          _error: err.message,
        });
      } else {
        // Transient — leave it pending for the next online event.
        console.warn(`Deferred ${rec.client_uuid}:`, err);
      }
    }
  }

  return accepted;
}

/**
 * Single-flight flush. Concurrent callers join the run already in progress
 * rather than starting a second one — without this, the three mounted hook
 * instances would each upload every queued photo.
 */
function flushQueue(): Promise<FlushResult> {
  if (!flushInFlight) {
    flushInFlight = runFlush().finally(() => {
      // Cleared in `finally` so a rejected run cannot wedge the lock: without
      // it one failure would leave every later flushQueue() returning the same
      // settled promise, and Sync would be dead for the rest of the session.
      flushInFlight = null;
    });
  }
  return flushInFlight;
}

/**
 * Move a quarantined record back into the queue.
 *
 * Nothing here fixes what the server objected to — that is the operator's job
 * (refresh the staff list, correct the sheet). This only clears the error so
 * the next flush tries again; if the cause is still there it will quarantine
 * again with a fresh message, which is the honest outcome.
 */
async function retryRecord(clientUuid: string): Promise<void> {
  const db = await getDb();
  const rec = await db.get("logsheet_queue", clientUuid);
  if (!rec || rec._status !== "error") return;
  await db.put("logsheet_queue", { ...rec, _status: "pending", _error: undefined });
  await refreshCount();
}

async function getQueue(): Promise<QueueRecord[]> {
  const db = await getDb();
  const all = await db.getAll("logsheet_queue");
  return all.sort((a, b) => (b._queuedAt ?? "").localeCompare(a._queuedAt ?? ""));
}

// One `online` listener for the whole app, registered on first use. Attaching
// per hook instance meant one reconnect fired as many flushes as there were
// mounted components.
let onlineListenerAttached = false;

function attachOnlineListener(): void {
  if (onlineListenerAttached) return;
  onlineListenerAttached = true;
  window.addEventListener("online", () => {
    void flushQueue();
  });
}

export { addToQueue, flushQueue, getQueue, refreshCount, retryRecord };

// ── Hook ────────────────────────────────────────────────────────────────────

/**
 * Thin subscriber over the module-level queue. Every mounted instance sees the
 * same pending count and shares one flush, so the badge in the header stays in
 * step with what the form and the queue view are doing.
 */
export function useOfflineQueue() {
  const [pendingCount, setPendingCount] = useState(lastPendingCount);

  useEffect(() => {
    countSubscribers.add(setPendingCount);
    attachOnlineListener();

    if (navigator.onLine) void flushQueue();
    void refreshCount();

    return () => {
      countSubscribers.delete(setPendingCount);
    };
  }, []);

  return { addToQueue, flushQueue, getQueue, pendingCount, refreshCount, retryRecord };
}

/** Remove the underscore-prefixed local bookkeeping fields before sending. */
function stripLocalFields(rec: QueueRecord): LogSheetIn {
  const clean: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(rec)) {
    if (!k.startsWith("_")) clean[k] = v;
  }
  return clean as unknown as LogSheetIn;
}
