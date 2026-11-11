import { useState } from 'react'
import { pad3, useApi } from '../lib'
import { href } from '../route'
import type { Inventory as Inv } from '../types'
import { Failed, Loading } from './common'

/** One step of the chain: what has arrived there, and what waits before it. */
function Step({ title, children, off }: { title: string; children: React.ReactNode; off?: string }) {
  return (
    <div className="panel pad stack" style={{ minWidth: 0 }}>
      <h2 style={{ fontSize: 14 }}>{title}</h2>
      {off ? <p className="faint" style={{ fontSize: 13 }}><span className="stub">not connected</span> {off}</p> : <div style={{ fontSize: 13 }}>{children}</div>}
    </div>
  )
}

export default function Inventory({ campaign, year }: { campaign: string; year: number }) {
  const { data, error } = useApi<Inv>(`/api/campaigns/${campaign}/years/${year}/inventory`)
  const [onlyWaiting, setOnlyWaiting] = useState(true)
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="the inventory" />
  const t = data.totals
  // The data, not the props: until the next year's answer arrives, data is still the last one.
  const { campaign: c, year: y } = data
  const waiting = (r: Inv['rows'][number]) => r.waiting_days > 0 || r.velocity === false || r.in_sta === false
  const rows = (onlyWaiting ? data.rows.filter(waiting) : data.rows).slice().sort((a, b) => b.waiting_days - a.waiting_days || a.station.localeCompare(b.station))
  return (
    <>
      <div className="titlebar">
        <div>
          <h1>Inventory · {c} {y}</h1>
          <p className="muted" style={{ maxWidth: '80ch' }}>How far each station's data has got this year, step by step, and what is waiting at each step. A step whose source this server cannot read says so instead of guessing.</p>
        </div>
        <div className="seg" role="group" aria-label="Year">
          {[year - 1, year, year + 1].map((n) => <a key={n} className="btn2" href={href.inventory(campaign, n)} aria-current={n === year ? 'page' : undefined}>{n}</a>)}
        </div>
      </div>
      <div className="cols" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
        <Step title="1. Field visit logged" off={data.not_connected.field_visits}>{null}</Step>
        <Step title="2. Raw data received" off={data.not_connected.raw_data}>{null}</Step>
        <Step title="3. RINEX in the datapool">
          <p><strong>{t.rinex_station_days}</strong> station-days, {t.rinex_stations} stations, in <span className="mono" style={{ overflowWrap: 'anywhere' }}>{data.rinex_dir}</span>.</p>
          <p className="faint"><span className="stub">not connected</span> QC: {data.not_connected.rinex_qc}</p>
        </Step>
        <Step title="4. Processed">
          <p><strong>{t.processed_station_days}</strong> station-days estimated by a final solution.</p>
          <p>Waiting: <strong>{t.waiting_in_sta}</strong> station-days with RINEX and no solution that estimated the station.{data.sta == null && <> The STA could not be read, so which stations a run would process is not known.</>}{t.waiting_not_in_sta > 0 && <> Another <strong>{t.waiting_not_in_sta}</strong> belong to stations not in <span className="mono" style={{ overflowWrap: 'anywhere' }}>{data.sta}</span>, which no run of this campaign processes.</>}</p>
        </Step>
        <Step title="5. Time series and velocity">
          <p><strong>{t.in_time_series}</strong> of these stations in the series, from a fixed solution in any year of the campaign.</p>
          <p>Waiting: <strong>{t.short_for_velocity}</strong> with less than {data.min_span_years} year of solutions, too short for a velocity.</p>
        </Step>
      </div>
      <div className="seg" role="group" aria-label="Rows">
        <button type="button" aria-pressed={onlyWaiting} onClick={() => setOnlyWaiting(true)}>Stations with something waiting</button>
        <button type="button" aria-pressed={!onlyWaiting} onClick={() => setOnlyWaiting(false)}>Every station ({data.rows.length})</button>
      </div>
      <div className="panel scroll">
        <table className="t" style={{ fontSize: 13 }}>
          <thead><tr><th scope="col">Station</th><th scope="col">In {data.sta ?? 'the STA'}</th><th scope="col" className="num">RINEX days</th><th scope="col" className="num">Processed days</th><th scope="col">Waiting</th><th scope="col">Span of solutions</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.station}>
                <td className="mono">{r.station}</td>
                <td>{r.in_sta == null ? <span className="faint">not known</span> : r.in_sta ? 'yes' : r.processed_days ? 'no' : <strong style={{ color: 'var(--warn-strong)' }}>no: never processed</strong>}</td>
                <td className="num">{r.rinex_days}</td>
                <td className="num">{r.processed_days}</td>
                <td>{r.waiting_days ? <>{r.waiting_days} {r.waiting_days === 1 ? 'day' : 'days'}: {r.waiting_first.map((d, i) => <span key={d}>{i > 0 && ', '}<a href={href.day(c, y, d)}>{pad3(d)}</a></span>)}{r.waiting_days > r.waiting_first.length && ', …'}</> : '—'}</td>
                <td>{r.span_years == null ? '—' : <>{r.span_years.toFixed(2)} yr{r.velocity === false && <span className="faint"> · too short for a velocity</span>}</>}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={6} className="muted">{onlyWaiting ? 'Nothing waiting.' : 'No station has RINEX or a solution this year.'}</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="faint" style={{ fontSize: 12 }}>RINEX from the campaign's datapool directory (the PCF's V_RNXDIR); processed from the year's final CRDs, counting only the stations each one estimated; the span covers every year of the campaign, as the Time series page reads them. A waiting day can be one not run yet, one that failed, or one where the station was dropped from the solution: its Day page says which.</p>
    </>
  )
}
