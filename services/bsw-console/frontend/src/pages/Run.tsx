import { useState } from 'react'
import { duration, post, useApi, pad3 } from '../lib'
import { href } from '../route'
import type { RunDetail } from '../types'
import { Failed, Loading, When } from './common'

const MARK: Record<string, string> = { done: '✓', failed: '✕', running: '●', wait: '' }

export default function Run({ campaign, year, run }: { campaign: string; year: number; run?: string }) {
  const { data, error } = useApi<RunDetail>(`/api/campaigns/${campaign}/years/${year}/runs${run ? `?run=${run}` : ''}`)
  const [stopMsg, setStopMsg] = useState<{ off: boolean; text: string } | null>(null)
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="the run record" />
  const r = data.run
  if (!r) {
    return (
      <>
        <h1>Runs · {campaign} {year}</h1>
        <p className="muted">The service has no run recorded for {campaign} {year}. Runs started through scripts/ before the cutover are not in its record.</p>
      </>
    )
  }
  const rows = data.rows ?? []
  const groups = data.groups ?? []
  const b = data.breaker!
  const live = ['running', 'slow', 'unknown'].includes(r.state)
  const count = (o: string) => rows.filter((x) => x.outcome === o).length
  const span = r.doys.length ? `DOY ${pad3(Math.min(...r.doys))}–${pad3(Math.max(...r.doys))}` : ''

  const stop = async () => {
    const res = await post<{ reason?: string; detail?: string; queued?: string }>('/api/runs/stop', { campaign, year, run: r.run })
    setStopMsg(
      res.ok
        ? { off: false, text: `Stop queued as ${res.body.queued}. The run ends after the block in progress; no BPE is killed.` }
        : { off: res.status === 501, text: res.body.reason ?? res.body.detail ?? `Answered ${res.status}` },
    )
  }

  return (
    <>
      <div className="titlebar">
        <div>
          <h1>Run · {campaign} {year} · {span}</h1>
          <p className="muted">
            Run <span className="mono">{r.run}</span> on {r.host} · started <When ts={r.started} />
            {r.config && <> · config <span className="mono">{r.config}</span></>}
          </p>
        </div>
        <div className="row">
          {data.runs.length > 1 && (
            <label className="row" style={{ fontSize: 13 }}>
              Run
              <select value={r.run} onChange={(e) => (window.location.hash = href.run(campaign, year, e.target.value))} style={{ font: 'inherit' }}>
                {data.runs.map((x) => (
                  <option key={x.run} value={x.run}>{x.run} · {new Date(x.started * 1000).toLocaleString('en-GB')} · {x.state}</option>
                ))}
              </select>
            </label>
          )}
          {live && <button type="button" className="btn2" onClick={stop}>Stop after the current block</button>}
        </div>
      </div>
      {stopMsg && <div className="banner idle" role="status">{stopMsg.off && <span className="stub">not enabled yet</span>} {stopMsg.text}</div>}
      {r.state === 'halted' && (
        <div className="banner warn" role="alert">
          <strong>Halted</strong>
          <span>{r.halt}</span>
          <span>The lock is released. Days not started stay not started. Nothing was changed automatically; a person decides what happens next.</span>
        </div>
      )}
      {r.state === 'dead' && (
        <div className="banner warn" role="alert"><strong>The driver is gone</strong><span>{r.status_lines?.slice(-1)[0]}</span></div>
      )}
      <div className="cards" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(240px,1fr))' }}>
        <div className="panel pad stack"><span className="muted">Days</span><strong>{count('solved') + count('already solved')} solved · {count('failed')} failed · {count('running')} running · {rows.length - count('solved') - count('already solved') - count('failed') - count('running')} other</strong></div>
        <div className="panel pad stack"><span className="muted">Identical failures in a row (stops at {b.identical_limit})</span><strong>{b.identical} of {b.identical_limit}{b.last_error ? ` · last: ${b.last_error}` : ''}</strong></div>
        <div className="panel pad stack"><span className="muted">Failed days in a row, any error (stops at {b.any_limit})</span><strong>{b.any} of {b.any_limit}</strong></div>
        <div className="panel pad stack"><span className="muted">Time per day</span><strong>{data.median_seconds ? `median ${duration(data.median_seconds)}` : '—'}</strong></div>
      </div>
      <section aria-label="Days by PCF step" className="panel scroll">
        <table className="g">
          <thead>
            <tr>
              <th scope="col">DOY</th><th scope="col">Date</th>
              {groups.map((g) => <th key={g.key} scope="col">{g.key} {g.name}</th>)}
              <th scope="col">Outcome</th><th scope="col">Time</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.doy}>
                <td><a className="mono" href={href.day(campaign, year, x.doy)}>{pad3(x.doy)}</a></td>
                <td className="mono">{x.date.slice(5)}</td>
                {x.cells.map((c, i) => (
                  <td key={i}>
                    <div className={`s st-${c}`} title={`${groups[i]?.key} ${c === 'wait' ? 'not started' : c}${(c === 'failed' || c === 'running') && x.pid ? `, PID ${pad3(x.pid)}` : ''}`}>
                      {MARK[c]}{(c === 'failed' || c === 'running') && x.pid ? ` ${pad3(x.pid)}` : ''}
                    </div>
                  </td>
                ))}
                <td>
                  {x.outcome === 'failed' ? <a href={href.failure(campaign, year, x.doy)}>failed · {x.error}</a> : x.outcome}
                  {x.outcome.startsWith('not started') && x.note && <span className="faint" title={x.note}> ⓘ</span>}
                </td>
                <td className="mono">{duration(x.seconds)}{x.outcome === 'running' ? ' so far' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      <p className="faint" style={{ fontSize: 12 }}>Each cell is a group of PIDs in the PCF: done ✓, failed ✕ with the PID, running ● with the PID now running, not started blank. A solved day shows every group done; per-step times are not in the run record.</p>
      {r.status_lines && (
        <details>
          <summary>What the command line prints for this run</summary>
          <pre className="viewer mono" style={{ padding: 12 }}>{r.status_lines.join('\n')}</pre>
        </details>
      )}
    </>
  )
}
