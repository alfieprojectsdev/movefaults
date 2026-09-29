/**
 * What to show on the check-before-sending step.
 *
 * WHY THIS EXISTS: the most common correction is "oops, I forgot to add X".
 * Once a sheet reaches the server it can't be edited, so the cheapest fix is
 * to catch the omission before Send.
 *
 * WHAT IT FLAGS, AND WHY SO LITTLE: only a field that is
 *   1. expected for THIS kind of visit (continuous or campaign),
 *   2. blank, and
 *   3. not already enforced by the form.
 * About 40 fields can legitimately be empty, so a flat "these are blank" list
 * would fire on every sheet and teach people to dismiss it. And the form
 * already refuses to submit without a method, date, arrival time, equipment
 * status, photo, antenna model and UTC start (campaign), or a complete
 * equipment change, so repeating those here would be a list that can never
 * appear.
 *
 * The rules below are the ones judged likely from how the form is used. They
 * are meant to be adjusted once real blank rates come back from production
 * and field staff say which fields they actually forget. Change the list, not
 * the mechanism.
 */

import { summariseSlants, MIN_SLANTS } from "./slants";

export interface ReviewInput {
  monitoring_method: "campaign" | "continuous" | "";
  departure_time: string;
  weather_conditions: string;
  observer_ids: number[];
  battery_voltage_v: string;
  slant_n_m: string;
  slant_e_m: string;
  slant_s_m: string;
  slant_w_m: string;
  session_id: string;
  utc_end: string;
  bubble_centred: boolean;
}

export interface ReviewItem {
  /** Which field, for tests and for focusing the input. */
  field: string;
  /** What the observer reads. */
  label: string;
  /**
   * blank: expected and missing, so probably forgotten.
   * confirm: allowed as it stands, but easy to get wrong, so worth one look.
   */
  level: "blank" | "confirm";
}

const isBlank = (v: string | undefined | null) => !v || v.trim() === "";

export function reviewBeforeSend(v: ReviewInput): ReviewItem[] {
  const items: ReviewItem[] = [];

  // Expected on every visit.
  if (isBlank(v.departure_time)) {
    items.push({ field: "departure_time", label: "Departure time", level: "blank" });
  }
  if (isBlank(v.weather_conditions)) {
    items.push({ field: "weather_conditions", label: "Weather", level: "blank" });
  }
  if (!v.observer_ids || v.observer_ids.length === 0) {
    items.push({ field: "observer_ids", label: "Observers (nobody listed)", level: "blank" });
  }

  if (v.monitoring_method === "continuous") {
    if (isBlank(v.battery_voltage_v)) {
      items.push({ field: "battery_voltage_v", label: "Battery voltage", level: "blank" });
    }
  }

  if (v.monitoring_method === "campaign") {
    const s = summariseSlants({ N: v.slant_n_m, E: v.slant_e_m, S: v.slant_s_m, W: v.slant_w_m });
    if (s.count < MIN_SLANTS) {
      items.push({
        field: "slants",
        label: `Slant readings: ${s.missing.join(", ")} missing. No RINEX height without at least ${MIN_SLANTS}`,
        level: "blank",
      });
    } else if (s.missing.length > 0) {
      items.push({
        field: "slants",
        label: `Only ${s.count} slant readings (${s.missing.join(", ")} missing). Fine if that direction was blocked`,
        level: "confirm",
      });
    }
    if (isBlank(v.session_id)) {
      items.push({ field: "session_id", label: "Session ID", level: "blank" });
    }
    if (isBlank(v.utc_end)) {
      items.push({ field: "utc_end", label: "UTC end", level: "blank" });
    }
    if (!v.bubble_centred) {
      items.push({ field: "bubble_centred", label: "Bubble centred is not ticked", level: "confirm" });
    }
  }

  return items;
}
