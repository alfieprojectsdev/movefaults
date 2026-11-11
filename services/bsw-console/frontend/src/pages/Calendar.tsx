import { useState } from 'react'
import { useApi, pad3 } from '../lib'
import { href } from '../route'
import type { Calendar as Cal, DayState } from '../types'
import { Failed, Loading } from './common'

const WORDS: Record<DayState, string> = {
  fixed: 'solved, ambiguities fixed',
  float: 'solved, float (ambiguities not fixed)',
  failed: 'failed',
  running: 'running now',
  queued: 'queued in the current run',
  excluded: 'excluded by the plan',
  none: 'not run',
}
const LEGEND: [DayState, string][] = [
  ['fixed', 'Fixed'], ['float', 'Float'], ['failed', 'Failed'], ['running', 'Running'],
  ['queued', 'Queued in the current run'], ['excluded', 'Excluded by the plan'], ['none', 'Not run'],
]
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export default function Calendar({ campaign, year }: { campaign: string; year: number }) {
  const { data, error } = useApi<Cal>(`/api/campaigns/${campaign}/years/${year}/days`)
  const [sel, setSel] = useState<number | null>(null)
  const [end, setEnd] = useState<number | null>(null)
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="the calendar" />

  const months = MONTHS.map((name, i) => ({ name, days: data.days.filter((d) => Number(d.date.slice(5, 7)) === i + 1) }))
  const pick = (doy: number, shift: boolean) => {
    if (shift && sel != null) setEnd(doy)
    else { setSel(doy); setEnd(null) }
  }
  const s = sel != null ? data.days[sel - 1] : null
  const lo = sel != null && end != null ? Math.min(sel, end) : sel
  const hi = sel != null && end != null ? Math.max(sel, end) : sel
  const inRange = (doy: number) => lo != null && hi != null && doy >= lo && doy <= hi

  return (
    <>
      <div className="titlebar">
        <div>
          <h1>{campaign} · {year}</h1>
          <p className="muted">One square per day, labelled with the day of the month; its DOY is in the panel on the right. Shift-click a second day to select a range.</p>
        </div>
        <div className="seg" role="group" aria-label="Year">
          {[year - 1, year, year + 1].map((y) => (
            <a key={y} className="btn2" href={href.calendar(campaign, y)} aria-current={y === year ? 'page' : undefined} style={y === year ? { background: 'var(--badge)', color: 'var(--badge-ink)' } : undefined}>{y}</a>
          ))}
        </div>
      </div>
      <div className="legend">
        {LEGEND.map(([k, label]) => (
          <span key={k}><span aria-hidden="true" className={`key st-${k}`} />{label} ({data.counts[k]})</span>
        ))}
      </div>
      <div className="cols calcols">
        <section aria-label="Days of the year" className="panel pad scroll">
          <div className="cal">
            {months.map((m) => (
              <div key={m.name} className="m">
                <span>{m.name}</span>
                {m.days.map((d) => (
                  <button
                    key={d.doy}
                    type="button"
                    className={`cell st-${d.state}`}
                    aria-pressed={inRange(d.doy)}
                    aria-label={`DOY ${pad3(d.doy)}, ${WORDS[d.state]}`}
                    title={`DOY ${pad3(d.doy)}, ${WORDS[d.state]}`}
                    onClick={(e) => pick(d.doy, e.shiftKey)}
                  >
                    {Number(d.date.slice(8))}
                  </button>
                ))}
              </div>
            ))}
          </div>
        </section>
        <aside aria-label="Selected day" className="panel pad stack">
          {s ? (
            <>
              <h2>{end != null ? `DOY ${pad3(lo!)}–${pad3(hi!)} · ${year}` : `DOY ${pad3(s.doy)} · ${year}`}</h2>
              <dl className="kv">
                <dt>Date</dt><dd className="mono">{s.date}</dd>
                <dt>DOY</dt><dd className="mono">{pad3(s.doy)}</dd>
                <dt>GPS week</dt><dd className="mono">{s.gps_week}, day {s.gps_day}</dd>
                <dt>Session</dt><dd className="mono">{s.session}</dd>
                <dt>State</dt><dd>{WORDS[s.state]}</dd>
              </dl>
              {s.note && <p style={{ fontSize: 13, overflowWrap: 'anywhere' }}>{s.note}</p>}
              <div className="stack" style={{ fontSize: 13 }}>
                <a href={href.day(campaign, year, s.doy)}>Open this day</a>
                {s.state === 'failed' && <a href={href.failure(campaign, year, s.doy)}>Why it failed</a>}
                <a href={href.plan(campaign, year, lo!, hi!)}>Plan a run {end != null ? 'for this range' : 'starting here'}</a>
              </div>
            </>
          ) : (
            <p className="muted">Pick a day. Shift-click a second one to select a range for a plan.</p>
          )}
        </aside>
      </div>
      <p className="faint" style={{ fontSize: 12 }}>Fixed and float come from the FIN files in SAVEDISK (float: solved only by the float PCF). Failed, running and queued come from the service's run record. Days excluded by a plan are shown on the Plan screen; the run record does not keep plans.</p>
    </>
  )
}
