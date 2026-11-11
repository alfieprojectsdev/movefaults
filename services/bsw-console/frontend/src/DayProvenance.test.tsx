import { act, render, screen, within } from '@testing-library/react'
import App from './App'
import api from './__fixtures__/api.json'

// Day 035 in the fixture has one attempt, from a run written before #318 (no
// provenance in its run_start). The "new run" case adds one written after,
// with the fields bsw_console.status.run_provenance returns.
const responses = api as Record<string, unknown>
const DAY = '/api/campaigns/LUZON/years/2025/days/35'

function serve(overrides: Record<string, unknown> = {}) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.split('?')[0]
    const body = path in overrides ? overrides[path] : responses[path]
    if (body === undefined) return new Response(JSON.stringify({ detail: 'not in fixture' }), { status: 501 })
    return new Response(JSON.stringify(body), { status: 200 })
  }))
}
afterEach(() => vi.unstubAllGlobals())

async function day() {
  window.location.hash = '#/c/LUZON/2025/day/35'
  render(<App />)
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

const recorded = {
  recorded: true, started_by: 'processing', command: 'bernese-run-year --campaign LUZON --run',
  code_version: '0123456789', pcf: 'LUZON_DLY', products: 'COD0OPSFIN', product_tier: 'final', config_hash: 'def',
}

function withNewRun() {
  const base = JSON.parse(JSON.stringify(responses[DAY])) as {
    attempts: Record<string, unknown>[]; provenance: Record<string, unknown>
  }
  const old = base.attempts[0]
  base.attempts = [{ ...old, run: 'r2', provenance: recorded }, ...base.attempts]
  base.provenance = { ...base.provenance, ...recorded, pcf: 'LUZON_DLY.PCF', run: 'r2' }
  return base
}

it('an old run: every provenance field says not recorded, nothing is invented', async () => {
  serve()
  await day()
  const block = screen.getByRole('heading', { name: 'How this result was produced' }).parentElement!
  expect(within(block).getAllByText('not recorded for this run').length).toBe(4)
  expect(within(block).getByText('r1')).toBeTruthy()
  const rows = within(screen.getByRole('heading', { name: 'Attempts' }).parentElement!).getAllByRole('row')
  expect(within(rows[1]).getByText('not recorded for this run')).toBeTruthy()
})

it('a new run: its own record is shown, and an older run still says not recorded', async () => {
  serve({ [DAY]: withNewRun() })
  await day()
  const block = screen.getByRole('heading', { name: 'How this result was produced' }).parentElement!
  expect(within(block).queryByText('not recorded for this run')).toBeNull()
  expect(within(block).getByText('processing')).toBeTruthy()
  expect(within(block).getByText('bernese-run-year --campaign LUZON --run')).toBeTruthy()
  expect(within(block).getByText('0123456789')).toBeTruthy()
  expect(within(block).getByText('COD0OPSFIN')).toBeTruthy()
  const rows = within(screen.getByRole('heading', { name: 'Attempts' }).parentElement!).getAllByRole('row')
  expect(rows[1].textContent).toMatch(/by processing · code 0123456789 · COD0OPSFIN \(final\)/)
  expect(within(rows[2]).getByText('not recorded for this run')).toBeTruthy()
})

it('quality: one row per ambiguity method, from the day summary', async () => {
  serve()
  await day()
  const block = screen.getByRole('heading', { name: 'Quality' }).parentElement!
  const rows = within(block).getAllByRole('row')
  expect(rows.map((r) => r.textContent)).toEqual([
    'MethodBaselinesAmbiguitiesLeft unresolvedResolved',
    'Code-Based Narrowlane (NL)13, under 6000 km87831763.9%',
    'Phase-Based Narrowlane (L3)23, under 200 km207273864.4%',
  ])
  expect(within(block).getByText('OUT/R2S_20250350.PRC:4')).toBeTruthy()
})

it('quality: a summary without the ambiguity part says so, with no table', async () => {
  const base = JSON.parse(JSON.stringify(responses[DAY])) as { quality: Record<string, unknown> }
  base.quality = { ...base.quality, ambiguities: null }
  serve({ [DAY]: base })
  await day()
  const block = screen.getByRole('heading', { name: 'Quality' }).parentElement!
  expect(within(block).getByText("not in this day's summary")).toBeTruthy()
  expect(within(block).queryByRole('table')).toBeNull()
})
