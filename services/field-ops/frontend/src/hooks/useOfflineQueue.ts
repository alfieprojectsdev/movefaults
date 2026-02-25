/**
 * Offline queue hook using IndexedDB via the `idb` library.
 *
 * Flow:
 *   1. User submits a logsheet form while offline
 *   2. addToQueue() saves it to IndexedDB with status "pending"
 *   3. When the browser regains connectivity (online event), flushQueue() fires
 *   4. All pending records are POSTed to /api/v1/logsheets as a batch
 *   5. Successfully synced records are marked "synced" in IDB
 *
 * The server's ON CONFLICT (client_uuid) DO NOTHING means repeated flushes
 * are safe — no duplicates regardless of how many times a record is submitted.
 */

import { openDB, DBSchema, IDBPDatabase } from "idb";
import { useEffect, useCallback } from "react";
import { LogSheetIn, submitLogSheets } from "../services/api";

// ── IDB schema ──────────────────────────────────────────────────────────────

interface QueueRecord extends LogSheetIn {
  _status: "pending" | "synced" | "error";
  _error?: string;
}

interface FieldOpsDB extends DBSchema {
  logsheet_queue: {
    key: string;           // client_uuid is the key
    value: QueueRecord;
    indexes: { by_status: string };
  };
}

let dbInstance: IDBPDatabase<FieldOpsDB> | null = null;

async function getDb(): Promise<IDBPDatabase<FieldOpsDB>> {
  if (!dbInstance) {
    dbInstance = await openDB<FieldOpsDB>("field-ops", 1, {
      upgrade(db) {
        const store = db.createObjectStore("logsheet_queue", { keyPath: "client_uuid" });
        store.createIndex("by_status", "_status");
      },
    });
  }
  return dbInstance;
}

// ── Hook ────────────────────────────────────────────────────────────────────

export function useOfflineQueue() {
  const addToQueue = useCallback(async (record: LogSheetIn) => {
    const db = await getDb();
    await db.put("logsheet_queue", { ...record, _status: "pending" });
  }, []);

  const flushQueue = useCallback(async () => {
    const db = await getDb();
    const pending = await db.getAllFromIndex("logsheet_queue", "by_status", "pending");
    if (pending.length === 0) return;

    try {
      // Batch submit all pending records
      await submitLogSheets(pending);
      // Mark all as synced
      const tx = db.transaction("logsheet_queue", "readwrite");
      await Promise.all(
        pending.map((r) =>
          tx.store.put({ ...r, _status: "synced" })
        )
      );
      await tx.done;
    } catch (err) {
      console.warn("Offline queue flush failed:", err);
      // Leave records as "pending" — they'll retry on next online event
    }
  }, []);

  // Auto-flush when browser goes online
  useEffect(() => {
    window.addEventListener("online", flushQueue);
    // If already online at mount time, attempt a flush immediately
    if (navigator.onLine) {
      flushQueue();
    }
    return () => window.removeEventListener("online", flushQueue);
  }, [flushQueue]);

  return { addToQueue, flushQueue };
}
