import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { openDB } from "idb";

/**
 * The offline queue, against a real (in-memory) IndexedDB.
 *
 * This is where a day's fieldwork lives between a monument with no signal and
 * the server. The assertions below are mostly about the two fixes that came
 * out of a handset: that a photo batch's upload progress is persisted without
 * rewriting the photos themselves, and that a record's identity survives a
 * retry so the server's ON CONFLICT (client_uuid) has something to match.
 *
 * The API module is mocked — this is about the store, not the network.
 *
 * One limit worth knowing before trusting a green run: fake-indexeddb clones
 * values with jsdom's structuredClone, which cannot clone a Blob. A File put
 * into the store comes back as an empty object. Everything here therefore
 * asserts record shape, ordering, write counts and status transitions — never
 * photo bytes. Byte fidelity is a browser concern and is checked there.
 */

const submitLogSheets = vi.fn();
const uploadLogSheetPhoto = vi.fn();

vi.mock("../services/api", () => ({
  submitLogSheets: (...a: unknown[]) => submitLogSheets(...a),
  uploadLogSheetPhoto: (...a: unknown[]) => uploadLogSheetPhoto(...a),
  ApiError: class ApiError extends Error {
    isPermanent = false;
  },
}));

// Imported after the mock is registered.
const { addToQueue, flushQueue, getQueue } = await import("./useOfflineQueue");

const DB_NAME = "field-ops";

async function rawDb() {
  // Opened without a version so it attaches to whatever the module created,
  // rather than racing it with an upgrade.
  return openDB(DB_NAME);
}

async function wipe() {
  const db = await rawDb();
  for (const name of Array.from(db.objectStoreNames)) {
    const tx = db.transaction(name, "readwrite");
    await tx.objectStore(name).clear();
    await tx.done;
  }
  db.close();
}

const record = (over: Record<string, unknown> = {}) => ({
  client_uuid: "uuid-1",
  station_code: "BLNA",
  visit_date: "2026-08-17",
  monitoring_method: "continuous",
  ...over,
});

const photo = (name: string, bytes = 16) =>
  new File([new Uint8Array(bytes)], name, { type: "image/jpeg" });

