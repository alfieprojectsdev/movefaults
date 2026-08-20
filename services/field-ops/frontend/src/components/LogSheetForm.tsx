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
 *   - Slant heights (N/E/S/W) + selected antenna model drive a live RH calc.
 *     Three of the four are enough — see utils/slants.ts for why, and for
 *     what the missing one costs.
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
import { summariseSlants, MIN_SLANTS } from "../utils/slants";
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

/**
 * Per-model geometry for the slant-height reduction.
 *
 *   C  — radial distance from the antenna's vertical axis to the edge the tape
 *        is hooked on (metres). Trimble's drawings call this R1 or C.
 *   VO — vertical distance from that same edge down to the antenna reference
 *        point (metres).
 *
 * Values are taken from Trimble's antenna reference surface diagrams and cross
 * checked against PHIVOLCS' own `antenna_height_conversion` workbooks, which
 * carry the identical formula per model and are what every historical campaign
 * was reduced with. The two agree on all five models to within 0.05 mm.
 *
 * VO is NOT simply "row A minus row B" on the drawing, and reading it that way
 * is what produced the TRM22020 error below. The rows are labelled per antenna:
 * on the Zephyrs, B is "bottom of antenna mark to nominal phase centre" and the
 * subtraction is right, but on the Compact L1/L2 the drawing has three vertical
 * rows and B is "TOP of ground plane" while C is "BOTTOM of ground plane".
 *
 * A and B are kept only to show the arithmetic behind VO. Nothing reads them —
 * computeRH takes C and VO. Add a model by reading its drawing, not by pattern
 * matching this table.
 */
interface AntennaConstants {
  /** Bottom of antenna to nominal phase centre (cm) — provenance only. */
  A: number;
  /** The row subtracted from A to give VO (cm) — provenance only. */
  B: number;
  /** Radial centre to the measured edge (m). */
  C: number;
  /** Measured edge down to the antenna reference point (m). */
  VO: number;
}

