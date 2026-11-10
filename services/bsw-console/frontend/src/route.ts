import { useEffect, useState } from 'react'

/** Hash routes, so the server serves one page and a link names the campaign:
 *  two tabs can show two campaigns (brief, section 4). */
export type Route =
  | { page: 'campaigns' }
  | { page: 'calendar'; campaign: string; year: number }
  /** `at` scrolls the day table to a DOY, or to the first day that is `running`,
   *  `failed` or `queued`, so a link can open on the part that matters. */
  | { page: 'run'; campaign: string; year: number; run?: string; at?: string }
  | { page: 'day'; campaign: string; year: number; doy: number }
  | { page: 'failure'; campaign: string; year: number; doy: number }
  | { page: 'redo'; campaign: string; year: number; doy: number }
  | { page: 'plan'; campaign: string; year: number; from?: number; to?: number }
  | { page: 'known-errors' }
  | { page: 'stations'; campaign: string; year: number }
  | { page: 'time-series'; campaign: string; year: number }

export function parse(hash: string): Route {
  const [path, query = ''] = hash.replace(/^#\/?/, '').split('?')
  const q = new URLSearchParams(query)
  const p = path.split('/').filter(Boolean)
  const num = (v: string | null | undefined) => (v && /^\d+$/.test(v) ? Number(v) : undefined)
  if (p[0] === 'known-errors') return { page: 'known-errors' }
  if (p[0] === 'c' && p[1]) {
    const campaign = p[1].toUpperCase()
    // The year-less form is what earlier links used: it opens this year.
    if (p[2] === 'time-series') return { page: 'time-series', campaign, year: new Date().getFullYear() }
    const year = num(p[2]) ?? new Date().getFullYear()
    const what = p[3]
    if (what === 'run') return { page: 'run', campaign, year, run: q.get('run') || undefined, at: q.get('at') || undefined }
    if (what === 'plan') return { page: 'plan', campaign, year, from: num(q.get('from')), to: num(q.get('to')) }
    if (what === 'stations') return { page: 'stations', campaign, year }
    if (what === 'time-series') return { page: 'time-series', campaign, year }
    if (what === 'day' && num(p[4])) {
      const doy = num(p[4])!
      if (p[5] === 'failure') return { page: 'failure', campaign, year, doy }
      if (p[5] === 'redo') return { page: 'redo', campaign, year, doy }
      return { page: 'day', campaign, year, doy }
    }
    return { page: 'calendar', campaign, year }
  }
  return { page: 'campaigns' }
}

export const href = {
  campaigns: () => '#/',
  calendar: (c: string, y: number) => `#/c/${c}/${y}`,
  run: (c: string, y: number, run?: string, at?: string | number) => {
    const q = new URLSearchParams()
    if (run) q.set('run', run)
    if (at !== undefined) q.set('at', String(at))
    const qs = q.toString()
    return `#/c/${c}/${y}/run${qs ? `?${qs}` : ''}`
  },
  day: (c: string, y: number, d: number) => `#/c/${c}/${y}/day/${d}`,
  failure: (c: string, y: number, d: number) => `#/c/${c}/${y}/day/${d}/failure`,
  redo: (c: string, y: number, d: number) => `#/c/${c}/${y}/day/${d}/redo`,
  plan: (c: string, y: number, from?: number, to?: number) =>
    `#/c/${c}/${y}/plan${from ? `?from=${from}&to=${to ?? from}` : ''}`,
  knownErrors: () => '#/known-errors',
  stations: (c: string, y: number) => `#/c/${c}/${y}/stations`,
  timeSeries: (c: string, y: number) => `#/c/${c}/${y}/time-series`,
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash))
  useEffect(() => {
    const on = () => setRoute(parse(window.location.hash))
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return route
}
