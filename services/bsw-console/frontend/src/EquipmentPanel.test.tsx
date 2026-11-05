import { act, fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import api from './__fixtures__/api.json'

// The responses come from the real bernese-check-equipment report built in
// services/bsw-console/tests/conftest.py (make_frontend_fixture.py).
const responses = api as Record<string, unknown>

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

async function stations() {
  window.location.hash = '#/c/LUZON/2025/stations'
  render(<App />)
  await settle()
}

it('shows one station from the report, with the export time', async () => {
  serve()
  await stations()
  expect(screen.getByRole('heading', { name: /Equipment: the .STA file against field-ops/ })).toBeTruthy()
  expect(screen.getByText('2026-11-05T17:41:00+00:00')).toBeTruthy()
  fireEvent.change(screen.getByLabelText(/Station/), { target: { value: 'ALBU' } })
  await settle()
  expect(screen.getByText('different', { selector: '.badge' })).toBeTruthy()
  expect(screen.getByText('LEIAT504GG')).toBeTruthy()
  expect(screen.getByText('no STA row for the change')).toBeTruthy()
  expect(screen.queryByText(/Could not read this/)).toBeNull()
})

it('asks only for the chosen station', async () => {
  serve()
  await stations()
  const fetched = () => (fetch as unknown as { mock: { calls: string[][] } }).mock.calls.map((c) => c[0])
  expect(fetched().some((u) => u.includes('/api/stations/'))).toBe(false)
  fireEvent.change(screen.getByLabelText(/Station/), { target: { value: 'ALBU' } })
  await settle()
  expect(fetched()).toContain('/api/stations/ALBU/equipment')
})

it('says plainly when no report is configured, and offers no station picker', async () => {
  const none = { configured: false, message: 'No equipment report is configured for this console (BSW_CONSOLE_EQUIPMENT_REPORT), so there is nothing to compare this station\'s .STA equipment with.' }
  serve({ '/api/equipment-report': none })
  await stations()
  expect(screen.getByRole('status').textContent).toMatch(/No equipment report is configured/)
  expect(screen.queryByLabelText(/Station/)).toBeNull()
})

it('says so when the report cannot be read', async () => {
  serve({ '/api/equipment-report': { configured: true, available: false, message: 'The equipment report equipment_report.json could not be read: JSONDecodeError.' } })
  await stations()
  expect(screen.getByRole('status').textContent).toMatch(/could not be read/)
  expect(screen.queryByLabelText(/Station/)).toBeNull()
})
