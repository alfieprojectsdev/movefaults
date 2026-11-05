import { useState } from 'react'
import { useApi } from '../lib'
import type { EquipmentField, EquipmentReport, StationEquipment } from '../types'
import { Failed, Loading, When } from './common'

/** Read-only: one station's part of the bernese-check-equipment report.
 *  The report is advisory; nothing here changes the .STA file or field-ops. */
export default function EquipmentPanel({ stations }: { stations: string[] }) {
  const about = useApi<EquipmentReport>('/api/equipment-report')
  const [station, setStation] = useState('')
  const one = useApi<StationEquipment>(station ? `/api/stations/${station}/equipment` : null)

  return (
    <section aria-labelledby="equipment" className="panel pad stack">
      <h2 id="equipment">Equipment: the .STA file against field-ops <span className="stub">read-only · advisory</span></h2>
      {about.error && <Failed error={about.error} />}
      {!about.data && !about.error && <Loading what="the equipment report" />}
      {about.data && !about.data.configured && <p role="status">{about.data.message}</p>}
      {about.data && about.data.configured && !about.data.available && <p role="status" className="err-box">{about.data.message}</p>}
      {about.data && about.data.configured && about.data.available && (
        <>
          <p style={{ fontSize: 13 }}>
            Compared <span className="mono">{about.data.sta.path}</span>{' '}
            {about.data.exported_at
              ? <>with the field-ops export of <strong className="mono">{about.data.exported_at}</strong></>
              : <>with the inventory sheet (its export time is not recorded in the file)</>}
            ; report written <When ts={about.data.written} />. Either side may be wrong: a disagreement is for the processing lead to resolve.
          </p>
          <label className="row" style={{ fontSize: 13 }}>
            Station
            <select value={station} onChange={(e) => setStation(e.target.value)}>
              <option value="">Choose a station…</option>
              {stations.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          {one.error && <Failed error={one.error} />}
          {station && !one.data && !one.error && <Loading what={`${station}'s equipment`} />}
          {one.data && one.data.configured && one.data.available && <Station data={one.data} />}
        </>
      )}
    </section>
  )
}

function Station({ data }: { data: StationEquipment }) {
  const current = data.current ?? []
  const visits = data.visits ?? []
  const names = data.names ?? []
  if (!current.length && !visits.length && !names.length)
    return <p className="muted">The report has nothing on {data.station}.</p>
  return (
    <div className="stack">
      {current.map((c) => (
        <div key={c.station} className="stack">
          <p><span className="badge">{c.category}</span>{' '}
            {c.sta_line ? <>latest .STA row, line {c.sta_line}, from <span className="mono">{c.sta_from}</span> to <span className="mono">{c.sta_to || '(open)'}</span></> : null}
            {c.note && <span className="muted"> · {c.note}</span>}
          </p>
          {Object.keys(c.fields).length > 0 && (
            <table className="t">
              <thead><tr><th scope="col"></th><th scope="col">.STA</th><th scope="col">Field-ops</th><th scope="col">Name map</th><th scope="col">Result</th></tr></thead>
              <tbody>
                {(['receiver', 'antenna', 'radome'] as const).map((k) => c.fields[k] && <FieldRow key={k} label={k} f={c.fields[k]!} />)}
              </tbody>
            </table>
          )}
        </div>
      ))}
      {visits.length > 0 && (
        <table className="t">
          <caption style={{ textAlign: 'left' }}>Visits</caption>
          <thead><tr><th scope="col">Visit (UTC)</th><th scope="col">What was found</th><th scope="col">After a change</th></tr></thead>
          <tbody>
            {visits.map((v, i) => (
              <tr key={i}>
                <td className="mono">{v.visit_time}</td>
                <td>{v.before_status}</td>
                <td>{v.after_status ?? '—'}{v.after_row_from && <> (from <span className="mono">{v.after_row_from}</span>)</>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {names.map((n) => (
        <p key={n.problem}><strong>{n.problem}</strong>{n.sta_names.length ? `: ${n.sta_names.join(', ')}` : ''}</p>
      ))}
    </div>
  )
}

function FieldRow({ label, f }: { label: string; f: EquipmentField }) {
  return (
    <tr>
      <th scope="row">{label}</th>
      <td className="mono">{f.sta || '(blank)'}</td>
      <td className="mono">{f.source || '(blank)'}</td>
      <td className="mono">{f.source_igs ?? (f.status === 'unmapped name' ? 'not in the map' : '')}</td>
      <td>{f.status}{f.note && <span className="muted"> · {f.note}</span>}</td>
    </tr>
  )
}
