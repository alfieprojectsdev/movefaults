/**
 * QueueView — what is on this device and not yet on the server.
 *
 * Replaces a stub that said "records will sync automatically" and rendered
 * nothing. In the field that is the wrong shape of reassurance: an operator
 * finishing a day out of signal has no way to confirm their work exists, and
 * "trust me" is not an answer when the alternative is driving back to a
 * monument. This lists every record, its photo state, and its age.
 *
 * Sync is automatic on reconnect; the manual button exists because signal
 * often returns as a brief window (a ridge, a barangay centre) and waiting for
 * the browser's own `online` event to fire is not always fast enough to catch
 * it.
 */

import { useCallback, useEffect, useState } from "react";
import { useOfflineQueue, QueueRecord, storageHeadroom } from "../hooks/useOfflineQueue";
import { useOnline } from "../hooks/useOnline";

export default function QueueView() {
  const { getQueue, flushQueue, pendingCount, retryRecord } = useOfflineQueue();
  const [records, setRecords] = useState<QueueRecord[]>([]);
  const [storage, setStorage] = useState<string>("");
  const [busy, setBusy] = useState(false);
  // Outcome of the last manual sync. Without this a failed flush looked
  // identical to a successful no-op: the button settled back, the count stayed
  // put, and nothing said whether the server had been reached at all.
  const [syncNote, setSyncNote] = useState<{ kind: "ok" | "warn"; text: string } | null>(
    null
  );
  const online = useOnline();

  const refresh = useCallback(async () => {
    setRecords(await getQueue());
    const h = await storageHeadroom();
    if (h && h.quota > 0) {
      setStorage(
        `${(h.usage / 1048576).toFixed(1)} MB used of ` +
          `${(h.quota / 1048576).toFixed(0)} MB available on this device`
      );
    }
  }, [getQueue]);

  // pendingCount changes whenever ANY component's flush or queue write lands,
  // so this also re-lists after an automatic background sync — without it the
  // view kept showing records as pending after they had already gone.
  useEffect(() => {
    refresh();
  }, [refresh, pendingCount, online]);

  const onSync = async () => {
    setBusy(true);
    setSyncNote(null);
    try {
      const r = await flushQueue();
      if (r.error) {
        // Punctuate defensively: r.error comes from several places and may or
        // may not end a sentence. Two messages run together read as noise.
        const why = r.error.replace(/\s*$/, "");
        const sep = /[.!?]$/.test(why) ? "" : ".";
        setSyncNote({
          kind: "warn",
          text: `${why}${sep} Nothing was lost — everything is still on this device. Tap Sync again once you have signal.`,
        });
      } else if (r.attempted === 0) {
        setSyncNote({ kind: "ok", text: "Nothing waiting to sync." });
      } else {
        const parts = [`${r.synced} of ${r.attempted} sheet${r.attempted === 1 ? "" : "s"} synced`];
        if (r.quarantined > 0) parts.push(`${r.quarantined} refused — see below`);
        setSyncNote({ kind: r.quarantined > 0 ? "warn" : "ok", text: parts.join("; ") + "." });
      }
      await refresh();
    } catch (err) {
      // flushQueue rejecting is not expected — runFlush handles its own
      // failures — but an unhandled rejection here would leave the operator
      // with a button that just stops spinning and says nothing.
      setSyncNote({
        kind: "warn",
        text: (err instanceof Error ? err.message : "Sync failed.") +
          " Your data is still on this device.",
      });
    } finally {
      setBusy(false);
    }
  };

  const onRetry = async (clientUuid: string) => {
    await retryRecord(clientUuid);
    await refresh();
  };

  const pending = records.filter((r) => r._status === "pending");
  const rejected = records.filter((r) => r._status === "error");
  const synced = records.filter((r) => r._status === "synced");

  return (
    <section>
      <h2>Queue</h2>

      {records.length === 0 && (
        <p className="msg msg-info">
          Nothing queued. Submitted sheets appear here until they reach the
          server.
        </p>
      )}

      {pending.length > 0 && (
        <>
          <p className="msg msg-warn">
            <strong>{pending.length}</strong> sheet{pending.length === 1 ? "" : "s"} waiting
            to sync. Keep this app installed and do not clear browsing data.
          </p>
          <button
            type="button"
            className="submit-btn"
            onClick={onSync}
            disabled={busy || !online}
          >
            {busy ? "Syncing…" : online ? "Sync now" : "Sync now (offline)"}
          </button>
          {syncNote && (
            <p className={`msg msg-${syncNote.kind === "ok" ? "ok" : "warn"}`}>
              {syncNote.text}
            </p>
          )}
        </>
      )}

      {pending.length > 0 && (
        <ul className="queue-list">
          {pending.map((r) => (
            <QueueItem key={r.client_uuid} rec={r} />
          ))}
        </ul>
      )}

      {/* Rejected records sit above the synced list, not hidden inside it: they
          are the only ones that need the operator to do something, and they are
          the reason a queue would otherwise appear to stall with no explanation. */}
      {rejected.length > 0 && (
        <>
          <p className="msg msg-error">
            <strong>{rejected.length}</strong> sheet{rejected.length === 1 ? " was" : "s were"}{" "}
            refused by the server and will not sync until corrected. The reason is
            shown against each. Nothing has been lost — photos are still held on
            this device.
          </p>
          <ul className="queue-list">
            {rejected.map((r) => (
              <QueueItem key={r.client_uuid} rec={r} onRetry={onRetry} />
            ))}
          </ul>
        </>
      )}

      {synced.length > 0 && (
        <details className="queue-synced">
          <summary>{synced.length} synced</summary>
          <ul className="queue-list">
            {synced.map((r) => (
              <QueueItem key={r.client_uuid} rec={r} />
            ))}
          </ul>
        </details>
      )}

      {storage && <p className="hint">{storage}</p>}
    </section>
  );
}

