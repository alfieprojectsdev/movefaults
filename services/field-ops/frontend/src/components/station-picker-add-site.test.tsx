import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import StationPicker from "./StationPicker";
import type { Station } from "../services/api";
import type { LocationState } from "../hooks/useDeviceLocation";

/**
 * The promise the whole feature rests on: create a site at the monument and
 * file a sheet against it, now, with no signal.
 *
 * The queue tests prove the record survives and syncs. These prove the other
 * half — that the observer can actually pick the site they just created. A
 * proposal that is stored but unselectable is the same dead end #219 is about,
 * moved along by one step.
 */

const stationsResult = vi.fn();
const proposalsResult = vi.fn();
const addProposal = vi.fn().mockResolvedValue(undefined);

vi.mock("../hooks/useStations", () => ({ useStations: () => stationsResult() }));
vi.mock("../hooks/useOnline", () => ({ useOnline: () => false }));
const retryProposal = vi.fn();
vi.mock("../hooks/useOfflineQueue", () => ({
  useProposals: () => ({ proposals: proposalsResult(), addProposal, retryProposal }),
}));
vi.mock("../hooks/useDeviceLocation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../hooks/useDeviceLocation")>();
  return {
    ...actual,
    useDeviceLocation: () =>
      ({ status: "denied" }) as LocationState,
  };
});

const station = (code: string): Station => ({
  station_code: code,
  name: `${code} site`,
  latitude: 14.6,
  longitude: 121.0,
  elevation: null,
  fault_segment: null,
  status: "active",
});

beforeEach(() => {
  vi.clearAllMocks();
  addProposal.mockResolvedValue(undefined);
  stationsResult.mockReturnValue({
    data: [station("PBIS"), station("PPPC")],
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    isFetching: false,
  });
  proposalsResult.mockReturnValue([]);
});

describe("the way in", () => {
  it("offers to add a site that is not listed", () => {
    render(<StationPicker value="" onChange={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /not listed/i })).not.toBeNull();
  });

  it("offers it while offline, which is when it is needed", () => {
    // useOnline is mocked false for this whole file. An observer at an
    // uncatalogued monument with no signal is the person this exists for.
    render(<StationPicker value="" onChange={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /not listed/i })).not.toBeNull();
  });
});

describe("creating a site selects it", () => {
  it("queues the proposal and hands the code back to the form", async () => {
    const onChange = vi.fn();
    render(<StationPicker value="" onChange={onChange} />);

    await userEvent.click(screen.getByRole("button", { name: /not listed/i }));
    await userEvent.type(screen.getByLabelText(/site code/i), "NEWA");
    await userEvent.click(screen.getByRole("button", { name: /save site/i }));

    expect(addProposal).toHaveBeenCalledWith(
      expect.objectContaining({ station_code: "NEWA" }),
    );
    // The half that makes it usable rather than merely stored.
    expect(onChange).toHaveBeenCalledWith("NEWA");
  });

  it("guards against a code already in the inventory", async () => {
    render(<StationPicker value="" onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /not listed/i }));
    await userEvent.type(screen.getByLabelText(/site code/i), "PBIS");
    expect(screen.getByRole("button", { name: /save site/i })).toBeDisabled();
  });
});

describe("a site created on this device is in the list", () => {
  it("appears as an option before the server has ever seen it", () => {
    proposalsResult.mockReturnValue([
      {
        client_uuid: "u1",
        station_code: "NEWA",
        name: "New Site A",
        monitoring_method: "campaign",
        _status: "pending",
      },
    ]);
    render(<StationPicker value="NEWA" onChange={vi.fn()} />);
    // Selectable, and the <select> keeps the value rather than silently
    // resetting it because the option was absent.
    expect(screen.queryByRole("option", { name: /NEWA/ })).not.toBeNull();
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("NEWA");
  });

  it("is not listed twice once the server returns it too", () => {
    stationsResult.mockReturnValue({
      data: [station("PBIS"), station("NEWA")],
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isFetching: false,
    });
    proposalsResult.mockReturnValue([
      { client_uuid: "u1", station_code: "NEWA", monitoring_method: "campaign", _status: "synced" },
    ]);
    render(<StationPicker value="" onChange={vi.fn()} />);
    expect(screen.getAllByRole("option", { name: /NEWA/ })).toHaveLength(1);
  });
});

describe("a refused site is reported where the observer can act on it", () => {
  /**
   * Two outcomes, two messages, and the difference is whether asking again
   * could ever help. Found by gps3 in review: both used to be "conflict",
   * which in this store means "someone else took this code" — so a 422 told
   * the observer to re-propose under a different code, which cannot work.
   */
  const refused = (over: Record<string, unknown>) => [
    {
      client_uuid: "u1",
      station_code: "NEWA",
      monitoring_method: "campaign",
      ...over,
    },
  ];

  it("says the code is taken, and offers no retry", () => {
    proposalsResult.mockReturnValue(
      refused({ _status: "conflict", _error: "Station code NEWA has already been proposed." }),
    );
    render(<StationPicker value="" onChange={vi.fn()} />);
    expect(screen.queryByText(/NEWA was not accepted/)).not.toBeNull();
    expect(screen.queryByText(/Choose a different code/)).not.toBeNull();
    // A button guaranteed not to work is worse than no button: the code stays
    // taken however many times the handset asks.
    expect(screen.queryByRole("button", { name: /try sending it again/i })).toBeNull();
  });

  it("says a quarantined site is NOT taken, and offers a retry", () => {
    proposalsResult.mockReturnValue(
      refused({ _status: "error", _error: "field required" }),
    );
    render(<StationPicker value="" onChange={vi.fn()} />);
    expect(screen.queryByText(/NEWA could not be sent/)).not.toBeNull();
    // The distinction that was missing. Telling this observer to pick another
    // code would put a wrong code in the record.
    expect(screen.queryByText(/The code is not taken/)).not.toBeNull();
    expect(screen.queryByRole("button", { name: /try sending it again/i })).not.toBeNull();
  });

  it("requeues a quarantined site when the retry is tapped", async () => {
    proposalsResult.mockReturnValue(refused({ _status: "error", _error: "field required" }));
    render(<StationPicker value="" onChange={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /try sending it again/i }));
    expect(retryProposal).toHaveBeenCalledWith("u1");
  });

  it("says the sheets are safe in both cases", () => {
    // They really are still queued -- station_code is a loose TEXT reference
    // with no foreign key -- so saying so is honest, not reassurance.
    for (const status of ["conflict", "error"]) {
      proposalsResult.mockReturnValue(refused({ _status: status, _error: "x" }));
      const { unmount } = render(<StationPicker value="" onChange={vi.fn()} />);
      expect(screen.queryByText(/sheets you filed against it are still saved/i)).not.toBeNull();
      unmount();
    }
  });
});
