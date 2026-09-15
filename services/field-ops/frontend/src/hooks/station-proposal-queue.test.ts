import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { openDB } from "idb";

/**
 * Sites created at a monument, between the handset and the server.
 *
 * Three behaviours here are load-bearing and none of them are obvious:
 *
 *   1. A proposal is ALWAYS queued, never posted directly, so there is one
 *      code path rather than an online one that works and an offline one that
 *      is exercised least and matters most.
 *   2. Proposals flush BEFORE sheets, so a sheet's station exists by the time
 *      anyone reads the sheet.
 *   3. A 409 is not a retryable error. It means the code was taken while this
 *      device was offline — the endpoint's own docstring says two teams can
 *      both propose the same code and both will sync. Retrying never resolves
 *      it; dropping it destroys the record of a real site someone visited. It
 *      is kept and marked.
 *
 * The API is mocked. This is about the store and the ordering, not the wire.
 */

const submitLogSheets = vi.fn();
const uploadLogSheetPhoto = vi.fn();
const proposeStation = vi.fn();
/** Every API call in order, so "proposals before sheets" is assertable. */
const callOrder: string[] = [];

class FakeApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
  get isPermanent() {
    return this.status >= 400 && this.status < 500 && ![401, 408, 429].includes(this.status);
  }
}

vi.mock("../services/api", () => ({
  submitLogSheets: (...a: unknown[]) => {
    callOrder.push("sheets");
    return submitLogSheets(...a);
  },
  uploadLogSheetPhoto: (...a: unknown[]) => uploadLogSheetPhoto(...a),
  proposeStation: (...a: unknown[]) => {
    callOrder.push("proposal");
    return proposeStation(...a);
  },
  ApiError: FakeApiError,
}));

const { addToQueue, addProposal, flushQueue, flushProposals, getProposals } =
  await import("./useOfflineQueue");

async function wipe() {
  const db = await openDB("field-ops");
  for (const name of Array.from(db.objectStoreNames)) {
    const tx = db.transaction(name, "readwrite");
    await tx.objectStore(name).clear();
    await tx.done;
  }
  db.close();
}

const proposal = (over: Record<string, unknown> = {}) => ({
  client_uuid: "site-uuid-1",
  station_code: "NEWA",
  name: "New Site A",
  latitude: 14.65,
  longitude: 121.05,
  monitoring_method: "campaign",
  ...over,
});

beforeEach(async () => {
  submitLogSheets.mockReset();
  uploadLogSheetPhoto.mockReset();
  proposeStation.mockReset();
  callOrder.length = 0;
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
  await addProposal(proposal({ client_uuid: "warmup" })); // ensures the DB exists
  await wipe();
});

afterEach(() => vi.restoreAllMocks());

describe("a site is queued, never posted directly", () => {
  it("stores it locally without touching the network", async () => {
    await addProposal(proposal());
    // The whole point: the record exists the moment the observer taps save,
    // whether or not there is a signal to send it over.
    expect(proposeStation).not.toHaveBeenCalled();
    const rows = await getProposals();
    expect(rows).toHaveLength(1);
    expect(rows[0]._status).toBe("pending");
    expect(rows[0].station_code).toBe("NEWA");
  });

  it("keeps the client_uuid it was minted with", async () => {
    // The server's idempotency key. A re-sent proposal must be recognisable as
    // the same proposal, or the inventory grows a site every time signal drops.
    await addProposal(proposal({ client_uuid: "minted-at-the-monument" }));
    proposeStation.mockResolvedValue({ id: 1 });
    await flushProposals();
    expect(proposeStation).toHaveBeenCalledWith(
      expect.objectContaining({ client_uuid: "minted-at-the-monument" }),
    );
  });

  it("does not send local bookkeeping fields to the server", async () => {
    await addProposal(proposal());
    proposeStation.mockResolvedValue({ id: 1 });
    await flushProposals();
    const sent = proposeStation.mock.calls[0][0] as Record<string, unknown>;
    expect(Object.keys(sent).filter((k) => k.startsWith("_"))).toEqual([]);
  });
});

