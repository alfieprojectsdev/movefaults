import { panRange, panelData, sessionDate, zoomRange } from './tsPlot'
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

it('pans by a fraction of the window and stops at the data', () => {
  expect(panRange(2020, 2021, 0.1, 2019, 2022)).toEqual([2020.1, 2021.1])
  expect(panRange(2020.5, 2021.5, 1, 2019, 2022)).toEqual([2021, 2022])
  expect(panRange(2019.2, 2020.2, -1, 2019, 2022)).toEqual([2019, 2020])
})

import { applicable, decisionMarks, lineAt } from './tsPlot'
import type { TsDecision } from './types'

const dec = (epoch: string, decision: 'outlier' | 'not_outlier', extra: Partial<TsDecision> = {}): TsDecision => ({
  epoch, decision, by: 'abc', ts: '', reason: '', reference: 'REF0', auto_flag: true, history: 1,
  superseded: false, other_reference: false, ...extra,
})

it('rings only decisions made on this solution and this reference', () => {
  const s = { ...series, t: [2020 + 1 / 365.25, 2020 + 2 / 365.25, 2020 + 3 / 365.25, 2020 + 4 / 365.25, 2020 + 5 / 365.25, 2020 + 6 / 365.25] }
  const ds = [
    dec('2020-001', 'outlier'),
    dec('2020-002', 'not_outlier'),
    dec('2020-003', 'outlier', { superseded: true }),
    dec('2020-004', 'outlier', { other_reference: true }),
  ]
  expect([...applicable(ds).keys()]).toEqual(['2020-001', '2020-002'])
  const m = decisionMarks(s, ds, 'e')
  expect(m.confirmed).toEqual([0, null, null, null, null, null])
  expect(m.overridden).toEqual([null, 5, null, null, null, null])
})

it('draws the side-by-side fit by time span, whatever its segment numbers', () => {
  const alt = [{ line: { t: [2021.2, 2022.0] as [number, number], e_mm: [12, 20] as [number, number], n_mm: [0, 0] as [number, number], u_mm: [0, 0] as [number, number] } }]
  const got = lineAt(series, alt, 'e')
  expect(got.slice(0, 3)).toEqual([null, null, null])
  expect(got[3]).toBeCloseTo(12)
  expect(got[4]).toBeCloseTo(15)
  expect(got[5]).toBeCloseTo(20)
})
