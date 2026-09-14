import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TodayView from "./TodayView";
import type { Sheet, Station } from "../services/api";
import type { LocationState } from "../hooks/useDeviceLocation";

/**
 * What this screen claims, and therefore what can be wrong with it.
 *
 * Today tells an observer which stations are near, when each was last visited
 * and whether one is overdue. Every one of those is a claim about the field
 * that someone will act on by driving somewhere. The tests below are about the
 * claims, not the markup:
 *
 *   - a station outside the radius is not "near you"
 *   - a poor fix does not silently become a position
 *   - overdue means the interval was actually exceeded
 *   - starting a sheet carries the station the observer tapped
 *
 * The overdue case is the one that could not be written at all before the
 * detail fields landed: `maintenance_interval_days` is what turns "last
 * visited in March" into "this one needs visiting".
 */

const stationsResult = vi.fn();
const sheetsResult = vi.fn();
const locationResult = vi.fn();

vi.mock("../hooks/useStations", () => ({ useStations: () => stationsResult() }));
vi.mock("../hooks/useSheets", () => ({ useSheets: () => sheetsResult() }));
vi.mock("../hooks/useOfflineQueue", () => ({
  useOfflineQueue: () => ({ pendingCount: 2 }),
}));
vi.mock("../hooks/useDeviceLocation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../hooks/useDeviceLocation")>();
  return { ...actual, useDeviceLocation: () => locationResult() as LocationState };
});

// PHIVOLCS Quezon City, near enough to the real thing for distance arithmetic.
const HERE = { latitude: 14.6537, longitude: 121.0584 };

const station = (over: Partial<Station> = {}): Station => ({
  station_code: "PHIV",
  name: "PHIVOLCS Main",
  latitude: HERE.latitude,
  longitude: HERE.longitude,
  elevation: null,
  fault_segment: null,
  status: "active",
  monitoring_method: "continuous",
  municipality: "Quezon City",
  province: "Metro Manila",
  ...over,
});

const sheet = (over: Partial<Sheet> = {}): Sheet => ({
  id: 1,
  client_uuid: "u1",
  station_code: "PHIV",
  visit_date: "2026-09-14",
  monitoring_method: "continuous",
  session_id: null,
  antenna_model: null,
  rinex_height_m: null,
  equipment_status: "ok",
  battery_voltage_v: null,
  equipment_changed: null,
  notes: null,
  created_at: null,
  synced_at: null,
  observers: [],
  photos: [],
  ...over,
});

/** A station roughly `km` east of HERE. */
function kmEast(code: string, km: number, over: Partial<Station> = {}): Station {
  return station({
    station_code: code,
    name: code,
    longitude: HERE.longitude + km / 107.5, // ~107.5 km per degree at 14.65°N
    ...over,
  });
}

const goodFix: LocationState = {
  status: "located",
  fix: { ...HERE, accuracy: 20, at: Date.now() },
};

beforeEach(() => {
  vi.clearAllMocks();
  stationsResult.mockReturnValue({ data: [station()], isLoading: false });
  sheetsResult.mockReturnValue({ data: [] });
  locationResult.mockReturnValue(goodFix);
});

describe("near you", () => {
  it("orders by distance and says how far", async () => {
    stationsResult.mockReturnValue({
      data: [kmEast("FAR", 9), kmEast("NEAR", 1)],
      isLoading: false,
    });
    render(<TodayView onStartSheet={vi.fn()} />);

    const codes = screen
      .getAllByRole("listitem")
      .map((li) => li.querySelector("strong")?.textContent);
    expect(codes).toEqual(["NEAR", "FAR"]);
    // Distance is stated, not implied by position in the list.
    expect(screen.getByText(/1\.0 km|1 km/)).toBeTruthy();
  });

  it("leaves out a station beyond the radius", () => {
    stationsResult.mockReturnValue({
      data: [kmEast("NEAR", 2), kmEast("AWAY", 40)],
      isLoading: false,
    });
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.queryByText("AWAY")).toBeNull();
    expect(screen.getByText("NEAR")).toBeTruthy();
  });

  it("says so rather than showing an empty list when nothing is close", () => {
    stationsResult.mockReturnValue({ data: [kmEast("AWAY", 40)], isLoading: false });
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.getByText(/No station within/)).toBeTruthy();
  });
});

