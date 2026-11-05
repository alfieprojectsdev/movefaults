import { useEffect, useState } from 'react'
import { post, useApi } from '../lib'
import { applicable, sessionDate } from '../tsPlot'
import type { Session, TsDecision, TsSeries } from '../types'

type Choice = 'outlier' | 'not_outlier' | 'cleared'

const LABEL: Record<Choice, string> = {
  outlier: 'Outlier',
  not_outlier: 'Not an outlier',
  cleared: 'Cleared',
}

/**
 * The decision form for the epoch picked on the plot. A decision is recorded
 * with the signed-in name, the reference shown and the day's CRD hash; it never
 * changes a file or the published velocity (outlier_review_design.md).
 *
 * It offers only what makes sense for this epoch: a flagged epoch can be
 * confirmed in one click or kept as real with a reason; an unflagged one can
 * be marked as an outlier with a reason; a decided one can be undone. Going
 * against the rule's flag opens a reason box before anything is recorded.
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
  // A decision that goes against the flag waits here for its reason.
  const [pending, setPending] = useState<Choice | null>(null)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const user = session.data?.user ?? null
  const current = mine?.decision ?? null

  // A recorded decision keeps the buttons off until the reloaded decisions
  // arrive: until then they still offer what was just recorded.
  useEffect(() => setBusy(false), [decisions])

  const save = async (decision: Choice, why: string) => {
    setBusy(true)
    let r: Awaited<ReturnType<typeof post<{ detail?: string; by?: string }>>>
    try {
      r = await post<{ detail?: string; by?: string }>(`${base}/${station}/decisions`, {
        epoch, decision, reason: why, reference, auto_flag: flagged,
      })
    } catch (e) {
      setBusy(false)
      setMsg({ ok: false, text: `Not recorded: ${e instanceof Error ? e.message : String(e)}` })
      return
    }
    if (r.ok) {
      const what = decision === 'cleared' ? 'Decision undone' : `Recorded as ${LABEL[decision].toLowerCase()}`
      setMsg({ ok: true, text: `${what} by ${r.body.by}. The published velocity is unchanged.` })
      setPending(null)
      setReason('')
      onSaved()
    } else {
      setBusy(false)
      setMsg({ ok: false, text: r.body.detail ?? `Not recorded (${r.status})` })
      // The server decides the flag. If it disagrees with the page's (the
      // solution changed since it loaded), a one-click decision is refused for
      // want of a reason: open the reason box rather than leave a dead end.
      if (r.status === 422 && !why && decision !== 'cleared') setPending(decision)
    }
  }

  const against = (c: Choice) => (c === 'outlier' && !flagged) || (c === 'not_outlier' && flagged)
  const choose = (c: Choice) => {
    setMsg(null)
    if (against(c)) { setPending(c); return }
    void save(c, '')
  }

  // The actions this epoch offers, given its flag and any current decision.
  const actions: { choice: Choice; label: string; primary?: boolean }[] = []
  if (flagged) {
    if (current !== 'outlier') actions.push({ choice: 'outlier', label: 'Confirm outlier', primary: true })
    if (current !== 'not_outlier') actions.push({ choice: 'not_outlier', label: 'Keep it: not an outlier' })
  } else {
    if (current !== 'outlier') actions.push({ choice: 'outlier', label: 'Mark as outlier' })
    if (current === 'outlier') actions.push({ choice: 'not_outlier', label: 'Keep it: not an outlier', primary: true })
  }
  if (current) actions.push({ choice: 'cleared', label: 'Undo decision' })

  return (
    <section aria-labelledby="ts-decide" className="panel pad stack">
      <h2 id="ts-decide">{station} · {epoch}</h2>
      <p className="mono" style={{ fontSize: 13 }}>
        E {series.e_mm[index].toFixed(1)} · N {series.n_mm[index].toFixed(1)} · U {series.u_mm[index].toFixed(1)} mm, relative to {reference}
      </p>
      <dl className="kv">
        <dt>Outlier rule</dt>
        <dd>{flagged ? <strong>Flagged</strong> : 'Not flagged'}</dd>
        <dt>Decision</dt>
        <dd>
          {mine ? (
            <>
              <strong>{LABEL[mine.decision]}</strong> by {mine.by} ({mine.ts}){mine.reason && <>: {mine.reason}</>}
              {mine.history > 1 && <span className="muted"> · {mine.history} decisions on this epoch</span>}
            </>
          ) : <span className="muted">none yet</span>}
        </dd>
      </dl>
      {other && (
        <p className="muted" style={{ fontSize: 13 }}>
          An earlier decision on this epoch ({LABEL[other.decision]} by {other.by}) was made {other.superseded ? 'on a solution since reprocessed' : `relative to ${other.reference}`}, so it is not applied here.
        </p>
      )}
      {!user ? (
        <p className="muted" style={{ fontSize: 13 }}>Sign in to record a decision: each one is kept with who made it.</p>
      ) : pending ? (
        <form className="f" onSubmit={(e) => { e.preventDefault(); if (reason.trim() && !busy) void save(pending, reason) }}>
          <label>
            Why is this {pending === 'outlier' ? 'an outlier' : 'not an outlier'}? The rule {flagged ? 'flagged' : 'did not flag'} it, so a reason is kept with the decision.
            <textarea rows={2} value={reason} maxLength={500} autoFocus onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="row">
            <button type="submit" className="btn" disabled={busy || !reason.trim()}>Record as {user}</button>
            <button type="button" className="btn2" onClick={() => { setPending(null); setReason('') }}>Cancel</button>
          </div>
        </form>
      ) : (
        <div className="row">
          {actions.map((a) => (
            <button key={a.choice} type="button" className={a.primary ? 'btn' : 'btn2'} disabled={busy} onClick={() => choose(a.choice)}>
              {a.label}
            </button>
          ))}
          <span className="muted" style={{ fontSize: 13 }}>recorded as {user}</span>
        </div>
      )}
      {msg && <div className={`banner ${msg.ok ? 'info' : 'warn'}`} role="status">{msg.text}</div>}
    </section>
  )
}
