import { act, fireEvent, render, screen, within } from '@testing-library/react'
import App from './App'
import api from './__fixtures__/api.json'

const responses = api as Record<string, unknown>
const BASE = '/api/campaigns/LUZON/years/2025/station-files'

function serve(check?: unknown) {
  const calls: { url: string; body: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.split('?')[0]
    if (init?.method === 'POST') {
      calls.push({ url: path, body: JSON.parse(String(init.body)) })
      return new Response(JSON.stringify(check), { status: 200 })
    }
    const body = responses[path]
    if (body === undefined) return new Response(JSON.stringify({ detail: 'not in fixture' }), { status: 501 })
    return new Response(JSON.stringify(body), { status: 200 })
  }))
  return calls
}
afterEach(() => vi.unstubAllGlobals())

async function page() {
  window.location.hash = '#/c/LUZON/2025/stations'
  render(<App />)
  await act(async () => { await new Promise((r) => setTimeout(r, 0)) })
}

it('gives the lines for the Onsala form, from the CRD', async () => {
  serve()
  await page()
  expect((screen.getByLabelText('Lines for the Onsala form') as HTMLTextAreaElement).value).toBe('BILI 1.00000 2.00000 3.00000')
  expect(screen.getByText(/Listed under two names in the CRD/)).toBeTruthy()
})

it('sends the pasted reply to be checked and shows the verdict and the command', async () => {
  const calls = serve({
    campaign: 'LUZON', blq: '/srv/bsw/LUZON.BLQ', problems: [], settings_differ: [], new: ['BILI'], ready: true,
    command: 'scripts/merge_blq.py --blq /srv/bsw/LUZON.BLQ --new <the reply, saved as a file>',
    stations: [{ station: 'BILI', status: 'new', key_line: 'ok', problems: [] }],
  })
  await page()
  fireEvent.change(screen.getByLabelText(/paste the emailed reply/), { target: { value: '  BILI\n...' } })
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Check the reply' })) })
  expect(calls).toEqual([{ url: `${BASE}/blq-check`, body: { reply: '  BILI\n...' } }])
  const result = screen.getByLabelText('Reply check')
  expect(within(result).getByText(/Ready to merge/)).toBeTruthy()
  expect(within(result).getByText(/scripts\/merge_blq.py --blq/)).toBeTruthy()
})

it('shows what using a final CRD as a priori would change, largest first', async () => {
  const preview = {
    ...(responses[`${BASE}/apriori-preview`] as object),
    rows: [
      { station: 'BLN2 BLN2', change: 'moved', neu_mm: [2997.0, 3750.7, 539.2], horizontal_mm: 4801.0 },
      { station: 'NEWS NEWS', change: 'added', neu_mm: null, horizontal_mm: null },
    ],
    warnings: ['The a priori is IGS14 and the final is IGS20: the differences include the change of frame, not only new positions.'],
  }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    const path = url.split('?')[0]
    const body = path === `${BASE}/apriori-preview` ? preview : responses[path]
    return new Response(JSON.stringify(body ?? { detail: 'x' }), { status: body ? 200 : 501 })
  }))
  await page()
  const block = screen.getByRole('heading', { name: /Use a final CRD as a priori/ }).parentElement!
  const rows = within(block).getAllByRole('row').map((r) => r.textContent)
  expect(rows[1]).toBe('BLN2 BLN22997.03750.7539.24801.0')
  expect(rows[2]).toMatch(/would be added/)
  expect(within(block).getByText(/change of frame/)).toBeTruthy()
})
