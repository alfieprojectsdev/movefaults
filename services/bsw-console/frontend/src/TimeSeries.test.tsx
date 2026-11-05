import { act, fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import api from './__fixtures__/api.json'

// The configured responses are pogf_geodetic_suite.timeseries.status run on the
// synthetic CRDs in services/bsw-console/tests/conftest.py (make_frontend_fixture.py).
const responses = api as Record<string, unknown>
const BASE = '/api/campaigns/LUZON/time-series'

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
      missing: ['BSW_CONSOLE_TS_OFFSETS'],
      message: 'The time series is not configured for this console: set BSW_CONSOLE_TS_OFFSETS (the offsets catalog).',
    },
  })
  await page()
  const status = screen.getByRole('status')
  expect(status.textContent).toMatch(/Not configured\./)
  expect(status.textContent).toMatch(/BSW_CONSOLE_TS_OFFSETS/)
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


it('names the campaign and every yearly folder it reads, whichever year the address carries', async () => {
  serve()
  await page()
  expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/LUZON$/)
  expect(screen.getByText(/2020\/STA, .*2021\/STA/)).toBeTruthy()
  expect((globalThis.fetch as any).mock.calls.every(([u]: [string]) => !u.includes('/years/2021/time-series'))).toBe(true)
})

it('a far-away reference is warned about above the plot, once, and the distance is always shown', async () => {
  const st = responses[`${BASE}/SYN1`] as object
  const warning = 'the reference REF0 is 19.4 degrees from SYN1: East, North and Up are the axes'
  serve({ [`${BASE}/SYN1`]: { ...st, reference_distance_deg: 19.4, reference_warning: warning, warnings: [warning] } })
  await page()
  fireEvent.change(screen.getByLabelText(/Station/), { target: { value: 'SYN1' } })
  await settle()
  expect(screen.getAllByText(new RegExp(warning))).toHaveLength(1)
  expect(screen.getByText(/REF0, 19\.4° from SYN1/)).toBeTruthy()
})

