import { describe, it, expect } from "vitest";
import { describePhotos } from "./QueueView";
import type { QueueRecord } from "../hooks/useOfflineQueue";

/**
 * What the queue tells an operator about their photos.
 *
 * This is the regression guard for a fault that shipped: the queue read only
 * the legacy `_photo` field, so every batch record — which is every new sheet
 * — displayed "no photo" while the images sat safely on the device. Wrong in
 * the direction that sends someone back to a monument.
 */

const base = (over: Partial<QueueRecord> = {}): QueueRecord =>
  ({
    client_uuid: "u1",
    station_code: "BLNA",
    visit_date: "2026-08-17",
    _status: "pending",
    ...over,
  }) as QueueRecord;

const blob = () => new Blob(["x"], { type: "image/jpeg" });

describe("describePhotos — batch records", () => {
  it("reports photos held on the device, not 'no photo'", () => {
    const rec = base({ _photos: [blob(), blob(), blob()], _photosUploaded: 0 });
    expect(describePhotos(rec)).toBe("3 photos held");
  });

  it("uses the singular for one held photo", () => {
    expect(describePhotos(base({ _photos: [blob()], _photosUploaded: 0 }))).toBe(
      "1 photo held"
    );
  });

  it("shows partial progress after an interrupted upload", () => {
    // The point of tracking a count rather than a flag: a batch can stop
    // halfway on a weak link, and the operator should see where it got to.
    const rec = base({ _photos: [blob(), blob(), blob()], _photosUploaded: 2 });
    expect(describePhotos(rec)).toBe("2 of 3 photos sent");
  });

  it("reports a fully uploaded batch as sent", () => {
    const rec = base({ _photos: [blob(), blob()], _photosUploaded: 2 });
    expect(describePhotos(rec)).toBe("2 photos sent");
  });

  it("still reports the count after the blobs are dropped on sync", () => {
    // A synced record has had `_photos` cleared to reclaim device storage;
    // `_photosUploaded` survives that write for exactly this reason.
    const rec = base({ _status: "synced", _photosUploaded: 4 });
    expect(describePhotos(rec)).toBe("4 photos sent");
  });
});

describe("describePhotos — legacy single-photo records", () => {
  it("reports a held photo", () => {
    expect(describePhotos(base({ _photo: blob() }))).toBe("photo held");
  });

  it("reports an uploaded photo", () => {
    expect(describePhotos(base({ _photo: blob(), _photoUploaded: true }))).toBe(
      "photo sent"
    );
  });

  it("reports a sent photo whose blob has since been dropped", () => {
    expect(describePhotos(base({ _photoUploaded: true }))).toBe("photo sent");
  });
});

describe("describePhotos — genuinely photoless records", () => {
  it("says so only when there is really no photo", () => {
    // Everything queued under store v1, when the offline path discarded the
    // photo outright. Telling an operator it was sent would be the false
    // reassurance this rewrite exists to remove.
    expect(describePhotos(base())).toBe("no photo");
  });

  it("treats an empty batch as photoless", () => {
    expect(describePhotos(base({ _photos: [], _photosUploaded: 0 }))).toBe("no photo");
  });
});
