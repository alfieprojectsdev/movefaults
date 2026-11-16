import { arrowHead, azimuth, compass, defaultScale, ELLIPSE_95, ellipse, scaleBar, SCALES, sortStations, speed, stepScale, tip, verticalClear, verticalRadius, withheld } from './vectors'
import type { TsFieldStation } from './types'

const station = (code: string, e: number, n: number, over: Partial<TsFieldStation['velocity']> = {}): TsFieldStation => ({
  station: code, lat: 14, lon: 121, reference_distance_deg: 1, far_from_reference: false,
  velocity: {
    segment: 0, velocity_mm_yr: { e, n, u: 1 }, sigma_mm_yr: { e: 1, n: 2, u: 3 },
    span_yr: 3, short_span: false, covers_latest_epoch: true, ...over,
  },
  t_first: 2020, t_last: 2023, n_epochs: 100, n_segments: 1, n_offsets: 0, warnings: [],
})

describe('which stations get an arrow', () => {
  it('a fitted final segment that reaches the newest epoch does', () => {
    expect(withheld(station('AAAA', 1, 1))).toBeNull()
  })
  it('a short final segment does not, and says how short', () => {
    expect(withheld(station('AAAA', 1, 1, { short_span: true, span_yr: 0.25 }))).toMatch(/0\.25 yr/)
  })
  it('a rate from before the latest event does not', () => {
    expect(withheld(station('AAAA', 1, 1, { covers_latest_epoch: false }))).toMatch(/before the latest event/)
  })
})

describe('direction', () => {
  it('azimuth is clockwise from north', () => {
    expect(azimuth(0, 1)).toBeCloseTo(0)
    expect(azimuth(1, 0)).toBeCloseTo(90)
    expect(azimuth(0, -1)).toBeCloseTo(180)
    expect(azimuth(-1, 0)).toBeCloseTo(270)
  })
  it('compass names the nearest of eight points', () => {
    expect(compass(azimuth(-3, 4))).toBe('NW')
    expect(compass(359)).toBe('N')
    expect(compass(azimuth(1, -1))).toBe('SE')
  })
  it('speed is the horizontal rate', () => {
    expect(speed(station('AAAA', -3, 4))).toBe(5)
  })
})

describe('arrow geometry, in screen pixels', () => {
  it('east is +x and north is -y', () => {
    expect(tip(10, 0, 3)).toEqual({ x: 30, y: -0 })
    expect(tip(0, 10, 3)).toEqual({ x: 0, y: -30 })
  })
  it('the head is a triangle at the tip, behind it and symmetric about the shaft', () => {
    const [point, left, right] = arrowHead({ x: 0, y: 0 }, { x: 40, y: 0 })
    expect(point).toEqual({ x: 40, y: 0 })
    expect(left.x).toBe(32)
    expect(right.x).toBe(32)
    expect(left.y).toBeCloseTo(-right.y)
  })
  it('a very short arrow has no head, and a short one a smaller head', () => {
    expect(arrowHead({ x: 0, y: 0 }, { x: 1, y: 0 })).toEqual([])
    const [, back] = arrowHead({ x: 0, y: 0 }, { x: 5, y: 0 })
    expect(back.x).toBeCloseTo(2)
  })
})

describe('the 95% ellipse', () => {
  it('has semi-axes of 2.448 sigma, east along x and north along y', () => {
    expect(ELLIPSE_95 ** 2).toBeCloseTo(5.991, 2)
    const pts = ellipse({ x: 100, y: 50 }, 1, 2, 3, 4)
    expect(pts[0].x).toBeCloseTo(100 + ELLIPSE_95 * 1 * 3)
    expect(pts[0].y).toBeCloseTo(50)
    expect(pts[1].x).toBeCloseTo(100)
    expect(pts[1].y).toBeCloseTo(50 + ELLIPSE_95 * 2 * 3)
  })
})

describe('the scale', () => {
  it('puts the median arrow near 40 px, on one of the steps', () => {
    const px = defaultScale([5, 13, 34])
    expect(SCALES).toContain(px)
    expect(13 * px).toBeGreaterThan(25)
    expect(13 * px).toBeLessThan(60)
  })
  it('one fast station does not shrink the rest', () => {
    expect(defaultScale([10, 12, 14, 900])).toBe(defaultScale([10, 12, 14, 15]))
  })
  it('with nothing to draw there is still a scale', () => {
    expect(defaultScale([])).toBe(2)
  })
  it('steps up and down and stops at the ends', () => {
    expect(stepScale(2, 1)).toBe(3)
    expect(stepScale(2, -1)).toBe(1.5)
    expect(stepScale(SCALES[0], -1)).toBe(SCALES[0])
    expect(stepScale(SCALES[SCALES.length - 1], 1)).toBe(SCALES[SCALES.length - 1])
  })
  it('the scale arrow is a round rate that fits', () => {
    expect(scaleBar(3)).toEqual({ mm: 20, px: 60 })
    expect(scaleBar(0.25)).toEqual({ mm: 200, px: 50 })
    expect(scaleBar(24)).toEqual({ mm: 2, px: 48 })
    for (const px of SCALES) expect(scaleBar(px).px).toBeLessThanOrEqual(90)
  })
})

describe('vertical rates', () => {
  it('the circle grows with the rate and is capped', () => {
    expect(verticalRadius(0)).toBe(4)
    expect(verticalRadius(-10)).toBe(verticalRadius(10))
    expect(verticalRadius(10)).toBeGreaterThan(verticalRadius(2))
    expect(verticalRadius(500)).toBe(18)
  })
  it('a rate under 2 sigma is not clear of zero', () => {
    expect(verticalClear(3, 2)).toBe(false)
    expect(verticalClear(-4, 2)).toBe(true)
  })
})

describe('sorting the table', () => {
  const rows = [station('BBBB', 1, 0), station('AAAA', -3, 4), station('CCCC', 2, 0, { span_yr: 9 })]
  it('by station, speed, a component and span', () => {
    expect(sortStations(rows, 'station', false).map((s) => s.station)).toEqual(['AAAA', 'BBBB', 'CCCC'])
    expect(sortStations(rows, 'speed', true).map((s) => s.station)).toEqual(['AAAA', 'CCCC', 'BBBB'])
    expect(sortStations(rows, 'e', false).map((s) => s.station)).toEqual(['AAAA', 'BBBB', 'CCCC'])
    expect(sortStations(rows, 'span', true)[0].station).toBe('CCCC')
  })
  it('does not reorder the list it was given', () => {
    sortStations(rows, 'station', false)
    expect(rows[0].station).toBe('BBBB')
  })
})
