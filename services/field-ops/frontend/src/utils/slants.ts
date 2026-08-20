/**
 * Slant-height readings → the average that feeds the RINEX height.
 *
 * A campaign setup is measured from the mark to the antenna edge in four
 * directions. N/S and E/W are opposing pairs, so a tilted tripod biases each
 * pair symmetrically and the mean of all four cancels it — that is the whole
 * reason four are taken rather than one.
 *
 * Three is allowed because it is what the field sometimes gives you: a tripod
 * leg, a wall or the monument itself can block one direction that would
 * otherwise be symmetric with the other three. Refusing the sheet in that case
 * does not produce a fourth reading; it produces a sheet filed on paper, or not
 * at all.
 *
 * What three costs, stated plainly because nothing on screen can show it: the
 * orphan reading's axis is no longer cancelled, and its tilt enters the mean at
 * one third weight. With the ~5 mm spreads visible in PHIVOLCS' own workbooks
 * that is on the order of 1-2 mm of vertical bias. Chosen deliberately over the
 * pair-only estimator (2026-08-20) — this keeps "average the readings" meaning
 * exactly what it says, at a cost small enough to accept and large enough to
 * record. `partial` marks these so the form can say so and a later reduction
 * can find them.
 */

/** Fewer than this and there is no usable average. */
export const MIN_SLANTS = 3;

export type SlantKey = "N" | "E" | "S" | "W";

export interface SlantSummary {
  /** Readings actually present, in N/E/S/W order. */
  values: number[];
  /** Directions left blank — what the tripod blocked. */
  missing: SlantKey[];
  count: number;
  /** Mean of the present readings; undefined below MIN_SLANTS. */
  avg?: number;
  /** Largest minus smallest reading, in millimetres. Undefined below 2. */
  spreadMm?: number;
  /** At least MIN_SLANTS present, so an average exists. */
  enough: boolean;
  /** Exactly MIN_SLANTS: usable, but carrying uncancelled tilt. */
  partial: boolean;
}

const ORDER: SlantKey[] = ["N", "E", "S", "W"];

export function summariseSlants(raw: Record<SlantKey, string>): SlantSummary {
  const values: number[] = [];
  const missing: SlantKey[] = [];

  for (const k of ORDER) {
    const n = parseFloat(raw[k]);
    // A blank field and "abc" are the same thing here: no reading. Treating
    // NaN as 0 would produce an average that looks plausible and is not.
    if (Number.isFinite(n)) values.push(n);
    else missing.push(k);
  }

  const count = values.length;
  const enough = count >= MIN_SLANTS;

  return {
    values,
    missing,
    count,
    enough,
    partial: count === MIN_SLANTS,
    avg: enough ? values.reduce((a, b) => a + b, 0) / count : undefined,
    spreadMm:
      count >= 2 ? (Math.max(...values) - Math.min(...values)) * 1000 : undefined,
  };
}
