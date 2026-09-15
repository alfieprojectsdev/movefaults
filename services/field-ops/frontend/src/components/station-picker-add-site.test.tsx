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
vi.mock("../hooks/useOfflineQueue", () => ({
  useProposals: () => ({ proposals: proposalsResult(), addProposal }),
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
  it("says which code was rejected and that the sheets are safe", () => {
    proposalsResult.mockReturnValue([
      {
        client_uuid: "u1",
        station_code: "NEWA",
        monitoring_method: "campaign",
        _status: "conflict",
        _error: "Station code NEWA has already been proposed.",
      },
    ]);
    render(<StationPicker value="" onChange={vi.fn()} />);
    expect(screen.queryByText(/NEWA was not accepted/)).not.toBeNull();
    // The sheets really are still queued -- station_code is a loose TEXT
    // reference -- so saying so is honest, not reassurance.
    expect(screen.queryByText(/sheets you filed against it are still saved/i)).not.toBeNull();
  });
});
