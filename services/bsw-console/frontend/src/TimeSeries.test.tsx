import { act, fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import { coreStations } from './stationMap'
import { popupPlace } from './pages/OutlierDecision'
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

  it('the popup sits over the plot, and Escape, the close button or a zoom closes it', async () => {
    serveWith('abc', [])
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(true))
    const dialog = () => screen.queryByRole('dialog')
    expect(dialog()!.parentElement!.querySelector('[data-testid="ts-plot"]')).toBeTruthy()
    fireEvent.keyDown(document, { key: 'Escape' })
    await settle()
    expect(dialog()).toBeNull()

    const chart = (globalThis as any).__uplots[0]
    chart.cursor.idx = 3
    chart.over.dispatchEvent(new MouseEvent('mousedown', { clientX: 10, clientY: 10 }))
    chart.over.dispatchEvent(new MouseEvent('click', { clientX: 10, clientY: 10 }))
    await settle()
    expect(dialog()).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    await settle()
    expect(dialog()).toBeNull()

    chart.over.dispatchEvent(new MouseEvent('mousedown', { clientX: 10, clientY: 10 }))
    chart.over.dispatchEvent(new MouseEvent('click', { clientX: 10, clientY: 10 }))
    await settle()
    expect(dialog()).toBeTruthy()
    await act(async () => { chart.setScale('x', { min: 2021.1, max: 2021.2 }) })
    await act(async () => { chart.setScale('x', { min: 2021.3, max: 2021.4 }) })
    await settle()
    expect(dialog()).toBeNull()
  })

  it('a click elsewhere closes it, a click on the plot does not, and Escape leaves a half-written reason first', async () => {
    serveWith('abc', [])
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(false))
    fireEvent.mouseDown(screen.getByTestId('ts-plot'))
    await settle()
    expect(screen.getByRole('dialog')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Mark as outlier' }))
    fireEvent.keyDown(document, { key: 'Escape' })
    await settle()
    expect(screen.getByRole('button', { name: 'Mark as outlier' })).toBeTruthy()
    fireEvent.mouseDown(document.body)
    await settle()
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('a click elsewhere does not throw away a reason being typed', async () => {
    serveWith('abc', [])
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(false))
    fireEvent.click(screen.getByRole('button', { name: 'Mark as outlier' }))
    fireEvent.change(screen.getByLabelText(/Why is this an outlier/), { target: { value: 'multipath' } })
    fireEvent.mouseDown(document.body)
    await settle()
    expect((screen.getByLabelText(/Why is this an outlier/) as HTMLTextAreaElement).value).toBe('multipath')
  })

  it('recording closes the popup and says what happened under the plot', async () => {
    serveWith('abc', [])
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(true))
    await act(async () => { screen.getByRole('button', { name: 'Confirm outlier' }).click() })
    await settle()
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByRole('status').textContent).toMatch(/recorded as outlier by abc\. The published velocity is unchanged/)
  })

  // Holds back what `held` matches until release() is called, to look inside the
  // time a request is in flight.
  function holdBack(held: (url: string, init?: RequestInit) => boolean) {
    const served = globalThis.fetch as any
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => { release = resolve })
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (held(url, init)) await gate
      return served(url, init)
    }))
    return () => release()
  }
  const isPost = (_url: string, init?: RequestInit) => init?.method === 'POST'

  it('a refusal that arrives after the popup has closed is still shown', async () => {
    serveWith('abc', [])
    const served = globalThis.fetch as any
    let answer: (r: Response) => void = () => {}
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') return new Promise<Response>((resolve) => { answer = resolve })
      return served(url, init)
    }))
    await page()
    await pickEpoch(syn1().series.outlier.indexOf(true))
    await act(async () => { screen.getByRole('button', { name: 'Confirm outlier' }).click() })
    fireEvent.mouseDown(document.body)
    await settle()
    expect(screen.queryByRole('dialog')).toBeNull()
    await act(async () => { answer(new Response(JSON.stringify({ detail: 'the lock is held' }), { status: 409 })) })
    await settle()
    expect(screen.getByRole('status').textContent).toMatch(/SYN1 2021-\d+: the lock is held/)
  })

  it('a decision answered late leaves the next epoch\'s popup open', async () => {
    serveWith('abc', [])
    const release = holdBack(isPost)
    await page()
    const flags = syn1().series.outlier
    await pickEpoch(flags.indexOf(true))
    await act(async () => { screen.getByRole('button', { name: 'Confirm outlier' }).click() })
    await pickEpoch(flags.indexOf(false))
    expect(screen.getByRole('button', { name: 'Mark as outlier' })).toBeTruthy()
    await act(async () => { release() })
    await settle()
    expect(screen.getByRole('button', { name: 'Mark as outlier' })).toBeTruthy()
    expect(screen.getByRole('status').textContent).toMatch(/recorded as outlier/)
  })

  it('an epoch reopened before the reload arrives cannot be decided twice', async () => {
    const posts: { url: string; body: any }[] = []
    serveWith('abc', posts)
    await page()
    const i = syn1().series.outlier.indexOf(true)
    await pickEpoch(i)
    const release = holdBack((url, init) => !init?.method && url.includes('/SYN1'))
    await act(async () => { screen.getByRole('button', { name: 'Confirm outlier' }).click() })
    await settle()
    expect(screen.queryByRole('dialog')).toBeNull()
    await pickEpoch(i)
    expect((screen.getByRole('button', { name: 'Confirm outlier' }) as HTMLButtonElement).disabled).toBe(true)
    await act(async () => { release() })
    await settle()
    expect(posts).toHaveLength(1)
    expect((screen.getByRole('button', { name: 'Confirm outlier' }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('each epoch clicked does not ask for the session again', async () => {
    serveWith('abc', [])
    await page()
    const flags = syn1().series.outlier
    await pickEpoch(flags.indexOf(true))
    const sessions = () => (globalThis.fetch as any).mock.calls.filter(([u]: [string]) => u === '/api/session').length
    const before = sessions()
    await pickEpoch(flags.indexOf(false))
    expect(sessions()).toBe(before)
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

describe('where the popup goes', () => {
  const size = { width: 340, height: 200 }
  const area = { width: 1000, height: 600 }

  it('beside the point, on its right when it fits', () => {
    expect(popupPlace({ x: 100, y: 300 }, size, area)).toEqual({ left: 114, top: 276 })
  })
  it('flips to the left at the right edge', () => {
    expect(popupPlace({ x: 900, y: 300 }, size, area).left).toBe(900 - 14 - 340)
  })
  it('stays inside the plot at the top and bottom', () => {
    expect(popupPlace({ x: 100, y: 5 }, size, area).top).toBe(0)
    expect(popupPlace({ x: 100, y: 590 }, size, area).top).toBe(400)
  })
  it('on a plot narrower than the popup, starts at its edge', () => {
    expect(popupPlace({ x: 100, y: 50 }, size, { width: 320, height: 600 }).left).toBe(0)
  })
})

describe('the station map', () => {
  const leaflet = () => (globalThis as any).__leaflet
  const mark = (label: RegExp) => leaflet().markers.find((m: { label: string }) => label.test(m.label))

  beforeEach(() => { leaflet().fits.length = 0 })

  it('draws every station, names the reference and each distance, and rings the warning distance', async () => {
    serve()
    await page()
    const sum = responses[BASE] as { all_stations: string[]; reference_warn_deg: number; distances: Record<string, number> }
    expect(leaflet().markers).toHaveLength(sum.all_stations.length)
    expect(mark(/^REF0, reference$/).permanent).toBe(true)
    expect(mark(/^SYN1, \d+\.\d° from REF0$/)).toBeTruthy()
    const { opts } = leaflet().circles[0]
    expect(opts.radius).toBe(sum.reference_warn_deg * 111_195)
    expect(leaflet().fits.length).toBe(1)
  })

  it('a click sets the station, and with Reference pressed sets the reference; the dropdowns follow', async () => {
    const urls: string[] = []
    serve()
    const get = globalThis.fetch as unknown as (u: string) => Promise<Response>
    vi.stubGlobal('fetch', vi.fn(async (u: string) => { urls.push(u); return get(u) }))
    await page()
    await act(async () => { mark(/^SYN1/).handlers.click() })
    await settle()
    expect(urls.some((u) => u.split('?')[0] === `${BASE}/SYN1`)).toBe(true)
    expect((screen.getByRole('heading', { name: /SYN1 · east/ }))).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: 'Reference' }))
    await act(async () => { mark(/^SYN1/).handlers.click() })
    await settle()
    expect(urls.some((u) => u.endsWith(`${BASE}?reference=SYN1`))).toBe(true)
    expect(screen.getByRole('button', { name: 'Station' }).getAttribute('aria-pressed')).toBe('true')
  })

  it('a click on the reference itself does not make it the station', async () => {
    serve()
    await page()
    await act(async () => { mark(/^REF0/).handlers.click() })
    await settle()
    expect(screen.queryByRole('heading', { name: /REF0 · east/ })).toBeNull()
  })

  it('a station past the warning distance is coloured apart', async () => {
    const sum = responses[BASE] as object
    serve({ [BASE]: { ...sum, distances: { SYN1: 19.4 } } })
    await page()
    expect(mark(/^SYN1, 19\.4°/).opts.fillColor).not.toBe(mark(/^REF0/).opts.fillColor)
  })
})

describe('coreStations', () => {
  it('leaves out far fiducials, which the median cannot be pulled by', () => {
    const p = {
      A: { lat: 14, lon: 121 }, B: { lat: 15, lon: 120 }, C: { lat: 16, lon: 122 },
      ALIC: { lat: -23, lon: 134 }, DAEJ: { lat: 36, lon: 127 },
    }
    expect(coreStations(p).sort()).toEqual(['A', 'B', 'C'])
  })
  it('never leaves nothing', () => {
    expect(coreStations({})).toEqual([])
    expect(coreStations({ A: { lat: 0, lon: 0 } })).toEqual(['A'])
  })
})
