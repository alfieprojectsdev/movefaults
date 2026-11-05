import { useState } from 'react'
import { post, useApi } from '../lib'
import { applicable, sessionDate } from '../tsPlot'
import type { Session, TsDecision, TsSeries } from '../types'

type Choice = 'outlier' | 'not_outlier' | 'cleared'

const LABEL: Record<Choice, string> = {
  outlier: 'Outlier',
  not_outlier: 'Not an outlier',
  cleared: 'Clear my decision',
}

/**
 * The decision form for the epoch picked on the plot. A decision is recorded
 * with the signed-in name, the reference shown and the day's CRD hash; it never
 * changes a file or the published velocity (outlier_review_design.md).
 */
export default function OutlierDecision({ base, station, reference, series, index, decisions, onSaved }: {
  base: string; station: string; reference: string; series: TsSeries; index: number
  decisions?: TsDecision[]; onSaved: () => void
}) {
  const session = useApi<Session>('/api/session')
  const epoch = sessionDate(series.t[index])
  const flagged = series.outlier[index]
  const mine = applicable(decisions).get(epoch)
  const other = (decisions ?? []).find((d) => d.epoch === epoch && (d.superseded || d.other_reference))
  const [choice, setChoice] = useState<Choice>(mine ? mine.decision : flagged ? 'outlier' : 'not_outlier')
  const [reason, setReason] = useState('')
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const against = (choice === 'outlier' && !flagged) || (choice === 'not_outlier' && flagged)
  const user = session.data?.user ?? null
  const ready = !!user && (!against || reason.trim().length > 0)

  const save = async () => {
    const r = await post<{ detail?: string; by?: string }>(`${base}/${station}/decisions`, {
      epoch, decision: choice, reason, reference, auto_flag: flagged,
    })
    if (r.ok) {
      setMsg({ ok: true, text: `Recorded by ${r.body.by}. The published velocity is unchanged.` })
      setReason('')
      onSaved()
    } else {
      setMsg({ ok: false, text: r.body.detail ?? `Not recorded (${r.status})` })
    }
  }

  return (
    <section aria-labelledby="ts-decide" className="panel pad stack">
      <h2 id="ts-decide">{station} · {epoch}</h2>
      <p className="mono" style={{ fontSize: 13 }}>
        E {series.e_mm[index].toFixed(1)} · N {series.n_mm[index].toFixed(1)} · U {series.u_mm[index].toFixed(1)} mm, relative to {reference} ·{' '}
        {flagged ? 'flagged by the outlier rule' : 'not flagged'}
      </p>
      {mine && (
        <p style={{ fontSize: 13 }}>
          Current decision: <strong>{LABEL[mine.decision]}</strong> by {mine.by} ({mine.ts}){mine.reason && <>: {mine.reason}</>}
          {mine.history > 1 && <span className="muted"> · {mine.history} decisions on this epoch</span>}
        </p>
      )}
      {other && (
        <p className="muted" style={{ fontSize: 13 }}>
          An earlier decision on this epoch ({LABEL[other.decision]} by {other.by}) was made {other.superseded ? 'on a solution since reprocessed' : `relative to ${other.reference}`}, so it is not applied here.
        </p>
      )}
      {!user ? (
        <p className="muted" style={{ fontSize: 13 }}>Sign in to record a decision: each one is kept with who made it.</p>
      ) : (
        <form className="f stack" onSubmit={(e) => { e.preventDefault(); if (ready) save() }}>
          <fieldset className="row" style={{ border: 0, padding: 0, gap: 16 }}>
            <legend className="muted" style={{ fontSize: 13 }}>Decision</legend>
            {(['outlier', 'not_outlier', 'cleared'] as Choice[]).map((c) => (
              <label key={c} className="row" style={{ gap: 6 }}>
                <input type="radio" name="decision" value={c} checked={choice === c} onChange={() => setChoice(c)} disabled={c === 'cleared' && !mine} />
                {LABEL[c]}
              </label>
            ))}
          </fieldset>
          <label className="stack" style={{ fontSize: 13, gap: 4 }}>
            Reason{against ? ' (needed: this goes against the automatic flag)' : ' (optional)'}
            <textarea rows={2} value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="row">
            <button type="submit" className="btn" disabled={!ready}>Record as {user}</button>
          </div>
        </form>
      )}
      {msg && <div className={`banner ${msg.ok ? 'info' : 'warn'}`} role="status">{msg.text}</div>}
    </section>
  )
}