/**
 * What this record's photos are doing, in words an operator can act on.
 *
 * Both queue shapes are covered. `_photo` is the single-photo shape from before
 * batch capture; `_photos` is what every new sheet uses. Reading only the
 * legacy field — which is what this did — reported "no photo" for every batch
 * record in the queue, telling an observer their site photos were missing at
 * the exact moment they were sitting safely on the device. Wrong in the
 * direction that sends someone back to a monument.
 *
 * A synced record has had its blobs dropped, so the count comes from
 * `_photosUploaded`, which survives that write for exactly this reason.
 */
function describePhotos(rec: QueueRecord): string {
  const held = rec._photos?.length ?? 0;
  const sent = rec._photosUploaded ?? 0;

  if (held > 0) {
    if (sent >= held) return `${held} photo${held === 1 ? "" : "s"} sent`;
    if (sent > 0) return `${sent} of ${held} photos sent`;
    return `${held} photo${held === 1 ? "" : "s"} held`;
  }
  if (sent > 0) return `${sent} photo${sent === 1 ? "" : "s"} sent`;

  // Legacy single-photo records.
  if (rec._photoUploaded) return "photo sent";
  if (rec._photo) return "photo held";
  return "no photo";
}

function QueueItem({
  rec,
  onRetry,
}: {
  rec: QueueRecord;
  onRetry?: (clientUuid: string) => void | Promise<void>;
}) {
  const queued = rec._queuedAt ? new Date(rec._queuedAt) : null;
  const photoState = describePhotos(rec);

  return (
    <li className={`queue-item is-${rec._status}`}>
      <span className="queue-station">{rec.station_code || "—"}</span>
      <span className="queue-meta">
        {rec.visit_date}
        {rec.session_id ? ` · ${rec.session_id}` : ""} · {photoState}
      </span>
      {queued && (
        <span className="queue-meta">
          saved {queued.toLocaleString(undefined, {
            dateStyle: "medium",
            timeStyle: "short",
          })}
        </span>
      )}
      {rec._error && <span className="field-error">{rec._error}</span>}
      {onRetry && rec._status === "error" && (
        <button
          type="button"
          className="queue-retry"
          onClick={() => void onRetry(String(rec.client_uuid))}
        >
          Try again
        </button>
      )}
    </li>
  );
}
