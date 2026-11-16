import { act, fireEvent, render, screen, within } from '@testing-library/react'
import App from './App'
import api from './__fixtures__/api.json'
import { ELLIPSE_95, scaleBar } from './vectors'

const responses = api as Record<string, unknown>
const BASE = '/api/campaigns/LUZON/time-series'
const FIELD = '/api/campaigns/LUZON/velocity-field'

// A small network around the fixture's reference. The mock map is flat, 100 px per degree.
const at = (lat: number, lon: number) => ({ lat, lon })
const POS = { REF0: at(14.5, 120.5), AAAA: at(14.6, 120.6), BBBB: at(14.4, 120.4), SHRT: at(14.7, 120.3), STAL: at(14.3, 120.7), FARR: at(22.5, 120.5) }
const entry = (station: keyof typeof POS, e: number, n: number, u: number, sigU: number, over: object = {}, top: object = {}) => ({
  station, ...POS[station], reference_distance_deg: 0.1, far_from_reference: false,
  velocity: { segment: 0, velocity_mm_yr: { e, n, u }, sigma_mm_yr: { e: 1, n: 2, u: sigU }, span_yr: 3.2, short_span: false, covers_latest_epoch: true, ...over },
  t_first: 2020.0027, t_last: 2023.5, n_epochs: 300, n_segments: 1, n_offsets: 0, warnings: [], ...top,
})
const field = {
  ...(responses[FIELD] as object),
  reference: 'REF0', reference_position: POS.REF0, t_first: 2020.0027, t_last: 2023.5, left_out: [],
  warnings: ['the reference REF0 is missing from 1 of 388 daily CRD files: those days give no epoch for any station'],
  stations: [
    entry('AAAA', 10, 0, 4, 1),
    entry('BBBB', -3, 4, -6, 1, {}, { n_offsets: 2 }),
    entry('FARR', 0, -20, 0.5, 2, {}, { reference_distance_deg: 8, far_from_reference: true }),
    entry('SHRT', 300, 0, 90, 30, { short_span: true, span_yr: 0.25 }),
    entry('STAL', 7, 7, 1, 1, { covers_latest_epoch: false }),
  ],
}
const summary = {
  ...(responses[BASE] as object),
  all_stations: Object.keys(POS), stations: Object.keys(POS).filter((c) => c !== 'REF0'), positions: POS,
  distances: { AAAA: 0.1, BBBB: 0.1, SHRT: 0.3, STAL: 0.3, FARR: 8 },
}

let urls: string[] = []
function serve(overrides: Record<string, unknown> = {}) {
  urls = []
  const all: Record<string, unknown> = { ...responses, [BASE]: summary, [FIELD]: field, ...overrides }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    urls.push(url)
    const body = all[url.split('?')[0]]
    if (body === undefined) return new Response(JSON.stringify({ detail: 'not in fixture' }), { status: 501 })
    return new Response(JSON.stringify(body), { status: 200 })
  }))
}
afterEach(() => vi.unstubAllGlobals())

const settle = () => act(async () => { await new Promise((r) => setTimeout(r, 0)) })
async function page() {
  window.location.hash = '#/c/LUZON/2021/time-series'
  render(<App />)
  await settle()
}
async function showField() {
  fireEvent.click(screen.getByRole('button', { name: 'Velocity field' }))
  await settle()
}
const leaflet = () => (globalThis as any).__leaflet
const pxPerMm = () => Number(screen.getByText(/px per mm\/yr/).textContent!.split(' ')[0])
const stationMark = (code: string) => leaflet().markers.find((m: { label: string }) => m.label.startsWith(code))
const arrowFrom = (code: keyof typeof POS) =>
  leaflet().lines.find((l: { points: [number, number][] }) => l.points[0][0] === POS[code].lat && l.points[0][1] === POS[code].lon)

