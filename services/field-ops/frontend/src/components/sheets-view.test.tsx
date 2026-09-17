import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SheetsView from "./SheetsView";
import { fetchSheets, fetchPhotoObjectUrl, Sheet } from "../services/api";

/**
 * The claim this view makes is about completeness, and getting that wrong is
 * how someone concludes a colleague never filed a sheet that is in fact sitting
 * on a phone in a bag. These assert the three states stay distinguishable.
 *
 * TWO SPELLINGS, AND WHY THEY DIFFER
 *
 * `today-view.test.tsx` carries the rule these follow: the line that reads
 * like the check has to be the check. `expect(screen.getByText(x)).toBeTruthy()`
 * is not one -- getBy throws when it finds nothing and otherwise returns an
 * element, so toBeTruthy has no input that could fail it. Nine lines here were
 * that shape, and the regression was still caught, one call inward, by the
 * throw -- but a reader deciding whether to trust this file reads the line.
 *
 * The fix is not one rewrite, because this file is async where that one is not:
 *
 *   `await screen.findByText(x);`  bare, no expect(). The await IS the
 *   assertion: findBy rejects on timeout with the text it wanted and a dump of
 *   what was actually rendered. Wrapping it in expect(...).toBeTruthy() adds a
 *   check that cannot fail in front of one that can, which is strictly worse
 *   than nothing -- it hides where the failure would come from.
 *
 *   `expect(screen.queryByText(x)).not.toBeNull();`  for anything asserted
 *   AFTER the await has settled the render. queryBy returns null rather than
 *   throwing, so this one genuinely can fail on its own line. Same spelling as
 *   today-view, including `.toBeNull()` for the negative case at line 83.
 *
 * So: one find per test to wait on, then queryBy for everything else that
 * should be on screen by then. A bare findBy reads like a statement rather
 * than a check, which is the cost; it is preferred anyway, because the
 * alternative is `await waitFor(() => expect(screen.queryByText(x)).not
 * .toBeNull())`, which is a polling loop wrapped around an assertion to say
 * what findBy already says, with a worse failure message.
 *
 * Follows the same finding as today-view's, from the #221 review.
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
    await screen.findByText("PPPC");
    expect(screen.queryByRole("button", { name: /1 photo/ })).not.toBeNull();
  });

  it("marks a sheet whose photo never arrived", async () => {
    // The "Log saved. Photo queued." path — on the server, photo not. This is
    // the one worth chasing, so it must not read the same as a complete sheet.
    vi.mocked(fetchSheets).mockResolvedValue([sheet({ photos: [] })]);
    render(<SheetsView />);
    await screen.findByText(/photo pending/i);
  });

  it("lists this device's unsent sheets separately from the server's", async () => {
    vi.mocked(fetchSheets).mockResolvedValue([]);
    getQueue.mockResolvedValue([
      { client_uuid: "local-1", station_code: "PNDO", visit_date: "2026-08-20", _status: "pending" },
    ]);
    render(<SheetsView />);
    await screen.findByText(/on this device, not yet sent/i);
    expect(screen.queryByText("PNDO")).not.toBeNull();
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
    await screen.findByText(/still waiting on someone else's device/i);
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
    await screen.findByText(/could not load photo/i);
    expect(screen.queryByText("PPPC")).not.toBeNull();
  });
});

describe("failure", () => {
  it("surfaces a failed load instead of an empty table", async () => {
    // An empty table reads as "nobody filed anything", which is the opposite of
    // what a failed request means.
    vi.mocked(fetchSheets).mockRejectedValue(new Error("Session expired"));
    render(<SheetsView />);
    await screen.findByText(/session expired/i);
  });
});
