import { useApi, pad3 } from '../lib'
import { href } from '../route'
import type { Failure as F } from '../types'
import { Failed, Loading, TextViewer } from './common'

export default function Failure({ campaign, year, doy }: { campaign: string; year: number; doy: number }) {
  const { data, error } = useApi<F>(`/api/campaigns/${campaign}/years/${year}/days/${doy}/failure`)
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="the diagnosis" />
  const e = data.entry
  const c = data.cause
  const v = data.verdict
  const params = c ? Object.entries(c.params).map(([k, val]) => `${k} ${val}`).join(' · ') : ''

  return (
    <>
      <div className="stack">
        <nav aria-label="Breadcrumb" className="crumb">
          <a href={href.calendar(campaign, year)}>{campaign} {year}</a> › <a href={href.day(campaign, year, doy)}>DOY {pad3(doy)}</a> › failure
        </nav>
        <h1>DOY {pad3(doy)} failed{data.pid != null ? ` at PID ${pad3(data.pid)} ${data.script ?? ''}` : ''}</h1>
      </div>
      <div className={`banner ${v.kind === 'session' ? 'info' : 'warn'}`}>
        <strong>{v.text}</strong>
        <span>{v.detail}</span>
      </div>
      <div className="cols">
        <section aria-labelledby="step" className="panel pad stack">
          <h2 id="step">What failed</h2>
          <dl className="kv">
            <dt>PID and script</dt><dd className="mono">{data.pid != null ? `${pad3(data.pid)} ${data.script ?? ''}` : '—'}</dd>
            <dt>Program</dt><dd className="mono">{data.program ?? '—'}</dd>
            <dt>Message from</dt><dd className="mono">{c ? `${c.emitter_type} ${c.emitter}` : '—'}</dd>
            <dt>Message</dt><dd className="mono">{c ? c.headline || c.detail[0] : data.label}</dd>
            <dt>Values in it</dt><dd className="mono">{params || '—'}</dd>
            <dt>Recorded as</dt><dd className="mono">{data.label || '—'}</dd>
            <dt>Attempt</dt><dd>{data.attempt_number} recorded for this day</dd>
          </dl>
        </section>
        <section aria-labelledby="kb" className="panel pad stack">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <h2 id="kb">Known-errors list</h2>
            {e && (
              <span className="row">
                <span className="muted" style={{ fontSize: 12 }}>scope: {e.scope}</span>
                <span className={`badge ${e.status === 'proposed' ? 'proposed' : ''}`}>{e.status === 'proposed' ? 'proposed · not yet confirmed' : e.status}</span>
              </span>
            )}
          </div>
          {e ? (
            <div className="stack" style={{ fontSize: 14 }}>
              <div><div className="muted" style={{ fontSize: 12 }}>Diagnosis</div><p>{e.diagnosis}</p></div>
              <div><div className="muted" style={{ fontSize: 12 }}>Remedy</div><p>{e.remedy}</p></div>
              {e.confirm && <div><div className="muted" style={{ fontSize: 12 }}>How to tell it worked</div><p>{e.confirm}</p></div>}
              <div><div className="muted" style={{ fontSize: 12 }}>Source</div><p>{e.source}</p></div>
              <p className="faint" style={{ fontSize: 12 }}>Nothing here is applied automatically. A remedy tells a person what to check and change.</p>
            </div>
          ) : (
            <div className="stack" style={{ fontSize: 14 }}>
              <p><strong>No entry on file for this message.</strong> The run stopped here so a person can look. There is no default remedy, and nothing was retried.</p>
              <ol style={{ margin: 0, paddingLeft: 20 }}>
                <li>Read the protocol lines below, and the program's own output for this PID.</li>
                <li>Check the day's inputs: the DATAPOOL files for this day, and the campaign's STA, CRD and ABB.</li>
                <li>Once the cause is known, send it to the processing lead so it can be added to the list.</li>
              </ol>
            </div>
          )}
        </section>
      </div>
      <section aria-labelledby="raw" className="stack">
        <div className="row" style={{ justifyContent: 'space-between' }}>
          <h2 id="raw" className="mono">{data.file ?? 'No BPE protocol file found'}</h2>
          <a href={href.day(campaign, year, doy)}>Open the day</a>
        </div>
        {data.lines.length ? (
          <>
            <TextViewer lines={data.lines} first={data.first_current_line} />
            <p className="faint" style={{ fontSize: 12 }}>Only the last attempt in this file is read. Earlier attempts are above it in the same file and are shown greyed.</p>
          </>
        ) : (
          <p className="muted">The day's BPE folder is gone or holds no failed step, so only the message the service recorded is shown. A per-day campaign is removed once its day is solved.</p>
        )}
      </section>
    </>
  )
}
