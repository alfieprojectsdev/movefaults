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
 * ── Showing status without relying on colour ────────────────────────────────
 *
 * Every station is selectable, including under-maintenance and closed ones —
 * an observer sent to fix a station is standing at one that is *not* healthy,
 * and a site being decommissioned still needs a final sheet. Hiding those made
 * the sheet impossible to file at exactly the visits that matter most.
 *
 * Colour alone cannot carry that distinction here. This is a native <select>,
 * and on Android and iOS the OS draws the option list itself: `color` on an
 * <option> is ignored outright on iOS and inconsistently honoured elsewhere.
 * A colour-only cue would therefore be invisible on the primary target device
 * — a phone, in the field. It would also fail anyone who cannot distinguish
 * the hues, in sunlight, on a dimmed screen.
 *
 * So status is carried three ways, strongest first:
 *   1. <optgroup> headings — native, rendered by every mobile picker
 *   2. a text suffix on each option
 *   3. colour, where the browser honours it (desktop Firefox/Chrome)
 *
 * Replacing the native control with a styled listbox would give full colour
 * control, but costs the OS picker's large touch targets, scroll momentum and
 * type-ahead over 140 entries — a bad trade for gloved hands on a phone.
 */

import { useStations } from "../hooks/useStations";
import type { Station } from "../services/api";

interface Props {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
}

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

export default function StationPicker({ value, onChange, disabled }: Props) {
  const { data: stations, isLoading, isError } = useStations();

  if (isLoading) {
    return <select disabled><option>Loading stations…</option></select>;
  }

  if (isError || !stations) {
    return (
      <div>
        <select disabled><option>Stations unavailable (offline?)</option></select>
        <small style={{ color: "#c00" }}>
          Connect to network at least once to cache the station list.
        </small>
      </div>
    );
  }

  const buckets = GROUPS.map((g) => ({
    ...g,
    items: stations.filter((s) => bucketOf(s).key === g.key),
  })).filter((g) => g.items.length > 0);

  const selected = stations.find((s) => s.station_code === value);
  const selectedBucket = selected ? bucketOf(selected) : null;

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
            {g.items.map((s) => (
              <option key={s.station_code} value={s.station_code} className={g.className}>
                {s.station_code} — {s.name ?? "(unnamed)"}
                {s.fault_segment ? ` [${s.fault_segment}]` : ""}
                {g.suffix}
              </option>
            ))}
          </optgroup>
        ))}
      </select>

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
    </>
  );
}
