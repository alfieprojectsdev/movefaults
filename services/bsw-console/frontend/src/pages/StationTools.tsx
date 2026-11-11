import { useRef, useState, type RefObject } from 'react'
import { post, useApi } from '../lib'
import type { AprioriPreview, BlqCheck, OnsalaRequest } from '../types'
import { Failed, Loading } from './common'

/** Copy to the clipboard, or select the text when the browser refuses or has
 * no clipboard (plain http on the office LAN is not a secure context). */
function CopyButton({ text, target }: { text: string; target: RefObject<HTMLTextAreaElement | null> }) {
  const [done, setDone] = useState(false)
  return (
    <button type="button" className="btn2 sm" onClick={() => {
      const select = () => target.current?.select()
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => setDone(true), select)
      else select()
    }}>{done ? 'Copied' : 'Copy'}</button>
  )
}

/** Ocean loading, 5.3.10: what to paste into the Onsala form, and a check of its reply. */
export function OceanLoading({ campaign, year }: { campaign: string; year: number }) {
  const base = `/api/campaigns/${campaign}/years/${year}/station-files`
  const req = useApi<OnsalaRequest>(`${base}/onsala-request`)
  const [reply, setReply] = useState('')
  const [check, setCheck] = useState<BlqCheck | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const area = useRef<HTMLTextAreaElement>(null)
  const run = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await post<BlqCheck & { detail?: string }>(`${base}/blq-check`, { reply })
      if (r.ok) setCheck(r.body); else setErr(r.body.detail ?? `HTTP ${r.status}`)
    } catch (e) { setErr(String(e)) } finally { setBusy(false) }
  }
  return (
    <section aria-labelledby="blq" className="panel pad stack">
      <h2 id="blq">Ocean loading (BLQ)</h2>
      {req.error && <Failed error={req.error} />}
      {!req.data && !req.error && <Loading what="the stations missing from the BLQ" />}
      {req.data && (
        <>
          <p style={{ fontSize: 13 }}>
            The Chalmers/Onsala service computes the coefficients and replies by email. {req.data.lines.length
              ? <>Paste these {req.data.lines.length} lines into <a href={req.data.form} target="_blank" rel="noreferrer">its form</a>: the stations in <span className="mono">{req.data.sta}</span> with no block in <span className="mono">{req.data.blq}</span>, at their coordinates in <span className="mono">{req.data.crd}</span> ({req.data.crd_datum ?? 'datum not stated'}, epoch {req.data.crd_epoch ?? 'not stated'}).</>
              : <>Every station in <span className="mono">{req.data.sta}</span> has a block in <span className="mono">{req.data.blq}</span>; there is nothing to request.</>}
          </p>
          {req.data.lines.length > 0 && (
            <>
              <textarea ref={area} readOnly className="mono" rows={Math.min(req.data.lines.length + 1, 12)} value={req.data.lines.join('\n')} aria-label="Lines for the Onsala form" style={{ width: '100%' }} />
              <div className="row"><CopyButton text={req.data.lines.join('\n')} target={area} /></div>
              <p style={{ fontSize: 13 }}>Choose the same settings the BLQ was made with, so the new blocks match the old: {Object.entries(req.data.settings).map(([k, v]) => <span key={k}>{k} <strong>{v ?? 'not stated in the BLQ'}</strong>; </span>)}</p>
            </>
          )}
          {req.data.no_coordinates.length > 0 && <div className="banner warn" role="status">Not in <span className="mono">{req.data.crd}</span>, so no coordinates to send: {req.data.no_coordinates.join(' ')}.</div>}
          {req.data.two_names.length > 0 && <p className="faint" style={{ fontSize: 13 }}>Listed under two names in the CRD; the first was used: {req.data.two_names.join('; ')}.</p>}
        </>
      )}
      <label className="stack" style={{ fontSize: 13 }}>
        Then paste the emailed reply here to check it before it is merged:
        <textarea className="mono" rows={6} value={reply} onChange={(e) => { setReply(e.target.value); setCheck(null) }} style={{ width: '100%' }} />
      </label>
      <div className="row"><button type="button" className="btn2" disabled={!reply.trim() || busy} onClick={run}>{busy ? 'Checking…' : 'Check the reply'}</button></div>
      {err && <Failed error={err} />}
      {check && (
        <div className="stack" aria-label="Reply check">
          <div className={`banner ${check.ready ? 'info' : 'warn'}`} role="status">
            {check.ready
              ? <><strong>Ready to merge:</strong> {check.new.join(' ')}.</>
              : <strong>Not ready to merge as it is.</strong>}
          </div>
          {[...check.problems, ...check.settings_differ].map((p) => <p key={p} style={{ fontSize: 13 }}>{p}</p>)}
          {check.stations.length > 0 && (
            <div className="scroll">
              <table className="t" style={{ fontSize: 13 }}>
                <thead><tr><th scope="col">Station</th><th scope="col">Against the BLQ</th><th scope="col">Key line</th><th scope="col">Problems</th></tr></thead>
                <tbody>
                  {check.stations.map((s, i) => (
                    // A station can come twice in a reply; the index keeps the keys apart.
                    <tr key={`${s.station}-${i}`}>
                      <td className="mono">{s.station}</td><td>{s.status}</td>
                      <td>{{ ok: 'line 3', early: 'early: merge_blq.py moves it', missing: 'missing', late: 'too late' }[s.key_line]}</td>
                      <td>{s.problems.join('; ') || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p style={{ fontSize: 13 }}>The merge is the maintainer's step: save the reply as a file, then run <span className="mono">{check.command}</span>, first as a dry run and then with <span className="mono">--apply</span>, while no run is using the BLQ. It keeps a backup and puts new blocks before <span className="mono">$$ END TABLE</span>, where Bernese reads them.</p>
        </div>
      )}
    </section>
  )
}

const mm = (v: number) => v.toFixed(1)

/** "Use a final CRD as a priori", 5.5.6: what the replacement would change, per station. */
export function AprioriPreviewPanel({ campaign, year }: { campaign: string; year: number }) {
  const [final, setFinal] = useState('')
  const q = final ? `?final=${encodeURIComponent(final)}` : ''
  const { data, error } = useApi<AprioriPreview>(`/api/campaigns/${campaign}/years/${year}/station-files/apriori-preview${q}`)
  const [all, setAll] = useState(false)
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="the a priori comparison" />
  const rows = all ? data.rows : data.rows.slice(0, 15)
  return (
    <section aria-labelledby="apr" className="panel pad stack">
      <h2 id="apr">Use a final CRD as a priori: what would change</h2>
      <p style={{ fontSize: 13 }}>Each station the final solution estimated, against <span className="mono">{data.apriori.file}</span> ({data.apriori.datum ?? '?'}, epoch {data.apriori.epoch ?? '?'}). Largest first. Replacing the file stays with the maintainer until it is decided how a change to a campaign file is reviewed.</p>
      {data.finals.length > 0 ? (
        <label className="row" style={{ fontSize: 13 }}>Final CRD
          <select value={final || data.final.file || ''} onChange={(e) => setFinal(e.target.value)}>
            {data.finals.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <span className="muted">{data.final.datum ?? '?'}, epoch {data.final.epoch ?? '?'}</span>
        </label>
      ) : <p className="muted">No final CRD for {year} yet.</p>}
      {data.warnings.map((w) => <div key={w} className="banner warn" role="status">{w}</div>)}
      {data.rows.length > 0 && (
        <div className="scroll">
          <table className="t" style={{ fontSize: 13 }}>
            <thead><tr><th scope="col">Station</th><th scope="col" className="num">North mm</th><th scope="col" className="num">East mm</th><th scope="col" className="num">Up mm</th><th scope="col" className="num">Horizontal mm</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.station}>
                  <td className="mono">{r.station}</td>
                  {r.neu_mm ? <>{r.neu_mm.map((v, i) => <td key={i} className="mono num">{mm(v)}</td>)}<td className="mono num"><strong>{mm(r.horizontal_mm!)}</strong></td></>
                    : <td colSpan={4} className="muted">not in the a priori file: would be added</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.rows.length > 15 && <div className="row"><button type="button" className="btn2 sm" onClick={() => setAll(!all)}>{all ? 'Show the 15 largest' : `Show all ${data.rows.length}`}</button></div>}
      {data.not_estimated.length > 0 && <p className="faint" style={{ fontSize: 12 }}>{data.not_estimated.length} stations in the a priori file were not estimated by this final solution; the replacement would keep or drop them, which is part of the decision.</p>}
    </section>
  )
}