beforeEach(async () => {
  submitLogSheets.mockReset();
  uploadLogSheetPhoto.mockReset();
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(true);
  await addToQueue(record({ client_uuid: "warmup" })); // ensures the DB exists
  await wipe();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("addToQueue", () => {
  it("stores the record as pending, with its photos", async () => {
    await addToQueue(record(), [photo("a.jpg"), photo("b.jpg")]);

    const all = await getQueue();
    expect(all).toHaveLength(1);
    expect(all[0]._status).toBe("pending");
    expect(all[0]._photos).toHaveLength(2);
    expect(all[0]._photoNames).toEqual(["a.jpg", "b.jpg"]);
    expect(all[0]._photosUploaded).toBe(0);
  });

  it("keeps a slot and a name per photo, not just the text", async () => {
    // The data loss this store exists to prevent: the offline path used to
    // queue only the text while the UI reported a successful save.
    //
    // NOT COVERED HERE: that the bytes survive. fake-indexeddb's structured
    // clone runs on jsdom, which cannot clone a Blob — a stored File comes
    // back as an empty object. So this asserts the record's shape, which is
    // what the flush logic indexes into, and leaves byte fidelity to the
    // browser check. Do not read a passing suite as proof the photo is intact.
    await addToQueue(record(), [photo("site.jpg", 1024)]);
    const [queued] = await getQueue();
    expect(queued._photos).toHaveLength(1);
    expect(queued._photoNames).toEqual(["site.jpg"]);
  });

  it("records when it was queued, so the queue view can show age", async () => {
    await addToQueue(record());
    const [queued] = await getQueue();
    expect(Date.parse(queued._queuedAt!)).not.toBeNaN();
  });

  it("re-queuing the same client_uuid replaces rather than duplicates", async () => {
    // client_uuid is the key. A retry of one sheet must stay one sheet — this
    // is the local half of the guarantee ON CONFLICT (client_uuid) makes
    // server-side, and the reason the form now holds its uuid across attempts.
    await addToQueue(record({ notes: "first" }));
    await addToQueue(record({ notes: "second" }));

    const all = await getQueue();
    expect(all).toHaveLength(1);
    expect(all[0].notes).toBe("second");
  });
});

describe("flushQueue — photo batches", () => {
  it("uploads every photo and marks the record synced", async () => {
    await addToQueue(record(), [photo("a.jpg"), photo("b.jpg"), photo("c.jpg")]);
    submitLogSheets.mockResolvedValue([{ id: 7, client_uuid: "uuid-1" }]);
    uploadLogSheetPhoto.mockResolvedValue(undefined);

    const result = await flushQueue();

    expect(result.synced).toBe(1);
    expect(uploadLogSheetPhoto).toHaveBeenCalledTimes(3);
    const [rec] = await getQueue();
    expect(rec._status).toBe("synced");
  });

  it("drops the blobs on sync to reclaim device storage", async () => {
    await addToQueue(record(), [photo("a.jpg", 4096)]);
    submitLogSheets.mockResolvedValue([{ id: 7, client_uuid: "uuid-1" }]);
    uploadLogSheetPhoto.mockResolvedValue(undefined);

    await flushQueue();

    const [rec] = await getQueue();
    expect(rec._photos).toBeUndefined();
    // The count survives, so the queue can still say what happened.
    expect(rec._photosUploaded).toBe(1);
  });

  it("does not rewrite the photo blobs to record progress", async () => {
    // The fault this guards: `put(logsheet_queue, {...fresh, _photosUploaded})`
    // after each photo rewrote the whole record — blobs included — so six 3 MB
    // photos pushed ~108 MB through IndexedDB on a phone already low on memory.
    // Progress now lives in its own store, so the queue record is written once
    // (on sync), not once per photo.
    await addToQueue(record(), [photo("a.jpg"), photo("b.jpg"), photo("c.jpg")]);
    submitLogSheets.mockResolvedValue([{ id: 7, client_uuid: "uuid-1" }]);
    uploadLogSheetPhoto.mockResolvedValue(undefined);

    const db = await rawDb();
    const originalPut = IDBObjectStore.prototype.put;
    const queuePuts: unknown[] = [];
    const spy = vi
      .spyOn(IDBObjectStore.prototype, "put")
      .mockImplementation(function (
        this: IDBObjectStore,
        value: unknown,
        key?: IDBValidKey
      ) {
        if (this.name === "logsheet_queue") queuePuts.push(value);
        return originalPut.call(this, value, key);
      });

    await flushQueue();
    spy.mockRestore();
    db.close();

    // One write, the terminal one. Before the fix this was four: three
    // progress rewrites plus the final one.
    expect(queuePuts).toHaveLength(1);
    expect((queuePuts[0] as { _status: string })._status).toBe("synced");
  });

  it("resumes at the photo it stopped on rather than re-sending the batch", async () => {
    await addToQueue(record(), [photo("a.jpg"), photo("b.jpg"), photo("c.jpg")]);
    submitLogSheets.mockResolvedValue([{ id: 7, client_uuid: "uuid-1" }]);

    // Link drops after the second photo.
    uploadLogSheetPhoto
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce(undefined)
      .mockRejectedValueOnce(new Error("connection reset"));

    const first = await flushQueue();
    expect(first.synced).toBe(0);
    const [stalled] = await getQueue();
    expect(stalled._status).toBe("pending"); // photos outstanding, keep it

    // Signal returns.
    uploadLogSheetPhoto.mockReset();
    uploadLogSheetPhoto.mockResolvedValue(undefined);
    const second = await flushQueue();

    expect(second.synced).toBe(1);
    // Only the third photo — the two already delivered are not re-sent, which
    // is the expensive part on a field link.
    expect(uploadLogSheetPhoto).toHaveBeenCalledTimes(1);
    const sentName = (uploadLogSheetPhoto.mock.calls[0][1] as File).name;
    expect(sentName).toBe("c.jpg");
  });

  it("clears the progress row on sync so a later record cannot inherit it", async () => {
    // Now that a client_uuid is stable per sheet, a stale progress row would be
    // read by a later flush and skip photos that were never sent.
    await addToQueue(record(), [photo("a.jpg"), photo("b.jpg")]);
    submitLogSheets.mockResolvedValue([{ id: 7, client_uuid: "uuid-1" }]);
    uploadLogSheetPhoto.mockResolvedValue(undefined);
    await flushQueue();

    const db = await rawDb();
    const leftover = await db.get("photo_progress", "uuid-1");
    db.close();
    expect(leftover).toBeUndefined();
  });

  it("keeps a record pending when the server never returned its row", async () => {
    await addToQueue(record());
    submitLogSheets.mockResolvedValue([]); // nothing came back

    const result = await flushQueue();

    expect(result.synced).toBe(0);
    const [rec] = await getQueue();
    expect(rec._status).toBe("pending");
  });

  it("leaves everything pending when the network is down", async () => {
    await addToQueue(record());
    submitLogSheets.mockRejectedValue(new Error("Failed to fetch"));

    const result = await flushQueue();

    expect(result.error).toBeTruthy();
    expect(result.synced).toBe(0);
    const [rec] = await getQueue();
    expect(rec._status).toBe("pending");
  });
});

describe("flushQueue — concurrency", () => {
  it("joins an in-flight run instead of starting a second", async () => {
    // Three components mount this hook. Without single-flight, one reconnect
    // uploads every queued photo three times — and the photo endpoint has no
    // idempotency guard.
    await addToQueue(record(), [photo("a.jpg")]);
    submitLogSheets.mockResolvedValue([{ id: 7, client_uuid: "uuid-1" }]);
    uploadLogSheetPhoto.mockResolvedValue(undefined);

    await Promise.all([flushQueue(), flushQueue(), flushQueue()]);

    expect(submitLogSheets).toHaveBeenCalledTimes(1);
    expect(uploadLogSheetPhoto).toHaveBeenCalledTimes(1);
  });
});
