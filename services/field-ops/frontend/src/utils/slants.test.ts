import { describe, it, expect } from "vitest";
import { summariseSlants, MIN_SLANTS } from "./slants";
import { computeRH } from "../components/LogSheetForm";

const s = (N = "", E = "", S = "", W = "") => summariseSlants({ N, E, S, W });

describe("how many readings are enough", () => {
  it("takes four", () => {
    const r = s("1.220", "1.228", "1.230", "1.222");
    expect(r.enough).toBe(true);
    expect(r.partial).toBe(false);
    expect(r.count).toBe(4);
    expect(r.avg).toBeCloseTo(1.225, 6);
  });

  it("takes three, whichever direction is blocked", () => {
    // The rule is a count, not a set: which leg is in the way is not knowable
    // in advance.
    for (const blocked of [0, 1, 2, 3]) {
      const raw = ["1.220", "1.228", "1.230", "1.222"];
      raw[blocked] = "";
      const r = summariseSlants({ N: raw[0], E: raw[1], S: raw[2], W: raw[3] });
      expect(r.enough).toBe(true);
      expect(r.partial).toBe(true);
      expect(r.count).toBe(MIN_SLANTS);
    }
  });

  it("refuses two, and produces no average to submit", () => {
    // Two readings need not even be an opposing pair, and a mean of two
    // adjacent ones is a tilt measurement wearing an average's clothes.
    const r = s("1.220", "1.228");
    expect(r.enough).toBe(false);
    expect(r.avg).toBeUndefined();
  });

  it("treats junk as absent rather than as zero", () => {
    // parseFloat("") is NaN and so is parseFloat("abc"). Coercing either to 0
    // would drag the mean down by a third of a metre and still look like a
    // number on screen.
    const r = s("1.220", "abc", "1.230", "1.222");
    expect(r.count).toBe(3);
    expect(r.missing).toEqual(["E"]);
    expect(r.avg).toBeCloseTo((1.22 + 1.23 + 1.222) / 3, 6);
  });
});

describe("the average itself", () => {
  it("is the plain mean of the readings present", () => {
    // Chosen deliberately 2026-08-20 over the pair-only estimator. Documented
    // here because the alternative is defensible and someone will re-propose it.
    const r = s("1.220", "1.228", "1.230");
    expect(r.avg).toBeCloseTo((1.22 + 1.228 + 1.23) / 3, 10);
  });

  it("names the blocked directions, which is what the nulls will record", () => {
    const r = s("1.220", "", "1.230", "");
    expect(r.missing).toEqual(["E", "W"]);
  });

  it("reports the spread in millimetres, for catching a mistyped tape reading", () => {
    const r = s("1.220", "1.228", "1.230", "1.222");
    expect(r.spreadMm).toBeCloseTo(10, 6);
  });

  it("has no spread from a single reading", () => {
    expect(s("1.220").spreadMm).toBeUndefined();
  });
});

describe("what three readings cost", () => {
  it("differs from the four-reading answer by the uncancelled tilt", () => {
    // N/S and E/W are opposing pairs, so tilt cancels within a pair. Dropping W
    // leaves E's contribution uncancelled at one third weight: E-W spans 6 mm
    // here, so the half-amplitude is 3 mm and the bias is 3/3 = 1.0 mm. This is
    // the known, accepted cost of allowing three — asserted so it stays known.
    const four = s("1.220", "1.228", "1.230", "1.222").avg!;
    const three = s("1.220", "1.228", "1.230").avg!;
    expect((three - four) * 1000).toBeCloseTo(1.0, 1);
  });

  it("carries that difference straight into the RINEX height", () => {
    // The bias does not attenuate through the reduction — it is a vertical
    // offset, which is the component this project exists to measure.
    const C = 0.16981;
    const VO = 0.04435;
    const four = computeRH(s("1.220", "1.228", "1.230", "1.222").avg!, C, VO);
    const three = computeRH(s("1.220", "1.228", "1.230").avg!, C, VO);
    expect((three - four) * 1000).toBeCloseTo(1.0, 1);
  });

  it("costs nothing when the setup is level", () => {
    // With no tilt every reading is the same and the count cannot matter. If
    // this ever fails, the averaging itself is wrong, not the sampling.
    expect(s("1.225", "1.225", "1.225", "1.225").avg).toBeCloseTo(1.225, 10);
    expect(s("1.225", "1.225", "1.225").avg).toBeCloseTo(1.225, 10);
  });
});
