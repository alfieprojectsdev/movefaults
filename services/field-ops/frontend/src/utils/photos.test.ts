import { describe, it, expect } from "vitest";
import {
  MAX_PHOTO_BYTES,
  WARN_TOTAL_BYTES,
  checkPhotos,
  formatBytes,
} from "./photos";

/**
 * The failure these guard against is not "the upload 413s" — the API handles
 * that. It is that offline, the upload happens after the observer has left the
 * site, and `runFlush` treats a rejected photo as transient: the record stays
 * pending and retries forever, never reaching "synced", with nothing on screen
 * saying why.
 */

// Size cannot be set through the File constructor without actually allocating
// the bytes, and allocating 15 MB per case makes the suite slow for no gain.
const file = (name: string, bytes: number): File =>
  Object.defineProperty(
    new File([new Uint8Array(1)], name, { type: "image/jpeg" }),
    "size",
    { value: bytes }
  );

const MB = 1024 * 1024;

describe("the server contract", () => {
  it("matches routers/logsheets.py MAX_PHOTO_BYTES", () => {
    // If the server's limit moves and this does not, the client will accept a
    // photo that can never upload — the exact failure this module prevents.
    expect(MAX_PHOTO_BYTES).toBe(15 * 1024 * 1024);
  });
});

describe("checkPhotos", () => {
  it("accepts an ordinary phone batch", () => {
    const r = checkPhotos([file("a.jpg", 3 * MB), file("b.jpg", 4 * MB)]);
    expect(r.ok).toBe(true);
    expect(r.oversized).toEqual([]);
    expect(r.totalBytes).toBe(7 * MB);
    expect(r.warnTotal).toBe(false);
  });

  it("rejects a file over the limit and names it", () => {
    const big = file("huge.jpg", 16 * MB);
    const r = checkPhotos([file("ok.jpg", 2 * MB), big]);
    expect(r.ok).toBe(false);
    expect(r.oversized).toEqual([big]);
  });

  it("accepts a file exactly at the limit", () => {
    // The server refuses past the limit, not at it — an off-by-one here would
    // block a photo the API would have taken.
    const r = checkPhotos([file("edge.jpg", MAX_PHOTO_BYTES)]);
    expect(r.ok).toBe(true);
  });

  it("rejects one byte over", () => {
    const r = checkPhotos([file("edge.jpg", MAX_PHOTO_BYTES + 1)]);
    expect(r.ok).toBe(false);
  });

  it("reports every oversized file, not just the first", () => {
    const r = checkPhotos([
      file("a.jpg", 20 * MB),
      file("b.jpg", 2 * MB),
      file("c.jpg", 18 * MB),
    ]);
    expect(r.oversized.map((f) => f.name)).toEqual(["a.jpg", "c.jpg"]);
  });

  it("warns on a large total without blocking it", () => {
    // Six 8 MB frames: each is legal, the batch is heavy. The observer should
    // see it before syncing over a field connection, but must not be stopped —
    // a photo is mandatory and this is a real station visit.
    const r = checkPhotos(Array.from({ length: 6 }, (_, i) => file(`${i}.jpg`, 8 * MB)));
    expect(r.totalBytes).toBe(48 * MB);
    expect(r.warnTotal).toBe(true);
    expect(r.ok).toBe(true);
  });

  it("does not warn just under the threshold", () => {
    expect(checkPhotos([file("a.jpg", WARN_TOTAL_BYTES)]).warnTotal).toBe(false);
  });

  it("treats no selection as fine, not as an error", () => {
    // "No photo yet" is enforced elsewhere. Reporting a size problem for an
    // empty selection would show an error to someone who has not chosen one.
    for (const empty of [null, undefined, [] as File[]]) {
      const r = checkPhotos(empty);
      expect(r.ok).toBe(true);
      expect(r.totalBytes).toBe(0);
      expect(r.oversized).toEqual([]);
    }
  });
});

describe("formatBytes", () => {
  it("uses units a person reads off a phone", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2 KB");
    expect(formatBytes(3.5 * MB)).toBe("3.5 MB");
    expect(formatBytes(48 * MB)).toBe("48 MB");
  });

  it("keeps one decimal only below 10 MB, where it carries information", () => {
    expect(formatBytes(9.4 * MB)).toBe("9.4 MB");
    expect(formatBytes(12.4 * MB)).toBe("12 MB");
  });

  it("handles a gigabyte without printing four digits of MB", () => {
    expect(formatBytes(2 * 1024 * MB)).toBe("2.0 GB");
  });
});
