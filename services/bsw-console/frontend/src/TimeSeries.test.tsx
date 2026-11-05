import { act, fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import api from './__fixtures__/api.json'

// The configured responses are pogf_geodetic_suite.timeseries.status run on the
// synthetic CRDs in services/bsw-console/tests/conftest.py (make_frontend_fixture.py).
const responses = api as Record<string, unknown>
const BASE = '/api/campaigns/LUZON/years/2021/time-series'

function serve(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.split('?')[0]
    const body = path in overrides ? overrides[path] : responses[path]
    if (body === undefined) return new Response(JSON.stringify({ detail: 'not in fixture' }), { status: 501 })
    return new Response(JSON.stringify(body), { status: 200 })
  }))
}
afterEach(() => vi.unstubAllGlobals())

async function settle() {
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

async function page() {
  window.location.hash = '#/c/LUZON/2021/time-series'
  render(<App />)
  await settle()
}

it('configured: a station shows its velocity, uncertainty, outliers, catalog sha256 and mode', async () => {
  serve()
  await page()
  expect(screen.queryByText(/not connected/i)).toBeNull()
  fireEvent.change(screen.getByLabelText(/Station/), { target: { value: 'SYN1' } })
  await settle()
  const st = responses[`${BASE}/SYN1`] as {
    velocity: { velocity_mm_yr: { e: number }; sigma_mm_yr: { e: number } }
    offsets_catalog: { sha256: string }
  }
  const east = `${st.velocity.velocity_mm_yr.e.toFixed(2)} ± ${st.velocity.sigma_mm_yr.e.toFixed(2)}`
  expect(screen.getAllByText(east).length).toBeGreaterThan(0)
  expect(screen.getByText(`sha256 ${st.offsets_catalog.sha256}`)).toBeTruthy()
  expect(screen.getByText(/1 of \d+ epochs/)).toBeTruthy()
  expect(screen.getAllByText('record').length).toBeGreaterThan(0)
  expect(screen.getByText(/flagged epochs are reported and kept in the fit/)).toBeTruthy()
  expect(screen.queryByText(/Could not read this/)).toBeNull()
})

it('not configured: the page says so and names the settings, instead of failing', async () => {
  serve({
    [BASE]: {
      configured: false,
      missing: ['BSW_CONSOLE_TS_CRD_DIR', 'BSW_CONSOLE_TS_OFFSETS'],
      message: 'The time series is not configured for this console: set BSW_CONSOLE_TS_CRD_DIR, BSW_CONSOLE_TS_OFFSETS (the daily final CRD directory and the offsets catalog).',
    },
  })
  await page()
  const status = screen.getByRole('status')
  expect(status.textContent).toMatch(/Not configured\./)
  expect(status.textContent).toMatch(/BSW_CONSOLE_TS_CRD_DIR/)
  expect(screen.queryByLabelText(/Station/)).toBeNull()
  expect(screen.queryByText(/Could not read this/)).toBeNull()
})

it('a default reference the files do not hold leaves every candidate pickable', async () => {
  const sum = responses[BASE] as Record<string, unknown>
  serve({ [BASE]: { ...sum, reference: 'GONE', default_reference: 'GONE', available: false, stations: [], message: 'GONE is not an estimated station in these CRD files.' } })
  await page()
  const pick = screen.getByLabelText('Reference station') as HTMLSelectElement
  expect(pick.value).toBe('')
  expect(screen.getByRole('option', { name: 'Choose a reference…' })).toBeTruthy()
})

it('a station is never shown under a reference it was not fitted against', async () => {
  serve()
  await page()
  fireEvent.change(screen.getByLabelText('Station'), { target: { value: 'SYN1' } })
  await settle()
  expect(screen.getByRole('heading', { name: /SYN1 · velocity/ })).toBeTruthy()
  // Make the shown station the reference: its old panel must go, not linger.
  fireEvent.change(screen.getByLabelText('Reference station'), { target: { value: 'SYN1' } })
  expect(screen.queryByRole('heading', { name: /SYN1 · velocity/ })).toBeNull()
  await settle()
  expect(screen.queryByRole('heading', { name: /SYN1 · velocity/ })).toBeNull()
})

it('after a reference change, the old fit is not shown while the new one fails', async () => {
  const sum = responses[BASE] as Record<string, unknown>
  const syn1 = responses[`${BASE}/SYN1`] as Record<string, unknown>
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const [path, qs] = url.split('?')
    const ref = new URLSearchParams(qs ?? '').get('reference') ?? 'REF0'
    if (path === BASE) {
      return new Response(JSON.stringify({ ...sum, reference: ref, all_stations: ['OTH1', 'REF0', 'SYN1'], stations: ['OTH1', 'REF0', 'SYN1'].filter((s) => s !== ref) }), { status: 200 })
    }
    if (path === `${BASE}/SYN1` && ref === 'REF0') return new Response(JSON.stringify({ ...syn1, reference: 'REF0' }), { status: 200 })
    return new Response(JSON.stringify({ detail: 'boom' }), { status: 500 })
  }))
  await page()
  fireEvent.change(screen.getByLabelText('Station'), { target: { value: 'SYN1' } })
  await settle()
  expect(screen.getByRole('heading', { name: /SYN1 · velocity/ })).toBeTruthy()
  fireEvent.change(screen.getByLabelText('Reference station'), { target: { value: 'OTH1' } })
  await settle()
  await settle()
  expect(screen.queryByRole('heading', { name: /SYN1 · velocity/ })).toBeNull()
})

