/**
 * Shared test setup.
 *
 * `fake-indexeddb/auto` installs a real in-memory IndexedDB implementation on
 * globalThis. jsdom ships no IndexedDB at all, and the offline queue is the
 * part of this app most worth testing — it is what stands between a day's
 * fieldwork and losing it.
 */

import "@testing-library/jest-dom/vitest";
import "fake-indexeddb/auto";

// jsdom implements neither half of the object-URL API. SheetsView creates URLs
// for photo blobs and revokes them on unmount; without these the revoke throws
// inside a cleanup, which React reports as an uncaught error and the test fails
// somewhere unrelated to what it was checking.
//
// Stubbed here rather than guarded in the component: the component is right to
// call an API every real browser has.
if (typeof URL.createObjectURL !== "function") {
  URL.createObjectURL = () => "blob:stub";
}
if (typeof URL.revokeObjectURL !== "function") {
  URL.revokeObjectURL = () => undefined;
}
