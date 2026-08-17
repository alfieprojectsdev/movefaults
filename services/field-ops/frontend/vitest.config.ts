/**
 * Test config, deliberately separate from vite.config.ts.
 *
 * The app config runs vite-plugin-pwa, which generates a service worker and a
 * manifest on every build. None of that is wanted under test, and the PWA
 * plugin's generateSW step is slow enough to make a watch loop unpleasant.
 *
 * The timezone is pinned before anything else evaluates. Several of these
 * tests assert on local wall-clock conversion, and the whole reason those
 * helpers exist is that a Philippine local time sent without a zone lands in
 * the database eight hours wrong. A suite that silently adopts the machine's
 * timezone would pass on a laptop set to Manila and fail in CI set to UTC —
 * or worse, pass in both while asserting nothing meaningful. `times.test.ts`
 * asserts the offset it got, so a mis-set TZ fails loudly rather than quietly.
 */

process.env.TZ = "Asia/Manila";

import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
