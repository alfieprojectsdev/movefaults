import { describe, it, expect } from "vitest";
import { distanceMetres, formatDistance } from "./distance";

/**
 * The station picker filters to sites near the device's fix. Too generous and
 * the operator scrolls past irrelevant stations; too tight and the site they
 * are standing at is missing from the list, which is the failure that matters.
 */

describe("distanceMetres", () => {
  it("is zero for a point and itself", () => {
    const p = { latitude: 14.68, longitude: 120.54 };
    expect(distanceMetres(p, p)).toBe(0);
  });

  it("is symmetric", () => {
    const a = { latitude: 14.68, longitude: 120.54 };
    const b = { latitude: 12.15, longitude: 123.95 };
    expect(distanceMetres(a, b)).toBeCloseTo(distanceMetres(b, a), 9);
  });

  it("matches a known separation along a meridian", () => {
    // One degree of latitude is ~111.2 km on the mean sphere, everywhere.
    const d = distanceMetres(
      { latitude: 14.0, longitude: 121.0 },
      { latitude: 15.0, longitude: 121.0 }
    );
    expect(d).toBeGreaterThan(111_100);
    expect(d).toBeLessThan(111_300);
  });

  it("shrinks a degree of longitude by the cosine of the latitude", () => {
    // The reason a flat-earth approximation tuned to one latitude drifts at
    // the other end of a network spanning 5°N to 21°N.
    const atEquator = distanceMetres(
      { latitude: 0, longitude: 120 },
      { latitude: 0, longitude: 121 }
    );
    const atManila = distanceMetres(
      { latitude: 14.6, longitude: 120 },
      { latitude: 14.6, longitude: 121 }
    );
    expect(atManila / atEquator).toBeCloseTo(Math.cos((14.6 * Math.PI) / 180), 4);
  });

  it("is accurate at the few-hundred-metre scale the picker uses", () => {
    // 0.001° of latitude ≈ 111.2 m. This is the range that decides whether the
    // station you are standing at appears in the list.
    const d = distanceMetres(
      { latitude: 14.6, longitude: 121.0 },
      { latitude: 14.601, longitude: 121.0 }
    );
    expect(d).toBeCloseTo(111.2, 0);
  });

  it("handles the antimeridian-free case across the whole archipelago", () => {
    // Batanes to Tawi-Tawi, roughly — about 1,700 km.
    const d = distanceMetres(
      { latitude: 20.45, longitude: 121.97 },
      { latitude: 5.05, longitude: 119.85 }
    );
    expect(d).toBeGreaterThan(1_700_000);
    expect(d).toBeLessThan(1_760_000);
  });
});

describe("formatDistance", () => {
  it("rounds to 10 m below a kilometre", () => {
    expect(formatDistance(0)).toBe("0 m");
    expect(formatDistance(123)).toBe("120 m");
    expect(formatDistance(996)).toBe("1000 m");
  });

  it("switches to one decimal of a kilometre past 1 km", () => {
    expect(formatDistance(1000)).toBe("1.0 km");
    expect(formatDistance(2470)).toBe("2.5 km");
  });

  it("drops the decimal past 10 km, which a handset fix cannot justify", () => {
    expect(formatDistance(10_000)).toBe("10 km");
    expect(formatDistance(1_712_345)).toBe("1712 km");
  });
});
