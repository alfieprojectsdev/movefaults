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
  ['#/c/LUZON/2025/stations', /BLQ, still by email/],
  ['#/c/LUZON/time-series', /Not connected/],
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
  expect(screen.getByText(/Start is off/).textContent).toMatch(/not enabled yet/)
})
