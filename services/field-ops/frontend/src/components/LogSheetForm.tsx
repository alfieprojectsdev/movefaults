/**
 * LogSheetForm — field data entry form supporting two monitoring methods:
 *
 *   - Campaign GPS: tripod/monument setup, antenna measurements, session info.
 *   - Continuous (CORS Maintenance): power check, battery voltage, equipment status.
 *
 * On submit:
 *   1. Generates a client_uuid (UUID v4) for idempotent sync.
 *   2. If online → submits text payload to POST /api/v1/logsheets, then uploads
 *      photo to POST /api/v1/logsheets/{id}/photos.
 *   3. If offline → saves to IndexedDB via useOfflineQueue.
 *      Photo cannot be uploaded offline; the UI warns the user to re-attach it
 *      after connectivity returns. Text data is never lost.
 *
 * Conditional sections:
 *   - Top-level "monitoring_method" dropdown controls which fields are rendered.
 *   - Switching method clears the mode-specific field values to avoid stale data.
 *
 * Antenna height computation (campaign only):
 *   - Four slant heights (N/E/S/W) + selected antenna model drive a live RH calc.
 *   - RH = SQRT(avgSH² - C²) - VO, where C and VO are per-model constants.
 *
 * Session ID auto-generation (campaign only):
 *   - Derived as {STATION_CODE}{DOY} when station and date are both set.
 *   - Remains editable so operators can append -01, -02 suffixes for multi-session days.
 */

import { useState, useEffect } from "react";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import StationPicker from "./StationPicker";
import { useOfflineQueue } from "../hooks/useOfflineQueue";
import {
  submitLogSheet,
  uploadLogSheetPhoto,
  fetchStaff,
  LogSheetIn,
  Staff,
} from "../services/api";

// ── Antenna constants ────────────────────────────────────────────────────────

interface AntennaConstants {
  A: number;
  B: number;
  C: number;
  VO: number;
}

const ANTENNA_CONSTANTS: Record<string, AntennaConstants> = {
  "TRM22020.00+gp": { A: 6.25,   B: 0.34,  C: 0.2334,  VO: 0.0591  },
  "TRM41249.00":    { A: 5.32,   B: 0.89,  C: 0.1698,  VO: 0.0443  },
  "TRM55971-00":    { A: 8.50,   B: 4.06,  C: 0.1698,  VO: 0.0444  },
  "TRM57971-00":    { A: 8.546,  B: 4.111, C: 0.1698,  VO: 0.04435 },
  "TRM115000":      { A: 6.519,  B: 2.085, C: 0.16981, VO: 0.04434 },
};

function computeRH(avgSH: number, C: number, VO: number): number {
  return Math.sqrt(avgSH ** 2 - C ** 2) - VO;
}

// ── Julian DOY helper ────────────────────────────────────────────────────────

function toDOY(dateStr: string): number {
  const d = new Date(dateStr + "T00:00:00");
  const start = new Date(d.getFullYear(), 0, 0);
  const diff = d.getTime() - start.getTime();
  return Math.floor(diff / (1000 * 60 * 60 * 24));
}

// ── UUID helper ──────────────────────────────────────────────────────────────

function generateUUID(): string {
  return crypto.randomUUID();
}

// ── Form values ──────────────────────────────────────────────────────────────

interface FormValues {
  station_code: string;
  monitoring_method: "campaign" | "continuous" | "";
  visit_date: string;
  arrival_time: string;
  departure_time: string;
  observer_ids: number[];
  equipment_status: string;
  weather_conditions: string;
  notes: string;
  // Photo
  photo: FileList | null;
  // Continuous-only
  power_notes: string;
  battery_voltage_v: string;
  // Campaign-only
  antenna_model: string;
  slant_n_m: string;
  slant_e_m: string;
  slant_s_m: string;
  slant_w_m: string;
  session_id: string;
  utc_start: string;
  utc_end: string;
  bubble_centred: boolean;
  plumbing_offset_mm: string;
}

