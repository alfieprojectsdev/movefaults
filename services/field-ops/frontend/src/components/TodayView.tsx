/**
 * Today — the landing screen. The station is the object; a sheet is something
 * you do to one.
 *
 * Design handoff `Field Ops Alternatives.dc.html`, option 1c.
 *
 * WHY A LANDING SCREEN AT ALL
 *
 * The app opened straight onto a 1,256-line form whose first question was
 * "which station?", answered by a dropdown of 138. An observer standing at a
 * monument knows exactly where they are and had to find it in a list; an
 * observer deciding whether to travel had nowhere to look at all.
 *
 * This screen answers "where am I and what do I know about this place" before
 * the form asks anything, and leaves the form to do the one job it is good at.
 *
 * WHAT IT DOES NOT DO
 *
 * It does not gate. Every route that worked before still works, the form is
 * one tab away, and a station can still be chosen inside it. A landing screen
 * that has to be got past is worse than no landing screen for the person who
 * files four sheets a week and knows the sheet cold.
 */

import { useMemo, useState } from "react";

import { useDeviceLocation, MAX_USEFUL_ACCURACY_M } from "../hooks/useDeviceLocation";
import { useOfflineQueue } from "../hooks/useOfflineQueue";
import { useSheets } from "../hooks/useSheets";
import { useStations } from "../hooks/useStations";
import { distanceMetres, formatDistance } from "../utils/distance";
import type { Sheet, Station } from "../services/api";

/**
 * How far away a station can be and still be "here".
 *
 * Wider than the picker's own radius on purpose. This list is for deciding
 * where you are, and being shown a site 12 km away costs a glance; being shown
 * nothing because the fix is poor costs the screen its entire reason to exist.
 */
const NEARBY_RADIUS_M = 15_000;

/** How many nearby stations to show before making the rest an explicit choice. */
const NEARBY_LIMIT = 4;

interface Props {
  /** Called with a station code when the observer starts a sheet for it. */
  onStartSheet: (stationCode: string) => void;
}

function placeOf(s: Station): string | null {
  // Municipality and province, when the endpoint has them. Falls back to the
  // station's own name, which for this inventory is usually a building.
  const parts = [s.municipality, s.province].filter(Boolean);
  if (parts.length) return parts.join(", ");
  return s.name ?? null;
}

/** ISO date of the most recent sheet per station code. */
function lastSheetByStation(sheets: Sheet[] | undefined): Map<string, string> {
  const out = new Map<string, string>();
  for (const sh of sheets ?? []) {
    const prev = out.get(sh.station_code);
    if (!prev || sh.visit_date > prev) out.set(sh.station_code, sh.visit_date);
  }
  return out;
}

function daysSince(iso: string): number | null {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  return Math.floor((Date.now() - then) / 86_400_000);
}

