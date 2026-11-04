import { useState } from 'react'
import { useApi, pad3 } from '../lib'
import { href } from '../route'
import type { KnownErrors as KE } from '../types'
import { Failed, Loading } from './common'

type Filter = 'all' | 'fired' | 'proposed' | 'configuration'

export default function KnownErrors() {
  const { data, error } = useApi<KE>('/api/known-errors')
  const [f, setF] = useState<Filter>('all')
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="the known-errors list" />
  const keep = (r: KE['entries'][number]) =>
    f === 'all' || (f === 'fired' && r.fired > 0) || (f === 'proposed' && r.status === 'proposed') || (f === 'configuration' && r.scope === 'configuration')
  const rows = data.entries.filter(keep)
  const filters: [Filter, string][] = [['all', `All ${data.entries.length}`], ['fired', 'Fired recently'], ['proposed', 'Proposed, not confirmed'], ['configuration', 'Stops at once']]

  return (
    <>
      <div className="stack">
        <h1>Known errors</h1>
        <p className="muted" style={{ maxWidth: '75ch' }}>
          The list the run looks failures up in, from <span className="mono">config/bernese/bpe_errors.yaml</span>. The processing lead edits that file; this page only reads it. A <strong>configuration</strong> error stops a run at once. A <strong>session</strong> error is counted, and 3 identical ones in a row stop it.
        </p>
      </div>
      <div className="seg" role="group" aria-label="Show">
        <span className="muted" style={{ fontSize: 13 }}>Show:</span>
        {filters.map(([k, label]) => (
          <button key={k} type="button" aria-pressed={f === k} onClick={() => setF(k)}>{label}</button>
        ))}
      </div>
      <div className="panel scroll">
        <table className="t">
          <thead>
            <tr><th scope="col">Program / routine</th><th scope="col">Message</th><th scope="col">Scope</th><th scope="col">Status</th><th scope="col">Fired, last {data.days} days</th><th scope="col">Last seen</th></tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.number}>
                <td className="mono">{r.emitter}</td>
                <td>
                  <details>
                    <summary className="mono">{r.message}</summary>
                    <div className="stack" style={{ padding: '8px 0', fontSize: 13, maxWidth: '80ch' }}>
                      <p><strong>Diagnosis.</strong> {r.diagnosis}</p>
                      <p><strong>Remedy.</strong> {r.remedy}</p>
                      <p className="muted"><strong>Source.</strong> {r.source}</p>
                    </div>
                  </details>
                </td>
                <td>{r.scope}</td>
                <td><span className={`badge ${r.status === 'proposed' ? 'proposed' : ''}`}>{r.status}</span></td>
                <td className="num">{r.fired}</td>
                <td>{r.last ? <a href={href.failure(r.last.campaign, r.last.year, r.last.doy)}>{r.last.campaign} {r.last.year} · DOY {pad3(r.last.doy)}</a> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p style={{ fontSize: 13 }}>
        Failures with no entry in the last {data.days} days: <strong>{data.unknown.length}</strong>
        {data.unknown.slice(0, 5).map((u, i) => (
          <span key={i}> · <a href={href.failure(u.campaign, u.year, u.doy)}>{u.campaign} {u.year} DOY {pad3(u.doy)}</a></span>
        ))}
        {data.unknown.length > 0 && '. Open one and send the cause to the processing lead.'}
      </p>
    </>
  )
}