describe('the time-series plot', () => {
  beforeEach(() => { (globalThis as any).__uplots.length = 0 })

  async function showSyn1() {
    serve()
    await page()
    fireEvent.change(screen.getByLabelText('Station'), { target: { value: 'SYN1' } })
    await settle()
    return (globalThis as any).__uplots as { opts: any; data: any[]; scales: any; over: HTMLElement; setScale: Function }[]
  }

  it('draws East, North and Up from the payload, on one shared time axis', async () => {
    const charts = await showSyn1()
    expect(charts).toHaveLength(3)
    expect(charts.map((c) => c.opts.axes[1].label)).toEqual(['East (mm)', 'North (mm)', 'Up (mm)'])
    const syn1 = responses[`${BASE}/SYN1`] as { series: { t: number[]; e_mm: number[]; outlier: boolean[] } }
    expect(charts[0].data[0]).toEqual(syn1.series.t)
    const flaggedAt = syn1.series.outlier.indexOf(true)
    expect(flaggedAt).toBeGreaterThanOrEqual(0)
    expect(charts[0].data[2][flaggedAt]).toBe(syn1.series.e_mm[flaggedAt])
    expect(new Set(charts.map((c) => c.opts.cursor.sync.key)).size).toBe(1)
  })

  it('zooming one panel zooms all three', async () => {
    const charts = await showSyn1()
    charts[1].setScale('x', { min: 2020.5, max: 2021.0 })
    for (const c of charts) expect(c.scales.x).toEqual({ min: 2020.5, max: 2021.0 })
  })

  it('a plain wheel leaves the page scrolling and the zoom alone', async () => {
    const charts = await showSyn1()
    const before = { ...charts[0].scales.x }
    const ev = new WheelEvent('wheel', { deltaY: -100, cancelable: true })
    Object.defineProperty(ev, 'offsetX', { value: 2021 })
    charts[2].over.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
    expect(charts[0].scales.x).toEqual(before)
  })

  it('shift + wheel pans all three panels', async () => {
    const charts = await showSyn1()
    charts[0].setScale('x', { min: 2020.5, max: 2021.0 })
    const ev = new WheelEvent('wheel', { deltaY: 100, shiftKey: true, cancelable: true })
    charts[1].over.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(true)
    for (const c of charts) {
      expect(c.scales.x.min).toBeCloseTo(2020.55)
      expect(c.scales.x.max - c.scales.x.min).toBeCloseTo(0.5)
    }
  })

  it('ctrl + wheel zooms in around the cursor', async () => {
    const charts = await showSyn1()
    const before = { ...charts[2].scales.x }
    const ev = new WheelEvent('wheel', { deltaY: -100, ctrlKey: true, cancelable: true })
    Object.defineProperty(ev, 'offsetX', { value: 2021 })
    charts[2].over.dispatchEvent(ev)
    const after = charts[0].scales.x
    expect(after.max - after.min).toBeLessThan(before.max - before.min)
    expect(ev.defaultPrevented).toBe(true)
  })
})


it('names the campaign and year it shows, and the year picker moves to another year', async () => {
  serve()
  await page()
  expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/LUZON 2021/)
  const pick = screen.getByLabelText('Year') as HTMLSelectElement
  expect(pick.value).toBe('2021')
  fireEvent.change(pick, { target: { value: '2025' } })
  expect(window.location.hash).toBe('#/c/LUZON/2025/time-series')
})
