import { useState } from 'react'
import { useApi } from '../lib'
import type { Enu, TsStation, TsSummary } from '../types'
import { Failed, Loading } from './common'

const mm = (v: number) => v.toFixed(2)
const rate = (v: Enu, s: Enu, c: keyof Enu) => `${mm(v[c])} ± ${mm(s[c])}`

/** Read-only: what pogf_geodetic_suite.timeseries.status returns, as it returns it. */
export default function TimeSeries({ campaign }: { campaign: string }) {
  const base = `/api/campaigns/${campaign}/time-series`
  // The reference is the viewer's choice; '' means the server's default, if any.
  const [reference, setReference] = useState('')
  const q = reference ? `?reference=${reference}` : ''
  const sum = useApi<TsSummary>(`${base}${q}`)
  const [station, setStation] = useState('')
  const one = useApi<TsStation>(station && station !== reference ? `${base}/${station}${q}` : null)
  const candidates = sum.data && sum.data.configured ? sum.data.all_stations ?? [] : []
  const chosen = sum.data && sum.data.configured ? sum.data.reference : null
  const pickReference = (r: string) => { setReference(r); if (r === station) setStation('') }

  return (
    <>
      <div className="stack">
        <h1>Time series · {campaign} <span className="stub">read-only</span></h1>
        <p className="muted" style={{ maxWidth: '80ch' }}>
          East, north and up per station relative to a reference station, with the offset-aware velocity from the timeseries package (the port of <span className="mono">vel_line_v8.m</span> verified against PHIVOLCS' output) and the offsets from the offsets catalogue. Outliers arrive flagged by the package; confirming or overriding one is not built here.
        </p>
      </div>
      {sum.error && <Failed error={sum.error} />}
      {!sum.data && !sum.error && <Loading what="the time series" />}
      {sum.data && !sum.data.configured && (
        <div className="banner idle" role="status"><strong>Not configured.</strong> <span>{sum.data.message}</span></div>
      )}
      {candidates.length > 0 && (
        <label className="row" style={{ fontSize: 13 }}>
          Reference station
          <select aria-label="Reference station" value={chosen ?? ''} onChange={(e) => pickReference(e.target.value)}>
            {!chosen && <option value="">Choose a reference…</option>}
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
          {station && !one.data && !one.error && <Loading what={`${station}'s time series`} />}
          {one.data && one.data.configured && !one.data.available && <div className="banner warn" role="status">{one.data.message}</div>}
          {one.data && one.data.configured && one.data.available && <Station data={one.data} />}
        </section>
      )}
      <p className="faint" style={{ fontSize: 13 }}>Open team decision: whether a flagged outlier is excluded from the velocity fit, or only recorded. The mode above says which produced these numbers.</p>
    </>
  )
}

function Station({ data }: { data: Extract<TsStation, { available: true }> }) {
  const v = data.velocity
  const flagged = data.series.outlier.filter(Boolean).length
  return (
    <div className="stack">
      <section aria-labelledby="ts-vel" className="panel pad stack">
        <h2 id="ts-vel">{data.station} · velocity (final segment)</h2>
        <table className="t">
          <thead><tr><th scope="col"></th><th scope="col">East</th><th scope="col">North</th><th scope="col">Up</th></tr></thead>
          <tbody>
            <tr><th scope="row">mm/yr ± 1σ</th>{(['e', 'n', 'u'] as const).map((c) => <td key={c} className="mono num" style={v.short_span ? { textDecoration: 'line-through' } : undefined}>{rate(v.velocity_mm_yr, v.sigma_mm_yr, c)}</td>)}</tr>
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
