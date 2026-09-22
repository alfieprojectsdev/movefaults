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
const fetchProposalStatus = vi.fn();
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
  fetchProposalStatus: (...a: unknown[]) => {
    callOrder.push("status");
    return fetchProposalStatus(...a);
  },
  ApiError: FakeApiError,
}));

const mod = await import("./useOfflineQueue");
const { addToQueue, addProposal, flushQueue, flushProposals, getProposals } = mod;

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
  fetchProposalStatus.mockReset();
  // Default: the server has decided nothing yet. A test that needs a verdict
  // says so; one that does not is not silently handed one.
  fetchProposalStatus.mockResolvedValue([]);
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

  it("a refused site does not hold back sheets for OTHER stations", async () => {
    /**
     * This test used to assert the opposite of what it asserts now, and it was
     * wrong. It read:
     *
     *   it("still sends the sheets when the site is refused")
     *     expect(submitLogSheets).toHaveBeenCalledTimes(1)
     *     // A day's fieldwork must not be held hostage to a station code
     *     // someone else also claimed.
     *
     * The principle is right and I applied it to the wrong sheets. A refused
     * code means the code belongs to something else, so a sheet naming it is
     * not held hostage by being kept — it is prevented from being filed
     * against a station the observer never visited. Sending was the harmful
     * direction, not the safe one.
     *
     * What the principle actually protects is the rest of the day: sheets for
     * stations that have nothing to do with the refused code must still go.
     * That is what this asserts now.
     */
    await addProposal(proposal({ station_code: "NEWA" }));
    await addToQueue({
      client_uuid: "sheet-newa",
      station_code: "NEWA",
      visit_date: "2026-09-15",
      monitoring_method: "campaign",
    } as never);
    await addToQueue({
      client_uuid: "sheet-other",
      station_code: "PPPC",
      visit_date: "2026-09-15",
      monitoring_method: "continuous",
    } as never);
    proposeStation.mockRejectedValue(new FakeApiError(409, "already proposed"));
    submitLogSheets.mockResolvedValue([{ client_uuid: "sheet-other", id: 9 }]);

    await flushQueue();

    expect(submitLogSheets).toHaveBeenCalledTimes(1);
    const sent = submitLogSheets.mock.calls[0][0] as Array<{ station_code: string }>;
    expect(sent.map((r) => r.station_code)).toEqual(["PPPC"]);
  });
});