// ── Shared styles ────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = { width: "100%", boxSizing: "border-box" };

const readonlyStyle: React.CSSProperties = {
  width: "100%",
  boxSizing: "border-box",
  background: "#f0f0f0",
  border: "none",
  fontFamily: "monospace",
  padding: "0.3rem 0.4rem",
};

const sectionHeaderStyle: React.CSSProperties = {
  marginTop: "1.5rem",
  marginBottom: "0.25rem",
  fontSize: "1rem",
  color: "#333",
};

const btnStyle: React.CSSProperties = {
  padding: "0.75rem",
  fontSize: "1rem",
  background: "#1a56a4",
  color: "#fff",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
};

const btnDisabledStyle: React.CSSProperties = {
  ...btnStyle,
  background: "#888",
  cursor: "not-allowed",
};

// ── Component ────────────────────────────────────────────────────────────────

export default function LogSheetForm() {
  const {
    register,
    handleSubmit,
    setValue,
    watch,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    defaultValues: {
      equipment_status: "ok",
      visit_date: new Date().toISOString().split("T")[0],
      monitoring_method: "",
      observer_ids: [],
      photo: null,
      bubble_centred: true,
    },
  });

  const { addToQueue } = useOfflineQueue();
  const [submitState, setSubmitState] = useState<
    "idle" | "saving" | "queued" | "saved" | "error"
  >("idle");
  const [errorMsg, setErrorMsg] = useState("");

  // ── Watched values ─────────────────────────────────────────────────────────

  const stationCode    = watch("station_code");
  const visitDate      = watch("visit_date");
  const method         = watch("monitoring_method");
  const antennaModel   = watch("antenna_model");
  const slantN         = watch("slant_n_m");
  const slantE         = watch("slant_e_m");
  const slantS         = watch("slant_s_m");
  const slantW         = watch("slant_w_m");
  const photoFiles     = watch("photo");

  // ── Staff query ────────────────────────────────────────────────────────────

  const {
    data: staffList,
    isLoading: staffLoading,
  } = useQuery<Staff[]>({
    queryKey: ["staff"],
    queryFn: fetchStaff,
    staleTime: 30 * 60 * 1000,
  });

  // ── Session ID auto-generation ─────────────────────────────────────────────

  useEffect(() => {
    if (method !== "campaign") return;
    if (stationCode && visitDate) {
      const doy = toDOY(visitDate);
      setValue("session_id", `${stationCode.toUpperCase()}${doy}`);
    }
  }, [stationCode, visitDate, method, setValue]);

  // ── Clear mode-specific values when method changes ─────────────────────────

  useEffect(() => {
    if (method === "campaign") {
      setValue("power_notes", "");
      setValue("battery_voltage_v", "");
    } else if (method === "continuous") {
      setValue("antenna_model", "");
      setValue("slant_n_m", "");
      setValue("slant_e_m", "");
      setValue("slant_s_m", "");
      setValue("slant_w_m", "");
      setValue("session_id", "");
      setValue("utc_start", "");
      setValue("utc_end", "");
      setValue("bubble_centred", true);
      setValue("plumbing_offset_mm", "");
    }
  }, [method, setValue]);

  // ── Live antenna height computation ───────────────────────────────────────

  const constants = antennaModel ? ANTENNA_CONSTANTS[antennaModel] : undefined;
  const slantNf = parseFloat(slantN);
  const slantEf = parseFloat(slantE);
  const slantSf = parseFloat(slantS);
  const slantWf = parseFloat(slantW);

  const allSlantsFilled =
    constants !== undefined &&
    !isNaN(slantNf) && !isNaN(slantEf) && !isNaN(slantSf) && !isNaN(slantWf);

  const avgSH = allSlantsFilled
    ? (slantNf + slantEf + slantSf + slantWf) / 4
    : undefined;

  const rhValue =
    allSlantsFilled && avgSH !== undefined && constants !== undefined
      ? computeRH(avgSH, constants.C, constants.VO)
      : undefined;

  // ── Photo checks ───────────────────────────────────────────────────────────

  const hasPhoto = photoFiles !== null && photoFiles !== undefined && photoFiles.length > 0;
  const photoFilename = hasPhoto ? photoFiles[0].name : null;

  // ── Submit ─────────────────────────────────────────────────────────────────

  const onSubmit = async (values: FormValues) => {
    setSubmitState("saving");
    setErrorMsg("");

    const record: LogSheetIn = {
      client_uuid: generateUUID(),
      station_code: values.station_code,
      monitoring_method: values.monitoring_method || undefined,
      visit_date: values.visit_date,
      arrival_time: values.arrival_time || undefined,
      departure_time: values.departure_time || undefined,
      weather_conditions: values.weather_conditions || undefined,
      equipment_status: values.equipment_status || undefined,
      notes: values.notes || undefined,
      observer_ids: values.observer_ids.length > 0 ? values.observer_ids : undefined,
    };

    if (values.monitoring_method === "continuous") {
      record.power_notes = values.power_notes || undefined;
      record.battery_voltage_v = values.battery_voltage_v
        ? parseFloat(values.battery_voltage_v)
        : undefined;
    }

    if (values.monitoring_method === "campaign") {
      record.antenna_model = values.antenna_model || undefined;
      record.slant_n_m = values.slant_n_m ? parseFloat(values.slant_n_m) : undefined;
      record.slant_e_m = values.slant_e_m ? parseFloat(values.slant_e_m) : undefined;
      record.slant_s_m = values.slant_s_m ? parseFloat(values.slant_s_m) : undefined;
      record.slant_w_m = values.slant_w_m ? parseFloat(values.slant_w_m) : undefined;
      record.avg_slant_m = avgSH;
      record.rinex_height_m = rhValue;
      record.session_id = values.session_id || undefined;
      record.utc_start = values.utc_start || undefined;
      record.utc_end = values.utc_end || undefined;
      record.bubble_centred = values.bubble_centred;
      record.plumbing_offset_mm = values.plumbing_offset_mm
        ? parseFloat(values.plumbing_offset_mm)
        : undefined;
    }

    if (!navigator.onLine) {
      await addToQueue(record);
      setSubmitState("queued");
      reset();
      return;
    }

    try {
      const created = await submitLogSheet(record);

      // Upload photo as a separate request after logsheet is created
      if (hasPhoto && photoFiles !== null) {
        try {
          await uploadLogSheetPhoto(created.id, photoFiles[0]);
        } catch {
          // Photo upload failed — logsheet was saved; user can re-attach later
          setSubmitState("saved");
          setErrorMsg("Log saved, but photo upload failed. Re-attach photo when reconnected.");
          reset();
          return;
        }
      }

      setSubmitState("saved");
      reset();
    } catch (err) {
      // Network error mid-submit — save text payload to queue as fallback
      await addToQueue(record);
      setSubmitState("queued");
      reset();
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const isSubmitting = submitState === "saving";

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      style={{ display: "flex", flexDirection: "column", gap: "1rem" }}
    >
      <h2 style={{ margin: 0 }}>Station Visit Log</h2>

      {/* ── Monitoring method ── */}
      <label>
        Monitoring method *
        <select
          {...register("monitoring_method", { required: true })}
          style={inputStyle}
        >
          <option value="">— Select method —</option>
          <option value="campaign">Campaign GPS</option>
          <option value="continuous">Continuous (CORS Maintenance)</option>
        </select>
        {errors.monitoring_method && (
          <span style={{ color: "#c00" }}>Required</span>
        )}
      </label>

      {/* ── Station picker ── */}
      <label>
        Station *
        <StationPicker
          value={stationCode}
          onChange={(code) => setValue("station_code", code)}
          disabled={isSubmitting}
        />
        {errors.station_code && (
          <span style={{ color: "#c00" }}>Required</span>
        )}
      </label>

      {/* ── Visit date + times ── */}
      <label>
        Visit date *
        <input
          type="date"
          {...register("visit_date", { required: true })}
          style={inputStyle}
        />
      </label>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
        <label>
          Arrival time
          <input type="time" {...register("arrival_time")} style={inputStyle} />
        </label>
        <label>
          Departure time
          <input type="time" {...register("departure_time")} style={inputStyle} />
        </label>
      </div>

      {/* ── Observers ── */}
      <label>
        Observers
        {staffLoading ? (
          <select disabled style={inputStyle}>
            <option>Loading staff…</option>
          </select>
        ) : staffList && staffList.length > 0 ? (
          <select
            multiple
            style={{ ...inputStyle, height: "7rem" }}
            onChange={(e) => {
              const selected = Array.from(e.target.selectedOptions).map((o) =>
                parseInt(o.value, 10)
              );
              setValue("observer_ids", selected);
            }}
          >
            {staffList.map((s) => (
              <option key={s.id} value={s.id}>
                {s.full_name} ({s.initials}) — {s.role}
              </option>
            ))}
          </select>
        ) : (
          <select disabled style={inputStyle}>
            <option>Staff unavailable (offline?)</option>
          </select>
        )}
        <small style={{ color: "#666" }}>Hold Ctrl / Cmd to select multiple</small>
      </label>

      {/* ── Equipment status ── */}
      <label>
        Equipment status *
        <select
          {...register("equipment_status", { required: true })}
          style={inputStyle}
        >
          <option value="ok">OK — no issues</option>
          <option value="issue_found">Issue found</option>
          <option value="repaired">Repaired on-site</option>
        </select>
      </label>

      {/* ── Weather ── */}
      <label>
        Weather conditions
        <input
          type="text"
          {...register("weather_conditions")}
          placeholder="e.g. Clear, 32°C, NE wind"
          style={inputStyle}
        />
      </label>

      {/* ── Notes ── */}
      <label>
        Notes
        <textarea
          {...register("notes")}
          rows={3}
          style={{ ...inputStyle, resize: "vertical" }}
        />
      </label>

      {/* ════════════════════════════════════════════════════════════
          CONTINUOUS-ONLY SECTION
      ════════════════════════════════════════════════════════════ */}
      {method === "continuous" && (
        <>
          <h3 style={sectionHeaderStyle}>Power &amp; Battery</h3>

          <label>
            Power notes
            <textarea
              {...register("power_notes")}
              rows={2}
              placeholder="Solar panel condition, UPS status, etc."
              style={{ ...inputStyle, resize: "vertical" }}
            />
          </label>

          <label>
            Battery voltage (V)
            <input
              type="number"
              step="0.01"
              min="0"
              max="30"
              {...register("battery_voltage_v")}
              placeholder="e.g. 12.6"
              style={inputStyle}
            />
          </label>
        </>
      )}

      {/* ════════════════════════════════════════════════════════════
          CAMPAIGN-ONLY SECTION
      ════════════════════════════════════════════════════════════ */}
      {method === "campaign" && (
        <>
          <h3 style={sectionHeaderStyle}>Antenna Setup</h3>

          <label>
            Antenna model *
            <select
              {...register("antenna_model", { required: method === "campaign" })}
              style={inputStyle}
            >
              <option value="">— Select antenna —</option>
              {Object.keys(ANTENNA_CONSTANTS).map((model) => (
                <option key={model} value={model}>
                  {model}
                </option>
              ))}
            </select>
            {errors.antenna_model && (
              <span style={{ color: "#c00" }}>Required for campaign</span>
            )}
          </label>

          <p style={{ margin: "0.25rem 0", fontSize: "0.875rem", color: "#555" }}>
            Slant heights (metres) — measure from mark to antenna reference point
          </p>

          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}
          >
            <label>
              Slant N (m)
              <input
                type="number"
                step="0.0001"
                min="0"
                {...register("slant_n_m")}
                placeholder="e.g. 1.4320"
                style={inputStyle}
              />
            </label>
            <label>
              Slant E (m)
              <input
                type="number"
                step="0.0001"
                min="0"
                {...register("slant_e_m")}
                placeholder="e.g. 1.4315"
                style={inputStyle}
              />
            </label>
            <label>
              Slant S (m)
              <input
                type="number"
                step="0.0001"
                min="0"
                {...register("slant_s_m")}
                placeholder="e.g. 1.4318"
                style={inputStyle}
              />
            </label>
            <label>
              Slant W (m)
              <input
                type="number"
                step="0.0001"
                min="0"
                {...register("slant_w_m")}
                placeholder="e.g. 1.4322"
                style={inputStyle}
              />
            </label>
          </div>

          {/* Live computation readouts */}
          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}
          >
            <label>
              Avg slant height (m)
              <input
                type="text"
                readOnly
                value={avgSH !== undefined ? avgSH.toFixed(4) : "—"}
                style={readonlyStyle}
              />
            </label>
            <label>
              RINEX height — RH (m)
              <input
                type="text"
                readOnly
                value={rhValue !== undefined ? rhValue.toFixed(4) : "—"}
                style={readonlyStyle}
              />
            </label>
          </div>

          <h3 style={sectionHeaderStyle}>Session Details</h3>

          <label>
            Session ID
            <input
              type="text"
              {...register("session_id")}
              placeholder="e.g. BUCA342 or BUCA342-01"
              style={inputStyle}
            />
            <small style={{ color: "#666" }}>
              Auto-filled from station + DOY. Append -01, -02 for multiple sessions.
            </small>
          </label>

          <div
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}
          >
            <label>
              UTC start
              <input type="datetime-local" {...register("utc_start")} style={inputStyle} />
            </label>
            <label>
              UTC end
              <input type="datetime-local" {...register("utc_end")} style={inputStyle} />
            </label>
          </div>

          <label style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <input type="checkbox" {...register("bubble_centred")} />
            Bubble centred (level confirmed)
          </label>

          <label>
            Plumbing offset (mm)
            <input
              type="number"
              step="0.1"
              min="0"
              {...register("plumbing_offset_mm")}
              placeholder="0.0 if plumb"
              style={inputStyle}
            />
          </label>
        </>
      )}

      {/* ── Photo ── */}
      <h3 style={sectionHeaderStyle}>Site Photo</h3>

      <label>
        Photo *
        <input
          type="file"
          accept="image/*"
          capture="environment"
          {...register("photo")}
          style={{ marginTop: "0.25rem" }}
        />
      </label>

      {hasPhoto && photoFilename && (
        <p style={{ margin: 0, color: "#1a56a4", fontSize: "0.875rem" }}>
          Photo selected: {photoFilename}
        </p>
      )}

      {!hasPhoto && !navigator.onLine && (
        <p style={{ margin: 0, color: "#a06000", fontSize: "0.875rem" }}>
          Your text entries are saved locally. Add a photo to submit.
        </p>
      )}

      {!hasPhoto && (
        <p style={{ margin: 0, color: "#c00", fontSize: "0.875rem" }}>
          Add a photo to submit.
        </p>
      )}

      {/* ── Submit ── */}
      <button
        type="submit"
        disabled={isSubmitting || !hasPhoto}
        style={isSubmitting || !hasPhoto ? btnDisabledStyle : btnStyle}
      >
        {isSubmitting ? "Saving…" : "Submit Log Sheet"}
      </button>

      {/* ── Status messages ── */}
      {submitState === "saved" && (
        <p style={{ color: "green", margin: 0 }}>Saved and synced to server.</p>
      )}
      {submitState === "saved" && errorMsg && (
        <p style={{ color: "#a06000", margin: 0 }}>{errorMsg}</p>
      )}
      {submitState === "queued" && (
        <p style={{ color: "#a06000", margin: 0 }}>
          Saved offline. Will sync automatically when connected.
        </p>
      )}
      {submitState === "error" && (
        <p style={{ color: "#c00", margin: 0 }}>Error: {errorMsg}</p>
      )}
    </form>
  );
}
