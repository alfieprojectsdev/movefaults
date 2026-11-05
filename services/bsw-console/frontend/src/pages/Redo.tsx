import { useState } from 'react'
import { post, size, useApi, pad3 } from '../lib'
import { href } from '../route'
import type { Lock, Redo as R } from '../types'
import { Failed, Loading, When } from './common'

export default function Redo({ campaign, year, doy, lock }: { campaign: string; year: number; doy: number; lock: Lock | null }) {
  const { data, error } = useApi<R>(`/api/campaigns/${campaign}/years/${year}/days/${doy}/redo`)
  const [reason, setReason] = useState('')
  const [typed, setTyped] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; off: boolean; text: string } | null>(null)
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="the day's results" />
  const ready = reason.trim().length > 0 && typed.trim() === pad3(doy) && data.files.length > 0
  const go = async () => {
    const r = await post<{ reason?: string; detail?: string; queued?: string }>('/api/redo', { campaign, year, doy, reason })
    setMsg(
      r.ok
        ? { ok: true, off: false, text: `Redo queued as ${r.body.queued}. The files move aside only when the run worker starts it, and come back if the redo fails.` }
        : { ok: false, off: r.status === 501, text: r.body.reason ?? r.body.detail ?? `Answered ${r.status}` },
    )
  }

  return (
    <>
      <nav aria-label="Breadcrumb" className="crumb">
        <a href={href.calendar(campaign, year)}>{campaign} {year}</a> › <a href={href.day(campaign, year, doy)}>DOY {pad3(doy)}</a> › redo
      </nav>
      <div className="stack">
        <h1>Redo DOY {pad3(doy)} ({data.date})?</h1>
        <p className="muted" style={{ maxWidth: '80ch' }}>
          Deleting a day's FIN files is not a redo on 5.4: only 2 of the day's 7 results would be replaced, and the next combination would pick up the old ones by name. This moves <strong>all of them</strong> aside first, as one step.
        </p>
      </div>
      <section aria-labelledby="moves" className="stack">
        <h2 id="moves">What will be moved</h2>
        <p style={{ fontSize: 13 }}>From <span className="mono">{data.from}</span> to <span className="mono">{data.to}/</span></p>
        <div className="panel scroll">
          <table className="t">
            <thead><tr><th scope="col">File</th><th scope="col">From</th><th scope="col">Size</th><th scope="col">Written</th></tr></thead>
            <tbody>
              {data.files.map((f) => (
                <tr key={f.name}><td className="mono">{f.name}</td><td>{f.folder}</td><td className="mono num">{size(f.size)}</td><td><When ts={f.written} /></td></tr>
              ))}
              {!data.files.length && <tr><td colSpan={4} className="muted">This day has no results to move aside.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <section aria-labelledby="then" className="cards" style={{ gridTemplateColumns: 'repeat(auto-fill,minmax(300px,1fr))' }}>
        <h2 id="then" style={{ gridColumn: '1/-1' }}>Then</h2>
        <div className="panel pad stack"><strong>If the redo succeeds</strong><span>The new files take their place, with the reprocessing title line in the PRC, TRO, TRP and CRD. The old set stays in SUPERSEDED.</span></div>
        <div className="panel pad stack"><strong>If it fails</strong><span>Whatever the failed attempt wrote is removed, and the old set is put back. The failure is diagnosed as usual.</span></div>
        <div className="panel pad stack"><strong>When it runs</strong><span>{lock?.held ? `After the run holding the lock (${lock.holder}) finishes. A redo is a BPE run, so it waits its turn.` : 'A redo is a BPE run: it takes the lock, so it waits for any run holding it.'}</span></div>
      </section>
      <form className="f" onSubmit={(e) => { e.preventDefault(); if (ready) go() }} style={{ maxWidth: 640 }}>
        <label>Why is this day being redone? (kept with the day's record)
          <textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <label>Type <span className="mono">{pad3(doy)}</span> to confirm
          <input value={typed} onChange={(e) => setTyped(e.target.value)} />
        </label>
        <div className="row">
          <a className="btn2" href={href.day(campaign, year, doy)}>Cancel</a>
          <button type="submit" className="btn" disabled={!ready}>Move aside and queue the redo</button>
          <span className="muted" style={{ fontSize: 13 }}>{ready ? 'Queued redos are listed on the Runs page and can be cancelled until they start.' : 'Give a reason and type the DOY to enable.'}</span>
        </div>
        {msg && <div className="banner idle" role="status">{msg.off && <span className="stub">not enabled yet</span>} {msg.text}{!msg.ok && ' Nothing was moved.'}</div>}
      </form>
    </>
  )
}
