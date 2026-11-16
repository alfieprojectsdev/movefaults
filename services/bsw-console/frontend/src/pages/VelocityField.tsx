import { useState } from 'react'
import type { TsField, TsFieldStation } from '../types'
import { azimuth, compass, ELLIPSE_95, sortStations, speed, stepScale, withheld, type SortKey } from '../vectors'

type Field = Extract<TsField, { available: true }>
export type Layer = 'horizontal' | 'vertical'

/** The switches above the map: the field on or off, which component, how long an arrow is. */
export function FieldControls({ on, onToggle, layer, onLayer, pxPerMm, onScale }: {
  on: boolean; onToggle: () => void; layer: Layer; onLayer: (l: Layer) => void
  pxPerMm: number; onScale: (px: number) => void
}) {
  return (
    <div className="row" style={{ fontSize: 13, flexWrap: 'wrap', gap: '8px 20px' }}>
      <div className="seg" role="group" aria-label="Velocity field">
        <button type="button" aria-pressed={on} onClick={onToggle}>Velocity field</button>
      </div>
      {on && (
        <>
          <div className="seg" role="group" aria-label="Component">
            <button type="button" aria-pressed={layer === 'horizontal'} onClick={() => onLayer('horizontal')}>Horizontal</button>
            <button type="button" aria-pressed={layer === 'vertical'} onClick={() => onLayer('vertical')}>Vertical</button>
          </div>
          {layer === 'horizontal' && (
            <div className="seg" role="group" aria-label="Arrow scale">
              <span className="muted">Arrow scale</span>
              <button type="button" aria-label="Shorter arrows" onClick={() => onScale(stepScale(pxPerMm, -1))}>−</button>
              <button type="button" aria-label="Longer arrows" onClick={() => onScale(stepScale(pxPerMm, 1))}>+</button>
              <span className="muted">{pxPerMm} px per mm/yr</span>
            </div>
          )}
        </>
      )}
    </div>
  )
}

const mm = (v: number) => v.toFixed(2)
const COLUMNS: { key: SortKey; label: string }[] = [
  { key: 'station', label: 'Station' }, { key: 'e', label: 'East mm/yr' }, { key: 'n', label: 'North mm/yr' },
  { key: 'u', label: 'Up mm/yr' }, { key: 'speed', label: 'Horizontal' }, { key: 'span', label: 'Span yr' },
]

function notes(s: TsFieldStation, reference: string): string[] {
  const out: string[] = []
  const held = withheld(s)
  if (held) out.push(`not drawn: ${held}`)
  if (s.far_from_reference) out.push(`${s.reference_distance_deg.toFixed(1)}° from ${reference}: East, North and Up are tilted`)
  if (s.n_offsets > 0) out.push(`${s.n_offsets} offset${s.n_offsets === 1 ? '' : 's'} in the catalogue`)
  return out
}

/**
 * Under the map: what frame the arrows are in, what was left out and why, the table
 * and the files. Every number is field_status's; the page adds none.
 */
export default function VelocityField({ field, campaign, query, station, warnDeg, onStation }: {
  field: Field; campaign: string; query: string; station: string; warnDeg: number; onStation: (code: string) => void
}) {
  const [sort, setSort] = useState<{ key: SortKey; descending: boolean }>({ key: 'station', descending: false })
  const rows = sortStations(field.stations, sort.key, sort.descending)
  const held = field.stations.filter((s) => withheld(s))
  const far = field.stations.filter((s) => s.far_from_reference)
  const file = (format: string) =>
    `/api/campaigns/${campaign}/velocity-field/export?format=${format}${query ? `&${query.slice(1)}` : ''}`
  const press = (key: SortKey) => setSort((s) => ({ key, descending: s.key === key ? !s.descending : key !== 'station' }))
  return (
    <section aria-labelledby="vf" className="stack">
      <h2 id="vf">Velocity field · relative to {field.reference}</h2>
      <p style={{ fontSize: 13, maxWidth: '90ch' }}>
        Each station's velocity <strong>relative to {field.reference}</strong>, from its final segment. These are not ITRF velocities: choose another reference and every arrow changes. Epochs {field.t_first.toFixed(4)} to {field.t_last.toFixed(4)}. Outlier mode: <strong>{field.outlier_rule.mode}</strong>. Uncertainties are the <strong>{field.sigma}</strong>, which understates the real uncertainty of a velocity; ellipses are 95% ({ELLIPSE_95}σ).
      </p>
      <p style={{ fontSize: 13 }}>
        {field.stations.length - held.length} of {field.stations.length} stations drawn.
        {held.length > 0 && <> {held.length} not drawn as a velocity (hollow on the map, struck through below): {held.map((s) => s.station).join(', ')}.</>}
        {far.length > 0 && <> {far.length} over {warnDeg}° from the reference, where East, North and Up are tilted: {far.map((s) => s.station).join(', ')}.</>}
      </p>
      {field.left_out.length > 0 && (
        <div className="banner warn" role="status">
          <strong>Left out of the field.</strong>
          <span>{field.left_out.map((l) => `${l.station}: ${l.reason}`).join('; ')}</span>
        </div>
      )}
      {field.warnings.length > 0 && <ul className="muted" style={{ fontSize: 13 }}>{field.warnings.map((w) => <li key={w}>{w}</li>)}</ul>}
      <p style={{ fontSize: 13 }}>
        Files, with the frame in their header:{' '}
        <a href={file('psvelo')} download>GMT psvelo (horizontal)</a> · <a href={file('vertical')} download>GMT vertical rates</a> · <a href={file('csv')} download>CSV table</a>
        {field.offsets_catalog && <span className="muted"> · offsets catalogue sha256 <span className="mono" style={{ fontSize: 12 }}>{field.offsets_catalog.sha256}</span></span>}
      </p>
      <div className="panel scroll">
        <table className="t">
          <caption style={{ textAlign: 'left' }} className="muted">Velocity ± formal 1σ. Press a heading to sort; press a station to open its series.</caption>
          <thead>
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} scope="col" className={c.key === 'station' ? undefined : 'num'}
                  aria-sort={sort.key === c.key ? (sort.descending ? 'descending' : 'ascending') : undefined}>
                  <button type="button" className="linkish" onClick={() => press(c.key)}>{c.label}{sort.key === c.key ? (sort.descending ? ' ▼' : ' ▲') : ''}</button>
                </th>
              ))}
              <th scope="col" className="num">Epochs</th><th scope="col">Notes</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((s) => {
              const v = s.velocity.velocity_mm_yr
              const sg = s.velocity.sigma_mm_yr
              const strike = withheld(s) ? { textDecoration: 'line-through' } : undefined
              return (
                <tr key={s.station} aria-current={s.station === station ? 'true' : undefined}>
                  <th scope="row"><button type="button" className="linkish mono" onClick={() => onStation(s.station)}>{s.station}</button></th>
                  {(['e', 'n', 'u'] as const).map((c) => <td key={c} className="mono num nowrap" style={strike}>{mm(v[c])} ± {mm(sg[c])}</td>)}
                  <td className="mono num nowrap" style={strike}>{speed(s).toFixed(1)} {compass(azimuth(v.e, v.n))}</td>
                  <td className="mono num">{s.velocity.span_yr.toFixed(2)}</td>
                  <td className="num">{s.n_epochs}</td>
                  <td style={{ fontSize: 12 }}>{notes(s, field.reference).join('; ')}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </section>
  )
}
