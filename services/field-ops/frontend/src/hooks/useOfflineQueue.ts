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
import { LogSheetIn, submitLogSheets, uploadLogSheetPhoto } from "../services/api";

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

let flushInFlight: Promise<void> | null = null;
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

async function runFlush(): Promise<void> {
  const db = await getDb();
  const pending = await db.getAllFromIndex("logsheet_queue", "by_status", "pending");
  if (pending.length === 0) return;

  let server;
  try {
    // Strip local-only fields; the API rejects unknown keys on some paths and
    // a Blob is not JSON-serialisable in any case.
    const payload = pending.map(stripLocalFields);
    server = await submitLogSheets(payload);
  } catch (err) {
    // Network still down, or auth expired. Records stay pending and retry on
    // the next online event — deliberately no error status here, because a
    // failed flush is the expected case in the field, not a fault.
    console.warn("Offline queue flush failed:", err);
    return;
  }

  // Match server rows back to queued records by client_uuid.
  const idByUuid = new Map(server.map((r) => [String(r.client_uuid), r.id]));

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
  }

  await refreshCount();
}

/**
 * Single-flight flush. Concurrent callers join the run already in progress
 * rather than starting a second one — without this, the three mounted hook
 * instances would each upload every queued photo.
 */
function flushQueue(): Promise<void> {
  if (!flushInFlight) {
    flushInFlight = runFlush().finally(() => {
      flushInFlight = null;
    });
  }
  return flushInFlight;
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

export { addToQueue, flushQueue, getQueue, refreshCount };

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

  return { addToQueue, flushQueue, getQueue, pendingCount, refreshCount };
}

/** Remove the underscore-prefixed local bookkeeping fields before sending. */
function stripLocalFields(rec: QueueRecord): LogSheetIn {
  const clean: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(rec)) {
    if (!k.startsWith("_")) clean[k] = v;
  }
  return clean as unknown as LogSheetIn;
}
