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
