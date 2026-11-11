import { useState } from 'react'
import { duration, size, useApi, pad3 } from '../lib'
import { href } from '../route'
import type { DayDetail, FileText } from '../types'
import { Failed, Loading, TextViewer, When } from './common'

// A run started before #318 did not record who, the command, the code or the
// products. Said per run, never guessed.
const NOT_RECORDED = <span className="faint">not recorded for this run</span>

export default function Day({ campaign, year, doy }: { campaign: string; year: number; doy: number }) {
  const base = `/api/campaigns/${campaign}/years/${year}/days/${doy}`
  const { data, error } = useApi<DayDetail>(base)
  const [open, setOpen] = useState<string | null>(null)
  const file = useApi<FileText>(open ? `${base}/file?path=${encodeURIComponent(open)}` : null)
  if (error) return <Failed error={error} />
  if (!data) return <Loading what={`DOY ${pad3(doy)}`} />
  const q = data.quality
  const p = data.provenance
  const prc = data.results.find((r) => r.folder === 'OUT' && r.path)

  return (
    <>
      <nav aria-label="Breadcrumb" className="crumb"><a href={href.calendar(campaign, year)}>{campaign} {year}</a> › DOY {pad3(doy)}</nav>
      <div className="titlebar">
        <div>
          <h1>DOY {pad3(doy)} · {data.date} · session {data.session}</h1>
          <div className="row" style={{ fontSize: 13 }}>
            <span className={`badge`}>{data.state === 'none' ? 'not run' : data.state}</span>
            <span className="muted">GPS week {data.gps_week}, day {data.gps_day} · {data.attempts.length} attempt(s) recorded</span>
          </div>
        </div>
        <div className="row">
          {data.state === 'failed' && <a className="btn" href={href.failure(campaign, year, doy)}>Why it failed</a>}
          <a className="btn2" href={href.redo(campaign, year, doy)}>Redo this day…</a>
          <a className="btn2" href={href.timeSeries(campaign, year)}>Time series</a>
        </div>
      </div>

      <div className="cols">
        <section aria-labelledby="prov" className="panel pad stack">
          <h2 id="prov">How this result was produced</h2>
          {p.run && <p className="muted" style={{ fontSize: 13 }}>From the record of run <a className="mono" href={href.run(campaign, year, p.run)}>{p.run}</a>, the latest attempt at this day.</p>}
          <dl className="kv">
            <dt>PCF</dt><dd className="mono">{p.pcf}</dd>
            <dt>Ambiguities</dt><dd>{p.ambiguities}</dd>
            <dt>Campaign</dt><dd className="mono">{p.campaign_dir}</dd>
            <dt>Config hash</dt><dd className="mono">{p.config_hash ?? NOT_RECORDED}</dd>
            <dt>Started by</dt><dd>{p.started_by ?? NOT_RECORDED}</dd>
            <dt>Command</dt><dd className="mono">{p.command ?? NOT_RECORDED}</dd>
            <dt>Code version</dt><dd className="mono">{p.code_version ?? NOT_RECORDED}</dd>
            <dt>IGS products</dt><dd>{p.products ? <><span className="mono">{p.products}</span> ({p.product_tier ?? 'tier unknown'})</> : NOT_RECORDED}</dd>
          </dl>
        </section>
        <section aria-labelledby="q" className="panel pad stack">
          <h2 id="q">Quality</h2>
          <dl className="kv">
            <dt>Stations in the solution</dt>
            <dd>{q.stations ?? '—'} {q.sources.stations && <span className="faint mono">({q.sources.stations})</span>}</dd>
            <dt>Dropped since the day before</dt>
            <dd>{q.dropped.length ? <strong style={{ color: 'var(--warn-strong)' }}>{q.dropped.join(' ')}</strong> : 'none'}</dd>
            <dt>HELMCHK RMS</dt>
            <dd>
              {q.helmert_rms_mm != null ? `${q.helmert_rms_mm.toFixed(2)} mm` : '—'}{' '}
              {q.sources.helmert_rms_mm && prc && <button type="button" className="btn2" style={{ padding: '1px 8px', fontSize: 12 }} onClick={() => setOpen(prc.path)}>{q.sources.helmert_rms_mm}</button>}
            </dd>
            <dt>Ambiguities resolved</dt>
            <dd>
              {q.ambiguities ? <>by method, below{' '}
                {q.sources.ambiguities && prc && <button type="button" className="btn2" style={{ padding: '1px 8px', fontSize: 12 }} onClick={() => setOpen(prc.path)}>{q.sources.ambiguities}</button>}</>
                : <span className="faint">not in this day's summary</span>}
            </dd>
          </dl>
          {q.ambiguities && (
            <div className="scroll">
              <table className="t" style={{ fontSize: 13 }}>
                <caption className="faint" style={{ textAlign: 'left', fontSize: 12 }}>Each method works on its own baselines, by length, so the rates are not added together.</caption>
                <thead><tr><th scope="col">Method</th><th scope="col">Baselines</th><th scope="col" className="num">Ambiguities</th><th scope="col" className="num">Left unresolved</th><th scope="col" className="num">Resolved</th></tr></thead>
                <tbody>
                  {q.ambiguities.map((a) => (
                    <tr key={`${a.tag ?? a.method}-${a.system}`}>
                      <td>{a.method}{a.system !== 'G' && ` · ${a.system}`}</td>
                      <td>{a.baselines}, {a.max_length.replace('<', 'under ').replace('km', ' km')}</td>
                      <td className="num">{a.before}</td>
                      <td className="num">{a.after}</td>
                      <td className="num"><strong>{a.percent.toFixed(1)}%</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>

      <section aria-labelledby="att" className="stack">
        <h2 id="att">Attempts</h2>
        <div className="panel scroll">
          <table className="t">
            <thead><tr><th scope="col">Run</th><th scope="col">Started</th><th scope="col">Outcome</th><th scope="col">Stations</th><th scope="col">Time</th><th scope="col">Recorded with the run</th></tr></thead>
            <tbody>
              {data.attempts.map((a, i) => (
                <tr key={i}>
                  <td className="mono"><a href={href.run(campaign, year, a.run)}>{a.run}</a></td>
                  <td><When ts={a.started} /></td>
                  <td>{a.outcome === 'failed' ? <a href={href.failure(campaign, year, doy)}>failed · {a.error}</a> : a.outcome}{a.note && <div className="faint" style={{ fontSize: 12, whiteSpace: 'pre-wrap' }}>{a.note}</div>}</td>
                  <td className="num">{a.stations ?? ''}</td>
                  <td className="mono">{duration(a.seconds)}</td>
                  <td style={{ fontSize: 13 }}>
                    {a.provenance?.recorded
                      ? <>by {a.provenance.started_by} · code <span className="mono">{a.provenance.code_version}</span>{a.provenance.products && <> · <span className="mono">{a.provenance.products}</span> ({a.provenance.product_tier ?? 'tier unknown'})</>}</>
                      : NOT_RECORDED}
                  </td>
                </tr>
              ))}
              {!data.attempts.length && <tr><td colSpan={6} className="muted">No attempt recorded by the service. A result made through scripts/ before the cutover has no record here.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="out" className="stack">
        <h2 id="out">Results in SAVEDISK/{campaign}/{year}</h2>
        <div className="panel scroll">
          <table className="t">
            <thead><tr><th scope="col">File (5.4 name)</th><th scope="col">5.2 name</th><th scope="col">Folder</th><th scope="col">What it is</th><th scope="col">Size</th><th scope="col">Written</th></tr></thead>
            <tbody>
              {data.results.map((r) => (
                <tr key={r.name}>
                  <td className="mono">
                    {r.path ? (
                      <button type="button" className="btn2" style={{ padding: '1px 8px', fontSize: 12 }} onClick={() => setOpen(r.path)} aria-pressed={open === r.path}>{r.name}</button>
                    ) : (
                      <span className="faint">{r.name} · missing</span>
                    )}
                  </td>
                  <td className="mono">{r.v52}</td>
                  <td>{r.folder}</td>
                  <td>{r.what}</td>
                  <td className="mono num">{size(r.size)}</td>
                  <td><When ts={r.written} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: 13 }}>
          {data.present} of {data.results.length} expected results present. In 5.4 the year has four digits and the session follows it: <span className="mono">FIN_{year} {pad3(doy)} 0</span> is 5.2's <span className="mono">F1_{String(year).slice(2)} {pad3(doy)} 0</span>.
        </p>
      </section>

      {open && (
        <section aria-labelledby="viewer" className="stack">
          <h2 id="viewer" className="mono">{open}{file.data?.truncated ? ` · first ${file.data.lines.length} of ${file.data.total} lines` : ''}</h2>
          {file.error && <Failed error={file.error} />}
          {file.data ? <TextViewer key={open} lines={file.data.lines} /> : !file.error && <Loading what={open} />}
        </section>
      )}
    </>
  )
}