describe("a 409 is a conflict, not a retry", () => {
  it("marks the proposal and keeps it", async () => {
    await addProposal(proposal());
    proposeStation.mockRejectedValue(
      new FakeApiError(409, "Station code NEWA has already been proposed."),
    );

    const result = await flushProposals();

    expect(result).toEqual({ synced: 0, conflicts: 1, quarantined: 0 });
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

describe("a sheet is never filed against a code the server refused", () => {
  /**
   * The defect: `station_code` has no foreign key and nothing in the queue
   * looked at it, so a 409 on the site did not stop the sheets naming it. They
   * were submitted in the same flush, seconds after the refusal.
   *
   * If the code was refused because it already exists in the central
   * inventory, the code names a real station somewhere else — and the
   * observer's day has just been filed against it. That is worse than losing
   * the record: a lost record gets noticed, a wrong record attached to a real
   * station is read as data.
   */

  it("does NOT send a sheet whose site was refused 409", async () => {
    const { addProposal, addToQueue, flushQueue } = mod;
    await addProposal(proposal({ station_code: "NEWA" }));
    await addToQueue({
      client_uuid: "sheet-1",
      station_code: "NEWA",
      visit_date: "2026-09-16",
      monitoring_method: "campaign",
    } as never);

    proposeStation.mockRejectedValue(
      new FakeApiError(409, "Station code NEWA already exists in the central inventory."),
    );
    submitLogSheets.mockResolvedValue([]);

    await flushQueue();

    // Before this guard: submitLogSheets was called with station_code NEWA.
    expect(submitLogSheets).not.toHaveBeenCalled();
  });

  it("keeps the sheet and says the code is what is wrong", async () => {
    const { addProposal, addToQueue, flushQueue, getQueue } = mod;
    await addProposal(proposal({ station_code: "NEWA" }));
    await addToQueue({
      client_uuid: "sheet-1", station_code: "NEWA",
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);
    proposeStation.mockRejectedValue(new FakeApiError(409, "already exists"));

    await flushQueue();

    const [sheet] = await getQueue();
    // Kept, not dropped — the observation is real.
    expect(sheet._status).toBe("error");
    expect(sheet._error).toMatch(/already belongs to a different station/);
    expect(sheet._error).toMatch(/NOT sent/);
  });

  it("still sends sheets for stations that were in the inventory all along", async () => {
    // The common path: 138 existing stations, no local proposal at all.
    const { addProposal, addToQueue, flushQueue } = mod;
    await addProposal(proposal({ station_code: "NEWA" }));
    await addToQueue({
      client_uuid: "s-newa", station_code: "NEWA",
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);
    await addToQueue({
      client_uuid: "s-pbis", station_code: "PBIS",
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);
    proposeStation.mockRejectedValue(new FakeApiError(409, "already exists"));
    submitLogSheets.mockResolvedValue([{ client_uuid: "s-pbis", id: 4 }]);

    await flushQueue();

    const sent = submitLogSheets.mock.calls[0][0] as Array<{ station_code: string }>;
    expect(sent.map((r) => r.station_code)).toEqual(["PBIS"]);
  });

  it("defers rather than errors when the site has not been adjudicated yet", async () => {
    // Transient failure on the proposal: nobody has refused the code, it just
    // has not landed. Delay of minutes on a queue built to survive days.
    const { addProposal, addToQueue, flushQueue, getQueue } = mod;
    await addProposal(proposal({ station_code: "NEWA" }));
    await addToQueue({
      client_uuid: "sheet-1", station_code: "NEWA",
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);
    proposeStation.mockRejectedValue(new FakeApiError(503, "gateway"));

    await flushQueue();

    expect(submitLogSheets).not.toHaveBeenCalled();
    const [sheet] = await getQueue();
    expect(sheet._status).toBe("pending");   // NOT error — nothing is wrong yet
    expect(sheet._error).toBeUndefined();
  });

  it("sends the deferred sheet once its site is accepted", async () => {
    const { addProposal, addToQueue, flushQueue } = mod;
    await addProposal(proposal({ station_code: "NEWA" }));
    await addToQueue({
      client_uuid: "sheet-1", station_code: "NEWA",
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);

    proposeStation.mockRejectedValueOnce(new FakeApiError(503, "gateway"));
    await flushQueue();
    expect(submitLogSheets).not.toHaveBeenCalled();

    proposeStation.mockResolvedValue({ id: 1 });
    submitLogSheets.mockResolvedValue([{ client_uuid: "sheet-1", id: 9 }]);
    await flushQueue();

    const sent = submitLogSheets.mock.calls[0][0] as Array<{ station_code: string }>;
    expect(sent[0].station_code).toBe("NEWA");
  });

  it("holds the sheets when the site was ACCEPTED but its code is contested", async () => {
    /**
     * #228. The dangerous case, because it arrives dressed as success.
     *
     * The server no longer refuses a taken code — it stores the proposal and
     * marks `collides_with`, so the office sees both claims. The proposal is
     * therefore `synced`: no error, nothing to retry. But the code may still
     * mean a catalogued station or the other team's monument, so a sheet sent
     * under it now lands on somebody else's station — the same misfiling the
     * 409 branch exists to prevent, reached through a status that reads fine.
     */
    const { addProposal, addToQueue, flushQueue, getProposals, getQueue } = mod;
    await addProposal(proposal({ station_code: "NEWA" }));
    await addToQueue({
      client_uuid: "sheet-1", station_code: "NEWA",
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);

    proposeStation.mockResolvedValue({ id: 1, collides_with: "inventory" });

    await flushQueue();

    expect(proposeStation).toHaveBeenCalled();
    expect(submitLogSheets).not.toHaveBeenCalled();

    const [site] = await getProposals();
    expect(site._status).toBe("synced");        // it DID reach the server
    expect(site._collidesWith).toBe("inventory");

    const [sheet] = await getQueue();
    expect(sheet._status).toBe("pending");      // held, not failed
    expect(sheet._error).toBeUndefined();
  });

  it("sends the sheets when the accepted site's code was free", async () => {
    /**
     * The anchor for the test above: without this, marking every synced
     * proposal as contested would pass it, and the common path — a new site
     * at an uncatalogued monument — would silently stop sending.
     */
    const { addProposal, addToQueue, flushQueue } = mod;
    await addProposal(proposal({ station_code: "NEWB" }));
    await addToQueue({
      client_uuid: "sheet-1", station_code: "NEWB",
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);

    proposeStation.mockResolvedValue({ id: 1, collides_with: null });
    submitLogSheets.mockResolvedValue([{ client_uuid: "sheet-1", id: 9 }]);

    await flushQueue();

    const sent = submitLogSheets.mock.calls[0][0] as Array<{ station_code: string }>;
    expect(sent[0].station_code).toBe("NEWB");
  });

  it("matches the code case-insensitively, as the server normalises it", async () => {
    const { addProposal, addToQueue, flushQueue } = mod;
    await addProposal(proposal({ station_code: "NEWA" }));
    await addToQueue({
      client_uuid: "sheet-1", station_code: "newa",
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);
    proposeStation.mockRejectedValue(new FakeApiError(409, "already exists"));

    await flushQueue();

    expect(submitLogSheets).not.toHaveBeenCalled();
  });
});

describe("a refusal that is about this client, not about the code", () => {
  // Found by gps3 in review: flushProposals keyed on isPermanent, which is
  // also true for 400, 403, 404 and 422, so all of them became "conflict" — a
  // word that in this store means "someone else took this code". A 422 then
  // told the observer to re-propose under a different code, which cannot work
  // and puts a wrong code in the record.
  //
  // It matters more than the arithmetic suggests: schema drift against a
  // handset days out of date makes EVERY queued proposal 422, and a misrouted
  // API base makes every one 404. Both would convert a recoverable
  // server-side condition into an unrecoverable client-side state, for the
  // whole queue at once.

  it("quarantines a 422 rather than calling the code taken", async () => {
    const { addProposal, flushProposals, getProposals } = mod;
    await addProposal(proposal());
    proposeStation.mockRejectedValue(new FakeApiError(422, "field required"));

    const result = await flushProposals();

    expect(result).toEqual({ synced: 0, conflicts: 0, quarantined: 1 });
    expect((await getProposals())[0]._status).toBe("error");
  });

  it("quarantines a 404, which a corrected API base would fix", async () => {
    const { addProposal, flushProposals, getProposals } = mod;
    await addProposal(proposal());
    proposeStation.mockRejectedValue(new FakeApiError(404, "Not Found"));

    await flushProposals();

    expect((await getProposals())[0]._status).toBe("error");
  });

  it("lets a quarantined site be sent again", async () => {
    const { addProposal, flushProposals, getProposals, retryProposal } = mod;
    await addProposal(proposal());
    proposeStation.mockRejectedValueOnce(new FakeApiError(422, "field required"));
    await flushProposals();
    expect((await getProposals())[0]._status).toBe("error");

    await retryProposal("site-uuid-1");
    expect((await getProposals())[0]._status).toBe("pending");

    proposeStation.mockResolvedValue({ id: 1 });
    expect(await flushProposals()).toEqual({ synced: 1, conflicts: 0, quarantined: 0 });
  });

  it("refuses to retry a conflict, because asking again cannot change it", async () => {
    // The code stays taken however many times the handset asks. Offering a
    // retry would be offering a button guaranteed not to work.
    const { addProposal, flushProposals, getProposals, retryProposal } = mod;
    await addProposal(proposal());
    proposeStation.mockRejectedValue(new FakeApiError(409, "taken"));
    await flushProposals();

    await retryProposal("site-uuid-1");

    expect((await getProposals())[0]._status).toBe("conflict");
  });
});

describe("a transient failure leaves the site queued", () => {
  it("keeps it pending and stops the batch", async () => {
    await addProposal(proposal({ client_uuid: "a", station_code: "AAAA" }));
    await addProposal(proposal({ client_uuid: "b", station_code: "BBBB" }));
    proposeStation.mockRejectedValue(new FakeApiError(503, "gateway"));

    const result = await flushProposals();

    expect(result).toEqual({ synced: 0, conflicts: 0, quarantined: 0 });
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

    expect(result).toEqual({ synced: 1, conflicts: 0, quarantined: 0 });
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


describe("a held sheet learns what the office decided", () => {
  /**
   * Since #228 a contested code is accepted and its sheets are held. These
   * cover the read-back that releases them — or explains why it never will.
   * Each test syncs a contested site first, then answers the status question.
   */
  const { addProposal, addToQueue, flushQueue, getProposals, getQueue } = mod;

  async function contestedSiteWithOneSheet(code = "NEWA") {
    await addProposal(proposal({ station_code: code }));
    await addToQueue({
      client_uuid: "sheet-1", station_code: code,
      visit_date: "2026-09-16", monitoring_method: "campaign",
    } as never);
    proposeStation.mockResolvedValue({ id: 1, collides_with: "proposal" });
    await flushQueue(); // syncs the site, holds the sheet
    expect(submitLogSheets).not.toHaveBeenCalled();
  }

  it("sends the sheets once the office promotes this claim", async () => {
    /**
     * Including a promotion onto a code the inventory already held
     * (merge_into_existing). Releasing then is right ONLY because a reviewer
     * compared both claims and decided they are one monument — the handset
     * cannot check that and does not try. It trusts the row.
     */
    await contestedSiteWithOneSheet();
    fetchProposalStatus.mockResolvedValue([
      { client_uuid: "site-uuid-1", reconciled_station_id: 88, rejected_reason: null },
    ]);
    submitLogSheets.mockResolvedValue([{ client_uuid: "sheet-1", id: 9 }]);

    await flushQueue();

    const sent = submitLogSheets.mock.calls[0][0] as Array<{ station_code: string }>;
    expect(sent[0].station_code).toBe("NEWA");
    const [site] = await getProposals();
    expect(site._collidesWith).toBeNull();
  });

  it("does not send, and says why in the office's words, when this claim is declined", async () => {
    await contestedSiteWithOneSheet();
    fetchProposalStatus.mockResolvedValue([
      {
        client_uuid: "site-uuid-1",
        reconciled_station_id: null,
        rejected_reason: "Same monument as PBIS; use that code",
      },
    ]);

    await flushQueue();

    expect(submitLogSheets).not.toHaveBeenCalled();
    const [site] = await getProposals();
    expect(site._status).toBe("conflict");
    const [sheet] = await getQueue();
    expect(sheet._status).toBe("error");
    // The reason is the one piece of guidance the observer has. The generic
    // "already belongs to a different station" sentence would throw it away.
    expect(sheet._error).toContain("Same monument as PBIS; use that code");
    expect(sheet._error).not.toContain("already belongs to a different station");
  });

  it("keeps holding, without an error, while the office has not decided", async () => {
    await contestedSiteWithOneSheet();
    fetchProposalStatus.mockResolvedValue([
      { client_uuid: "site-uuid-1", reconciled_station_id: null, rejected_reason: null },
    ]);

    await flushQueue();

    expect(submitLogSheets).not.toHaveBeenCalled();
    const [sheet] = await getQueue();
    expect(sheet._status).toBe("pending");
    expect(sheet._error).toBeUndefined();
  });

  it("keeps holding when the question cannot be asked", async () => {
    /** Offline or a struggling server. An unanswered question is not a
     * verdict, and defaulting either way would be a guess. */
    await contestedSiteWithOneSheet();
    fetchProposalStatus.mockRejectedValue(new FakeApiError(503, "gateway"));

    await flushQueue();

    expect(submitLogSheets).not.toHaveBeenCalled();
    const [sheet] = await getQueue();
    expect(sheet._status).toBe("pending");
  });

  it("asks only about contested sites, so a free code costs nothing", async () => {
    await addProposal(proposal({ station_code: "NEWB" }));
    proposeStation.mockResolvedValue({ id: 1, collides_with: null });

    await flushQueue();
    await flushQueue();

    expect(fetchProposalStatus).not.toHaveBeenCalled();
  });

  it("does not release on a verdict about a DIFFERENT proposal", async () => {
    /** One row decides, and only this handset's row. A promotion of some
     * other uuid — the rival claim, say — says nothing about this one. */
    await contestedSiteWithOneSheet();
    fetchProposalStatus.mockResolvedValue([
      { client_uuid: "someone-elses-uuid", reconciled_station_id: 88, rejected_reason: null },
    ]);

    await flushQueue();

    expect(submitLogSheets).not.toHaveBeenCalled();
  });
});
