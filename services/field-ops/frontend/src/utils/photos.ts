/**
 * Photo size rules, checked before anything is queued or uploaded.
 *
 * ── Why the client checks at all ───────────────────────────────────────────
 *
 * The API already refuses anything past 15 MB with a 413
 * (`routers/logsheets.py`, `MAX_PHOTO_BYTES`), so a client check looks
 * redundant. It is not, because of *when* the two fire.
 *
 * Offline — the normal case in the field — the photo is written to IndexedDB
 * and the sheet reports "Saved offline". The 413 only happens later, during a
 * flush, by which time the observer has left the site. `runFlush` treats a
 * failed photo upload as transient and leaves the record pending, so an
 * oversized photo is retried on every subsequent sync, forever, and the record
 * never reaches "synced". Nothing surfaces that: the queue just shows a sheet
 * that never quite finishes.
 *
 * Checking at selection turns a permanent silent failure into a message while
 * the observer is still standing at the monument and can retake the shot.
 *
 * ── And it bounds the storage bill ─────────────────────────────────────────
 *
 * R2's free tier is 10 GB. At ~3 MB a frame that is roughly 3,300 photos, which
 * a field season does not approach — but the ceiling is per-file, not per-shot,
 * and a phone set to maximum quality can produce 12 MB frames. Six of those in
 * one batch is 72 MB from a single station visit. The total is surfaced so the
 * cost is visible at the moment it is incurred rather than in a bill.
 *
 * Deliberately NOT downscaling. `docs/asset-storage-cloudflare-cloudinary-neondb.md`
 * chose R2 over Cloudinary specifically so that "tiny handwriting on logsheets
 * remains perfectly sharp and legible" — these photos are evidence, and some of
 * them are pictures of paper. Compressing them to save storage would trade the
 * thing the photos exist for against a cost we are nowhere near.
 */

/**
 * Must match `MAX_PHOTO_BYTES` in
 * `services/field-ops/src/field_ops/routers/logsheets.py`.
 *
 * If the server's limit changes and this does not, the failure is the one this
 * module exists to prevent: an accepted photo that can never upload.
 */
export const MAX_PHOTO_BYTES = 15 * 1024 * 1024;

/**
 * Total across one sheet's batch, above which the operator is warned but not
 * blocked. Six 3 MB frames is a thorough station visit and sits under this; it
 * takes unusually large files to trip it, which is exactly when someone should
 * look before syncing over a field connection.
 */
export const WARN_TOTAL_BYTES = 40 * 1024 * 1024;

/** Human-readable size. MB below a gigabyte — nobody counts photos in bytes. */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  if (bytes < 1024 * 1024 * 1024) {
    const mb = bytes / (1024 * 1024);
    return `${mb < 10 ? mb.toFixed(1) : Math.round(mb)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

export interface PhotoCheck {
  /** Files past the server's hard limit. Submission is blocked while non-empty. */
  oversized: File[];
  totalBytes: number;
  /** Total is large enough to be worth a look, but not blocked. */
  warnTotal: boolean;
  /** Safe to queue and upload. */
  ok: boolean;
}

/**
 * Check a selection. Empty input is `ok: true` — the mandatory-photo rule is
 * enforced elsewhere, and conflating "no photo yet" with "bad photo" would show
 * a size error to someone who has simply not chosen one.
 */
export function checkPhotos(files: readonly File[] | null | undefined): PhotoCheck {
  const list = files ? Array.from(files) : [];
  const oversized = list.filter((f) => f.size > MAX_PHOTO_BYTES);
  const totalBytes = list.reduce((sum, f) => sum + f.size, 0);
  return {
    oversized,
    totalBytes,
    warnTotal: totalBytes > WARN_TOTAL_BYTES,
    ok: oversized.length === 0,
  };
}
