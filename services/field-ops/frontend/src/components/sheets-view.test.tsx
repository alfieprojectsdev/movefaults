import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SheetsView from "./SheetsView";
import { fetchSheets, fetchPhotoObjectUrl, Sheet } from "../services/api";

/**
 * The claim this view makes is about completeness, and getting that wrong is
 * how someone concludes a colleague never filed a sheet that is in fact sitting
 * on a phone in a bag. These assert the three states stay distinguishable.
 */

vi.mock("../services/api", () => ({
  fetchSheets: vi.fn(),
  fetchPhotoObjectUrl: vi.fn(),
}));

const getQueue = vi.fn();
vi.mock("../hooks/useOfflineQueue", () => ({
  useOfflineQueue: () => ({ getQueue }),
}));
vi.mock("../hooks/useOnline", () => ({ useOnline: () => true }));

const sheet = (over: Partial<Sheet> = {}): Sheet => ({
  id: 1,
  client_uuid: "uuid-1",
  station_code: "PPPC",
  visit_date: "2026-08-20",
  monitoring_method: "continuous",
  session_id: null,
  antenna_model: null,
  rinex_height_m: null,
  equipment_status: "ok",
  battery_voltage_v: null,
  equipment_changed: null,
  notes: null,
  created_at: "2026-08-20T05:08:00Z",
  synced_at: "2026-08-20T05:08:00Z",
  observers: ["ARP"],
  photos: [{ id: 7, filename: "antenna.jpg", uploaded_at: "2026-08-20T05:08:01Z" }],
  ...over,
});

beforeEach(() => {
  vi.clearAllMocks();
  getQueue.mockResolvedValue([]);
});

describe("the three states", () => {
  it("shows a synced sheet with its photos", async () => {
    vi.mocked(fetchSheets).mockResolvedValue([sheet()]);
    render(<SheetsView />);
    expect(await screen.findByText("PPPC")).toBeTruthy();
    expect(screen.getByRole("button", { name: /1 photo/ })).toBeTruthy();
  });

  it("marks a sheet whose photo never arrived", async () => {
    // The "Log saved. Photo queued." path — on the server, photo not. This is
    // the one worth chasing, so it must not read the same as a complete sheet.
    vi.mocked(fetchSheets).mockResolvedValue([sheet({ photos: [] })]);
    render(<SheetsView />);
    expect(await screen.findByText(/photo pending/i)).toBeTruthy();
  });

  it("lists this device's unsent sheets separately from the server's", async () => {
    vi.mocked(fetchSheets).mockResolvedValue([]);
    getQueue.mockResolvedValue([
      { client_uuid: "local-1", station_code: "PNDO", visit_date: "2026-08-20", _status: "pending" },
    ]);
    render(<SheetsView />);
    expect(await screen.findByText(/on this device, not yet sent/i)).toBeTruthy();
    expect(screen.getByText("PNDO")).toBeTruthy();
  });

  it("does not list a local record that already synced", async () => {
    // It is already in the server list; showing it twice would imply two sheets.
    vi.mocked(fetchSheets).mockResolvedValue([sheet()]);
    getQueue.mockResolvedValue([
      { client_uuid: "uuid-1", station_code: "PPPC", visit_date: "2026-08-20", _status: "synced" },
    ]);
    render(<SheetsView />);
    await screen.findByText("PPPC");
    expect(screen.queryByText(/on this device, not yet sent/i)).toBeNull();
  });

  it("says out loud that other devices' sheets cannot appear here", async () => {
    // The completeness caveat is load-bearing, not decoration.
    vi.mocked(fetchSheets).mockResolvedValue([]);
    render(<SheetsView />);
    expect(await screen.findByText(/still waiting on someone else's device/i)).toBeTruthy();
  });
});

describe("photos", () => {
  it("fetches bytes only when asked, and shows them in place", async () => {
    // Not eagerly: a table of 4 MB photos on a field connection is the whole
    // reason these are behind a tap.
    vi.mocked(fetchSheets).mockResolvedValue([sheet()]);
    vi.mocked(fetchPhotoObjectUrl).mockResolvedValue("blob:fake");
    const user = userEvent.setup();
    render(<SheetsView />);

    const button = await screen.findByRole("button", { name: /1 photo/ });
    expect(fetchPhotoObjectUrl).not.toHaveBeenCalled();

    await user.click(button);
    await waitFor(() => expect(fetchPhotoObjectUrl).toHaveBeenCalledWith(7));
    expect(screen.getByRole("img", { name: "antenna.jpg" }).getAttribute("src")).toBe("blob:fake");
  });

  it("reports a photo that will not load without losing the row", async () => {
    vi.mocked(fetchSheets).mockResolvedValue([sheet()]);
    vi.mocked(fetchPhotoObjectUrl).mockRejectedValue(new Error("Could not load photo (404)"));
    const user = userEvent.setup();
    render(<SheetsView />);

    await user.click(await screen.findByRole("button", { name: /1 photo/ }));
    expect(await screen.findByText(/could not load photo/i)).toBeTruthy();
    expect(screen.getByText("PPPC")).toBeTruthy();
  });
});

describe("failure", () => {
  it("surfaces a failed load instead of an empty table", async () => {
    // An empty table reads as "nobody filed anything", which is the opposite of
    // what a failed request means.
    vi.mocked(fetchSheets).mockRejectedValue(new Error("Session expired"));
    render(<SheetsView />);
    expect(await screen.findByText(/session expired/i)).toBeTruthy();
  });
});