it('the field is off until asked for, and nothing is fetched or drawn for it', async () => {
  serve()
  await page()
  expect(screen.getByRole('button', { name: 'Velocity field' }).getAttribute('aria-pressed')).toBe('false')
  expect(urls.some((u) => u.startsWith(FIELD))).toBe(false)
  expect(leaflet().lines).toHaveLength(0)
  expect(screen.queryByTestId('field-legend')).toBeNull()
})

it('switched on: an arrow, an ellipse and a head for every station whose rate is a velocity', async () => {
  serve()
  await page()
  await showField()
  expect(urls.filter((u) => u.startsWith(FIELD))).toEqual([FIELD])
  expect(leaflet().lines).toHaveLength(3) // AAAA, BBBB, FARR; not SHRT (short) or STAL (pre-event rate)
  expect(leaflet().polygons).toHaveLength(6)
  expect(arrowFrom('SHRT')).toBeUndefined()
  expect(arrowFrom('STAL')).toBeUndefined()
})

it('an arrow is its rate times the scale, east to the right and north up', async () => {
  serve()
  await page()
  await showField()
  const px = pxPerMm()
  // 10 mm/yr east: 10 * px pixels right, which the flat mock map turns into px / 10 degrees.
  const [, tipA] = arrowFrom('AAAA').points
  expect(tipA[0]).toBeCloseTo(POS.AAAA.lat, 9)
  expect(tipA[1]).toBeCloseTo(POS.AAAA.lon + (10 * px) / 100, 9)
  // -3 east, 4 north.
  const [, tipB] = arrowFrom('BBBB').points
  expect(tipB[0]).toBeCloseTo(POS.BBBB.lat + (4 * px) / 100, 9)
  expect(tipB[1]).toBeCloseTo(POS.BBBB.lon - (3 * px) / 100, 9)
})

it('the ellipse sits at the arrow tip with 2.448-sigma semi-axes', async () => {
  serve()
  await page()
  await showField()
  const px = pxPerMm()
  const tipLon = POS.AAAA.lon + (10 * px) / 100
  const ell = leaflet().polygons.find((p: { points: [number, number][]; opts: { fill: boolean } }) =>
    p.opts.fill === false && Math.abs(p.points[0][0] - POS.AAAA.lat) < 1e-9)
  const lons = ell.points.map((p: [number, number]) => p[1])
  const lats = ell.points.map((p: [number, number]) => p[0])
  expect(Math.max(...lons) - tipLon).toBeCloseTo((ELLIPSE_95 * 1 * px) / 100, 9) // sigma east 1
  expect(Math.max(...lats) - POS.AAAA.lat).toBeCloseTo((ELLIPSE_95 * 2 * px) / 100, 9) // sigma north 2
})

it('the scale buttons lengthen and shorten every arrow, and the scale arrow follows', async () => {
  serve()
  await page()
  await showField()
  const before = pxPerMm()
  const length = () => arrowFrom('AAAA').points[1][1] - POS.AAAA.lon
  const was = length()
  fireEvent.click(screen.getByRole('button', { name: 'Longer arrows' }))
  expect(pxPerMm()).toBeGreaterThan(before)
  expect(length()).toBeCloseTo((was * pxPerMm()) / before, 9)
  expect(screen.getByTestId('field-legend').textContent).toContain(`${scaleBar(pxPerMm()).mm} mm/yr`)
  expect(screen.getByTestId('field-legend').textContent).toContain('95%')
  fireEvent.click(screen.getByRole('button', { name: 'Shorter arrows' }))
  expect(pxPerMm()).toBe(before)
})

it('the map is measured again when it grows for the field', async () => {
  serve()
  await page()
  const before = leaflet().resized
  await showField()
  expect(leaflet().resized).toBeGreaterThan(before)
})

it('a zoom redraws the arrows once, not twice', async () => {
  serve()
  await page()
  await showField()
  act(() => leaflet().handlers.zoomend())
  expect(leaflet().lines).toHaveLength(3)
  expect(leaflet().polygons).toHaveLength(6)
})

