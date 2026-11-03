import { useState } from 'react'
import { useApi } from '../lib'
import type { StationFiles as SF } from '../types'
import { Failed, Loading } from './common'

export default function StationFiles({ campaign, year }: { campaign: string; year: number }) {
  const { data, error } = useApi<SF>(`/api/campaigns/${campaign}/years/${year}/station-files`)
  const [onlyGaps, setOnlyGaps] = useState(true)
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="the station files" />
  const inSta = data.rows.filter((r) => r.cells.STA > 0)
  const rows = onlyGaps ? inSta.filter((r) => r.notes.length || data.columns.some((c) => !r.cells[c])) : data.rows

  return (
    <>
      <div className="titlebar">
        <div>
          <h1>Station files · {campaign} <span className="stub">stage 4 · read-only</span></h1>
          <p className="muted" style={{ maxWidth: '80ch' }}>Where each station is listed in the campaign's eight files, read from <span className="mono">{data.refdir}</span> as the PCF names them. A station missing from a file a run needs will block the plan once this check is wired into it.</p>
        </div>
        <div className="row">
          <button type="button" className="btn2" disabled title="Stage 4: a reviewed change with a diff and a backup">Add a site…</button>
          <button type="button" className="btn2" disabled title="Stage 4: a reviewed change with a diff and a backup">Use a final CRD as a priori…</button>
        </div>
      </div>
      <div className="row" style={{ fontSize: 13 }}>
        {data.columns.map((c) => (
          <span key={c} className="mono">{data.files[c].name}{data.files[c].present ? '' : ' (missing)'}</span>
        ))}
      </div>
      <div className="seg" role="group" aria-label="Rows">
        <button type="button" aria-pressed={onlyGaps} onClick={() => setOnlyGaps(true)}>Stations in the STA with a gap or a note</button>
        <button type="button" aria-pressed={!onlyGaps} onClick={() => setOnlyGaps(false)}>Every station in any file ({data.rows.length})</button>
      </div>
      <div className="panel scroll">
        <table className="t">
          <thead><tr><th scope="col">Station</th>{data.columns.map((c) => <th key={c} scope="col">{c}</th>)}<th scope="col">Note</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.station}>
                <td className="mono">{r.station}</td>
                {data.columns.map((c) => (
                  <td key={c} className="mono" style={!r.cells[c] ? { color: 'var(--warn-strong)', fontWeight: 700 } : undefined}>
                    {r.cells[c] === 0 ? '—' : r.cells[c] === 1 ? '✓' : r.cells[c]}
                  </td>
                ))}
                <td style={{ fontSize: 13 }}>{r.notes.join(' ')}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={data.columns.length + 2} className="muted">No gaps.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="panel pad stack" style={{ fontSize: 13 }}>
        <p><strong>BLQ, still by email.</strong> The console will write the coordinate block for the Chalmers ocean loading form for the stations missing from the BLQ, and check the emailed reply for missing stations and for anything after <span className="mono">$$ END TABLE</span> before it is merged.</p>
        <p className="faint">Not built yet (stage 4).</p>
      </div>
    </>
  )
}
