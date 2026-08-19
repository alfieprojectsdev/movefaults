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

import { useState, useEffect, useRef } from "react";
import { useForm } from "react-hook-form";
import { useQuery } from "@tanstack/react-query";
import StationPicker from "./StationPicker";
import { useOfflineQueue } from "../hooks/useOfflineQueue";
import { groupByRole } from "../utils/roles";
import { checkPhotos, formatBytes } from "../utils/photos";
import {
  localTimeToISO,
  utcFieldToISO,
  nowLocalHHMM,
  nowUTCFieldValue,
  todayLocalISODate,
  utcDayOfYear,
} from "../utils/times";
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

export function computeRH(avgSH: number, C: number, VO: number): number {
  return Math.sqrt(avgSH ** 2 - C ** 2) - VO;
}

// ── Julian DOY helper ────────────────────────────────────────────────────────

export function toDOY(dateStr: string): number {
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
    getValues,
    watch,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    defaultValues: {
      equipment_status: "ok",
      // Prefilled with the moment the form was opened, which for a sheet
      // started on arrival is the arrival time. Editable, because the form is
      // sometimes opened later — but a sensible value beats an empty box that
      // has to be typed on a phone in the rain.
      arrival_time: nowLocalHHMM(),
      // LOCAL date, not toISOString() — that returns the UTC calendar day,
      // which in Manila is yesterday between 00:00 and 08:00 local: exactly
      // when a field team sets out. See todayLocalISODate in utils/times.
      visit_date: todayLocalISODate(),
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

  /**
   * One identity per sheet, not per submit attempt.
   *
   * client_uuid is what makes sync idempotent: the server inserts
   * ON CONFLICT (client_uuid) DO NOTHING, so the same sheet arriving twice
   * lands once. That only holds if a retry carries the *same* uuid. Minting it
   * inside onSubmit gave every attempt a new one, which turned a retry after a
   * slow save into two station visits for one trip to the monument — and the
   * IndexedDB write has a 30 s timeout that rejects without being able to
   * cancel the underlying transaction, so "it failed, tap again" is a normal
   * thing for an operator to do.
   *
   * A new uuid is minted only when the form is cleared for the next sheet,
   * via resetForm() below.
   */
  const clientUuidRef = useRef<string>(generateUUID());

  /** Clear the form for the next sheet and start a new sheet identity. */
  const resetForm = () => {
    reset();
    clientUuidRef.current = generateUUID();
  };

  // ── Watched values ─────────────────────────────────────────────────────────

  const stationCode    = watch("station_code");
  const visitDate      = watch("visit_date");
  const method         = watch("monitoring_method");
  const antennaModel   = watch("antenna_model");
  const slantN         = watch("slant_n_m");
  const slantE         = watch("slant_e_m");
  const slantS         = watch("slant_s_m");
  const slantW         = watch("slant_w_m");
  const utcStart       = watch("utc_start");
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

  // RINEX names a session by its UTC day, so the day-of-year here is taken
  // from utc_start when the observer has entered it. Deriving it from the
  // LOCAL visit date instead agrees for any occupation starting after 08:00
  // Manila time and silently disagrees before that — and the disagreement
  // only shows up much later, when someone tries to pair this logsheet with
  // the observation file it is supposed to name.
  //
  // Falls back to the visit date while utc_start is still empty, so the
  // field is populated as soon as a station and date exist rather than
  // staying blank until the session times are filled in.
  useEffect(() => {
    if (method !== "campaign") return;
    if (stationCode && visitDate) {
      const doy = utcDayOfYear(utcFieldToISO(utcStart)) ?? toDOY(visitDate);
      setValue("session_id", `${stationCode.toUpperCase()}${doy}`);
    }
  }, [stationCode, visitDate, utcStart, method, setValue]);

  // ── Clear mode-specific values when method changes ─────────────────────────

  useEffect(() => {
    if (method === "campaign") {
      setValue("power_notes", "");
      setValue("battery_voltage_v", "");
      // Session start defaults to now, in UTC — the field is UTC by GNSS
      // convention and by its own label, so filling it from the local clock
      // would be eight hours out in the Philippines and look entirely
      // plausible on screen. Only set when empty, so re-selecting the method
      // does not overwrite a time the operator has already corrected.
      // getValues, not watch: this reads the current value once inside the
      // effect rather than subscribing to it, which would re-run the effect on
      // every keystroke in the field it is trying to fill.
      if (!getValues("utc_start")) setValue("utc_start", nowUTCFieldValue());
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
  }, [method, setValue, getValues]);

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
  const photoCount = hasPhoto ? photoFiles.length : 0;
  // Checked here rather than at upload: offline, the upload happens after the
  // observer has left the site, and a rejected photo is retried forever without
  // ever surfacing. See utils/photos.ts.
  const photoCheck = checkPhotos(photoFiles ? Array.from(photoFiles) : null);

  // ── Submit ─────────────────────────────────────────────────────────────────

  const onSubmit = async (values: FormValues) => {
    setSubmitState("saving");
    setErrorMsg("");

    const record: LogSheetIn = {
      client_uuid: clientUuidRef.current,
      station_code: values.station_code,
      monitoring_method: values.monitoring_method || undefined,
      visit_date: values.visit_date,
      // Combined with the visit date and sent as an explicit instant. A bare
      // "14:30" is not a datetime and was rejected with 422 by every sheet
      // that carried one; a naive datetime would be stored as UTC and read
      // back eight hours wrong.
      arrival_time: localTimeToISO(values.visit_date, values.arrival_time),
      departure_time: localTimeToISO(values.visit_date, values.departure_time),
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
      record.utc_start = utcFieldToISO(values.utc_start);
      record.utc_end = utcFieldToISO(values.utc_end);
      record.bubble_centred = values.bubble_centred;
      record.plumbing_offset_mm = values.plumbing_offset_mm
        ? parseFloat(values.plumbing_offset_mm)
        : undefined;
    }

    // Every selected photo is queued WITH the record. Before this it was
    // dropped on the offline path while the UI still reported a successful save.
    const photos: File[] =
      photoFiles && photoFiles.length > 0 ? Array.from(photoFiles) : [];

    if (!navigator.onLine) {
      try {
        await addToQueue(record, photos);
        setSubmitState("queued");
        resetForm();
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

      // Photos go up one at a time after the logsheet exists, because each is
      // a separate request keyed to the returned server id.
      if (photos.length > 0) {
        try {
          for (const p of photos) await uploadLogSheetPhoto(created.id, p);
        } catch {
          // Logsheet is on the server but the photo is not. Queue the photo
          // rather than asking the operator to remember to re-attach it later:
          // by then they have left the site. _photoUploaded stays false, so the
          // next flush re-POSTs the (idempotent) logsheet and retries the photo.
          try {
            await addToQueue(record, photos);
            setSubmitState("queued");
            setErrorMsg(
              photos.length === 1
                ? "Log saved. Photo queued — it will upload on the next sync."
                : `Log saved. ${photos.length} photos queued — they will upload on the next sync.`
            );
            resetForm();
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
      resetForm();
    } catch (err) {
      // Network error mid-submit — queue both halves as the fallback.
      try {
        await addToQueue(record, photos);
        setSubmitState("queued");
        resetForm();
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
          Arrival time *
          <input
            type="time"
            {...register("arrival_time", { required: "Arrival time is required" })}
            style={inputStyle}
          />
          {errors.arrival_time && (
            <small className="field-error">{errors.arrival_time.message}</small>
          )}
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
              {/* Grouped under headings rather than filtered by a control.
                  With 13 names a filter costs more taps than it saves, and a
                  station visit routinely mixes groups — a filter would have to
                  be switched mid-selection every time. Headings show the same
                  information for free and keep every name one scroll away. */}
              {groupByRole(staffList).map((group) => (
                <div key={group.role} className="observer-group">
                  <p className="observer-group-label">{group.label}</p>
                  {group.members.map((s) => {
                    const checked = observerIds.includes(s.id);
                    return (
                      <label key={s.id} className="checkbox-row observer-row">
                        <input
                          type="checkbox"
                          value={s.id}
                          checked={checked}
                          onChange={(e) => {
                            // Rebuilt from the current array rather than toggled
                            // in place, so the stored order stays stable and a
                            // double tap cannot leave a duplicate id behind.
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
                        </span>
                      </label>
                    );
                  })}
                </div>
              ))}
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
              UTC start *
              <input
                type="datetime-local"
                {...register("utc_start", {
                  // Conditional, matching antenna_model above: the field only
                  // applies to campaign sheets. react-hook-form skips validation
                  // for unmounted fields, so an unconditional rule here happens
                  // to be harmless today — but it is still a claim about a field
                  // this mode does not have, and it would start biting the day
                  // the section is hidden with CSS rather than unmounted.
                  required: method === "campaign" ? "UTC start is required" : false,
                })}
                style={inputStyle}
              />
              {errors.utc_start && (
                <small className="field-error">{errors.utc_start.message}</small>
              )}
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
        {/* No `capture` attribute. With it, Android and iOS open the camera
            directly and remove the option to choose an existing file — so a
            photo already taken with the phone's own camera app, or one shot
            before the sheet was started, could not be attached at all.
            Without it the OS offers camera and library both.

            `multiple` because a station visit routinely warrants several
            frames: the antenna, the receiver, the power setup, the damage
            being reported. One photo per sheet forced a choice between them. */}
        <input
          type="file"
          accept="image/*"
          multiple
          {...register("photo")}
        />
      </label>

      {/* Prevention, not just rejection. The size check above stops a photo
          that cannot upload, but by then the shot is already taken and the
          observer has to redo it. A phone left on maximum resolution
          produces 8-12 MB frames all day; changed once, in the settings,
          it produces 2-3 MB frames all day. Collapsed by default because
          this is a one-time setup task, not something to read at every
          station. */}
      <details className="photo-hint">
        <summary>Keeping photos small — set this once, before the trip</summary>
        <p>
          Aim for under about 5 MB a frame. Legibility of handwriting on a
          logsheet matters more than resolution, and a 3 MB photo is already
          past what a phone screen or a printed report resolves.
        </p>
        <ul>
          <li>
            <strong>iPhone or iPad:</strong> Settings → Camera → Formats →
            <strong> High Efficiency</strong>. HEIC is roughly half the size
            of JPEG at the same quality, and this app accepts it.
          </li>
          <li>
            <strong>Android:</strong> Camera app → Settings →
            <strong> Picture size</strong> (sometimes "Resolution" or
            "Image quality"). Drop from the highest setting to a middle one —
            on a 48 MP or 108 MP sensor the top option is far past useful
            here.
          </li>
          <li>
            Turn <strong>off</strong> RAW / "Pro" / "Expert RAW" modes. A RAW
            frame is 20-30 MB and will be refused.
          </li>
        </ul>
        <p>
          Every megabyte is also a megabyte to upload over whatever signal
          the site has, and the queue syncs the whole batch before a sheet
          counts as filed.
        </p>
      </details>

      {hasPhoto && photoCheck.ok && (
        <p className={photoCheck.warnTotal ? "msg msg-warn" : "msg msg-info"}>
          {photoCount === 1
            ? `1 photo selected: ${photoFiles![0].name}`
            : `${photoCount} photos selected`}
          {" — "}
          {formatBytes(photoCheck.totalBytes)}
          {photoCheck.warnTotal &&
            ". That is a large batch; it will take a while to sync on a weak connection."}
        </p>
      )}

      {photoCheck.oversized.length > 0 && (
        <p className="msg msg-error">
          {photoCheck.oversized.length === 1
            ? `${photoCheck.oversized[0].name} is ${formatBytes(
                photoCheck.oversized[0].size
              )} — over the 15 MB limit.`
            : `${photoCheck.oversized.length} photos are over the 15 MB limit: ` +
              photoCheck.oversized
                .map((f) => `${f.name} (${formatBytes(f.size)})`)
                .join(", ")}
          {" "}
          The server refuses these, and offline they would queue and then never
          finish syncing. Retake at a lower resolution, or choose different files.
        </p>
      )}

      {/* Gated on isDirty, and the offline half is gone entirely.

          Both banners used to render from empty state alone, which put them
          on screen at the two moments they were least wanted: a brand-new
          sheet opened under a red error nobody had earned yet, and — because
          resetForm() clears the form on a successful save — the instant a
          save succeeded. That second one was the bad one. "Add a photo to
          submit" in red, above "Saved offline — including the photo", reads
          as a failure report on a sheet that was in fact safely queued, and
          red is what the eye lands on. Observed in the 2026-08-20 E2E run.

          isDirty is the right gate because it is false in exactly those two
          cases and true the moment the operator types anything: reset() clears
          it, and the autofills (visit_date, utc_start, session_id) go through
          setValue, which does not mark the form dirty. Once someone is filling
          a sheet in earnest, the outstanding requirement is worth saying
          plainly — the Submit button is disabled until it is met and a
          disabled button with no explanation is its own bug.

          The offline banner said "Your text entries are saved locally." That
          was not true: nothing persists this form before submit — no draft, no
          localStorage — so an operator who closed the app on that promise lost
          the sheet. It also read navigator.onLine during render, which
          useOnline.ts exists precisely because it never re-renders on a
          connectivity change. App.tsx already shows an accurate, reactive
          offline banner at the top of the screen, so this is a deletion rather
          than a repair. */}
      {!hasPhoto && isDirty && (
        <p className="msg msg-error">
          Add a photo to submit.
        </p>
      )}

      {/* ── Submit ── */}
      <button
        type="submit"
        className="submit-btn"
        disabled={isSubmitting || !hasPhoto || !photoCheck.ok}
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