describe("a fix that is not good enough", () => {
  // The failure this prevents: a 5 km cell-tower fix quietly reordering the
  // list by a position that is wrong, so the observer trusts an ordering that
  // means nothing. Saying "only accurate to 5 km" costs a line and keeps the
  // judgement with the person who can make it.
  it("falls back to the full list and states the accuracy", () => {
    locationResult.mockReturnValue({
      status: "located",
      fix: { ...HERE, accuracy: 5_000, at: Date.now() },
    });
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.getByText(/only accurate to/)).toBeTruthy();
    expect(screen.queryByText("Near you")).toBeNull();
  });

  it("names a denied permission as the reason", () => {
    locationResult.mockReturnValue({ status: "denied" });
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.getByText(/Location permission is off/)).toBeTruthy();
  });
});

describe("what the station's own metadata buys", () => {
  it("marks a station overdue against its own interval", () => {
    const old = new Date(Date.now() - 200 * 86_400_000).toISOString().slice(0, 10);
    stationsResult.mockReturnValue({
      data: [station({ maintenance_interval_days: 180 })],
      isLoading: false,
    });
    sheetsResult.mockReturnValue({ data: [sheet({ visit_date: old })] });
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.getByText(/overdue/)).toBeTruthy();
  });

  it("does not mark one visited inside its interval", () => {
    const recent = new Date(Date.now() - 30 * 86_400_000).toISOString().slice(0, 10);
    stationsResult.mockReturnValue({
      data: [station({ maintenance_interval_days: 180 })],
      isLoading: false,
    });
    sheetsResult.mockReturnValue({ data: [sheet({ visit_date: recent })] });
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.queryByText(/overdue/)).toBeNull();
  });

  it("says nothing about overdue when the station carries no interval", () => {
    // Most of the inventory has no interval. Silence is correct here: the app
    // does not know, and inventing a default would put stations on a list the
    // observer is meant to act on.
    const old = new Date(Date.now() - 900 * 86_400_000).toISOString().slice(0, 10);
    stationsResult.mockReturnValue({
      data: [station({ maintenance_interval_days: null })],
      isLoading: false,
    });
    sheetsResult.mockReturnValue({ data: [sheet({ visit_date: old })] });
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.queryByText(/overdue/)).toBeNull();
  });

  it("shows the municipality and province the endpoint now returns", () => {
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.getByText("Quezon City, Metro Manila")).toBeTruthy();
  });

  it("falls back to the station name when it has no administrative location", () => {
    stationsResult.mockReturnValue({
      data: [station({ municipality: null, province: null, name: "Old Monument" })],
      isLoading: false,
    });
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.getByText("Old Monument")).toBeTruthy();
  });

  it("says when a station has never been visited", () => {
    render(<TodayView onStartSheet={vi.fn()} />);
    expect(screen.getByText(/no sheet on record/)).toBeTruthy();
  });
});

describe("search", () => {
  it("matches municipality, not only the code", async () => {
    stationsResult.mockReturnValue({
      data: [
        station({ station_code: "AAAA", municipality: "Tuguegarao", name: "A" }),
        station({ station_code: "BBBB", municipality: "Davao", name: "B" }),
      ],
      isLoading: false,
    });
    locationResult.mockReturnValue({ status: "denied" });
    render(<TodayView onStartSheet={vi.fn()} />);

    await userEvent.type(screen.getByLabelText("Search stations"), "tugue");
    expect(screen.getByText("AAAA")).toBeTruthy();
    expect(screen.queryByText("BBBB")).toBeNull();
  });
});

describe("starting a sheet", () => {
  it("hands back the station that was tapped", async () => {
    const onStartSheet = vi.fn();
    stationsResult.mockReturnValue({
      data: [kmEast("NEAR", 1), kmEast("ALSO", 3)],
      isLoading: false,
    });
    render(<TodayView onStartSheet={onStartSheet} />);

    await userEvent.click(screen.getAllByRole("button", { name: "Start sheet" })[1]);
    expect(onStartSheet).toHaveBeenCalledWith("ALSO");
  });
});