it('a near reference shows its distance and no warning', async () => {
  serve()
  await page()
  fireEvent.change(screen.getByLabelText(/Station/), { target: { value: 'SYN1' } })
  await settle()
  expect(screen.getByText(/REF0, \d+\.\d° from SYN1/)).toBeTruthy()
  expect(screen.queryByText(/rotates the station's motion/)).toBeNull()
})

describe('the year buttons and the range in view', () => {
  beforeEach(() => { (globalThis as any).__uplots.length = 0 })

  async function plot() {
    serve()
    await page()
    fireEvent.change(screen.getByLabelText(/Station/), { target: { value: 'SYN1' } })
    await settle()
    return (globalThis as any).__uplots as { scales: { x: { min: number; max: number } }; setScale: (k: string, r: object) => void; destroyed: boolean }[]
  }

  it('a year button moves every panel to that year; the velocity is still the whole series', async () => {
    const charts = await plot()
    const velocity = screen.getAllByText(/±/)[0].textContent
    fireEvent.click(screen.getByRole('button', { name: '2021' }))
    for (const c of charts) {
      expect(Math.floor(c.scales.x.min)).toBe(2021)
      expect(c.scales.x.max).toBeLessThan(2022.01)
    }
    expect(screen.getAllByText(/±/)[0].textContent).toBe(velocity)
    fireEvent.click(screen.getByRole('button', { name: 'All years' }))
    expect(Math.floor(charts[0].scales.x.min)).toBe(2020)
  })
})

describe('recording an outlier decision', () => {
  beforeEach(() => { (globalThis as any).__uplots.length = 0 })

  function serveWith(user: string | null, posts: { url: string; body: any }[]) {
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        posts.push({ url, body: JSON.parse(String(init.body)) })
        return new Response(JSON.stringify({ by: user }), { status: 201 })
      }
      const path = url.split('?')[0]
      if (path === '/api/session') return new Response(JSON.stringify({ ...(responses['/api/session'] as object), user }), { status: 200 })
      const body = responses[path]
      if (body === undefined) return new Response(JSON.stringify({ detail: 'not in fixture' }), { status: 501 })
      return new Response(JSON.stringify(body), { status: 200 })
    }))
  }

  async function pickEpoch(i: number) {
    fireEvent.change(screen.getByLabelText('Station'), { target: { value: 'SYN1' } })
    await settle()
    const chart = (globalThis as any).__uplots[0]
    chart.cursor.idx = i
    chart.over.dispatchEvent(new MouseEvent('mousedown', { clientX: 10, clientY: 10 }))
    chart.over.dispatchEvent(new MouseEvent('click', { clientX: 10, clientY: 10 }))
    await settle()
  }

  const syn1 = () => responses[`${BASE}/SYN1`] as { series: { outlier: boolean[] } }

  it('a click picks the epoch, and confirming its flag is recorded with the reference', async () => {
    const posts: { url: string; body: any }[] = []
    serveWith('abc', posts)
    await page()
    const i = syn1().series.outlier.indexOf(true)
    await pickEpoch(i)
    expect(screen.getByRole('heading', { name: /SYN1 · 2021-/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Mark as outlier' })).toBeNull()
    await act(async () => { screen.getByRole('button', { name: 'Confirm outlier' }).click() })
    await settle()
    expect(posts).toHaveLength(1)
    expect(posts[0].url).toBe(`${BASE}/SYN1/decisions`)
    expect(posts[0].body).toMatchObject({ decision: 'outlier', reference: 'REF0', auto_flag: true })
    expect(screen.getByText(/published velocity is unchanged/)).toBeTruthy()
  })

  it('recording a decision rebuilds the plot without losing the range in view', async () => {
    serveWith('abc', [])
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(true))
    const charts = (globalThis as any).__uplots
    const first = charts[0]
    first.setScale('x', { min: 2021.2, max: 2021.4 })
    await act(async () => { screen.getByRole('button', { name: 'Confirm outlier' }).click() })
    await settle()
    expect(first.destroyed).toBe(true)
    const live = charts.filter((c: { destroyed: boolean }) => !c.destroyed)
    expect(live).toHaveLength(3)
    for (const c of live) expect(c.scales.x).toEqual({ min: 2021.2, max: 2021.4 })
  })

  it('going against the flag asks for a reason before anything is recorded', async () => {
    const posts: { url: string; body: any }[] = []
    serveWith('abc', posts)
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(false))
    expect(screen.queryByRole('button', { name: 'Confirm outlier' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Mark as outlier' }))
    expect(posts).toHaveLength(0)
    const record = () => screen.getByRole('button', { name: 'Record as abc' }) as HTMLButtonElement
    expect(record().disabled).toBe(true)
    fireEvent.change(screen.getByLabelText(/Why is this an outlier/), { target: { value: 'multipath' } })
    expect(record().disabled).toBe(false)
    await act(async () => { record().click() })
    await settle()
    expect(posts[0].body).toMatchObject({ decision: 'outlier', reason: 'multipath', auto_flag: false })
  })

  it('a refusal for want of a reason opens the reason box; a network failure re-enables the buttons', async () => {
    let mode: 'refuse' | 'throw' = 'refuse'
    serveWith('abc', [])
    const served = globalThis.fetch as any
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        if (mode === 'throw') throw new TypeError('Failed to fetch')
        return new Response(JSON.stringify({ detail: 'A decision against the automatic flag needs a reason; it is kept with the epoch.' }), { status: 422 })
      }
      return served(url, init)
    }))
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(true))
    await act(async () => { screen.getByRole('button', { name: 'Confirm outlier' }).click() })
    await settle()
    expect(screen.getByText(/needs a reason/)).toBeTruthy()
    expect(screen.getByLabelText(/Why is this an outlier/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    mode = 'throw'
    await act(async () => { screen.getByRole('button', { name: 'Confirm outlier' }).click() })
    await settle()
    expect(screen.getByText(/Not recorded: Failed to fetch/)).toBeTruthy()
    expect((screen.getByRole('button', { name: 'Confirm outlier' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('cancel leaves the epoch undecided', async () => {
    const posts: { url: string; body: any }[] = []
    serveWith('abc', posts)
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(true))
    fireEvent.click(screen.getByRole('button', { name: 'Keep it: not an outlier' }))
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('button', { name: 'Confirm outlier' })).toBeTruthy()
    expect(posts).toHaveLength(0)
  })

  it('a drag does not pick, and signed out there is no form', async () => {
    serveWith(null, [])
    await page()
    fireEvent.change(screen.getByLabelText('Station'), { target: { value: 'SYN1' } })
    await settle()
    const chart = (globalThis as any).__uplots[0]
    chart.cursor.idx = 3
    chart.over.dispatchEvent(new MouseEvent('mousedown', { clientX: 10, clientY: 10 }))
    chart.over.dispatchEvent(new MouseEvent('click', { clientX: 90, clientY: 10 }))
    await settle()
    expect(screen.queryByText(/Sign in to record/)).toBeNull()
    chart.over.dispatchEvent(new MouseEvent('mousedown', { clientX: 10, clientY: 10 }))
    chart.over.dispatchEvent(new MouseEvent('click', { clientX: 10, clientY: 10 }))
    await settle()
    expect(screen.getByText(/Sign in to record/)).toBeTruthy()
  })
})
