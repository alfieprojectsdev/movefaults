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
  /** Photo bytes, held until the record syncs. Absent for online submissions. */
  _photo?: Blob;
  _photoName?: string;
  /** Set once the photo has reached the server. Guards against re-upload. */
  _photoUploaded?: boolean;
  /** Local timestamp, so the queue view can show age without a server call. */
  _queuedAt?: string;
}

interface FieldOpsDB extends DBSchema {
  logsheet_queue: {
    key: string; // client_uuid
    value: QueueRecord;
    indexes: { by_status: string };
  };
}

const DB_NAME = "field-ops";
const DB_VERSION = 2; // v1 → v2 adds _photo / _photoUploaded

let dbInstance: IDBPDatabase<FieldOpsDB> | null = null;

async function getDb(): Promise<IDBPDatabase<FieldOpsDB>> {
  if (!dbInstance) {
    dbInstance = await openDB<FieldOpsDB>(DB_NAME, DB_VERSION, {
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
  const { usage = 0, quota = 0 } = await navigator.storage.estimate();
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

async function addToQueue(record: LogSheetIn, photo?: File): Promise<void> {
  const db = await getDb();

  if (photo) {
    const headroom = await storageHeadroom();
    // Require the photo to fit with room to spare — a queue that fills the
    // quota exactly leaves no space for the next station's sheet.
    if (headroom && headroom.remaining < photo.size * 2) {
      throw new QueueStorageError(
        `Not enough device storage to queue this photo ` +
          `(${(headroom.remaining / 1048576).toFixed(0)} MB free). ` +
          `Sync pending records, or free space, before continuing.`
      );
    }
  }

  const entry: QueueRecord = {
    ...record,
    _status: "pending",
    _queuedAt: new Date().toISOString(),
    ...(photo ? { _photo: photo, _photoName: photo.name } : {}),
  };

  await db.put("logsheet_queue", entry);
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
      _photo: undefined,
    });
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
