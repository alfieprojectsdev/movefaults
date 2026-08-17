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
 *      The photo blob is queued with it and uploaded on sync, so
 *      nothing is lost while out of signal.
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

// Presentation now lives in src/styles/field.css. Pico styles bare
// <input>/<select>/<textarea> globally, so these are intentionally empty —
// keeping the names means the ~20 `style={inputStyle}` call sites below need
// no edit, and there is one obvious place to reintroduce an override if a
// single control ever genuinely needs one.
const inputStyle: React.CSSProperties = {};

// Computed fields (avg slant, RINEX height) are styled via `input[readonly]`.
const readonlyStyle: React.CSSProperties = {};


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
  const observerIds    = watch("observer_ids");

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

    // The photo is queued WITH the record. Before this it was dropped on the
    // offline path while the UI still reported a successful save.
    const photo = hasPhoto && photoFiles !== null ? photoFiles[0] : undefined;

    if (!navigator.onLine) {
      try {
        await addToQueue(record, photo);
        setSubmitState("queued");
        reset();
      } catch (err) {
        // Out of device storage — do NOT reset(), the operator still has the
        // form and the photo and can retry after syncing.
        setSubmitState("error");
        setErrorMsg(err instanceof Error ? err.message : "Could not save offline.");
      }
      return;
    }

    try {
      const created = await submitLogSheet(record);

      // Upload photo as a separate request after logsheet is created
      if (photo) {
        try {
          await uploadLogSheetPhoto(created.id, photo);
        } catch {
          // Logsheet is on the server but the photo is not. Queue the photo
          // rather than asking the operator to remember to re-attach it later:
          // by then they have left the site. _photoUploaded stays false, so the
          // next flush re-POSTs the (idempotent) logsheet and retries the photo.
          try {
            await addToQueue(record, photo);
            setSubmitState("queued");
            setErrorMsg("Log saved. Photo queued — it will upload on the next sync.");
            reset();
          } catch (queueErr) {
            // Device storage is full, so the photo cannot be held either. This
            // path was previously unguarded: the error escaped to the outer
            // catch, which queued again, failed again, and told the operator
            // "Could not save offline" — implying the whole submission was
            // lost, when in fact the sheet was already on the server. Wrong in
            // the direction that sends someone back to a monument for nothing.
            //
            // Say what is true of each half, and do NOT reset(): the form still
            // holds the photo, so freeing space and retrying is possible.
            setSubmitState("error");
            setErrorMsg(
              "Log saved on the server — but the photo could not be uploaded OR " +
                "stored on this device" +
                (queueErr instanceof Error ? ` (${queueErr.message})` : "") +
                ". Free space, then attach the photo again from this form."
            );
          }
          return;
        }
      }

      setSubmitState("saved");
      reset();
    } catch (err) {
      // Network error mid-submit — queue both halves as the fallback.
      try {
        await addToQueue(record, photo);
        setSubmitState("queued");
        reset();
      } catch (queueErr) {
        setSubmitState("error");
        setErrorMsg(
          queueErr instanceof Error ? queueErr.message : "Could not save offline."
        );
      }
    }
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  const isSubmitting = submitState === "saving";

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="logsheet-form"
    >
      <h2>Station Visit Log</h2>

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
          <span className="field-error">Required</span>
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
          <span className="field-error">Required</span>
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

      <div className="form-grid-2">
        <label>
          Arrival time
          <input type="time" {...register("arrival_time")} style={inputStyle} />
        </label>
        <label>
          Departure time
          <input type="time" {...register("departure_time")} style={inputStyle} />
        </label>
      </div>

      {/* ── Observers ──
          Checkboxes, not <select multiple>. There is no Ctrl key at a monument,
          and that was the only instruction telling anyone more than one
          observer could be recorded — so a team of four would file sheets
          naming one person. A multi-select also hides its state behind a
          native picker on a phone; here every name and every tick is visible
          at a glance, on 48px rows a gloved thumb can hit. */}
      <fieldset className="observer-field">
        <legend>Observers</legend>
        {staffLoading ? (
          <p className="hint">Loading staff…</p>
        ) : staffList && staffList.length > 0 ? (
          <>
            <div className="observer-list">
              {staffList.map((s) => {
                const checked = observerIds.includes(s.id);
                return (
                  <label key={s.id} className="checkbox-row observer-row">
                    <input
                      type="checkbox"
                      value={s.id}
                      checked={checked}
                      onChange={(e) => {
                        // Rebuilt from the current array rather than toggled in
                        // place, so the stored order stays stable and a double
                        // tap cannot leave a duplicate id behind.
                        const next = e.target.checked
                          ? [...observerIds, s.id]
                          : observerIds.filter((id) => id !== s.id);
                        setValue("observer_ids", next, { shouldDirty: true });
                      }}
                    />
                    <span>
                      {s.full_name === s.initials
                        ? s.initials
                        : `${s.full_name} (${s.initials})`}
                      <span className="observer-role"> — {s.role}</span>
                    </span>
                  </label>
                );
              })}
            </div>
            <small>
              {observerIds.length === 0
                ? "Tick everyone who was present — more than one is normal."
                : `${observerIds.length} selected`}
            </small>
          </>
        ) : (
          <p className="hint">Staff unavailable (offline?)</p>
        )}
      </fieldset>

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
          style={inputStyle}
        />
      </label>

      {/* ════════════════════════════════════════════════════════════
          CONTINUOUS-ONLY SECTION
      ════════════════════════════════════════════════════════════ */}
      {method === "continuous" && (
        <>
          <h3 className="section-header">Power &amp; Battery</h3>

          <label>
            Power notes
            <textarea
              {...register("power_notes")}
              rows={2}
              placeholder="Solar panel condition, UPS status, etc."
              style={inputStyle}
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
          <h3 className="section-header">Antenna Setup</h3>

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
              <span className="field-error">Required for campaign</span>
            )}
          </label>

          <p className="hint">
            Slant heights (metres) — measure from mark to antenna reference point
          </p>

          <div
            className="form-grid-2"
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
            className="form-grid-2"
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

          <h3 className="section-header">Session Details</h3>

          <label>
            Session ID
            <input
              type="text"
              {...register("session_id")}
              placeholder="e.g. BUCA342 or BUCA342-01"
              style={inputStyle}
            />
            <small>
              Auto-filled from station + DOY. Append -01, -02 for multiple sessions.
            </small>
          </label>

          <div
            className="form-grid-2"
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

          <label className="checkbox-row">
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
      <h3 className="section-header">Site Photo</h3>

      <label>
        Photo *
        <input
          type="file"
          accept="image/*"
          capture="environment"
          {...register("photo")}
          
        />
      </label>

      {hasPhoto && photoFilename && (
        <p className="msg msg-info">
          Photo selected: {photoFilename}
        </p>
      )}

      {!hasPhoto && !navigator.onLine && (
        <p className="msg msg-warn">
          Your text entries are saved locally.
        </p>
      )}

      {!hasPhoto && (
        <p className="msg msg-error">
          Add a photo to submit.
        </p>
      )}

      {/* ── Submit ── */}
      <button
        type="submit"
        className="submit-btn"
        disabled={isSubmitting || !hasPhoto}
      >
        {isSubmitting ? "Saving…" : "Submit Log Sheet"}
      </button>

      {/* ── Status messages ── */}
      {submitState === "saved" && (
        <p className="msg msg-ok">Saved and synced to server.</p>
      )}
      {submitState === "saved" && errorMsg && (
        <p className="msg msg-warn">{errorMsg}</p>
      )}
      {submitState === "queued" && (
        <p className="msg msg-warn">
          {/* errorMsg is set on the partial path, where the logsheet DID reach
              the server and only the photo is queued. Telling that operator
              "Saved offline" would be the same class of false reassurance this
              form was rewritten to remove. */}
          {errorMsg ||
            "Saved offline — including the photo. Will sync automatically when connected."}
        </p>
      )}
      {submitState === "error" && (
        <p className="msg msg-error">Error: {errorMsg}</p>
      )}
    </form>
  );
}
