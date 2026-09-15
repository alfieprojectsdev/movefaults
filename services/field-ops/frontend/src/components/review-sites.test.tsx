import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import ReviewSitesView from "./ReviewSitesView";
import { ApiError, type StationProposalOut } from "../services/api";

/**
 * Reviewing a site proposed from the field.
 *
 * The decision this screen supports is not "is the row well-formed". It is
 * *is there a monument there, and is this the right code for it* — and two
 * things carry that:
 *
 *   sheet_count, because rejecting a proposal with sheets against it orphans
 *   observations that were validly collected at something real. The endpoint's
 *   docstring says so; the screen has to say it at the moment of the decision,
 *   not in a tooltip.
 *
 *   notes, because that is where the field form writes the position accuracy —
 *   there is no column for it, and a coordinate from a 4 km cell fix looks
 *   identical to one from a 12 m GNSS fix.
 *
 * Also asserted: that reject is not presented as delete, that a reason is
 * required, and that a 409 reads as "someone else already did this" rather
 * than as a failure.
 */

vi.mock("../hooks/useOnline", () => ({ useOnline: () => true }));

const fetchProposals = vi.fn();
const promoteProposal = vi.fn();
const rejectProposal = vi.fn();

vi.mock("../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../services/api")>();
  return {
    ...actual,
    fetchProposals: (...a: unknown[]) => fetchProposals(...a),
    promoteProposal: (...a: unknown[]) => promoteProposal(...a),
    rejectProposal: (...a: unknown[]) => rejectProposal(...a),
  };
});

const proposal = (over: Partial<StationProposalOut> = {}): StationProposalOut => ({
  id: 1,
  client_uuid: "u1",
  station_code: "NEWA",
  name: "Bislig City Hall",
  latitude: 14.6537,
  longitude: 121.0584,
  elevation: null,
  monitoring_method: "campaign",
  status: "active",
  municipality: "Bislig",
  province: "Surigao del Sur",
  region: null,
  created_by: 3,
  created_at: "2026-09-14T02:00:00Z",
  proposed_at: "2026-09-13T22:10:00Z",
  reconciled_at: null,
  reconciled_by: null,
  reconciled_station_id: null,
  rejected_reason: null,
  notes: "Beside the flagpole. Fix accuracy ±12 m.",
  sheet_count: 0,
  ...over,
});

const renderView = () => {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ReviewSitesView />
    </QueryClientProvider>,
  );
};

beforeEach(() => {
  vi.clearAllMocks();
  fetchProposals.mockResolvedValue([proposal()]);
  promoteProposal.mockResolvedValue(proposal({ reconciled_at: "2026-09-15T01:00:00Z" }));
  rejectProposal.mockResolvedValue(proposal({ reconciled_at: "2026-09-15T01:00:00Z" }));
});

describe("what the reviewer is shown", () => {
  it("lists a pending proposal with its position", async () => {
    renderView();
    expect(await screen.findByText("NEWA")).toBeTruthy();
    expect(screen.queryByText("14.65370, 121.05840")).not.toBeNull();
  });

  it("shows the notes in full, because the fix accuracy lives there", async () => {
    // There is no column for accuracy. A coordinate from a 4 km cell fix and
    // one from a 12 m GNSS fix are identical in lat/lon.
    renderView();
    expect(await screen.findByText(/Fix accuracy ±12 m/)).toBeTruthy();
  });

  it("says when no position was recorded rather than showing nothing", async () => {
    fetchProposals.mockResolvedValue([proposal({ latitude: null, longitude: null })]);
    renderView();
    expect(await screen.findByText("No position recorded")).toBeTruthy();
  });

  it("says the queue is empty rather than rendering a bare heading", async () => {
    fetchProposals.mockResolvedValue([]);
    renderView();
    expect(await screen.findByText(/Nothing waiting/)).toBeTruthy();
  });
});

describe("the sheet count, which is what the decision turns on", () => {
  it("spells out the consequence beside the number", async () => {
    fetchProposals.mockResolvedValue([proposal({ sheet_count: 3 })]);
    renderView();
    // Not just "3". A figure in a row is not a decision aid.
    expect(await screen.findByText(/rejecting this orphans them/)).toBeTruthy();
  });

  it("warns again at the moment of rejection, naming the count", async () => {
    fetchProposals.mockResolvedValue([proposal({ sheet_count: 3 })]);
    renderView();
    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));
    expect(
      screen.queryByText(/3 sheets name NEWA/),
    ).not.toBeNull();
  });

  it("does not warn when nothing is filed against the code", async () => {
    renderView();
    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));
    expect(screen.queryByText(/orphans them/)).toBeNull();
    expect(screen.queryByText(/sheets name/)).toBeNull();
  });
});

describe("declining is not deleting, and the screen says so", () => {
  it("states that the row and the code are kept", async () => {
    renderView();
    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));
    // A reviewer who believes decline destroys the record will hesitate over
    // rows they should decline.
    expect(screen.queryByText(/row is kept, and the code is freed/)).not.toBeNull();
  });

  it("will not submit without a reason", async () => {
    renderView();
    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));
    expect(screen.getByRole("button", { name: /Decline NEWA/ })).toBeDisabled();
    expect(rejectProposal).not.toHaveBeenCalled();
  });

  it("sends the reason the reviewer typed", async () => {
    renderView();
    await userEvent.click(await screen.findByRole("button", { name: "Decline" }));
    await userEvent.type(screen.getByLabelText(/why is this being declined/i), "duplicate of PBIS");
    await userEvent.click(screen.getByRole("button", { name: /Decline NEWA/ }));
    await waitFor(() => expect(rejectProposal).toHaveBeenCalledWith(1, "duplicate of PBIS"));
  });
});

describe("promoting", () => {
  it("calls promote and confirms the site is in the inventory", async () => {
    renderView();
    await userEvent.click(await screen.findByRole("button", { name: /Add to inventory/ }));
    await waitFor(() => expect(promoteProposal).toHaveBeenCalledWith(1));
    expect(await screen.findByText(/NEWA is now in the inventory/)).toBeTruthy();
  });
});

describe("two people working one queue", () => {
  it("reads a 409 as already handled, not as a failure", async () => {
    // The endpoint answers 409 rather than 404 precisely so a second reviewer
    // hears "already handled" instead of "not found".
    promoteProposal.mockRejectedValue(new ApiError(409, "Proposal 1 was already reconciled."));
    renderView();
    await userEvent.click(await screen.findByRole("button", { name: /Add to inventory/ }));
    expect(await screen.findByText(/Someone else has already dealt with this one/)).toBeTruthy();
  });

  it("refetches the list after a 409 so the row stops inviting another attempt", async () => {
    promoteProposal.mockRejectedValue(new ApiError(409, "already reconciled"));
    renderView();
    await screen.findByText("NEWA");
    expect(fetchProposals).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: /Add to inventory/ }));
    await waitFor(() => expect(fetchProposals).toHaveBeenCalledTimes(2));
  });
});

describe("when the reviewer is not allowed", () => {
  it("names the role needed rather than showing an empty list", async () => {
    // The app offers this tab on an unanswered /me, so a field_staff account
    // with no role cached can land here. A blank screen would read as "no
    // proposals", which is a different and wrong fact.
    fetchProposals.mockRejectedValue(new ApiError(403, "Forbidden"));
    renderView();
    expect(
      await screen.findByText(/needs the admin or data-processor role/),
    ).toBeTruthy();
  });
});