it('a withheld station is hollow on the map and says why; the others say their velocity', async () => {
  serve()
  await page()
  await showField()
  expect(stationMark('SHRT').opts.fillOpacity).toBeLessThan(0.5)
  expect(stationMark('SHRT').label).toMatch(/no velocity: final segment spans 0\.25 yr/)
  expect(stationMark('STAL').label).toMatch(/before the latest event/)
  expect(stationMark('AAAA').opts.fillOpacity).toBeGreaterThan(0.9)
  expect(stationMark('BBBB').label).toMatch(/5\.0 mm\/yr toward NW \(E -3\.0 ± 1\.0, N 4\.0 ± 2\.0\)/)
})

it('vertical: circles, not arrows; up and down coloured apart; hollow under 2 sigma', async () => {
  serve()
  await page()
  await showField()
  fireEvent.click(screen.getByRole('button', { name: 'Vertical' }))
  expect(leaflet().lines).toHaveLength(0)
  expect(leaflet().polygons).toHaveLength(0)
  const rates = leaflet().markers.filter((m: { label: string }) => m.label === '')
  expect(rates).toHaveLength(3)
  const of = (code: keyof typeof POS) => rates.find((m: { at: [number, number] }) => m.at[0] === POS[code].lat)
  expect(of('AAAA').opts.color).not.toBe(of('BBBB').opts.color)
  expect(of('AAAA').opts.fillOpacity).toBeGreaterThan(0)
  expect(of('FARR').opts.fillOpacity).toBe(0) // 0.5 ± 2: not clear of zero
  expect(of('BBBB').opts.radius).toBeGreaterThan(of('AAAA').opts.radius)
  expect(screen.getByTestId('field-legend').textContent).toMatch(/up.*down.*hollow: under 2σ/)
  expect(screen.queryByRole('button', { name: 'Longer arrows' })).toBeNull()
  expect(stationMark('AAAA').label).toMatch(/up 4\.0 ± 1\.0 mm\/yr/)
})

it('says what frame the arrows are in, how far to trust sigma, and what was not drawn', async () => {
  serve()
  await page()
  await showField()
  const section = screen.getByRole('region', { name: /Velocity field · relative to REF0/ })
  const text = section.textContent!
  expect(text).toMatch(/relative to REF0/)
  expect(text).toMatch(/not ITRF velocities/)
  expect(text).toMatch(/formal 1-sigma, white noise only/)
  expect(text).toMatch(/Epochs 2020\.0027 to 2023\.5000/)
  expect(text).toMatch(/3 of 5 stations drawn/)
  expect(text).toMatch(/2 not drawn as a velocity.*SHRT, STAL/)
  expect(text).toMatch(/1 over 5° from the reference.*FARR/)
  expect(text).toMatch(/missing from 1 of 388/)
  expect(text).toContain((field as any).offsets_catalog.sha256)
})

it('the table lists every station; a withheld rate is struck through with its reason', async () => {
  serve()
  await page()
  await showField()
  const table = within(screen.getByRole('region', { name: /Velocity field/ })).getByRole('table')
  const row = (code: string) => within(table).getByRole('button', { name: code }).closest('tr')!
  expect(within(table).getAllByRole('row')).toHaveLength(1 + 5)
  expect(row('AAAA').textContent).toMatch(/10\.00 ± 1\.00.*0\.00 ± 2\.00.*10\.0 E/)
  expect(row('AAAA').querySelector('td')!.style.textDecoration).toBe('')
  expect(row('SHRT').querySelector('td')!.style.textDecoration).toBe('line-through')
  expect(row('SHRT').textContent).toMatch(/not drawn: final segment spans 0\.25 yr/)
  expect(row('FARR').textContent).toMatch(/8\.0° from REF0/)
  expect(row('BBBB').textContent).toMatch(/2 offsets in the catalogue/)
})