export const ANTENNA_CONSTANTS: Record<string, AntennaConstants> = {
  // Compact L1/L2 with ground plane. A - C on the drawing, not A - B: the tape
  // hooks under the ground plane, so the measured edge is its BOTTOM (0.69 cm
  // to phase centre), not its top (0.34 cm). Using the top row put VO 3.5 mm
  // high — the ground plane's own thickness — which is a real vertical bias,
  // not a rounding difference, and would have appeared as a step in the time
  // series against every occupation reduced with the workbook.
  "TRM22020.00+GP": { A: 6.25,   B: 0.69,  C: 0.2334,  VO: 0.0556  },
  // Zephyr Geodetic. A - B, both rows off the drawing.
  "TRM41249.00":    { A: 5.326,  B: 0.891, C: 0.16981, VO: 0.04435 },
  // Zephyr GNSS Geodetic Model 2 (P/N 55971-00). A - B off the drawing.
  "TRM55971.00":    { A: 8.50,   B: 4.06,  C: 0.16981, VO: 0.0444  },
  // No drawing: TRM55971.png and TRM57971.png are both the 55971-00 sheet.
  // These come from the workbook's own TRM57971.00 tab and are unconfirmed
  // against Trimble. Verify if a genuine 57971 diagram turns up.
  "TRM57971.00":    { A: 8.546,  B: 4.111, C: 0.16981, VO: 0.04435 },
  // Zephyr 3 (blue field card).
  "TRM115000.00":   { A: 6.519,  B: 2.085, C: 0.16981, VO: 0.04434 },
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
  equipment_changed: boolean;
  receiver_model_before: string;
  receiver_model_after: string;
  receiver_serial_before: string;
  receiver_serial_after: string;
  receiver_firmware_before: string;
  receiver_firmware_after: string;
  antenna_type_before: string;
  antenna_type_after: string;
  antenna_part_number_before: string;
  antenna_part_number_after: string;
  antenna_serial_before: string;
  antenna_serial_after: string;
  antenna_height_before_m: string;
  antenna_height_after_m: string;
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
  const equipmentChanged = watch("equipment_changed");
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
    }
  }, [method, setValue, getValues]);

  // ── Live antenna height computation ───────────────────────────────────────

  const constants = antennaModel ? ANTENNA_CONSTANTS[antennaModel] : undefined;

  // Three readings are enough. A tripod leg or the monument itself can block
  // the fourth, and refusing the sheet then does not produce a fourth reading —
  // it produces a sheet filed on paper. See utils/slants.ts for what the third
  // one costs in vertical bias, and why that trade was taken knowingly.
  const slants = summariseSlants({ N: slantN, E: slantE, S: slantS, W: slantW });

  const avgSH = slants.avg;

  // sqrt(avgSH² - C²) is imaginary once the average slant drops below the
  // antenna radius, and JavaScript answers NaN rather than raising. Unguarded
  // that reached the screen as the literal text "NaN" and the server as
  // rinex_height_m: null — JSON has no NaN — sitting next to a perfectly
  // ordinary avg_slant_m, with nothing anywhere reporting a problem.
  //
  // It is a typo, not a measurement: C is 0.17-0.23 m and a real slant is
  // 1.2-1.6 m, so this only happens when a decimal moves (0.432 for 1.432,
  // following the placeholder). min="0" on the inputs does not catch it.
  const rhImpossible =
    avgSH !== undefined && constants !== undefined && avgSH <= constants.C;

  const rhValue =
    avgSH !== undefined && constants !== undefined && !rhImpossible
      ? computeRH(avgSH, constants.C, constants.VO)
      : undefined;

  // ── Equipment change ───────────────────────────────────────────────────────

  // Ticking the box without naming what changed is worse than not ticking it:
  // the sheet records that a swap happened and keeps no trace of what it was
  // swapped to. Watched as a group rather than field by field so a value in any
  // one of them satisfies it.
  const equipmentAfter = watch([
    "receiver_model_after",
    "receiver_serial_after",
    "receiver_firmware_after",
    "antenna_type_after",
    "antenna_part_number_after",
    "antenna_serial_after",
    "antenna_height_after_m",
  ]);
  const anyEquipmentAfter = equipmentAfter.some((v) => String(v ?? "").trim() !== "");

  // Blocks Submit, not merely warned about.
  //
  // Online this would be a 422 the observer could fix on the spot. Offline it
  // queues, flushes hours later, and comes back "refused by the server" — by
  // which time the team has left the monument and the serial number needed to
  // answer it is back at the site. That is the same failure the photo size
  // check exists to prevent, in the same form.
  //
  // Scoped to continuous: the equipment block is not rendered for a campaign
  // sheet, and a stale tick left behind by a method switch must not lock a form
  // whose user cannot see the field causing it.
  const equipmentChangeIncomplete =
    method === "continuous" && !!equipmentChanged && !anyEquipmentAfter;

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
      record.receiver_model_before = values.receiver_model_before || undefined;
      record.receiver_model_after = values.receiver_model_after || undefined;
      record.receiver_serial_before = values.receiver_serial_before || undefined;
      record.receiver_serial_after = values.receiver_serial_after || undefined;
      record.receiver_firmware_before = values.receiver_firmware_before || undefined;
      record.receiver_firmware_after = values.receiver_firmware_after || undefined;
      record.antenna_type_before = values.antenna_type_before || undefined;
      record.antenna_type_after = values.antenna_type_after || undefined;
      record.antenna_part_number_before = values.antenna_part_number_before || undefined;
      record.antenna_part_number_after = values.antenna_part_number_after || undefined;
      record.antenna_serial_before = values.antenna_serial_before || undefined;
      record.antenna_serial_after = values.antenna_serial_after || undefined;
      record.equipment_changed = values.equipment_changed || undefined;
      record.antenna_height_before_m = values.antenna_height_before_m ? parseFloat(values.antenna_height_before_m) : undefined;
      record.antenna_height_after_m = values.antenna_height_after_m ? parseFloat(values.antenna_height_after_m) : undefined;
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

  // isDirty was supposed to cover the post-save case on its own: resetForm()
  // clears it, so a saved sheet should look like an untouched one. Observed on
  // the deployed app 2026-08-20 that it does not — after a successful ONLINE
  // save the form reports dirty again, and "Add a photo to submit." came back
  // in red directly beneath "Saved and synced to server."
  //
  // That is the same failure the offline path was fixed for, and the fix was
  // one layer too clever: it guarded the cause it had found rather than the
  // outcome it cared about. Whatever re-dirties the form after reset, there is
  // no state in which a pre-submit prompt belongs on screen next to a
  // confirmation that the sheet is filed.
  const justSaved = submitState === "saved" || submitState === "queued";

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

          {/* ── Equipment: as found, and as left ──────────────────────────
              The Before/After table from the paper GPS Station Maintenance
              Record. "As found" is the half that matters most right now:
              PPPC, PNDO and PKLY have no equipment history on record at all,
              so the Palawan visit is the first time their hardware is written
              down anywhere. An unrecorded swap later shows up in the
              coordinate series as a step that looks like ground movement. */}
          <h3 className="section-header">Equipment as found</h3>

          <p className="hint">
            Copy from the labels on the receiver and antenna. If a field is not
            marked on the hardware, leave it blank rather than guessing.
          </p>

          <label>
            Receiver model
            <input
              type="text"
              {...register("receiver_model_before")}
              placeholder="e.g. Leica GR50"
              style={inputStyle}
            />
          </label>

          <div className="form-grid-2">
            <label>
              Receiver serial
              <input
                type="text"
                {...register("receiver_serial_before")}
                placeholder="e.g. 1871357"
                style={inputStyle}
              />
            </label>
            <label>
              Firmware
              <input
                type="text"
                {...register("receiver_firmware_before")}
                placeholder="e.g. 4.31.101"
                style={inputStyle}
              />
            </label>
          </div>

          <label>
            Antenna type
            <input
              type="text"
              {...register("antenna_type_before")}
              placeholder="e.g. Leica AR20"
              style={inputStyle}
            />
          </label>

          <div className="form-grid-2">
            <label>
              Antenna part no.
              <input
                type="text"
                {...register("antenna_part_number_before")}
                style={inputStyle}
              />
            </label>
            <label>
              Antenna serial
              <input
                type="text"
                {...register("antenna_serial_before")}
                placeholder="e.g. 23055009"
                style={inputStyle}
              />
            </label>
          </div>

          <label>
            Antenna height, vertical (m)
            <input
              type="number"
              step="0.0001"
              min="0"
              {...register("antenna_height_before_m")}
              style={inputStyle}
            />
          </label>

          <label className="checkbox-row">
            <input type="checkbox" {...register("equipment_changed")} />
            Equipment was changed during this visit
          </label>

          {equipmentChanged && (
            <>
              <h3 className="section-header">Equipment as left</h3>
              <p className="hint">
                Fill in only what changed. Anything left blank means it is still
                what is recorded above.
              </p>

              <label>
                Receiver model
                <input
                  type="text"
                  {...register("receiver_model_after")}
                  style={inputStyle}
                />
              </label>

              <div className="form-grid-2">
                <label>
                  Receiver serial
                  <input
                    type="text"
                    {...register("receiver_serial_after")}
                    style={inputStyle}
                  />
                </label>
                <label>
                  Firmware
                  <input
                    type="text"
                    {...register("receiver_firmware_after")}
                    style={inputStyle}
                  />
                </label>
              </div>

              <label>
                Antenna type
                <input
                  type="text"
                  {...register("antenna_type_after")}
                  style={inputStyle}
                />
              </label>

              <div className="form-grid-2">
                <label>
                  Antenna part no.
                  <input
                    type="text"
                    {...register("antenna_part_number_after")}
                    style={inputStyle}
                  />
                </label>
                <label>
                  Antenna serial
                  <input
                    type="text"
                    {...register("antenna_serial_after")}
                    style={inputStyle}
                  />
                </label>
              </div>

              <label>
                Antenna height, vertical (m)
                <input
                  type="number"
                  step="0.0001"
                  min="0"
                  {...register("antenna_height_after_m")}
                  style={inputStyle}
                />
              </label>

              {!anyEquipmentAfter && (
                <p className="msg msg-error">
                  Tick means something was swapped — record what it was changed
                  to. A ticked box with nothing under it says a change happened
                  and destroys the only record of what it was.
                </p>
              )}
            </>
          )}
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
              {slants.count > 0 && ` — ${slants.count} of 4`}
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

          {/* Said on the form, not only in the code, because this is the one
              thing about a three-reading sheet that cannot be recovered later:
              which direction was blocked, and therefore which axis the height
              carries tilt on. The office can see the null column, but not why. */}
          {slants.partial && (
            <p className="msg msg-warn">
              Averaging {MIN_SLANTS} readings — {slants.missing.join(", ")} not
              measured. The height is usable, but carries a small tilt bias
              (roughly 1–2 mm) that four readings would have cancelled. Note in
              the log why the direction was blocked.
            </p>
          )}

          {slants.count > 0 && !slants.enough && (
            <p className="msg msg-error">
              At least {MIN_SLANTS} slant readings are needed to compute a
              height. {slants.count} entered.
            </p>
          )}

          {rhImpossible && constants !== undefined && (
            <p className="msg msg-error">
              Average slant {avgSH!.toFixed(4)} m is shorter than the antenna's
              own radius ({constants.C.toFixed(4)} m), so no height can be
              computed. Check for a misplaced decimal — a real slant is around
              1.2–1.6 m. The readings you entered are still saved.
            </p>
          )}

          {slants.spreadMm !== undefined && slants.spreadMm > 20 && (
            <p className="msg msg-warn">
              Readings span {slants.spreadMm.toFixed(0)} mm. That is a lot for
              one setup — check for a mistyped figure or a tape caught on the
              tripod before submitting.
            </p>
          )}

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
      {!hasPhoto && isDirty && !justSaved && (
        <p className="msg msg-error">
          Add a photo to submit.
        </p>
      )}

      {/* ── Submit ── */}
      <button
        type="submit"
        className="submit-btn"
        disabled={isSubmitting || !hasPhoto || !photoCheck.ok || equipmentChangeIncomplete}
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
