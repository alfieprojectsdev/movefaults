import { describe, it, expect } from "vitest";
import { reviewBeforeSend, type ReviewInput } from "./review";

/**
 * The check-before-sending step flags only what is EXPECTED for this kind of
 * sheet, blank, and not already enforced by the form. A continuous visit with
 * every campaign field empty must review clean: a warning that fires on every
 * sheet teaches people to dismiss it, in the one place it has to land.
 */

const base: ReviewInput = {
  monitoring_method: "continuous",
  departure_time: "14:30",
  weather_conditions: "clear",
  observer_ids: [3],
  battery_voltage_v: "12.8",
  slant_n_m: "",
  slant_e_m: "",
  slant_s_m: "",
  slant_w_m: "",
  session_id: "",
  utc_end: "",
  bubble_centred: false,
};

const campaign: ReviewInput = {
  ...base,
  monitoring_method: "campaign",
  battery_voltage_v: "",
  slant_n_m: "1.5012",
  slant_e_m: "1.5020",
  slant_s_m: "1.5031",
  slant_w_m: "1.5018",
  session_id: "BUCA342",
  utc_end: "2026-09-29T06:00",
  bubble_centred: true,
};

const fields = (items: ReturnType<typeof reviewBeforeSend>) => items.map((i) => i.field);

describe("a complete sheet", () => {
  it("reviews clean for a continuous visit, whatever the campaign fields hold", () => {
    expect(reviewBeforeSend(base)).toEqual([]);
  });

  it("reviews clean for a complete campaign session, whatever the battery field holds", () => {
    expect(reviewBeforeSend(campaign)).toEqual([]);
  });
});

describe("fields expected on every visit", () => {
  it("flags a blank departure time", () => {
    expect(fields(reviewBeforeSend({ ...base, departure_time: "" }))).toEqual(["departure_time"]);
  });

  it("flags blank weather, treating whitespace as blank", () => {
    expect(fields(reviewBeforeSend({ ...base, weather_conditions: "   " }))).toEqual([
      "weather_conditions",
    ]);
  });

  it("flags a sheet with no observers", () => {
    expect(fields(reviewBeforeSend({ ...base, observer_ids: [] }))).toEqual(["observer_ids"]);
  });
});

describe("continuous visits", () => {
  it("flag a blank battery voltage", () => {
    expect(fields(reviewBeforeSend({ ...base, battery_voltage_v: "" }))).toEqual([
      "battery_voltage_v",
    ]);
  });
});

describe("campaign sessions", () => {
  it("flag fewer than three slants as blank: there is no RINEX height without them", () => {
    const items = reviewBeforeSend({ ...campaign, slant_s_m: "", slant_w_m: "" });
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ field: "slants", level: "blank" });
    expect(items[0].label).toMatch(/S, W/);
  });

  it("ask to confirm exactly three slants, which the form allows on purpose", () => {
    const items = reviewBeforeSend({ ...campaign, slant_w_m: "" });
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ field: "slants", level: "confirm" });
  });

  it("flag a blank session ID and UTC end", () => {
    expect(fields(reviewBeforeSend({ ...campaign, session_id: "", utc_end: "" }))).toEqual([
      "session_id",
      "utc_end",
    ]);
  });

  it("ask to confirm an unticked bubble, since unticked and forgotten look the same", () => {
    const items = reviewBeforeSend({ ...campaign, bubble_centred: false });
    expect(items).toEqual([
      expect.objectContaining({ field: "bubble_centred", level: "confirm" }),
    ]);
  });
});

describe("a sheet with no method chosen", () => {
  it("checks only the always-expected fields; the form blocks the missing method itself", () => {
    const items = reviewBeforeSend({ ...base, monitoring_method: "", battery_voltage_v: "" });
    expect(items).toEqual([]);
  });
});
