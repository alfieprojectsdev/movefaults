import { describe, it, expect } from "vitest";

/*
 * Reading the stylesheet as text, which is harder than it should be.
 *
 * `import css from "./field.css?raw"` is the tidy way and returns an EMPTY
 * STRING under vitest, because CSS processing is off — every assertion below
 * would then pass or fail for reasons unrelated to the stylesheet. Checked,
 * not assumed: the probe printed `typeof: string  len: 0`.
 *
 * node:fs works at runtime but does not typecheck: this project has no
 * @types/node, its lib is ES2020 + DOM, and adding that dependency to
 * typecheck a single test is a worse trade than one suppressed line.
 *
 * The path is relative to the vitest root, which is this package. A wrong path
 * throws rather than yielding "", so this cannot degrade into the silent
 * empty-string failure it exists to avoid.
 */
// @ts-expect-error - no @types/node; vitest runs in node so this resolves.
const { readFileSync } = await import("node:fs");
const css: string = readFileSync("src/styles/field.css", "utf8");

/**
 * A text check on the stylesheet, and it is deliberately a text check.
 *
 * The defect it guards against cannot be caught any other way here: vitest
 * loads no CSS, jsdom computes no cascade from a stylesheet, and the
 * consequence is a touch hit area that only a real screen reader on a real
 * handset would reveal.
 *
 * WHAT WENT WRONG
 *
 * `.observer-tile input[type=checkbox].sr-only` overrides the generic
 * `.sr-only` recipe so the checkbox fills its tile rather than being clipped
 * to one pixel — without that, explore-by-touch lands on an aria-hidden span
 * with the real control behind it.
 *
 * But the generic rule still MATCHES the same element, and the cascade
 * resolves per property, not per rule. Every property the override does not
 * declare still arrives from `.sr-only`. `clip` and `clip-path` were not
 * declared, so the input was laid out filling the tile and then clipped to a
 * zero-area region — and clip-path affects hit-testing, not just painting.
 *
 * Found by gps3 in review of #225, in a fix gps3 had itself suggested: the
 * suggestion listed the properties to set and neither of us noticed that the
 * ones it did not list would keep arriving from elsewhere.
 *
 * WHY IT IS WRITTEN GENERICALLY
 *
 * Asserting "clip and clip-path are present" would guard the two properties
 * that happened to bite. This asserts the rule that was actually broken —
 * every property the base recipe sets is accounted for in the override — so
 * the next one dropped is caught too.
 */

function ruleBody(selector: string): string {
  // Anchored to a line start. `.sr-only` is a suffix of the override's own
  // selector, so a bare indexOf finds the override when asked for the generic
  // rule and silently compares it against itself — which is how the first
  // version of this file passed two of its three tests for the wrong reason.
  const i = css.indexOf("\n" + selector + " {");
  expect(i, `selector not found: ${selector}`).toBeGreaterThan(-1);
  const open = css.indexOf("{", i);
  const close = css.indexOf("\n}", open);
  return css.slice(open + 1, close);
}

/** Property names declared in a rule body, ignoring anything inside comments. */
function declaredProperties(body: string): string[] {
  const withoutComments = body.replace(/\/\*[\s\S]*?\*\//g, "");
  return [...withoutComments.matchAll(/(^|;)\s*([a-z-]+)\s*:/g)].map((m) => m[2]);
}

describe("the observer tile's checkbox override", () => {
  it("accounts for every property the generic .sr-only recipe sets", () => {
    const generic = declaredProperties(ruleBody(".sr-only"));
    const override = declaredProperties(
      ruleBody('.observer-tile input[type="checkbox"].sr-only'),
    );

    /**
     * Two genuine exceptions, both inert on an empty <input>, both listed here
     * rather than left to be rediscovered:
     *
     *   overflow    `hidden` changes nothing about layout or hit-testing on a
     *               control with no content to overflow.
     *   white-space `nowrap` is a text-wrapping rule and there is no text.
     *
     * Anything else must be declared in the override. This list is meant to be
     * argued with when it grows -- an exception added without a reason beside
     * it is how this check stops being one.
     */
    const INERT_ON_AN_EMPTY_INPUT = ["overflow", "white-space"];
    const mustBeHandled = generic.filter((p) => !INERT_ON_AN_EMPTY_INPUT.includes(p));
    const missing = mustBeHandled.filter((p) => !override.includes(p));

    expect(missing, `.sr-only properties still cascading in: ${missing.join(", ")}`).toEqual([]);
  });

  it("neutralises the clipping specifically, because it governs hit-testing", () => {
    // Stated separately from the generic check above: this is the property
    // whose absence produced a control that could not be touched, and a
    // reader should not have to derive that from a list comparison.
    const override = ruleBody('.observer-tile input[type="checkbox"].sr-only');
    expect(override).toMatch(/clip:\s*auto/);
    expect(override).toMatch(/clip-path:\s*none/);
  });

  it("still clips anything using the generic recipe on its own", () => {
    // The recipe is correct for what it is for -- text that exists only for
    // assistive technology. Only a control with a visible surrogate needs the
    // override.
    const generic = ruleBody(".sr-only");
    expect(generic).toMatch(/clip-path:\s*inset\(50%\)/);
  });
});
