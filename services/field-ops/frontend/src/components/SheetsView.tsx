import { useCallback, useEffect, useRef, useState } from "react";
import { fetchSheets, fetchPhotoObjectUrl, Sheet, SheetPhoto } from "../services/api";
import { useOfflineQueue, QueueRecord } from "../hooks/useOfflineQueue";
import { useOnline } from "../hooks/useOnline";

/**
 * /sheets — what has been filed.
 *
 * Two audiences, one table: an observer checking their own day at the end of
 * it, and a team seeing what other teams filed elsewhere. Everyone signed in
 * sees everything; there is no per-user filter to get wrong.
 *
 * WHAT THIS TABLE CANNOT SHOW, and says so on screen: a sheet still sitting in
 * a colleague's IndexedDB is invisible to the server and therefore to this
 * view. Only two of the three states are knowable here —
 *
 *   photo pending   the sheet reached the server, its photo did not. The real
 *                   "Log saved. Photo queued." path, and the one worth chasing.
 *   on this device  from the local queue, merged in and marked. This handset
 *                   only, never anyone else's.
 *
 * Presenting a partial list as complete is how someone concludes a colleague
 * never filed a sheet that is in fact sitting on a phone in a bag.
 */

const WAKE_HINT_MS = 4000;

function fmtDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

function PhotoCell({ photos }: { photos: SheetPhoto[] }) {
  const [urls, setUrls] = useState<string[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  // Held in a ref as well as state so the cleanup on unmount sees the current
  // list without re-running the effect — and therefore without revoking a URL
  // the img is still displaying.
  const created = useRef<string[]>([]);

  useEffect(
    () => () => {
      // Object URLs pin their blob for the life of the document. A dozen 4 MB
      // photos left un-revoked is a tab the phone kills while someone is
      // reading it.
      created.current.forEach((u) => URL.revokeObjectURL(u));
    },
    []
  );

  if (photos.length === 0) {
    return <span className="sheet-photo-pending">photo pending</span>;
  }

  const show = async () => {
    setLoading(true);
    setError("");
    try {
      const loaded = await Promise.all(photos.map((p) => fetchPhotoObjectUrl(p.id)));
      created.current.push(...loaded);
      setUrls(loaded);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load photos");
    } finally {
      setLoading(false);
    }
  };

  if (urls) {
    return (
      <div className="sheet-photos">
        {urls.map((u, i) => (
          <img key={u} src={u} alt={photos[i].filename ?? `Photo ${i + 1}`} loading="lazy" />
        ))}
      </div>
    );
  }

  return (
    <>
      {/* A button, not a link. The bytes need an Authorization header, so they
          are fetched rather than navigated to, and shown in place — a new tab
          opened after an await is what popup blockers exist to stop. */}
      <button type="button" className="link-btn" onClick={show} disabled={loading}>
        {loading ? "Loading…" : `${photos.length} photo${photos.length > 1 ? "s" : ""}`}
      </button>
      {error && <span className="sheet-photo-error"> {error}</span>}
    </>
  );
}

export default function SheetsView() {
  const [sheets, setSheets] = useState<Sheet[] | null>(null);
  const [local, setLocal] = useState<QueueRecord[]>([]);
  const [error, setError] = useState("");
  const [slow, setSlow] = useState(false);
  const { getQueue } = useOfflineQueue();
  const online = useOnline();

  const load = useCallback(async () => {
    setError("");
    setSlow(false);
    // Render's free tier sleeps. The first request after an idle period takes
    // 30-60 s to wake it, and a spinner that long reads as broken — so the
    // reason is stated rather than left to be guessed at.
    const timer = setTimeout(() => setSlow(true), WAKE_HINT_MS);
    try {
      setLocal(await getQueue());
      setSheets(await fetchSheets());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load sheets");
    } finally {
      clearTimeout(timer);
      setSlow(false);
    }
  }, [getQueue]);

  useEffect(() => {
    void load();
  }, [load]);

  const unsynced = local.filter((r) => r._status !== "synced");

  return (
    <section className="sheets-view">
      <h2>Sheets filed</h2>

      <p className="hint">
        Everything that has reached the server, newest first — every team, not
        just yours. Sheets still waiting on someone else's device cannot appear
        here until they sync.
      </p>

      {!online && (
        <p className="msg msg-warn">
          Offline — showing only what is on this device. Reconnect to see the
          full list.
        </p>
      )}

      <button type="button" className="link-btn" onClick={() => void load()}>
        Refresh
      </button>

      {slow && (
        <p className="msg msg-info">
          Waking the server — the first request after a quiet period takes up to
          a minute.
        </p>
      )}

      {error && <p className="msg msg-error">{error}</p>}

      {unsynced.length > 0 && (
        <>
          <h3 className="section-header">On this device, not yet sent</h3>
          <ul className="sheet-local-list">
            {unsynced.map((r) => (
              <li key={r.client_uuid}>
                <strong>{r.station_code}</strong> · {r.visit_date}
                {r._status === "error" ? " · refused — see the Queue tab" : " · waiting to sync"}
              </li>
            ))}
          </ul>
        </>
      )}

      {sheets === null && !error ? (
        <p className="hint">Loading…</p>
      ) : sheets && sheets.length === 0 ? (
        <p className="hint">Nothing filed yet.</p>
      ) : (
        // The table scrolls inside its own container. A phone is narrower than
        // these columns and the page itself must never scroll sideways.
        <div className="table-scroll">
          <table className="sheets-table">
            <thead>
              <tr>
                <th>Station</th>
                <th>Visit date</th>
                <th>Method</th>
                <th>Observers</th>
                <th>Session</th>
                <th>RH (m)</th>
                <th>Status</th>
                <th>Filed</th>
                <th>Photos</th>
              </tr>
            </thead>
            <tbody>
              {(sheets ?? []).map((s) => (
                <tr key={s.client_uuid}>
                  <td>
                    <strong>{s.station_code}</strong>
                  </td>
                  <td>{s.visit_date}</td>
                  <td>{s.monitoring_method ?? "—"}</td>
                  <td>{s.observers.length ? s.observers.join(", ") : "—"}</td>
                  <td>{s.session_id ?? "—"}</td>
                  <td>{s.rinex_height_m != null ? s.rinex_height_m.toFixed(4) : "—"}</td>
                  <td>
                    {s.equipment_status ?? "—"}
                    {s.equipment_changed ? " · equipment changed" : ""}
                  </td>
                  <td>{fmtDateTime(s.created_at)}</td>
                  <td>
                    <PhotoCell photos={s.photos} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
