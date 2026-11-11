import { act, render, screen } from '@testing-library/react'
import App from './App'
import api from './__fixtures__/api.json'

// Every screen renders against responses from the synthetic tree in
// services/bsw-console/tests/conftest.py (make_frontend_fixture.py).
const responses = api as Record<string, unknown>

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.split('?')[0]
    const body = responses[path]
    if (body === undefined) return new Response(JSON.stringify({ detail: 'not in fixture' }), { status: 501 })
    return new Response(JSON.stringify(body), { status: 200 })
  }))
})
afterEach(() => vi.unstubAllGlobals())

async function at(hash: string) {
  window.location.hash = hash
  render(<App />)
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

const screens: [string, RegExp][] = [
  ['#/', /Recent activity/],
  ['#/c/LUZON/2025', /One square per day/],
  ['#/c/LUZON/2025/run', /Identical failures in a row/],
  ['#/c/LUZON/2025/day/35', /How this result was produced/],
  ['#/c/LUZON/2025/day/36/failure', /Known-errors list/],
  ['#/c/LUZON/2025/day/35/redo', /What will be moved/],
  ['#/c/LUZON/2025/plan?from=35&to=40', /Checks before the run/],
  ['#/known-errors', /The list the run looks failures up in/],
  ['#/c/LUZON/2025/inventory', /RINEX in the datapool/],
  ['#/c/LUZON/2025/stations', /Ocean loading \(BLQ\)/],
  ['#/c/LUZON/2021/time-series', /Outlier mode/],
]

describe.each(screens)('%s', (hash, text) => {
  it('renders', async () => {
    await at(hash)
    expect(screen.getAllByText(text).length).toBeGreaterThan(0)
    expect(screen.queryByText(/Could not read this/)).toBeNull()
  })
})

it('names the failed PID and the known remedy', async () => {
  await at('#/c/LUZON/2025/day/36/failure')
  expect(screen.getByRole('heading', { level: 1 }).textContent).toMatch(/PID 513 HELMCHK/)
  expect(screen.getByText('Counted, and the run continued.')).toBeTruthy()
})

it('keeps Start disabled and says why', async () => {
  await at('#/c/LUZON/2025/plan?from=35&to=40')
  expect((screen.getByRole('button', { name: 'Start' }) as HTMLButtonElement).disabled).toBe(true)
  expect(screen.getByText(/Start is off/).textContent).toMatch(/switched off \(BSW_CONSOLE_ACTIONS\)/)
})

describe('stage 3 buttons', () => {
  function answer(status: number, body: unknown) {
    const get = (globalThis.fetch as unknown as (u: string) => Promise<Response>)
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) =>
      init?.method === 'POST' ? new Response(JSON.stringify(body), { status }) : get(url)))
  }

  it('says what was queued, and by whom, when the worker accepts', async () => {
    answer(202, { queued: '20261105T021500.000000Z-0a1b2c3d', kind: 'preflight', by: 'abc' })
    await at('#/c/LUZON/2025/plan?from=35&to=40')
    await act(async () => { screen.getByRole('button', { name: 'Queue preflight' }).click() })
    expect(screen.getByRole('status').textContent).toMatch(/Preflight queued as 20261105T021500\.000000Z-0a1b2c3d by abc/)
  })

  it('shows the gate\'s reason when nothing was queued', async () => {
    answer(503, { detail: 'No run worker is running on gps3, so nothing was queued.' })
    await at('#/c/LUZON/2025/plan?from=35&to=40')
    await act(async () => { screen.getByRole('button', { name: 'Queue preflight' }).click() })
    expect(screen.getByRole('status').textContent).toMatch(/No run worker is running on gps3/)
  })
})


describe('time series reference', () => {
  it('starts on the default and re-asks the server when another reference is chosen', async () => {
    const urls: string[] = []
    const get = (globalThis.fetch as unknown as (u: string) => Promise<Response>)
    vi.stubGlobal('fetch', vi.fn(async (url: string) => { urls.push(url); return get(url) }))
    await at('#/c/LUZON/2021/time-series')
    const pick = screen.getByLabelText('Reference station') as HTMLSelectElement
    expect(pick.value).toBe('REF0')
    expect(screen.getByRole('option', { name: 'REF0 (default)' })).toBeTruthy()
    await act(async () => {
      pick.value = 'SYN1'
      pick.dispatchEvent(new Event('change', { bubbles: true }))
      await new Promise((r) => setTimeout(r, 0))
    })
    expect(urls.some((u) => u.endsWith('/api/campaigns/LUZON/time-series?reference=SYN1'))).toBe(true)
  })
})
