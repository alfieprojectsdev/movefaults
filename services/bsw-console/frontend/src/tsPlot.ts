/**
 * Pure helpers for the time-series chart: turn the status payload into the
 * columnar arrays a chart draws, and the zoom arithmetic. No drawing here, so
 * everything a reader could get wrong about the data is testable without a canvas.
 *
 * Nothing is computed that the timeseries package did not already return: the
 * fitted line is the package's own (its segment-end values, interpolated along
 * the straight line between them), and the flags are the package's flags.
 */
import type { TsDecision, TsSegment, TsSeries } from './types'

export type Component = 'e' | 'n' | 'u'
export const COMPONENTS: { key: Component; label: string }[] = [
  { key: 'e', label: 'East (mm)' },
  { key: 'n', label: 'North (mm)' },
  { key: 'u', label: 'Up (mm)' },
]

/** One chart's columns, index-aligned with `t`. null = no mark at that epoch. */
export type PanelData = {
  t: number[]
  kept: (number | null)[] // epochs the fit used
  flagged: (number | null)[] // flagged by the outlier rule (kept or not)
  left: (number | null)[] // not in the fit and not flagged: unfitted interval, or excluded
  fit: (number | null)[] // the fitted line; null between segments, so it breaks there
}

export function panelData(series: TsSeries, segments: TsSegment[], c: Component): PanelData {
  const ys = series[`${c}_mm`]
  const lineOf = new Map(segments.map((s) => [s.index, s.line]))
  const kept: (number | null)[] = []
  const flagged: (number | null)[] = []
  const left: (number | null)[] = []
  const fit: (number | null)[] = []
  series.t.forEach((t, i) => {
    const y = ys[i]
    const isFlag = series.outlier[i]
    const inFit = series.in_fit[i]
    flagged.push(isFlag ? y : null)
    kept.push(!isFlag && inFit ? y : null)
    left.push(!isFlag && !inFit ? y : null)
    const seg = series.segment[i]
    const line = seg === null ? undefined : lineOf.get(seg)
    if (!line) {
      fit.push(null)
      return
    }
    const [t0, t1] = line.t
    const [a, b] = line[`${c}_mm`]
    fit.push(t1 === t0 ? a : a + ((t - t0) / (t1 - t0)) * (b - a))
  })
  return { t: series.t, kept, flagged, left, fit }
}

/**
 * Zoom the time axis around `center` by `factor` (< 1 zooms in, > 1 out), the
 * way a waveform editor does: the time under the cursor stays put. Clamped to
 * [lo, hi], the series' own extent, and never narrower than `minSpan`.
 */
export function zoomRange(
  min: number, max: number, center: number, factor: number,
  lo: number, hi: number, minSpan = 1 / 365.25,
): [number, number] {
  const full = hi - lo
  let span = Math.min(Math.max((max - min) * factor, Math.min(minSpan, full)), full)
  const frac = max > min ? (center - min) / (max - min) : 0.5
  let nmin = center - frac * span
  let nmax = nmin + span
  if (nmin < lo) { nmin = lo; nmax = lo + span }
  if (nmax > hi) { nmax = hi; nmin = hi - span }
  return [nmin, nmax]
}

/**
 * "2025.5969" → "2025-218", the session date the decimal year came from.
 *
 * The convention is year + DOY/365.25 (settled), so a leap year's DOY 366
 * lands just past the next whole year (2024 + 366/365.25 = 2025.0021) and
 * flooring alone would call it 2025-001. Both candidate years are tried and the
 * one that reproduces `t` exactly wins; if neither does, `t` is not a session
 * epoch and the nearest reading is given with a "~".
 */
export function sessionDate(t: number): string {
  for (const year of [Math.floor(t), Math.floor(t) - 1]) {
    const doy = Math.round((t - year) * 365.25)
    if (doy >= 1 && doy <= 366 && Math.abs(year + doy / 365.25 - t) < 1e-6) {
      return `${year}-${String(doy).padStart(3, '0')}`
    }
  }
  const year = Math.floor(t)
  return `~${year}-${String(Math.max(1, Math.round((t - year) * 365.25))).padStart(3, '0')}`
}

/** Shift the time window by `frac` of its width (negative = earlier), clamped to [lo, hi]. */
export function panRange(min: number, max: number, frac: number, lo: number, hi: number): [number, number] {
  const span = max - min
  let nmin = min + frac * span
  let nmax = nmin + span
  if (nmin < lo) { nmin = lo; nmax = Math.min(hi, lo + span) }
  if (nmax > hi) { nmax = hi; nmin = Math.max(lo, hi - span) }
  return [nmin, nmax]
}

/** The decisions that apply to what is shown: same reference, same solution. */
export function applicable(decisions: TsDecision[] | undefined): Map<string, TsDecision> {
  return new Map((decisions ?? []).filter((d) => !d.superseded && !d.other_reference).map((d) => [d.epoch, d]))
}

/** Rings over epochs a person decided on: confirmed outliers, and flags overridden as real. */
export function decisionMarks(series: TsSeries, decisions: TsDecision[] | undefined, c: Component) {
  const by = applicable(decisions)
  const ys = series[`${c}_mm`]
  const confirmed: (number | null)[] = []
  const overridden: (number | null)[] = []
  series.t.forEach((t, i) => {
    const d = by.get(sessionDate(t))
    confirmed.push(d?.decision === 'outlier' ? ys[i] : null)
    overridden.push(d?.decision === 'not_outlier' ? ys[i] : null)
  })
  return { confirmed, overridden }
}

/**
 * The side-by-side fit's line at each epoch. Matched by time span, not by
 * segment number: leaving epochs out can drop a short segment, and then the
 * second fit's numbering no longer lines up with the series'.
 */
export function lineAt(series: TsSeries, segments: Pick<TsSegment, 'line'>[], c: Component): (number | null)[] {
  const lines = segments.map((s) => s.line).filter((l): l is NonNullable<typeof l> => !!l)
  return series.t.map((t) => {
    const l = lines.find((x) => x.t[0] <= t && t <= x.t[1])
    if (!l) return null
    const [t0, t1] = l.t
    const [a, b] = l[`${c}_mm`]
    return t1 === t0 ? a : a + ((t - t0) / (t1 - t0)) * (b - a)
  })
}
