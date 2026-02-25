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
 */

import { useStations } from "../hooks/useStations";

interface Props {
  value: string;
  onChange: (code: string) => void;
  disabled?: boolean;
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

  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      style={{ width: "100%", padding: "0.4rem", fontSize: "1rem" }}
    >
      <option value="">— Select station —</option>
      {stations.map((s) => (
        <option key={s.station_code} value={s.station_code}>
          {s.station_code} — {s.name ?? "(unnamed)"}
          {s.fault_segment ? ` [${s.fault_segment}]` : ""}
        </option>
      ))}
    </select>
  );
}
