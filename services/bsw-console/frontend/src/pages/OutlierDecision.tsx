import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { post, useApi } from '../lib'
import { applicable, sessionDate } from '../tsPlot'
import type { Session, TsDecision, TsSeries } from '../types'

type Choice = 'outlier' | 'not_outlier' | 'cleared'

const LABEL: Record<Choice, string> = {
  outlier: 'Outlier',
  not_outlier: 'Not an outlier',
  cleared: 'Cleared',
}

/** Where a popup of this size goes beside a point: right of it, or left when it
 * would run off the plot, and kept inside the plot vertically. */
export function popupPlace(
  point: { x: number; y: number }, size: { width: number; height: number }, area: { width: number; height: number },
): { left: number; top: number } {
  const gap = 14
  const right = point.x + gap
  const left = right + size.width <= area.width ? right : Math.max(0, point.x - gap - size.width)
  const top = Math.min(Math.max(0, point.y - 24), Math.max(0, area.height - size.height))
  return { left, top }
}

/**
 * The decision popup beside the epoch picked on the plot. A decision is recorded
 * with the signed-in name, the reference shown and the day's CRD hash; it never
 * changes a file or the published velocity (outlier_review_design.md).
 *
 * It offers only what makes sense for this epoch: a flagged epoch can be
 * confirmed in one click or kept as real with a reason; an unflagged one can
 * be marked as an outlier with a reason; a decided one can be undone. Going
 * against the rule's flag opens a reason box before anything is recorded.
 *
 * It is a popup and not a modal: the plot stays usable, a click on another epoch
 * moves it there, and recording closes it, so a run of epochs is one click each.
 * Escape, the close button or a click elsewhere closes it.
 */
export default function OutlierDecision({ base, station, reference, series, index, decisions, point, onSaved, onClose }: {
  base: string; station: string; reference: string; series: TsSeries; index: number
  decisions?: TsDecision[]; point: { x: number; y: number }
  onSaved: (text: string) => void; onClose: () => void
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
  const [msg, setMsg] = useState<{ text: string } | null>(null)
  const user = session.data?.user ?? null
  const current = mine?.decision ?? null

  const box = useRef<HTMLElement>(null)
  // Measured on every render, because the reason box and a message change its size.
  useLayoutEffect(() => {
    const el = box.current
    const area = el?.offsetParent
    if (!el || !area) return
    const { left, top } = popupPlace(point, { width: el.offsetWidth, height: el.offsetHeight },
      { width: area.clientWidth, height: area.clientHeight })
    el.style.left = `${left}px`
    el.style.top = `${top}px`
  })

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      if (pending) { setPending(null); setReason('') } else onClose()
    }
    const down = (e: MouseEvent) => {
      const t = e.target as Element
      // A click on the plot picks another epoch or starts a zoom: the plot decides.
      if (!box.current?.contains(t) && !t.closest?.('[data-testid="ts-plot"]')) onClose()
    }
    document.addEventListener('keydown', key)
    document.addEventListener('mousedown', down)
    return () => {
      document.removeEventListener('keydown', key)
      document.removeEventListener('mousedown', down)
    }
  }, [pending, onClose])

  const save = async (decision: Choice, why: string) => {
    setBusy(true)
    let r: Awaited<ReturnType<typeof post<{ detail?: string; by?: string }>>>
    try {
      r = await post<{ detail?: string; by?: string }>(`${base}/${station}/decisions`, {
        epoch, decision, reason: why, reference, auto_flag: flagged,
      })
    } catch (e) {
      setBusy(false)
      setMsg({ text: `Not recorded: ${e instanceof Error ? e.message : String(e)}` })
      return
    }
    if (r.ok) {
      const what = decision === 'cleared' ? 'Decision undone' : `Recorded as ${LABEL[decision].toLowerCase()}`
      onSaved(`${station} ${epoch}: ${what.charAt(0).toLowerCase()}${what.slice(1)} by ${r.body.by}. The published velocity is unchanged.`)
    } else {
      setBusy(false)
      setMsg({ text: r.body.detail ?? `Not recorded (${r.status})` })
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
    <section ref={box} role="dialog" aria-labelledby="ts-decide" className="popup stack" style={{ gap: 8 }}>
      <div className="row" style={{ justifyContent: 'space-between', flexWrap: 'nowrap' }}>
        <h3 id="ts-decide" style={{ margin: 0 }}>{station} · {epoch}</h3>
        <button type="button" className="popup-x" aria-label="Close" onClick={onClose}>×</button>
      </div>
      <p className="mono" style={{ fontSize: 12, margin: 0 }}>
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
        <form className="f" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (reason.trim() && !busy) void save(pending, reason) }}>
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
      {msg && <div className="banner warn" role="status" style={{ padding: '8px 10px', fontSize: 13 }}>{msg.text}</div>}
    </section>
  )
}
