/**
 * StationPicker — dropdown populated from the central stations table.
 *
 * Shows a loading state while fetching, falls back gracefully if the
 * query fails (e.g. offline on first ever load before cache is warm).
 *
 * Props:
 *   value        — current station_code value
 *   onChange     — callback when user selects a station
 *   disabled     — optional disable state
 *
 * ── Nearby-first, with an escape hatch ──────────────────────────────────────
 *
 * 138 stations is a long list to scroll on a phone, and an observer standing at
 * a monument almost always wants the one they are standing at. So when the
 * device knows where it is, the list narrows to stations within a short radius
 * and says how far each one is.
 *
 * The filter is never a gate. "Show all stations" is always present, and the
 * list falls back to everything whenever position is unknown — permission
 * refused, no fix under canopy, a station with no coordinates in the database.
 * Filing a sheet must never depend on the GPS working: the observer is at the
 * monument either way, and the sheet is the record of that.
 *
 * Three cases force the full list open regardless of position:
 *   - the current selection is outside the radius (editing an earlier sheet)
 *   - nothing is nearby (the site is not in the database, or the fix is off)
 *   - the operator asked for it
 *
 * ── Showing status without relying on colour ────────────────────────────────
 *
 * Every station is selectable, including under-maintenance and closed ones —
 * an observer sent to fix a station is standing at one that is *not* healthy,
 * and a site being decommissioned still needs a final sheet.
 *
 * Colour alone cannot carry that distinction here. This is a native <select>,
 * and on Android and iOS the OS draws the option list itself: `color` on an
 * <option> is ignored outright on iOS and inconsistently honoured elsewhere.
 * So status is carried by <optgroup> headings first, a text suffix second, and
 * colour only where the browser cooperates.
 */

import { useMemo, useState } from "react";
import { useStations } from "../hooks/useStations";
import { useProposals, type ProposalRecord } from "../hooks/useOfflineQueue";
import NewSiteForm from "./NewSiteForm";
import { useDeviceLocation } from "../hooks/useDeviceLocation";
import { distanceMetres, formatDistance } from "../utils/distance";
import { ApiError, TimeoutError, type Station, type StationProposalIn } from "../services/api";
import { useOnline } from "../hooks/useOnline";

interface Props {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
}

/**
 * How near counts as "here".
 *
 * The brief said 1 km. This is 2 km because the radius has to cover the fix's
 * own error as well as the walk from the vehicle: a good handset fix is ±10 m,
 * but a poor one under canopy is a few hundred, and a station 1.1 km away that
 * silently vanishes from the list is a worse failure than one extra entry to
 * scroll past. Anything wider than MAX_USEFUL_ACCURACY_M in the location hook
 * is rejected as a fix entirely, so this radius is never applied to a position
 * that cannot support it.
 */
const NEARBY_RADIUS_M = 2_000;

/** Visual + textual treatment per status bucket. */
const GROUPS = [
  {
    key: "active",
    label: "Active",
    suffix: "",
    className: "station-opt-active",
    match: (s: string | null) => s === "active" || s == null,
  },
  {
    key: "maintenance",
    label: "Under maintenance",
    suffix: " · under maintenance",
    className: "station-opt-maintenance",
    match: (s: string | null) => s === "under_maintenance",
  },
  {
    key: "closed",
    label: "Decommissioned / archived",
    suffix: " · closed",
    className: "station-opt-closed",
    // Everything else, so a status value added to the database later still
    // appears in the list rather than vanishing from the picker.
    match: () => true,
  },
] as const;

function bucketOf(station: Station) {
  return GROUPS.find((g) => g.match(station.status ?? null)) ?? GROUPS[2];
}

function hasCoords(s: Station): boolean {
  return typeof s.latitude === "number" && typeof s.longitude === "number";
}

/**
 * Turn a query failure into something the person at the monument can act on.
 *
 * Each branch exists because the right action differs. Offline: wait for
 * signal. Timeout: the server is waking -- retry in a moment, and that IS the
 * fix rather than a workaround. Session expired: log in. Server error: nobody
 * in the field can fix it, so do not imply they can.
 *
 * `retryable` gates the button rather than always showing one: offering "try
 * again" for a permanently rejected request teaches people to press it
 * forever, and the queue already covers the case where the sheet matters more
 * than the list.
 */