describe("sites flush before sheets", () => {
  it("proposes the station before submitting the sheet that names it", async () => {
    await addProposal(proposal());
    await addToQueue({
      client_uuid: "sheet-1",
      station_code: "NEWA",
      visit_date: "2026-09-15",
      monitoring_method: "campaign",
    } as never);
    proposeStation.mockResolvedValue({ id: 1 });
    submitLogSheets.mockResolvedValue([{ client_uuid: "sheet-1", id: 9 }]);

    await flushQueue();

    // Not required for the sheet to land -- station_code is a loose TEXT
    // reference with no foreign key -- but it means the station exists by the
    // time someone opens the sheet.
    expect(callOrder).toEqual(["proposal", "sheets"]);
  });

  it("still sends the sheets when the site is refused", async () => {
    await addProposal(proposal());
    await addToQueue({
      client_uuid: "sheet-1",
      station_code: "NEWA",
      visit_date: "2026-09-15",
      monitoring_method: "campaign",
    } as never);
    proposeStation.mockRejectedValue(new FakeApiError(409, "already proposed"));
    submitLogSheets.mockResolvedValue([{ client_uuid: "sheet-1", id: 9 }]);

    await flushQueue();

    // A day's fieldwork must not be held hostage to a station code someone
    // else also claimed.
    expect(submitLogSheets).toHaveBeenCalledTimes(1);
  });
});

describe("a 409 is a conflict, not a retry", () => {
  it("marks the proposal and keeps it", async () => {
    await addProposal(proposal());
    proposeStation.mockRejectedValue(
      new FakeApiError(409, "Station code NEWA has already been proposed."),
    );

    const result = await flushProposals();

    expect(result).toEqual({ synced: 0, conflicts: 1 });
    const rows = await getProposals();
    // Kept, not dropped: it records that someone stood at a real site.
    expect(rows).toHaveLength(1);
    expect(rows[0]._status).toBe("conflict");
    expect(rows[0]._error).toMatch(/already been proposed/);
  });

  it("does not try a conflicted proposal again", async () => {
    await addProposal(proposal());
    proposeStation.mockRejectedValue(new FakeApiError(409, "taken"));
    await flushProposals();
    proposeStation.mockClear();

    await flushProposals();

    // Retrying would fail identically forever. Only a human can resolve it.
    expect(proposeStation).not.toHaveBeenCalled();
  });
});

describe("a transient failure leaves the site queued", () => {
  it("keeps it pending and stops the batch", async () => {
    await addProposal(proposal({ client_uuid: "a", station_code: "AAAA" }));
    await addProposal(proposal({ client_uuid: "b", station_code: "BBBB" }));
    proposeStation.mockRejectedValue(new FakeApiError(503, "gateway"));

    const result = await flushProposals();

    expect(result).toEqual({ synced: 0, conflicts: 0 });
    const rows = await getProposals();
    expect(rows.every((r) => r._status === "pending")).toBe(true);
    // Stopped after the first: hammering a dead link costs battery at a site
    // that has none to spare.
    expect(proposeStation).toHaveBeenCalledTimes(1);
  });

  it("sends it on the next flush once the link is back", async () => {
    await addProposal(proposal());
    proposeStation.mockRejectedValueOnce(new FakeApiError(503, "gateway"));
    await flushProposals();

    proposeStation.mockResolvedValue({ id: 1 });
    const result = await flushProposals();

    expect(result).toEqual({ synced: 1, conflicts: 0 });
    expect((await getProposals())[0]._status).toBe("synced");
  });
});

describe("a synced site is not sent twice", () => {
  it("skips proposals already accepted", async () => {
    await addProposal(proposal());
    proposeStation.mockResolvedValue({ id: 1 });
    await flushProposals();
    proposeStation.mockClear();

    await flushProposals();

    expect(proposeStation).not.toHaveBeenCalled();
  });
});
