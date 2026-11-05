import { panelData, sessionDate, zoomRange } from './tsPlot'
import type { TsSegment, TsSeries } from './types'

const seg = (index: number, t: [number, number], e: [number, number]): TsSegment => ({
  index, t_start: t[0], t_end: t[1], span_yr: t[1] - t[0], n_epochs: 0, n_fit: 0, n_outliers: 0,
  velocity_mm_yr: { e: 0, n: 0, u: 0 }, sigma_mm_yr: { e: 0, n: 0, u: 0 }, r2: { e: 0, n: 0, u: 0 },
  short_span: false, line: { t, e_mm: e, n_mm: [0, 0], u_mm: [0, 0] },
})

const series: TsSeries = {
  t: [2020.0, 2020.5, 2021.0, 2021.2, 2021.5, 2022.0],
  e_mm: [0, 5, 10, 99, 16, 20],
  n_mm: [0, 0, 0, 0, 0, 0],
  u_mm: [0, 0, 0, 0, 0, 0],
  outlier: [false, false, false, true, false, false],
  in_fit: [true, true, true, true, true, false],
  segment: [0, 0, 0, 1, 1, null],
}
const segments = [seg(0, [2020.0, 2021.0], [0, 10]), seg(1, [2021.2, 2021.5], [12, 16])]

it('splits each epoch into exactly one mark: in fit, flagged, or not in fit', () => {
  const d = panelData(series, segments, 'e')
  expect(d.kept).toEqual([0, 5, 10, null, 16, null])
  expect(d.flagged).toEqual([null, null, null, 99, null, null])
  expect(d.left).toEqual([null, null, null, null, null, 20])
  d.t.forEach((_, i) => {
    expect([d.kept[i], d.flagged[i], d.left[i]].filter((v) => v !== null)).toHaveLength(1)
  })
})

it('draws the package\'s own fitted line, broken between segments', () => {
  const d = panelData(series, segments, 'e')
  expect(d.fit[0]).toBe(0)
  expect(d.fit[1]).toBeCloseTo(5)
  expect(d.fit[2]).toBe(10)
  expect(d.fit[3]).toBe(12) // segment 1 starts on its own line, not continuing segment 0's
  expect(d.fit[4]).toBe(16)
  expect(d.fit[5]).toBeNull() // an epoch in no segment has no line
})

it('zooms around the cursor and keeps the time under it in place', () => {
  const [a, b] = zoomRange(2020, 2022, 2021.5, 0.5, 2020, 2022)
  expect(b - a).toBeCloseTo(1)
  expect((2021.5 - a) / (b - a)).toBeCloseTo((2021.5 - 2020) / 2)
})

it('never zooms past the data or below a day', () => {
  expect(zoomRange(2020, 2022, 2021, 4, 2020, 2022)).toEqual([2020, 2022])
  const [a, b] = zoomRange(2021, 2021.001, 2021.0005, 0.001, 2020, 2022)
  expect(b - a).toBeCloseTo(1 / 365.25)
  const [c, d] = zoomRange(2020, 2020.5, 2020.01, 0.5, 2020, 2022)
  expect(c).toBeGreaterThanOrEqual(2020)
  expect(d).toBeGreaterThan(c)
})

it('turns a decimal year back into its session date', () => {
  expect(sessionDate(2025 + 218 / 365.25)).toBe('2025-218')
  expect(sessionDate(2024 + 366 / 365.25)).toBe('2024-366')
  expect(sessionDate(2025 + 1 / 365.25)).toBe('2025-001')
  expect(sessionDate(2024 + 365 / 365.25)).toBe('2024-365')
  expect(sessionDate(2021.0)).toMatch(/^~/)
})