export function describeStationFailure(
  err: unknown,
  online: boolean
): { label: string; hint: string; retryable: boolean } {
  if (!online) {
    return {
      label: "Stations unavailable \u2014 no network",
      hint:
        "This device is offline. The list is cached after one online visit; " +
        "you can still fill and queue the sheet.",
      retryable: false,
    };
  }
  if (err instanceof TimeoutError) {
    return {
      label: "Stations unavailable \u2014 server not answering",
      hint:
        "The network is fine but the server did not reply in time. It may be " +
        "waking up; wait a few seconds and try again.",
      retryable: true,
    };
  }
  if (err instanceof ApiError) {
    if (err.status === 401) {
      return {
        label: "Stations unavailable \u2014 session expired",
        hint: "Log in again to reload the station list.",
        retryable: false,
      };
    }
    if (err.status >= 500) {
      return {
        label: `Stations unavailable \u2014 server error (${err.status})`,
        hint:
          "The server failed, not this device or the network. Report it; " +
          "you can still fill and queue the sheet.",
        retryable: true,
      };
    }
    return {
      label: `Stations unavailable \u2014 request rejected (${err.status})`,
      hint: err.message,
      retryable: false,
    };
  }
  // A fetch that never produced a response: DNS, TLS, a captive portal, or a
  // network that reports itself up. `navigator.onLine` says nothing about
  // whether anything is REACHABLE, which is why this is not the offline case.
  return {
    label: "Stations unavailable \u2014 cannot reach the server",
    hint:
      "The device thinks it is online but the server could not be reached. " +
      "Check for a sign-in page on this Wi-Fi, then try again.",
    retryable: true,
  };
}

/**
 * A site created on this device, shaped like a station so the picker can offer
 * it before the server has ever heard of it.
 *
 * Without this the observer creates a site at the monument and then cannot
 * select it — the same dead end the feature exists to remove, moved along by
 * one step. `source: "field"` is what the API itself uses for an unreconciled
 * proposal merged into GET /stations, so a site looks the same whether it is
 * still on the handset or has synced.
 */
function proposalAsStation(p: ProposalRecord): Station {
  return {
    station_code: p.station_code,
    name: p.name ?? null,
    latitude: p.latitude ?? null,
    longitude: p.longitude ?? null,
    elevation: p.elevation ?? null,
    fault_segment: null,
    status: "active",
    municipality: p.municipality ?? null,
    province: p.province ?? null,
    monitoring_method: p.monitoring_method,
    source: "field",
  };
}

