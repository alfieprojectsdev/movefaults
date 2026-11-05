import { useEffect, useState } from 'react'
import { useApi } from '../lib'
import { href } from '../route'
import type { Enu, TsStation, TsSummary } from '../types'
import { Failed, Loading } from './common'
import TsPlot from './TsPlot'
import OutlierDecision from './OutlierDecision'

const mm = (v: number) => v.toFixed(2)
const rate = (v: Enu, s: Enu, c: keyof Enu) => `${mm(v[c])} ± ${mm(s[c])}`

/** Read-only: what pogf_geodetic_suite.timeseries.status returns, as it returns it. */
export default function TimeSeries({ campaign, year }: { campaign: string; year: number }) {
  const base = `/api/campaigns/${campaign}/years/${year}/time-series`
  // The reference is the viewer's choice; '' means the server's default, if any.
  const [reference, setReference] = useState('')
  const q = reference ? `?reference=${reference}` : ''
  const sum = useApi<TsSummary>(`${base}${q}`)
  const [station, setStation] = useState('')
  const one = useApi<TsStation>(station && station !== reference ? `${base}/${station}${q}` : null)
  const candidates = sum.data && sum.data.configured ? sum.data.all_stations ?? [] : []
  const chosen = sum.data && sum.data.configured ? sum.data.reference : null
  // A default the files do not hold is no choice: show the placeholder, so every
  // real candidate stays pickable.
  const shown = chosen && candidates.includes(chosen) ? chosen : ''
  // useApi keeps the last answer while a new URL loads, or after the URL goes
  // away. Show a station only when the answer is for this station AND this
  // reference, never an old pair under a new heading.
  const current =
    one.data && one.data.configured && one.data.available && station && one.data.station === station && one.data.reference === chosen
      ? one.data
      : null
  const currentProblem =
    one.data && one.data.configured && !one.data.available && station && one.data.station === station && one.data.reference === chosen
      ? one.data.message
      : null
  const pickReference = (r: string) => { setReference(r); if (r === station) setStation('') }

  return (
    <>
      <div className="stack">
        <h1>Time series · {campaign} {year} <span className="stub">read-only</span></h1>
        <p className="muted" style={{ maxWidth: '80ch' }}>
          East, north and up per station relative to a reference station, with the offset-aware velocity from the timeseries package (the port of <span className="mono">vel_line_v8.m</span> verified against PHIVOLCS' output) and the offsets from the offsets catalogue. Outliers arrive flagged by the package; confirming or overriding one is not built here yet.
        </p>
      </div>
      {sum.error && <Failed error={sum.error} />}
      {!sum.data && !sum.error && <Loading what="the time series" />}
      {sum.data && !sum.data.configured && (
        <div className="banner idle" role="status"><strong>Not configured.</strong> <span>{sum.data.message}</span></div>
      )}
      {sum.data && sum.data.configured && (sum.data.years ?? []).length > 0 && (
        <label className="row" style={{ fontSize: 13 }}>
          Year
          <select aria-label="Year" value={year} onChange={(e) => { window.location.hash = href.timeSeries(campaign, Number(e.target.value)) }}>
            {!(sum.data.years ?? []).includes(year) && <option value={year}>{year}</option>}
            {(sum.data.years ?? []).map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <span className="muted">Daily final CRDs of {campaign} {year}, from <span className="mono">{sum.data.crd_dir}</span>.</span>
        </label>
      )}
      {candidates.length > 0 && (
        <label className="row" style={{ fontSize: 13 }}>
          Reference station
          <select aria-label="Reference station" value={shown} onChange={(e) => pickReference(e.target.value)}>
            {!shown && <option value="">Choose a reference…</option>}
            {candidates.map((s) => <option key={s} value={s}>{s}{sum.data && sum.data.configured && s === sum.data.default_reference ? ' (default)' : ''}</option>)}
          </select>
          <span className="muted">Every series is relative to it; changing it re-fits every station.</span>
        </label>
      )}
      {sum.data && sum.data.configured && !sum.data.available && (
        <div className="banner warn" role="status"><strong>Cannot read the time series.</strong> <span>{sum.data.message}</span></div>
      )}
      {sum.data && sum.data.configured && sum.data.available && !sum.data.reference && (
        <div className="banner idle" role="status">{sum.data.message ?? 'Choose a reference station.'}</div>
      )}
      {sum.data && sum.data.configured && sum.data.available && sum.data.reference && (
        <section className="stack">
          <p style={{ fontSize: 13 }}>
            Daily final CRDs from <span className="mono">{sum.data.crd_dir}</span>, relative to <span className="mono">{sum.data.reference}</span>; offsets from <span className="mono">{sum.data.offsets_path}</span>. Outlier mode: <strong>{sum.data.outlier_mode}</strong>.
          </p>
          <label className="row" style={{ fontSize: 13 }}>
            Station
            <select value={station} onChange={(e) => setStation(e.target.value)}>
              <option value="">Choose a station…</option>
              {sum.data.stations.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </label>
          {one.error && <Failed error={one.error} />}
          {station && !current && !currentProblem && !one.error && <Loading what={`${station}'s time series`} />}
          {currentProblem && <div className="banner warn" role="status">{currentProblem}</div>}
          {current && <Station key={`${current.station}-${current.reference}`} data={current} base={base} reload={one.reload} />}
        </section>
      )}
      <p className="faint" style={{ fontSize: 13 }}>Open team decision: whether a flagged outlier is excluded from the velocity fit, or only recorded. The mode above says which produced these numbers.</p>
    </>
  )
}

function Station({ data, base, reload }: { data: Extract<TsStation, { available: true }>; base: string; reload: () => void }) {
  const v = data.velocity
  const flagged = data.series.outlier.filter(Boolean).length
  const [picked, setPicked] = useState<number | null>(null)
  useEffect(() => setPicked(null), [data.station, data.reference])
  const fit = data.decided_fit
  return (
    <div className="stack">
      <TsPlot series={data.series} segments={data.segments} offsets={data.offsets} station={data.station}
        decisions={data.decisions} decidedFit={fit} onPick={setPicked} />
      {picked !== null && data.reference && (
        <OutlierDecision key={picked} base={base.split('?')[0]} station={data.station} reference={data.reference}
          series={data.series} index={picked} decisions={data.decisions} onSaved={reload} />
      )}
      <section aria-labelledby="ts-vel" className="panel pad stack">
        <h2 id="ts-vel">{data.station} · velocity (final segment)</h2>
        <table className="t">
          <thead><tr><th scope="col"></th><th scope="col">East</th><th scope="col">North</th><th scope="col">Up</th></tr></thead>
          <tbody>
            <tr><th scope="row">mm/yr ± 1σ</th>{(['e', 'n', 'u'] as const).map((c) => <td key={c} className="mono num" style={v.short_span ? { textDecoration: 'line-through' } : undefined}>{rate(v.velocity_mm_yr, v.sigma_mm_yr, c)}</td>)}</tr>
            {fit && fit.available && (
              <tr><th scope="row">without {fit.excluded.length} confirmed outlier{fit.excluded.length === 1 ? '' : 's'} <span className="muted">(not published)</span></th>{(['e', 'n', 'u'] as const).map((c) => <td key={c} className="mono num">{rate(fit.velocity.velocity_mm_yr, fit.velocity.sigma_mm_yr, c)}</td>)}</tr>
            )}
          </tbody>
        </table>
        <p style={{ fontSize: 13 }}>
          Span {v.span_yr.toFixed(2)} yr{v.short_span && <strong> · shorter than {data.min_span_years} yr: too little data to mean anything</strong>}
          {!v.covers_latest_epoch && <strong> · the newest epochs sit in an interval too short to fit: this is the rate before the latest event</strong>}
        </p>
        <dl className="kv">
          <dt>Outlier mode</dt><dd><strong>{data.outlier_rule.mode}</strong> ({data.outlier_rule.method}, factor {data.outlier_rule.factor}, {data.outlier_rule.scope.replace('_', ' ')}, on {data.outlier_rule.on.replace('_', ' ')}){data.outlier_rule.mode === 'record' && <span className="muted"> · flagged epochs are reported and kept in the fit</span>}</dd>
          <dt>Outliers flagged</dt><dd>{flagged} of {data.series.t.length} epochs</dd>
          <dt>Offsets catalog</dt><dd>{data.offsets_catalog ? <><span className="mono">{data.offsets_catalog.path}</span><br /><span className="mono" style={{ fontSize: 12 }}>sha256 {data.offsets_catalog.sha256}</span></> : 'none'}</dd>
        </dl>
      </section>
      <section aria-labelledby="ts-seg" className="panel scroll">
        <table className="t">
          <caption id="ts-seg" style={{ textAlign: 'left' }}>Segments, split at the catalogue's events</caption>
          <thead><tr><th scope="col">#</th><th scope="col">From</th><th scope="col">To</th><th scope="col">Epochs</th><th scope="col">In fit</th><th scope="col">Outliers</th><th scope="col">East mm/yr</th><th scope="col">North mm/yr</th><th scope="col">Up mm/yr</th></tr></thead>
          <tbody>
            {data.segments.map((s) => (
              <tr key={s.index}>
                <td className="num">{s.index}</td><td className="mono">{s.t_start.toFixed(4)}</td><td className="mono">{s.t_end.toFixed(4)}</td>
                <td className="num">{s.n_epochs}</td><td className="num">{s.n_fit}</td><td className="num">{s.n_outliers}</td>
                {(['e', 'n', 'u'] as const).map((c) => <td key={c} className="mono num">{rate(s.velocity_mm_yr, s.sigma_mm_yr, c)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>
      </section>
      {data.offsets.length > 0 && (
        <p style={{ fontSize: 13 }}>Offsets: {data.offsets.map((o) => `${o.t.toFixed(4)} ${o.type} (${o.label})${o.within_span ? '' : ', outside the series'}`).join('; ')}</p>
      )}
      {data.warnings.length > 0 && <ul className="muted" style={{ fontSize: 13 }}>{data.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
    </div>
  )
}
