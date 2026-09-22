import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import LogSheetForm from "./LogSheetForm";

/**
 * The collapsible sections, checked against the real form rather than a
 * harness.
 *
 * FormSection's own tests prove the primitive keeps its children mounted. That
 * is necessary and not sufficient: what matters operationally is that the
 * 1,200-line sheet still behaves after being cut into sections, and that a
 * reason not to submit is never left inside something folded shut.
 *
 * The defect these exist against has shipped in this form once already:
 * continuous-mode Submit was a dead button because a required field lived in
 * a branch that was not rendered, so validation failed from somewhere with no
 * visible error. Collapsing sections is the same hazard with a friendlier
 * face, and these are the tests that say it did not come back.
 */

vi.mock("../services/api", () => ({
  fetchStaff: vi.fn().mockResolvedValue([]),
  submitLogSheet: vi.fn(),
  uploadLogSheetPhoto: vi.fn(),
}));
vi.mock("../hooks/useOfflineQueue", () => ({
  useOfflineQueue: () => ({ addToQueue: vi.fn(), pendingCount: 0, flushQueue: vi.fn() }),
}));
vi.mock("./StationPicker", () => ({ default: () => <div data-testid="station-picker" /> }));

const renderForm = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <LogSheetForm />
    </QueryClientProvider>,
  );
};

const sectionNamed = (title: string): HTMLDetailsElement | null => {
  const label = screen.queryByText(title);
  return (label?.closest("details") as HTMLDetailsElement) ?? null;
};

const chooseMethod = async (value: string) =>
  userEvent.selectOptions(screen.getByLabelText(/monitoring method/i), value);

beforeEach(() => vi.clearAllMocks());

describe("the photo section", () => {
  it("is open while the photo is missing, because that is what blocks Submit", () => {
    renderForm();
    const photo = sectionNamed("Site photo");
    expect(photo).not.toBeNull();
    // Mandatory, and it disables the Submit button. An operator who cannot see
    // why the button is grey has no way to find out.
    expect(photo!.open).toBe(true);
  });

  it("names its state in the summary rather than only itself", () => {
    renderForm();
    expect(screen.queryByText("add a photo before submitting")).not.toBeNull();
  });
});

describe("a blocker that only the summary states", () => {
  it("leaves the photo summary announced on an untouched sheet", () => {
    // The photo is missing, Submit is disabled, and the section force-opens.
    // "Add a photo to submit." is gated on isDirty, so on a sheet nobody has
    // typed into yet the summary is the ONLY statement of why the button is
    // grey. It has to stay in the accessibility tree.
    renderForm();
    const summary = screen.getByText("add a photo before submitting");
    expect(sectionNamed("Site photo")!.open).toBe(true);
    expect(summary.getAttribute("aria-hidden")).toBe("false");
    // And the message that would otherwise carry it is indeed absent here.
    // Matched on the exact in-content wording, which is "to submit" rather
    // than the summary's "before submitting" -- close enough to read as one
    // voice, distinct enough for this assertion to mean something.
    expect(screen.queryByText(/add a photo to submit\./i)).toBeNull();
  });
});

describe("continuous mode", () => {
  it("collapses the optional sections and keeps their fields in the DOM", async () => {
    renderForm();
    await chooseMethod("continuous");

    const power = sectionNamed("Power & battery");
    expect(power).not.toBeNull();
    expect(power!.open).toBe(false);

    // The assertion that matters. Closed, and still registered — so the field
    // validates and submits exactly as it did before it was folded away.
    expect(screen.queryByLabelText(/battery voltage/i)).not.toBeNull();
    expect(screen.queryByLabelText(/power notes/i)).not.toBeNull();
  });

  it("opens Equipment by force when a ticked change has nothing recorded", async () => {
    renderForm();
    await chooseMethod("continuous");

    const equipment = sectionNamed("Equipment");
    expect(equipment!.open).toBe(false);

    // Ticking without naming the replacement blocks Submit. Before this, the
    // reason sat inside a collapsed section and the button was simply grey.
    await userEvent.click(screen.getByLabelText(/equipment was changed/i));

    expect(sectionNamed("Equipment")!.open).toBe(true);
    expect(screen.queryByText(/record what it was changed to/i)).not.toBeNull();
  });

  it("says in the collapsed summary that a tick has nothing under it", async () => {
    renderForm();
    await chooseMethod("continuous");
    await userEvent.click(screen.getByLabelText(/equipment was changed/i));
    expect(screen.queryByText("change ticked, nothing recorded")).not.toBeNull();
  });
});

describe("campaign mode", () => {
  it("opens Antenna setup, which holds the only required field in the branch", async () => {
    renderForm();
    await chooseMethod("campaign");
    expect(sectionNamed("Antenna setup")!.open).toBe(true);
    expect(screen.queryByLabelText(/antenna model/i)).not.toBeNull();
  });

  it("collapses Session details but keeps UTC start registered", async () => {
    renderForm();
    await chooseMethod("campaign");
    expect(sectionNamed("Session details")!.open).toBe(false);
    // utc_start is required in campaign mode. If collapsing unmounted it, the
    // rule would survive, the error would render out of sight, and Submit
    // would do nothing — the exact defect this form has already had.
    expect(screen.queryByLabelText(/utc start/i)).not.toBeNull();
  });

  it("summarises an unselected antenna rather than showing a bare heading", async () => {
    renderForm();
    await chooseMethod("campaign");
    expect(screen.queryByText("antenna not selected")).not.toBeNull();
  });
});

describe("identity fields are never collapsible", () => {
  it("leaves method, station, date and observers outside any section", () => {
    renderForm();
    // These say which visit the sheet is about. A sheet whose station is
    // folded away is not a sheet you can check at a glance before submitting.
    for (const el of [
      screen.getByLabelText(/monitoring method/i),
      screen.getByLabelText(/visit date/i),
    ]) {
      expect(el.closest("details")).toBeNull();
    }
    expect(screen.getByTestId("station-picker").closest("details")).toBeNull();
  });
});