export default function TodayView({ onStartSheet }: Props) {
  const { data: stations, isLoading } = useStations();
  const { data: sheets } = useSheets();
  const { pendingCount } = useOfflineQueue();
  const location = useDeviceLocation(true);
  const [showAll, setShowAll] = useState(false);
  const [query, setQuery] = useState("");

  const fix = location.status === "located" ? location.fix : null;
  const coarse = fix != null && fix.accuracy > MAX_USEFUL_ACCURACY_M;

  const lastSheet = useMemo(() => lastSheetByStation(sheets), [sheets]);

  const nearby = useMemo(() => {
    if (!fix || coarse || !stations) return null;
    return stations
      .filter((s) => s.latitude != null && s.longitude != null)
      .map((s) => ({
        station: s,
        metres: distanceMetres(fix, {
          latitude: s.latitude as number,
          longitude: s.longitude as number,
        }),
      }))
      .filter((d) => d.metres <= NEARBY_RADIUS_M)
      .sort((a, b) => a.metres - b.metres);
  }, [fix, coarse, stations]);

  const searched = useMemo(() => {
    if (!stations) return [];
    const q = query.trim().toUpperCase();
    if (!q) return stations;
    return stations.filter(
      (s) =>
        s.station_code.includes(q) ||
        (s.name ?? "").toUpperCase().includes(q) ||
        (s.municipality ?? "").toUpperCase().includes(q) ||
        (s.province ?? "").toUpperCase().includes(q),
    );
  }, [stations, query]);

  const filedThisWeek = useMemo(() => {
    const cutoff = Date.now() - 7 * 86_400_000;
    return (sheets ?? []).filter((s) => Date.parse(s.visit_date) >= cutoff).length;
  }, [sheets]);

  function stationRow(s: Station, metres?: number) {
    const place = placeOf(s);
    const last = lastSheet.get(s.station_code);
    const age = last ? daysSince(last) : null;
    const overdue =
      s.maintenance_interval_days != null && age != null && age > s.maintenance_interval_days;

    return (
      <li key={s.station_code} className="today-station">
        <div className="today-station-head">
          <strong>{s.station_code}</strong>
          {metres != null && <span className="today-distance">{formatDistance(metres)}</span>}
          {s.source === "field" && <span className="today-tag">field-created</span>}
        </div>
        {place && <div className="today-place">{place}</div>}
        <div className="today-meta">
          {s.monitoring_method === "campaign" ? "Campaign" : "Continuous"}
          {last ? ` · last sheet ${last}` : " · no sheet on record"}
          {/* Overdue is only expressible because the station carries its own
              interval. Without it this line could say when, never whether. */}
          {overdue && <span className="today-overdue"> · overdue</span>}
        </div>
        <button type="button" onClick={() => onStartSheet(s.station_code)}>
          Start sheet
        </button>
      </li>
    );
  }

  return (
    <section className="today">
      <div className="today-counts">
        <div>
          <strong>{pendingCount}</strong> waiting to sync
        </div>
        <div>
          <strong>{filedThisWeek}</strong> filed this week
        </div>
      </div>

      {isLoading && <p className="today-hint">Loading stations…</p>}

      {!isLoading && nearby != null && nearby.length > 0 && !showAll && (
        <>
          <h2>Near you</h2>
          <ul className="today-list">
            {nearby.slice(0, NEARBY_LIMIT).map((d) => stationRow(d.station, d.metres))}
          </ul>
        </>
      )}

      {!isLoading && nearby != null && nearby.length === 0 && !showAll && (
        <p className="today-hint">
          No station within {formatDistance(NEARBY_RADIUS_M)}. Search below, or start a sheet
          and choose one in the form.
        </p>
      )}

      {/* The reason position is unavailable is stated rather than hidden. A
          list that silently stops being nearby-first looks broken, and the
          observer is the only one who can tell whether to fix it. */}
      {!isLoading && nearby == null && (
        <p className="today-hint">
          {coarse
            ? `Location is only accurate to ${formatDistance(fix?.accuracy ?? 0)} — showing all stations.`
            : location.status === "denied"
              ? "Location permission is off, so stations cannot be sorted by distance."
              : "Waiting for a position fix — showing all stations."}
        </p>
      )}

      <button
        type="button"
        className="today-showall"
        onClick={() => setShowAll((v) => !v)}
        aria-expanded={showAll}
      >
        {showAll ? "Show nearby only" : `Search all ${stations?.length ?? 0} stations`}
      </button>

      {(showAll || nearby == null) && (
        <>
          <input
            type="search"
            className="today-search"
            placeholder="Code, name, municipality or province"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Search stations"
          />
          <ul className="today-list">{searched.map((s) => stationRow(s))}</ul>
          {searched.length === 0 && (
            <p className="today-hint">
              Nothing matches “{query}”.
            </p>
          )}
        </>
      )}

      {/* #219 lands here: a site that is not in the list at all. The API for
          it exists (POST /stations, promote, reject); no interface reaches it,
          so an observer at an uncatalogued monument still cannot file. This is
          where that belongs -- on the screen whose premise is that the station
          is the object -- and it is deliberately NOT a dead button until the
          form behind it is built. */}
    </section>
  );
}
