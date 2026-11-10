import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import App from './App'
import api from './__fixtures__/api.json'

// A live run, built from the fixture's halted one: days 1-2 solved, 3 failed,
// 4-5 running, 6-7 queued. Enough to exercise every jump link and filter.
const base = (api as Record<string, any>)['/api/campaigns/LUZON/years/2025/runs']
const outcomes = ['solved', 'solved', 'failed', 'running', 'running', 'queued', 'queued']
const live = {
  ...base,
  run: { ...base.run, state: 'running', halt: null, doys: [1, 7] },
  runs: [{ ...base.runs[0], state: 'running', halt: null }],
  rows: outcomes.map((outcome, i) => ({ ...base.rows[0], doy: i + 1, session: `${String(i + 1).padStart(3, '0')}0`, outcome })),
}

const scrolled: string[] = []
beforeEach(() => {
  scrolled.length = 0
  Element.prototype.scrollIntoView = function (this: Element) { scrolled.push(this.id) }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.split('?')[0]
    const body = path === '/api/campaigns/LUZON/years/2025/runs' ? live : (api as Record<string, unknown>)[path]
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
const doys = () => [...document.querySelectorAll('tbody tr')].map((tr) => tr.id)

it('says how many days run when the running span has gaps', async () => {
  live.rows[4] = { ...live.rows[4], outcome: 'queued' }
  live.rows[6] = { ...live.rows[6], outcome: 'running' }
  try {
    await at('#/c/LUZON/2025/run')
    expect(screen.getByRole('button', { name: 'Running now (DOY 004–007, 2 days)' })).toBeTruthy()
  } finally {
    live.rows[4] = { ...live.rows[4], outcome: 'running' }
    live.rows[6] = { ...live.rows[6], outcome: 'queued' }
  }
})

it('names the running block and jumps to it', async () => {
  await at('#/c/LUZON/2025/run')
  fireEvent.click(screen.getByRole('button', { name: 'Running now (DOY 004–005)' }))
  expect(scrolled).toEqual(['doy-004'])
  expect(document.getElementById('doy-004')!.className).toBe('hl')
})

it('opens on the running days when the link says at=running', async () => {
  await at('#/c/LUZON/2025/run?at=running')
  expect(scrolled).toEqual(['doy-004'])
})

it('opens on a named DOY, and ignores one that is not in the run', async () => {
  await at('#/c/LUZON/2025/run?at=6')
  expect(scrolled).toEqual(['doy-006'])
  cleanup() // one App at a time: a second one would also answer the hash change
  scrolled.length = 0
  await at('#/c/LUZON/2025/run?at=200')
  expect(scrolled).toEqual([])
})

it('filters the table by outcome, and a jump outside the filter shows every day again', async () => {
  await at('#/c/LUZON/2025/run')
  fireEvent.click(screen.getByRole('button', { name: 'running (2)' }))
  expect(doys()).toEqual(['doy-004', 'doy-005'])
  fireEvent.click(screen.getByRole('button', { name: 'First failed' }))
  expect(doys()).toHaveLength(7)
  expect(screen.getByRole('button', { name: 'all (7)' }).getAttribute('aria-pressed')).toBe('true')
})

it('makes the day counts links that jump to the first day of each kind', async () => {
  await at('#/c/LUZON/2025/run')
  fireEvent.click(screen.getByRole('button', { name: '1 failed' }))
  expect(scrolled).toEqual(['doy-003'])
  expect((screen.getByRole('button', { name: '2 queued' }) as HTMLButtonElement).disabled).toBe(false)
})
