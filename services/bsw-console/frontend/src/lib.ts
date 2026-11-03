import { useEffect, useState } from 'react'

export type Loaded<T> = { data: T | null; error: string | null; loading: boolean; reload: () => void }

/** GET a console endpoint. Errors are shown, never swallowed. */
export function useApi<T>(url: string | null): Loaded<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [tick, setTick] = useState(0)
  useEffect(() => {
    if (!url) return
    let live = true
    setLoading(true)
    setError(null)
    fetch(url)
      .then(async (r) => {
        const body = await r.json().catch(() => ({}))
        if (!r.ok) throw new Error(body.detail || body.reason || `${r.status} ${r.statusText}`)
        return body as T
      })
      .then((d) => live && setData(d))
      .catch((e) => live && setError(String(e.message || e)))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [url, tick])
  return { data, error, loading, reload: () => setTick((t) => t + 1) }
}

export const pad3 = (n: number) => String(n).padStart(3, '0')

/** "2026-02-14, DOY 045": dates always carry the DOY. */
export const dayLabel = (date: string, doy: number) => `${date}, DOY ${pad3(doy)}`

/** Local time (UTC+8 on gps3's office PCs), with UTC on hover. */
export function when(ts: number | null | undefined): { text: string; utc: string } {
  if (!ts) return { text: '—', utc: '' }
  const d = new Date(ts * 1000)
  const text = d.toLocaleString('en-GB', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', hour12: false })
  return { text, utc: d.toISOString().replace('T', ' ').slice(0, 16) + ' UTC' }
}

export function duration(s: number | null | undefined): string {
  if (s == null) return ''
  const m = Math.floor(s / 60)
  const sec = Math.round(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}

export function size(b: number | null | undefined): string {
  if (b == null) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${Math.round(b / 1024)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

/** Line classes for a BSW protocol file: *** errors, ### warnings, ERR status lines. */
export function lineClass(text: string, hit?: string): string {
  if (hit && text.toUpperCase().includes(hit.toUpperCase())) return 'hit'
  if (text.includes('***')) return 'err'
  if (text.includes('###') || / ERR /.test(text)) return 'warn'
  return ''
}

export async function post<T>(url: string, body: unknown): Promise<{ ok: boolean; status: number; body: T }> {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  return { ok: r.ok, status: r.status, body: (await r.json().catch(() => ({}))) as T }
}
