import { useEffect, useRef, useState } from 'react'
import { duration, jumpTargets, post, resolveAt, rowKind, type RowKind, useApi, pad3 } from '../lib'
import { href } from '../route'
import type { RunDetail } from '../types'
import { Failed, JumpBar, Loading, scrollToId, When } from './common'

const MARK: Record<string, string> = { done: '✓', failed: '✕', running: '●', wait: '' }
type Filter = 'all' | Exclude<RowKind, 'other'>
const FILTERS: Filter[] = ['all', 'running', 'failed', 'queued', 'solved']
const rowId = (doy: number) => `doy-${pad3(doy)}`
/** Above this many days the table scrolls inside its own box, so its header can stay put. */
const TALL = 40

export default function Run({ campaign, year, run, at }: { campaign: string; year: number; run?: string; at?: string }) {
  const { data, error } = useApi<RunDetail>(`/api/campaigns/${campaign}/years/${year}/runs${run ? `?run=${run}` : ''}`)
  const [stopMsg, setStopMsg] = useState<{ off: boolean; text: string } | null>(null)
  const [filter, setFilter] = useState<Filter>('all')
  // The row to bring into view and mark; `n` makes a second click on the same link scroll again.
  const [target, setTarget] = useState<{ doy: number; n: number } | null>(null)
  const atDone = useRef<string | null>(null)

  useEffect(() => {
    if (!target) return
    scrollToId(rowId(target.doy))
    const t = setTimeout(() => setTarget((x) => (x === target ? null : x)), 2500)
    return () => clearTimeout(t)
  }, [target])

  // A link with ?at= opens on that part of the table, once per page load: the
  // table does not refresh on its own, so this never moves the page later.
  useEffect(() => {
    const rows = data?.rows
    if (!rows || !at || atDone.current === at) return
    atDone.current = at
    const doy = resolveAt(at, jumpTargets(rows))
    if (doy !== null && rows.some((x) => x.doy === doy)) setTarget({ doy, n: 0 })
  }, [data, at])

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
  const counts: Record<RowKind, number> = { running: 0, failed: 0, queued: 0, solved: 0, other: 0 }
  for (const x of rows) counts[rowKind(x.outcome)]++
  const kinds = (k: RowKind) => counts[k]
  const span = r.doys.length ? `DOY ${pad3(Math.min(...r.doys))}–${pad3(Math.max(...r.doys))}` : ''
  const t = jumpTargets(rows)
  // Parallel blocks can leave gaps between the running days, so say how many when the span is not all running.
  const runningLabel = !t.running
    ? 'Running now'
    : `Running now (DOY ${pad3(t.running[0])}–${pad3(t.running[1])}${counts.running < t.running[1] - t.running[0] + 1 ? `, ${counts.running} days` : ''})`
  const shown = filter === 'all' ? rows : rows.filter((x) => rowKind(x.outcome) === filter)

  /** Bring a day into view, showing every day first if the filter hides it. */
  const jump = (doy: number | null) => {
    if (doy === null) return
    const k = rowKind(rows.find((x) => x.doy === doy)?.outcome ?? '')
    if (filter !== 'all' && k !== filter) setFilter('all')
    setTarget((x) => ({ doy, n: (x?.n ?? 0) + 1 }))
  }
  const countLink = (k: RowKind, label: string, doy: number | null) => {
    const n = kinds(k)
    return (
      <button type="button" className="linkbtn" disabled={doy === null} onClick={() => jump(doy)}>
        {n} {label}
      </button>
    )
  }

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
        <div className="panel pad stack">
          <span className="muted">Days</span>
          <strong>
            {countLink('solved', 'solved', t.solved)} · {countLink('failed', 'failed', t.failed)} · {countLink('running', 'running', t.running?.[0] ?? null)} · {countLink('queued', 'queued', t.queued)} · {kinds('other')} other
          </strong>
        </div>
        <div className="panel pad stack"><span className="muted">Identical failures in a row (stops at {b.identical_limit})</span><strong>{b.identical} of {b.identical_limit}{b.last_error ? ` · last: ${b.last_error}` : ''}</strong></div>
        <div className="panel pad stack"><span className="muted">Failed days in a row, any error (stops at {b.any_limit})</span><strong>{b.any} of {b.any_limit}</strong></div>
        <div className="panel pad stack"><span className="muted">Time per day</span><strong>{data.median_seconds ? `median ${duration(data.median_seconds)}` : '—'}</strong></div>
      </div>
      <JumpBar
        jumps={[
          { label: runningLabel, onClick: () => jump(t.running?.[0] ?? null), disabled: !t.running },
          { label: 'First failed', onClick: () => jump(t.failed), disabled: t.failed === null },
          { label: 'Next queued', onClick: () => jump(t.queued), disabled: t.queued === null },
          { label: 'First day', onClick: () => jump(shown[0]?.doy ?? null), disabled: !shown.length },
          { label: 'Last day', onClick: () => jump(shown[shown.length - 1]?.doy ?? null), disabled: !shown.length },
        ]}
      >
        <span className="sep" aria-hidden="true" />
        <span className="muted">Show</span>
        {FILTERS.map((f) => {
          const n = f === 'all' ? rows.length : kinds(f)
          return (
            <button key={f} type="button" className="btn2 sm" aria-pressed={filter === f} disabled={f !== 'all' && !n} onClick={() => setFilter(f)}>
              {f} ({n})
            </button>
          )
        })}
      </JumpBar>
      <section aria-label="Days by PCF step" className={`panel scroll${rows.length > TALL ? ' tall' : ''}`}>
        <table className="g">
          <thead>
            <tr>
              <th scope="col">DOY</th><th scope="col">Date</th>
              {groups.map((g) => <th key={g.key} scope="col">{g.key} {g.name}</th>)}
              <th scope="col">Outcome</th><th scope="col">Time</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((x) => (
              <tr key={x.doy} id={rowId(x.doy)} className={target?.doy === x.doy ? 'hl' : undefined}>
                <td><a className="mono" href={href.day(campaign, year, x.doy)}>{pad3(x.doy)}</a></td>
                <td className="mono">{x.date.slice(5)}</td>
                {x.cells.map((c, i) => (
                  <td key={i}>
                    <div className={`s st-${c}`} title={`${groups[i]?.key} ${c === 'wait' ? 'not started' : c}${(c === 'failed' || c === 'running') && x.pid ? `, PID ${pad3(x.pid)}` : ''}`}>
                      {MARK[c]}{(c === 'failed' || c === 'running') && x.pid ? ` ${pad3(x.pid)}` : ''}
                    </div>
                  </td>
                ))}
                <td style={{ whiteSpace: 'normal', overflowWrap: 'anywhere' }}>
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
