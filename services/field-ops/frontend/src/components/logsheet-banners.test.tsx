import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LogSheetForm from "./LogSheetForm";
import { todayLocalISODate } from "../utils/times";

/**
 * These cover the pre-submit banners, which are about *when* a message is on
 * screen rather than what it says.
 *
 * The failure they lock out was found in the 2026-08-20 E2E run: a successful
 * offline save calls resetForm(), the form goes back to empty, and the two
 * empty-state banners came straight back up — so "Add a photo to submit" in
 * red sat directly above "Saved offline — including the photo". Red is what
 * the eye lands on, and the reading is that the sheet did not save. On a
 * mountain with no signal, that costs a re-visit.
 *
 * Testing the reset path end-to-end would mean driving a file input and an
 * IndexedDB write through jsdom. The gate itself is what matters and is what
 * these assert: isDirty, which reset() clears and setValue does not set.
 */

vi.mock("../services/api", () => ({
  fetchStaff: vi.fn().mockResolvedValue([]),
  submitLogSheet: vi.fn(),
  uploadLogSheetPhoto: vi.fn(),
}));

vi.mock("../hooks/useOfflineQueue", () => ({
  useOfflineQueue: () => ({ addToQueue: vi.fn(), pendingCount: 0, flushQueue: vi.fn() }),
}));

// StationPicker fetches its own list; the banners do not depend on it.
vi.mock("./StationPicker", () => ({ default: () => <div data-testid="station-picker" /> }));

const renderForm = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LogSheetForm />
    </QueryClientProvider>
  );
};

const photoPrompt = () => screen.queryByText(/add a photo to submit/i);

beforeEach(() => vi.clearAllMocks());

describe("the photo prompt", () => {
  it("is absent on an untouched form", () => {
    // Also the post-save state: resetForm() returns the form to exactly this.
    renderForm();
    expect(photoPrompt()).toBeNull();
  });

  it("appears once the operator has entered something", async () => {
    // The requirement is real and Submit is disabled until it is met, so once
    // a sheet is genuinely being filled the reason must be on screen — a
    // disabled button with no explanation is its own bug.
    const user = userEvent.setup();
    renderForm();
    await user.type(screen.getByLabelText(/notes/i), "clear sky");
    expect(photoPrompt()).not.toBeNull();
  });

  it("is not raised by the autofilled fields", () => {
    // visit_date, utc_start and session_id are written with setValue, which
    // does not mark the form dirty. If any of them ever switches to
    // shouldDirty, every new sheet opens under a red banner again.
    renderForm();
    expect(screen.getByLabelText(/visit date/i)).toHaveValue(todayLocalISODate());
    expect(photoPrompt()).toBeNull();
  });
});

describe("the deleted offline banner", () => {
  // jsdom reports navigator.onLine as true, so without this the offline branch
  // is never reached and the assertion below passes for the wrong reason — it
  // did exactly that on the first run of this file.
  const goOffline = () =>
    vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);

  it("never claims that text entries are saved locally, online or off", async () => {
    // It said so while nothing persisted the form before submit — no draft, no
    // localStorage. An operator who closed the app on that promise lost the
    // sheet. App.tsx carries the accurate offline banner, driven by useOnline.
    goOffline();
    const user = userEvent.setup();
    renderForm();
    expect(navigator.onLine).toBe(false); // the branch is actually reachable
    expect(screen.queryByText(/saved locally/i)).toBeNull();
    await user.type(screen.getByLabelText(/notes/i), "x");
    expect(screen.queryByText(/saved locally/i)).toBeNull();
  });
});