export default function StationPicker({ value, onChange, disabled }: Props) {
  const { data: stations, isLoading, isError, error, refetch, isFetching } = useStations();
  const online = useOnline();
  const { proposals, addProposal, retryProposal } = useProposals();
  const [showAll, setShowAll] = useState(false);
  const [adding, setAdding] = useState(false);
  // Only ask for position while the filter could actually use it. Asking after
  // the operator has chosen "show all" would prompt for a permission whose
  // answer changes nothing.
  const location = useDeviceLocation(!showAll);

  const fix = location.status === "located" ? location.fix : null;

  /**
   * The inventory, plus sites created on this device that have not synced.
   *
   * Merged here rather than after the guards so that `nearby` sees them too. A
   * site proposed at the monument is by definition where the observer is
   * standing, so it belongs at the top of the nearby list — being pushed to
   * "show all" to find the site you just created would be absurd.
   *
   * A local proposal whose code is already in the inventory is dropped rather
   * than shown twice. That happens after a sync: the server returns the site
   * in GET /stations while the local record is still marked synced here.
   */
  const allStations = useMemo(() => {
    if (!stations) return undefined;
    const known = new Set(stations.map((s) => s.station_code.toUpperCase()));
    const local = proposals
      .filter((p) => !known.has(p.station_code.toUpperCase()))
      .map(proposalAsStation);
    return [...local, ...stations];
  }, [stations, proposals]);

  /** Stations within the radius, nearest first, with their distances. */
  const nearby = useMemo(() => {
    if (!fix || !allStations) return null;
    return allStations
      .filter(hasCoords)
      .map((s) => ({
        station: s,
        metres: distanceMetres(fix, {
          latitude: s.latitude as number,
          longitude: s.longitude as number,
        }),
      }))
      .filter((d) => d.metres <= NEARBY_RADIUS_M)
      .sort((a, b) => a.metres - b.metres);
  }, [fix, allStations]);

  if (isLoading) {
    return <select disabled><option>Loading stations…</option></select>;
  }

  if (isError || !stations || !allStations) {
    // Name the actual failure. "Offline?" for all five is what sent a field
    // report chasing a browser bug that did not exist -- see useStations.
    const { label, hint, retryable } = describeStationFailure(error, online);
    return (
      <div>
        <select disabled><option>{label}</option></select>
        <small className="station-hint is-error">{hint}</small>
        {retryable && (
          <button
            type="button"
            className="station-retry"
            onClick={() => void refetch()}
            disabled={isFetching}
          >
            {isFetching ? "Trying…" : "Try again"}
          </button>
        )}
      </div>
    );
  }

  // The selection must always be present in the list, or the <select> would
  // silently reset it — losing a station already chosen for an earlier sheet
  // that is now being corrected somewhere else entirely.
  const selectionOutsideRadius =
    value !== "" && nearby !== null && !nearby.some((d) => d.station.station_code === value);

  const filtering = !showAll && nearby !== null && nearby.length > 0 && !selectionOutsideRadius;

  const visible: Station[] = filtering
    ? (nearby as NonNullable<typeof nearby>).map((d) => d.station)
    : allStations;

  const distanceByCode = new Map(
    (nearby ?? []).map((d) => [d.station.station_code, d.metres])
  );

  const buckets = GROUPS.map((g) => ({
    ...g,
    items: visible.filter((s) => bucketOf(s).key === g.key),
  })).filter((g) => g.items.length > 0);

  const selected = allStations.find((s) => s.station_code === value);
  const selectedBucket = selected ? bucketOf(selected) : null;
  const selectedDistance = selected ? distanceByCode.get(selected.station_code) : undefined;

  return (
    <>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="station-select"
      >
        <option value="">— Select station —</option>
        {buckets.map((g) => (
          <optgroup key={g.key} label={g.label}>
            {g.items.map((s) => {
              const m = distanceByCode.get(s.station_code);
              return (
                <option key={s.station_code} value={s.station_code} className={g.className}>
                  {s.station_code} — {s.name ?? "(unnamed)"}
                  {s.fault_segment ? ` [${s.fault_segment}]` : ""}
                  {m !== undefined ? ` · ${formatDistance(m)} away` : ""}
                  {g.suffix}
                </option>
              );
            })}
          </optgroup>
        ))}
      </select>

      <LocationNote
        filtering={filtering}
        nearbyCount={nearby?.length ?? 0}
        total={allStations.length}
        location={location}
        showAll={showAll}
        selectionOutsideRadius={selectionOutsideRadius}
        onToggle={() => setShowAll((v) => !v)}
      />

      {/* The selected station's status, restated outside the <select>. This is
          the only place the cue is guaranteed to render on a phone: once the
          native picker closes, the collapsed control shows plain text. */}
      {selectedBucket && selectedBucket.key !== "active" && (
        <p className={`station-status-note is-${selectedBucket.key}`}>
          {selectedBucket.key === "maintenance"
            ? "This station is under maintenance."
            : "This station is decommissioned or archived."}{" "}
          You can still file a sheet for it.
        </p>
      )}

      {selectedDistance !== undefined && selectedDistance > NEARBY_RADIUS_M && (
        <p className="station-status-note is-maintenance">
          {formatDistance(selectedDistance)} from where this device thinks it is.
          Check the station is the one you meant.
        </p>
      )}

      {/* The site is not in the list.
          Deliberately last, small, and never in the way of the common case —
          138 of 139 selections will be an existing station. But it is always
          present, including offline, because an observer at an uncatalogued
          monument with no signal is exactly who needs it, and the queue is
          built for precisely that. */}
      {adding ? (
        <NewSiteForm
          takenCodes={allStations.map((s) => s.station_code)}
          onCancel={() => setAdding(false)}
          onCreated={(proposal: StationProposalIn) => {
            // Queued, then selected. The select() happens regardless of
            // whether the network is up: the record exists locally, the picker
            // merges it in above, and a sheet may name a code the server has
            // not seen -- station_code on a logsheet is a loose TEXT reference
            // with no foreign key, decided in 001_field_ops_schema.py.
            void addProposal(proposal).then(() => {
              onChange(proposal.station_code);
              setAdding(false);
            });
          }}
        />
      ) : (
        <button type="button" className="link-btn station-add" onClick={() => setAdding(true)}>
          The site is not listed — add it
        </button>
      )}

      {/* A site the server refused. Shown here rather than only in the queue
          view: this is where the observer chooses a code, and it is where they
          can act on it.

          Two outcomes, two messages, and the difference is whether asking
          again could ever help. A 409 is an answer about the world — the code
          stays taken — so there is no retry, because a button guaranteed not
          to work is worse than none. Anything else permanent is an answer
          about this client, which a reload or a corrected API base does
          change, so it offers one. */}
      {proposals
        .filter((p) => p._status === "conflict")
        .map((p) => (
          <p key={p.client_uuid} className="station-status-note is-error">
            {p.station_code} was not accepted: {p._error ?? "the code is already in use."}{" "}
            Choose a different code. The sheets you filed against it are still saved.
          </p>
        ))}

      {/* A code two teams claimed. Since #228 the server keeps this rather
          than refusing it, so there is nothing for the observer to fix and no
          retry to offer — the office has both claims in front of it. What
          this line has to convey is the one consequence the observer can see:
          their sheets are saved and waiting, not lost and not sent. */}
      {proposals
        .filter((p) => p._status === "synced" && p._collidesWith)
        .map((p) => (
          <p key={p.client_uuid} className="station-status-note">
            {p.station_code} was sent, but{" "}
            {p._collidesWith === "inventory"
              ? "that code already belongs to a station in the central list"
              : "another team has claimed that code too"}
            . The office can see both and will settle it. The sheets you filed
            against it are saved and will be sent once they do.
          </p>
        ))}

      {proposals
        .filter((p) => p._status === "error")
        .map((p) => (
          <p key={p.client_uuid} className="station-status-note is-error">
            {p.station_code} could not be sent: {p._error ?? "the server refused it."}{" "}
            The code is not taken — this is something on this device or with the
            app version. The sheets you filed against it are still saved.{" "}
            <button
              type="button"
              className="link-btn"
              onClick={() => void retryProposal(p.client_uuid)}
            >
              Try sending it again
            </button>
          </p>
        ))}
    </>
  );
}

