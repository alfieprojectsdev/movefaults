import { type ReactNode, useEffect, useMemo, useState } from 'react'
import { lineClass, when } from '../lib'

export function Loading({ what }: { what: string }) {
  return <p className="muted">Reading {what}…</p>
}

export function Failed({ error }: { error: string }) {
  return <div className="err-box" role="alert">Could not read this: {error}</div>
}

export function When({ ts }: { ts: number | null | undefined }) {
  const w = when(ts)
  return <span className="mono" title={w.utc}>{w.text}</span>
}

/** BSW text with line numbers, no wrapping, search, and *** / ### highlighted. */
export function TextViewer({ lines, first = 0, search = '' }: { lines: string[]; first?: number; search?: string }) {
  const [q, setQ] = useState(search)
  const hits = useMemo(() => (q ? lines.filter((l) => l.toUpperCase().includes(q.toUpperCase())).length : 0), [q, lines])
  return (
    <div className="stack">
      <label className="row" style={{ fontSize: 13 }}>
        Find <input type="search" value={q} onChange={(e) => setQ(e.target.value)} style={{ font: 'inherit', padding: '4px 8px' }} />
        {q && <span className="muted">{hits} line(s)</span>}
      </label>
      <div className="viewer mono" role="region" aria-label="File text" tabIndex={0}>
        {lines.map((t, i) => (
          <div key={i} className={`ln ${i < first ? 'old' : lineClass(t, q)}`}>
            <span>{i + 1}</span>
            <span>{t}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export type Jump = { label: string; onClick: () => void; disabled?: boolean }

/** A row of links that move the page to the part that matters, for any page
 *  long enough to need scrolling. `children` sit after them (filters, say). */
export function JumpBar({ jumps, children }: { jumps: Jump[]; children?: ReactNode }) {
  return (
    <nav aria-label="Jump to" className="jumpbar">
      <span className="muted">Jump to</span>
      {jumps.map((j) => (
        <button key={j.label} type="button" className="btn2 sm" disabled={j.disabled} onClick={j.onClick}>{j.label}</button>
      ))}
      {children}
    </nav>
  )
}

/** Scroll an element into the middle of the view. jsdom has no scrollIntoView. */
export function scrollToId(id: string): boolean {
  const el = document.getElementById(id)
  if (!el) return false
  el.scrollIntoView?.({ block: 'center', behavior: 'smooth' })
  return true
}

/** A "Top" button that appears once the page is more than two screens down. */
export function BackToTop() {
  const [show, setShow] = useState(false)
  useEffect(() => {
    const on = () => setShow(window.scrollY > 2 * window.innerHeight)
    on()
    window.addEventListener('scroll', on, { passive: true })
    window.addEventListener('resize', on)
    return () => {
      window.removeEventListener('scroll', on)
      window.removeEventListener('resize', on)
    }
  }, [])
  if (!show) return null
  return (
    <button type="button" className="btn2 totop" onClick={() => window.scrollTo({ top: 0, behavior: 'smooth' })}>
      Top
    </button>
  )
}
