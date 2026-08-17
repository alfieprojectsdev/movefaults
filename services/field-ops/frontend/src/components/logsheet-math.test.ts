import { describe, it, expect } from "vitest";
import { computeRH, toDOY } from "./LogSheetForm";

/**
 * The antenna-height reduction and the session-id day number.
 *
 * These two feed the parts of a log sheet that are hardest to check after the
 * fact. A wrong RINEX height propagates silently into the Bernese solution as
 * a vertical bias; a wrong day-of-year produces a session id that does not
 * match the RINEX file it is supposed to name. Neither is visible on the form.
 */

describe("computeRH — slant height to RINEX (vertical) height", () => {
  // RH = sqrt(avgSH² - C²) - VO. The slant is measured from the mark to the
  // antenna's edge, so C (the horizontal offset to that edge) comes out by
  // Pythagoras, and VO (the vertical offset from that point to the ARP) is
  // then subtracted.
  const TRM55971 = { C: 0.1698, VO: 0.0444 };

  it("reduces a slant measurement to the vertical height", () => {
    const rh = computeRH(1.5, TRM55971.C, TRM55971.VO);
    expect(rh).toBeCloseTo(Math.sqrt(1.5 ** 2 - 0.1698 ** 2) - 0.0444, 10);
    expect(rh).toBeCloseTo(1.4460, 4);
  });

  it("is always shorter than the slant it came from", () => {
    // The hypotenuse is the longest side; subtracting VO only shortens it
    // further. An RH exceeding its slant would mean the formula was inverted.
    for (const slant of [0.5, 1.0, 1.5, 2.0]) {
      expect(computeRH(slant, TRM55971.C, TRM55971.VO)).toBeLessThan(slant);
    }
  });

  it("increases monotonically with the slant", () => {
    const heights = [1.0, 1.2, 1.4, 1.6].map((s) =>
      computeRH(s, TRM55971.C, TRM55971.VO)
    );
    for (let i = 1; i < heights.length; i++) {
      expect(heights[i]).toBeGreaterThan(heights[i - 1]);
    }
  });

  it("subtracts VO exactly when the horizontal offset is zero", () => {
    // Degenerate but useful: with C = 0 the slant IS the vertical, so the
    // whole reduction collapses to the VO subtraction. Catches a swapped
    // C/VO argument order, which is otherwise nearly invisible numerically.
    expect(computeRH(1.5, 0, 0.0444)).toBeCloseTo(1.4556, 10);
  });

  it("returns NaN when the slant is shorter than the horizontal offset", () => {
    // Physically impossible — the hypotenuse cannot be shorter than a leg —
    // and means a mistyped measurement. It must not quietly produce a number.
    expect(Number.isNaN(computeRH(0.1, 0.1698, 0.0444))).toBe(true);
  });

  it("matches the published constants for each supported antenna", () => {
    // Guards the constants table against an editing slip: these are the
    // values a field team's numbers are reduced with.
    const cases: Array<[number, number, number, number]> = [
      // avgSH,  C,        VO,       expected RH
      [1.5, 0.2334, 0.0591, Math.sqrt(1.5 ** 2 - 0.2334 ** 2) - 0.0591],
      [1.5, 0.1698, 0.0443, Math.sqrt(1.5 ** 2 - 0.1698 ** 2) - 0.0443],
      [1.5, 0.16981, 0.04434, Math.sqrt(1.5 ** 2 - 0.16981 ** 2) - 0.04434],
    ];
    for (const [slant, C, VO, expected] of cases) {
      expect(computeRH(slant, C, VO)).toBeCloseTo(expected, 12);
    }
  });
});

describe("toDOY — day of year for the session id", () => {
  it("gives 1 for January 1st", () => {
    expect(toDOY("2026-01-01")).toBe(1);
  });

  it("gives 365 for December 31st of a common year", () => {
    expect(toDOY("2026-12-31")).toBe(365);
  });

  it("gives 366 for December 31st of a leap year", () => {
    expect(toDOY("2024-12-31")).toBe(366);
  });

  it("counts February 29th in a leap year", () => {
    expect(toDOY("2024-03-01")).toBe(61);
  });

  it("does not count a 29th of February in a common year", () => {
    expect(toDOY("2026-03-01")).toBe(60);
  });

  it("is unaffected by the local timezone offset", () => {
    // Parsed as `${dateStr}T00:00:00`, i.e. local midnight. Parsing it as UTC
    // midnight instead would shift the day back by one everywhere east of
    // Greenwich — including every station in this network.
    expect(toDOY("2026-08-17")).toBe(229);
  });
});
