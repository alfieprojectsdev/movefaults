import { useMemo, useState } from 'react'
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
