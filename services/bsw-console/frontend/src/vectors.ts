/**
 * Pure helpers for the velocity field on the station map: which stations get an
 * arrow, the arrow and ellipse geometry in screen pixels, and the scale.
 *
 * Nothing here fits or changes a number. The velocities and their 1-sigma are the
 * timeseries package's (field_status); this turns them into shapes.
 *
 * Screen coordinates: x grows east, y grows SOUTH, so north is -y.
 */
import type { TsFieldStation } from './types'

export type XY = { x: number; y: number }

/** Semi-axes of the 95% confidence ellipse, in sigmas: sqrt of chi-square(2 dof) at 0.95,
 * sqrt(5.991). One sigma would cover only 39% in two dimensions. */
export const ELLIPSE_95 = 2.448

/** Why a station's rate is not drawn as a velocity, or null when it is. The same two
 * tests the exports withhold on (bsw_console/timeseries.py, _withheld). */
export function withheld(s: TsFieldStation): string | null {
  const v = s.velocity
  if (v.short_span) return `final segment spans ${v.span_yr.toFixed(2)} yr, under the minimum`
  if (!v.covers_latest_epoch) return 'the newest epochs are too few to fit: this is the rate before the latest event'
  return null
}

export const speed = (s: TsFieldStation) => Math.hypot(s.velocity.velocity_mm_yr.e, s.velocity.velocity_mm_yr.n)

/** Direction of motion, degrees clockwise from north, 0 to 360. */
export function azimuth(e: number, n: number): number {
  const a = (Math.atan2(e, n) * 180) / Math.PI
  return a < 0 ? a + 360 : a
}

const POINTS = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
/** The nearest of eight compass points, for a sentence a person reads. */
export const compass = (az: number) => POINTS[Math.round(az / 45) % 8]

/** Where the arrow ends, relative to the station, for a rate and a scale. */
export const tip = (e: number, n: number, pxPerMm: number): XY => ({ x: e * pxPerMm, y: -n * pxPerMm })

/** The arrowhead: a triangle at `end`, pointing away from `start`. Empty when the
 * arrow is too short for a head to mean anything. */
export function arrowHead(start: XY, end: XY, size = 8): XY[] {
  const dx = end.x - start.x
  const dy = end.y - start.y
  const len = Math.hypot(dx, dy)
  if (len < 2) return []
  const h = Math.min(size, len * 0.6)
  const ux = dx / len
  const uy = dy / len
  const back = { x: end.x - ux * h, y: end.y - uy * h }
  const half = h * 0.4
  return [
    end,
    { x: back.x - uy * half, y: back.y + ux * half },
    { x: back.x + uy * half, y: back.y - ux * half },
  ]
}

/** The 95% ellipse around `centre`, as a polygon. Axis-aligned: East and North are
 * separate fits, so their formal errors are uncorrelated (timeseries/gmt.py). */
export function ellipse(centre: XY, sigE: number, sigN: number, pxPerMm: number, steps = 32): XY[] {
  const a = ELLIPSE_95 * sigE * pxPerMm
  const b = ELLIPSE_95 * sigN * pxPerMm
  return Array.from({ length: steps }, (_, k) => {
    const th = (2 * Math.PI * k) / steps
    return { x: centre.x + a * Math.cos(th), y: centre.y + b * Math.sin(th) }
  })
}

/** Screen pixels per mm/yr the scale buttons step through. */
export const SCALES = [0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 16, 24]

/** A scale at which the typical drawn arrow is about `targetPx` long. Typical is
 * the median, which one fast station cannot pull. */
export function defaultScale(speeds: number[], targetPx = 40): number {
  const s = speeds.filter((v) => v > 0).sort((a, b) => a - b)
  if (s.length === 0) return 2
  const median = s[Math.floor(s.length / 2)]
  const want = targetPx / median
  return SCALES.reduce((best, c) => (Math.abs(Math.log(c / want)) < Math.abs(Math.log(best / want)) ? c : best))
}

export const stepScale = (pxPerMm: number, dir: -1 | 1): number => {
  const i = SCALES.indexOf(pxPerMm)
  if (i < 0) return defaultScale([40 / pxPerMm])
  return SCALES[Math.min(SCALES.length - 1, Math.max(0, i + dir))]
}

/** The scale arrow: the largest round rate (1, 2, 5 times a power of ten) whose
 * arrow is at most `maxPx` long. */
export function scaleBar(pxPerMm: number, maxPx = 90): { mm: number; px: number } {
  let best = 0
  for (let p = -1; p <= 3; p++) {
    for (const m of [1, 2, 5]) {
      const mm = m * 10 ** p
      if (mm * pxPerMm <= maxPx && mm > best) best = mm
    }
  }
  if (best === 0) best = 0.1
  return { mm: best, px: best * pxPerMm }
}

/** Radius of a vertical-rate circle, in pixels: grows with the rate, capped so one
 * runaway station does not cover its neighbours. */
export const verticalRadius = (vu: number) => Math.min(18, 4 + Math.abs(vu) * 0.7)

/** Whether a vertical rate is distinguishable from zero at 2 sigma. */
export const verticalClear = (vu: number, sig: number) => Math.abs(vu) >= 2 * sig

export type SortKey = 'station' | 'e' | 'n' | 'u' | 'speed' | 'span'

export function sortStations(rows: TsFieldStation[], key: SortKey, descending: boolean): TsFieldStation[] {
  const value = (s: TsFieldStation): number | string =>
    key === 'station' ? s.station
      : key === 'speed' ? speed(s)
        : key === 'span' ? s.velocity.span_yr
          : s.velocity.velocity_mm_yr[key]
  const sorted = [...rows].sort((a, b) => {
    const x = value(a)
    const y = value(b)
    return typeof x === 'string' ? x.localeCompare(y as string) : x - (y as number)
  })
  return descending ? sorted.reverse() : sorted
}
