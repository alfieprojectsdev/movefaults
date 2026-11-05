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
  window.location.hash = '#/c/LUZON/time-series'
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
      missing: ['BSW_CONSOLE_TS_CRD_DIR', 'BSW_CONSOLE_TS_REFERENCE', 'BSW_CONSOLE_TS_OFFSETS'],
      message: 'The time series is not configured for this console: set BSW_CONSOLE_TS_CRD_DIR, BSW_CONSOLE_TS_REFERENCE, BSW_CONSOLE_TS_OFFSETS (the daily final CRD directory, the reference station and the offsets catalog).',
    },
  })
  await page()
  const status = screen.getByRole('status')
  expect(status.textContent).toMatch(/Not configured\./)
  expect(status.textContent).toMatch(/BSW_CONSOLE_TS_CRD_DIR/)
  expect(screen.queryByLabelText(/Station/)).toBeNull()
  expect(screen.queryByText(/Could not read this/)).toBeNull()
})
