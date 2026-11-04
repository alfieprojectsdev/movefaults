import { useState } from 'react'
import { post, useApi, pad3 } from '../lib'
import type { Plan as P, SavedPlan } from '../types'
import { Failed, Loading } from './common'

export default function Plan({ campaign, year, from, to }: { campaign: string; year: number; from?: number; to?: number }) {
  const [start, setStart] = useState(from ?? 1)
  const [end, setEnd] = useState(to ?? Math.min((from ?? 1) + 29, 365))
  const [pcf, setPcf] = useState<string | null>(null)
  const [skipped, setSkipped] = useState<number[]>([])
  const [rnxgra, setRnxgra] = useState('continuous')
  const [name, setName] = useState('')
  const [msg, setMsg] = useState<{ kind: 'info' | 'warn'; text: string } | null>(null)

  const qs = new URLSearchParams({ start: String(start), end: String(end), skip: skipped.join(','), rnxgra })
  if (pcf) qs.set('pcf', pcf)
  const ok = start >= 1 && end >= start && end <= 366
  const { data, error, loading } = useApi<P>(ok ? `/api/campaigns/${campaign}/years/${year}/plan?${qs}` : null)
  const saved = useApi<{ plans: SavedPlan[] }>('/api/plans')

  const toggle = (i: number) => setSkipped((s) => (s.includes(i) ? s.filter((x) => x !== i) : [...s, i].sort()))
  const save = async () => {
    const r = await post<SavedPlan & { detail?: string }>('/api/plans', { name: name || `${campaign} ${year} DOY ${pad3(start)}-${pad3(end)}`, campaign, year, from: start, to: end, pcf: data?.pcf, skipped, rnxgra })
    setMsg(r.ok ? { kind: 'info', text: `Saved as ${r.body.id}${r.body.by ? ` by ${r.body.by}` : ''}.` } : { kind: 'warn', text: r.body.detail ?? `Not saved (${r.status})` })
    saved.reload()
  }
  const stage3 = async (what: 'preflight' | 'runs/start') => {
    const r = await post<{ reason?: string }>(`/api/${what}`, { campaign, year, from: start, to: end, pcf: data?.pcf, skipped })
    setMsg({ kind: 'warn', text: r.body.reason ?? `Answered ${r.status}` })
  }

  return (
    <>
      <div className="stack">
        <h1>Plan a run · {campaign} {year}</h1>
        <p className="muted">What RUNBPE 1 and 2 ask for, checked before anything runs. The day selection, reference-station check and MAXPAR are the service's own, the same as <span className="mono">bernese-run-year --plan</span>.</p>
      </div>
      <div className="cols" style={{ gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.2fr)' }}>
        <form className="f" onSubmit={(e) => e.preventDefault()}>
          <fieldset>
            <legend>Sessions (RUNBPE 1)</legend>
            <label>First day, DOY
              <input inputMode="numeric" value={start} onChange={(e) => setStart(Number(e.target.value) || 0)} />
              {data && <span className="muted">{data.from.date} · GPS week {data.from.gps_week}, day {data.from.gps_day}</span>}
            </label>
            <label>Last day, DOY
              <input inputMode="numeric" value={end} onChange={(e) => setEnd(Number(e.target.value) || 0)} />
              {data && <span className="muted">{data.to.date} · GPS week {data.to.gps_week}, day {data.to.gps_day}</span>}
            </label>
            <label>PCF
              <select value={pcf ?? data?.pcf ?? ''} onChange={(e) => setPcf(e.target.value)}>
                {(data?.pcfs ?? []).map((p) => <option key={p}>{p}</option>)}
              </select>
            </label>
            <label>RNXGRA file selection
              <select value={rnxgra} onChange={(e) => setRnxgra(e.target.value)}>
                {Object.entries(data?.rnxgra_presets ?? {}).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
              <span className="faint">Shown for the record. The preset in use is set in the RNXGRA panel; the console does not change panels.</span>
            </label>
          </fieldset>
          <fieldset>
            <legend>Scripts (RUNBPE 2: start with, skip)</legend>
            <p className="muted" style={{ fontSize: 13 }}>Untick a group to skip it. Groups before the first ticked one are "start with". A skip that leaves a later script waiting on nothing is caught on the right.</p>
            {(data?.groups ?? []).map((g) => (
              <label key={g.index} className="cb">
                <input type="checkbox" checked={!skipped.includes(g.index)} onChange={() => toggle(g.index)} />
                <span className="stack" style={{ gap: 2 }}>
                  <span><span className="mono">{g.key}</span> · {g.name}</span>
                  <span className="mono faint" style={{ fontSize: 12 }}>{g.pids.join(' · ')}</span>
                </span>
              </label>
            ))}
          </fieldset>
        </form>
        <section aria-labelledby="checks" className="panel pad stack">
          <h2 id="checks">Checks before the run</h2>
          {!ok && <p className="err-box">The first day must be between 1 and the last day.</p>}
          {error && <Failed error={error} />}
          {loading && !data && <Loading what="the plan" />}
          {data && (
            <>
              <div>
                {data.checks.map((c, i) => (
                  <div key={i} className="check">
                    <span aria-hidden="true" className={`mark ${c.level}`}>{c.level === 'ok' ? '✓' : c.level === 'bad' ? '✕' : 'i'}</span>
                    <div className="stack" style={{ gap: 2 }}>
                      <strong style={{ fontSize: 14 }}>{c.title}</strong>
                      <span className="muted" style={{ fontSize: 13 }}>{c.detail}</span>
                    </div>
                  </div>
                ))}
              </div>
              <details>
                <summary className="muted" style={{ fontSize: 13 }}>Where the service looked</summary>
                <pre className="mono" style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{[data.label, ...data.sources].join('\n')}</pre>
              </details>
              <label className="stack" style={{ fontSize: 13, gap: 4 }}>
                Plan name
                <input value={name} placeholder={`${campaign} ${year} DOY ${pad3(start)}-${pad3(end)}`} onChange={(e) => setName(e.target.value)} style={{ font: 'inherit', padding: '6px 8px' }} />
              </label>
              <div className="row">
                <button type="button" className="btn2" onClick={() => stage3('preflight')}>Queue preflight</button>
                <button type="button" className="btn" onClick={save}>Save plan</button>
                <button type="button" className="btn" disabled={!data.can_start} onClick={() => stage3('runs/start')}>Start</button>
              </div>
              <p className="muted" style={{ fontSize: 13 }}>Start is off: {data.start_blocked_because.join('; ')}.</p>
              {msg && <div className={`banner ${msg.kind}`} role="status">{msg.text}</div>}
            </>
          )}
        </section>
      </div>
      {saved.data && saved.data.plans.length > 0 && (
        <section className="stack" aria-labelledby="saved">
          <h2 id="saved">Saved plans</h2>
          <div className="panel scroll">
            <table className="t">
              <thead><tr><th scope="col">Name</th><th scope="col">Days</th><th scope="col">PCF</th><th scope="col">Saved</th><th scope="col">By</th></tr></thead>
              <tbody>
                {saved.data.plans.map((p) => (
                  <tr key={p.id}><td>{p.name ?? p.id}</td><td className="mono">{p.campaign} {p.year} DOY {pad3(p.from)}–{pad3(p.to)}</td><td className="mono">{p.pcf}</td><td className="mono">{p.saved}</td><td>{p.by}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  )
}
