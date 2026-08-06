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
import { useCallback, useEffect, useState } from "react";
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
    });
  }
  return dbInstance;
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
  return { usage, quota, remaining: Math.max(0, quota - usage) };
}

export class QueueStorageError extends Error {}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useOfflineQueue() {
  const [pendingCount, setPendingCount] = useState(0);

  const refreshCount = useCallback(async () => {
    const db = await getDb();
    const pending = await db.getAllFromIndex("logsheet_queue", "by_status", "pending");
    setPendingCount(pending.length);
    return pending;
  }, []);

  const addToQueue = useCallback(
    async (record: LogSheetIn, photo?: File) => {
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
    },
    [refreshCount]
  );

  const flushQueue = useCallback(async () => {
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

      if (rec._photo && !rec._photoUploaded) {
        try {
          const file = new File([rec._photo], rec._photoName ?? "photo.jpg", {
            type: rec._photo.type || "image/jpeg",
          });
          await uploadLogSheetPhoto(serverId, file);

          // Persist the flag BEFORE marking synced. If the tab closes here, the
          // next flush re-POSTs the logsheet (idempotent) and skips the photo.
          rec._photoUploaded = true;
          await db.put("logsheet_queue", rec);
        } catch (err) {
          // Text is safe on the server; the photo is not. Stay pending so the
          // photo retries — never drop the blob.
          console.warn(`Photo upload failed for ${rec.client_uuid}:`, err);
          continue;
        }
      }

      // Both halves are on the server. Drop the blob to reclaim device storage;
      // keeping it would fill the quota with data that is already safe.
      await db.put("logsheet_queue", {
        ...rec,
        _status: "synced",
        _photo: undefined,
      });
    }

    await refreshCount();
  }, [refreshCount]);

  const getQueue = useCallback(async (): Promise<QueueRecord[]> => {
    const db = await getDb();
    const all = await db.getAll("logsheet_queue");
    return all.sort((a, b) => (b._queuedAt ?? "").localeCompare(a._queuedAt ?? ""));
  }, []);

  // Auto-flush on reconnect, and once at mount if already online.
  useEffect(() => {
    window.addEventListener("online", flushQueue);
    if (navigator.onLine) flushQueue();
    refreshCount();
    return () => window.removeEventListener("online", flushQueue);
  }, [flushQueue, refreshCount]);

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