/**
 * One line under the picker saying what the list is currently showing and how
 * to change it. Deliberately always rendered when position matters: a filtered
 * list that does not announce itself is indistinguishable from a broken one.
 */
function LocationNote({
  filtering,
  nearbyCount,
  total,
  location,
  showAll,
  selectionOutsideRadius,
  onToggle,
}: {
  filtering: boolean;
  nearbyCount: number;
  total: number;
  location: ReturnType<typeof useDeviceLocation>;
  showAll: boolean;
  selectionOutsideRadius: boolean;
  onToggle: () => void;
}) {
  const toggle = (
    <button type="button" className="station-toggle" onClick={onToggle}>
      {showAll || !filtering ? "Show nearby only" : `Show all ${total} stations`}
    </button>
  );

  if (filtering) {
    return (
      <p className="station-hint">
        Showing {nearbyCount} station{nearbyCount === 1 ? "" : "s"} within{" "}
        {formatDistance(NEARBY_RADIUS_M)} of this device. {toggle}
      </p>
    );
  }

  if (showAll) {
    return (
      <p className="station-hint">
        Showing all {total} stations. {toggle}
      </p>
    );
  }

  if (selectionOutsideRadius) {
    return (
      <p className="station-hint">
        Showing all {total} stations, because the one selected is not nearby.
      </p>
    );
  }

  // Not filtering, and not by choice — say why, so an unexpectedly long list
  // is explained rather than looking like the feature failed silently.
  const reason =
    location.status === "denied"
      ? "Location permission was declined, so all stations are listed."
      : location.status === "unsupported"
        ? "This device cannot report its position, so all stations are listed."
        : location.status === "prompting"
          ? "Finding your position… showing all stations meanwhile."
          : location.status === "unavailable"
            ? `${location.reason} — showing all stations.`
            : nearbyCount === 0
              ? "No stations within 2 km of this device — showing all."
              : "Showing all stations.";

  return <p className="station-hint">{reason}</p>;
}