it('a heading sorts the table: fastest first, then slowest first', async () => {
  serve()
  await page()
  await showField()
  const table = within(screen.getByRole('region', { name: /Velocity field/ })).getByRole('table')
  const order = () => within(table).getAllByRole('rowheader').map((th) => th.textContent)
  expect(order()).toEqual(['AAAA', 'BBBB', 'FARR', 'SHRT', 'STAL'])
  fireEvent.click(within(table).getByRole('button', { name: /^Horizontal/ }))
  expect(order()[0]).toBe('SHRT')
  expect(within(table).getByRole('columnheader', { name: /^Horizontal/ }).getAttribute('aria-sort')).toBe('descending')
  fireEvent.click(within(table).getByRole('button', { name: /^Horizontal/ }))
  expect(order()[0]).toBe('BBBB')
})

it('a station in the table opens its series', async () => {
  serve()
  await page()
  await showField()
  fireEvent.click(within(screen.getByRole('region', { name: /Velocity field/ })).getByRole('button', { name: 'AAAA' }))
  await settle()
  expect(urls.some((u) => u.split('?')[0] === `${BASE}/AAAA`)).toBe(true)
})

it('the files are the server\'s, for the reference in view', async () => {
  serve()
  await page()
  await showField()
  const href = (name: RegExp) => screen.getByRole('link', { name }).getAttribute('href')
  expect(href(/psvelo/)).toBe(`${FIELD}/export?format=psvelo`)
  expect(href(/vertical rates/)).toBe(`${FIELD}/export?format=vertical`)
  expect(href(/CSV/)).toBe(`${FIELD}/export?format=csv`)
  // Another reference: the field is asked for again, and the files follow it.
  serve({ [BASE]: { ...summary, reference: 'AAAA' }, [FIELD]: { ...field, reference: 'AAAA' } })
  fireEvent.change(screen.getByRole('combobox', { name: 'Reference station' }), { target: { value: 'AAAA' } })
  await settle()
  expect(urls).toContain(`${FIELD}?reference=AAAA`)
  expect(href(/psvelo/)).toBe(`${FIELD}/export?format=psvelo&reference=AAAA`)
})

it('an answer for another reference is never drawn under this one', async () => {
  serve({ [FIELD]: { ...field, reference: 'OTHR' } })
  await page()
  await showField()
  expect(leaflet().lines).toHaveLength(0)
  expect(screen.queryByRole('region', { name: /Velocity field/ })).toBeNull()
  expect(screen.getByText(/Reading the velocity field/)).toBeTruthy()
})

it('a field that cannot be computed says why', async () => {
  const { stations: _s, ...rest } = field as any
  serve({ [FIELD]: { ...rest, available: false, message: 'No usable *.CRD files found' } })
  await page()
  await showField()
  expect(screen.getByText(/Cannot compute the velocity field/)).toBeTruthy()
  expect(screen.getByText(/No usable \*\.CRD files found/)).toBeTruthy()
  expect(leaflet().lines).toHaveLength(0)
})

it('stations left out of the field are named with the reason', async () => {
  serve({ [FIELD]: { ...field, left_out: [{ station: 'GONE', reason: 'series contains NaN or inf' }] } })
  await page()
  await showField()
  expect(screen.getByText(/GONE: series contains NaN or inf/)).toBeTruthy()
})

it('switching the field off clears the arrows and the panel', async () => {
  serve()
  await page()
  await showField()
  fireEvent.click(screen.getByRole('button', { name: 'Velocity field' }))
  expect(leaflet().lines).toHaveLength(0)
  expect(leaflet().polygons).toHaveLength(0)
  expect(screen.queryByRole('region', { name: /Velocity field/ })).toBeNull()
  expect(stationMark('SHRT').opts.fillOpacity).toBeGreaterThan(0.9)
})
