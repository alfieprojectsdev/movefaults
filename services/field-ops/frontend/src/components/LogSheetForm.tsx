/**
 * LogSheetForm — the main field data entry form.
 *
 * On submit:
 *   1. Generates a client_uuid (UUID v4) for idempotent sync
 *   2. If online → submits directly to POST /api/v1/logsheets
 *   3. If offline → saves to IndexedDB via useOfflineQueue
 *      The queue flushes automatically when connectivity returns.
 *
 * Fields mirror a standard PHIVOLCS CORS station visit log sheet:
 *   - Station (from central DB via StationPicker)
 *   - Visit date + arrival/departure times
 *   - Equipment status (ok / issue found / repaired)
 *   - Weather conditions
 *   - Maintenance performed
 *   - Free text notes
 */

import { useState } from "react";
import { useForm } from "react-hook-form";
import StationPicker from "./StationPicker";
import { useOfflineQueue } from "../hooks/useOfflineQueue";
import { submitLogSheets, LogSheetIn } from "../services/api";

interface FormValues {
  station_code: string;
  visit_date: string;
  arrival_time: string;
  departure_time: string;
  weather_conditions: string;
  maintenance_performed: string;
  equipment_status: string;
  notes: string;
}

function generateUUID(): string {
  return crypto.randomUUID();
}

export default function LogSheetForm() {
  const { register, handleSubmit, setValue, watch, reset, formState: { errors } } = useForm<FormValues>({
    defaultValues: { equipment_status: "ok", visit_date: new Date().toISOString().split("T")[0] },
  });
  const { addToQueue } = useOfflineQueue();
  const [submitState, setSubmitState] = useState<"idle" | "saving" | "queued" | "saved" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState("");

  const stationCode = watch("station_code");

  const onSubmit = async (values: FormValues) => {
    setSubmitState("saving");
    setErrorMsg("");

    const record: LogSheetIn = {
      client_uuid: generateUUID(),
      station_code: values.station_code,
      visit_date: values.visit_date,
      arrival_time: values.arrival_time || undefined,
      departure_time: values.departure_time || undefined,
      weather_conditions: values.weather_conditions || undefined,
      maintenance_performed: values.maintenance_performed || undefined,
      equipment_status: values.equipment_status || undefined,
      notes: values.notes || undefined,
    };

    if (!navigator.onLine) {
      await addToQueue(record);
      setSubmitState("queued");
      reset();
      return;
    }

    try {
      await submitLogSheets([record]);
      setSubmitState("saved");
      reset();
    } catch (err) {
      // Network error mid-submit — save to queue as fallback
      await addToQueue(record);
      setSubmitState("queued");
      reset();
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
      <h2 style={{ margin: 0 }}>Station Visit Log</h2>

      <label>
        Station *
        <StationPicker
          value={stationCode}
          onChange={(code) => setValue("station_code", code)}
          disabled={submitState === "saving"}
        />
        {errors.station_code && <span style={{ color: "#c00" }}>Required</span>}
      </label>

      <label>
        Visit date *
        <input type="date" {...register("visit_date", { required: true })} style={{ width: "100%" }} />
      </label>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
        <label>
          Arrival time
          <input type="time" {...register("arrival_time")} style={{ width: "100%" }} />
        </label>
        <label>
          Departure time
          <input type="time" {...register("departure_time")} style={{ width: "100%" }} />
        </label>
      </div>

      <label>
        Equipment status *
        <select {...register("equipment_status", { required: true })} style={{ width: "100%" }}>
          <option value="ok">OK — no issues</option>
          <option value="issue_found">Issue found</option>
          <option value="repaired">Repaired on-site</option>
        </select>
      </label>

      <label>
        Weather conditions
        <input type="text" {...register("weather_conditions")}
          placeholder="e.g. Clear, 32°C, NE wind" style={{ width: "100%" }} />
      </label>

      <label>
        Maintenance performed
        <textarea {...register("maintenance_performed")} rows={2}
          placeholder="Antenna cable check, receiver reboot, etc."
          style={{ width: "100%", resize: "vertical" }} />
      </label>

      <label>
        Notes
        <textarea {...register("notes")} rows={3}
          style={{ width: "100%", resize: "vertical" }} />
      </label>

      <button type="submit" disabled={submitState === "saving"}
        style={{ padding: "0.75rem", fontSize: "1rem", background: "#1a56a4", color: "#fff", border: "none", borderRadius: 4 }}>
        {submitState === "saving" ? "Saving…" : "Submit Log Sheet"}
      </button>

      {submitState === "saved" && (
        <p style={{ color: "green" }}>✓ Saved and synced to server.</p>
      )}
      {submitState === "queued" && (
        <p style={{ color: "#a06000" }}>
          ⚠ Saved offline. Will sync automatically when connected.
        </p>
      )}
      {submitState === "error" && (
        <p style={{ color: "#c00" }}>Error: {errorMsg}</p>
      )}
    </form>
  );
}
