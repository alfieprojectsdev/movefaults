import { describe, it, expect } from "vitest";
import { ANTENNA_CONSTANTS, computeRH } from "./LogSheetForm";

/**
 * These pin the per-model constants against two independent sources: Trimble's
 * antenna reference surface diagrams, and PHIVOLCS'
 * `analysis/01 RINEX conversion/antenna_height_conversion*.{xlsx,xlsm}`
 * workbooks — the tool every campaign occupation to date was reduced with.
 *
 * Why pin numbers that "obviously" do not change: one of them was wrong for
 * months. TRM22020.00+GP carried VO = 0.0591, taken from the drawing's row B
 * ("TOP of ground plane to nominal phase centre") where the workbook uses row C
 * ("BOTTOM of ground plane"). The tape hooks under the ground plane, so bottom
 * is the measured surface. The error was exactly the ground plane's thickness,
 * 3.5 mm, in the vertical — the component this project exists to measure, at a
 * magnitude that reads as real subsidence rather than as a mistake.
 *
 * The failure mode is what makes a test worth having here: a wrong constant
 * produces a plausible number on screen and a plausible number in the solution.
 * Nothing downstream can catch it.
 */

// Radius and vertical offset, in metres, exactly as the workbooks compute them.
// Kept as literal arithmetic rather than decimals so each value can be read
// straight off the workbook cell it came from.
const WORKBOOK: Record<string, { C: number; VO: number; cell: string }> = {
  "TRM22020.00+GP": { C: 0.2334,  VO: (62.5 - 6.9) * 1e-3,      cell: "(62.5-6.9)*10^(-3)" },
  "TRM41249.00":    { C: 0.16981, VO: (5.326 - 0.891) * 1e-2,   cell: "(5.326-0.891)*10^(-2)" },
  "TRM55971.00":    { C: 0.16981, VO: (85 - 40.6) * 1e-3,       cell: "(85-40.6)*10^(-3)" },
  "TRM57971.00":    { C: 0.16981, VO: (8.546 - 4.111) * 1e-2,   cell: "(8.546-4.111)*10^(-2)" },
  "TRM115000.00":   { C: 0.16981, VO: (6.519 - 2.085) * 1e-2,   cell: "(6.519-2.085)*10^(-2)" },
};

describe("constants agree with the PHIVOLCS workbooks", () => {
  it("covers every model the workbooks define, and no invented ones", () => {
    expect(Object.keys(ANTENNA_CONSTANTS).sort()).toEqual(Object.keys(WORKBOOK).sort());
  });

  for (const [model, want] of Object.entries(WORKBOOK)) {
    it(`${model} — C and VO match ${want.cell}`, () => {
      const got = ANTENNA_CONSTANTS[model];
      // 0.1 mm. Tighter than any tape reading, loose enough for the workbook's
      // own rounding (it writes 0.16981 where a drawing says 16.98 cm).
      expect(got.C).toBeCloseTo(want.C, 4);
      expect(got.VO).toBeCloseTo(want.VO, 4);
    });
  }

  it("keeps A - B consistent with the VO it is meant to explain", () => {
    // A and B are provenance, not inputs — nothing reads them. If they drift
    // from VO, the comment block is lying about where the number came from,
    // which is exactly the state that produced the TRM22020 error.
    const drifted = Object.entries(ANTENNA_CONSTANTS)
      .filter(([, k]) => Math.abs((k.A - k.B) / 100 - k.VO) > 5e-5)
      .map(([model]) => model);
    expect(drifted).toEqual([]);
  });
});

describe("TRM22020.00+GP specifically", () => {
  it("uses the bottom of the ground plane, not the top", () => {
    // The regression itself. 0.0591 is the top-of-ground-plane row.
    expect(ANTENNA_CONSTANTS["TRM22020.00+GP"].VO).toBeCloseTo(0.0556, 4);
    expect(ANTENNA_CONSTANTS["TRM22020.00+GP"].VO).not.toBeCloseTo(0.0591, 4);
  });

  it("differs from the old value by the ground plane thickness, 3.5 mm", () => {
    const slant = 1.5;
    const now = computeRH(slant, 0.2334, ANTENNA_CONSTANTS["TRM22020.00+GP"].VO);
    const before = computeRH(slant, 0.2334, 0.0591);
    expect((now - before) * 1000).toBeCloseTo(3.5, 1);
  });
});

describe("model names are the IGS/RINEX spellings", () => {
  // The catalogue sheet in both workbooks lists these under "Antenna Type
  // (RINEX Header)". The form previously stored TRM55971-00, TRM57971-00 and
  // TRM115000 — hyphens for dots, and a truncation. None of those match an
  // ANTEX entry, so a RINEX header built from them loses its calibration and
  // Bernese falls back silently.
  it("uses dots, not hyphens, and never truncates", () => {
    for (const model of Object.keys(ANTENNA_CONSTANTS)) {
      expect(model).toMatch(/^TRM\d+\.\d\d(\+GP)?$/);
    }
  });

  it("spells the ground plane suffix in upper case, as the catalogue does", () => {
    expect(Object.keys(ANTENNA_CONSTANTS)).toContain("TRM22020.00+GP");
  });

  it("fits the antenna_model column, which is String(20)", () => {
    for (const model of Object.keys(ANTENNA_CONSTANTS)) {
      expect(model.length).toBeLessThanOrEqual(20);
    }
  });
});
