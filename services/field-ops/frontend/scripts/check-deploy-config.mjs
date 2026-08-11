/**
 * Fail the build if vercel.json still carries the placeholder API host.
 *
 * A rewrite destination is not validated at build time, so a deploy that skips
 * the DEPLOY.md edit succeeds at every stage a human would check: Vercel builds
 * it, the PWA loads, renders and installs. Only the API calls fail — and since
 * the app is deliberately offline-capable, a field observer reads that as "no
 * signal", not "misconfigured deploy".
 *
 * Better to break the build, where someone is watching, than to hand out a URL
 * that looks fine and cannot reach its backend.
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const configPath = join(here, "..", "vercel.json");

let raw;
try {
  raw = readFileSync(configPath, "utf8");
} catch {
  // No vercel.json — a local or container build, nothing to check.
  process.exit(0);
}

if (!raw.includes("REPLACE-WITH-BACKEND-HOST")) process.exit(0);

const message =
  "vercel.json still contains the placeholder REPLACE-WITH-BACKEND-HOST.\n" +
  "Set the API rewrite destination to the deployed backend host —\n" +
  "see services/field-ops/DEPLOY.md section 4.";

// Hard-fail only where the placeholder actually matters. Vercel sets VERCEL=1
// in its build environment; the Docker image and local `npm run build` never
// read vercel.json, so failing there would break builds over a file they do
// not use. The placeholder is meant to stay in the repo as the template.
if (process.env.VERCEL) {
  console.error(`\n${message}\n`);
  process.exit(1);
}

console.warn(`\nwarning: ${message}\n`);
