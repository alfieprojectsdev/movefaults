import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { coreStations, METRES_PER_DEGREE, type LatLon } from '../stationMap'
import { arrowHead, azimuth, compass, ELLIPSE_95, ellipse, scaleBar, speed, tip, verticalClear, verticalRadius, withheld, type XY } from '../vectors'
import type { TsFieldStation } from '../types'

type Mode = 'station' | 'reference'
/** The velocity field to draw over the stations: which component, and how long a mm/yr is. */
export type FieldLayer = { stations: TsFieldStation[]; layer: 'horizontal' | 'vertical'; pxPerMm: number }

/**
 * Where the stations are, so choosing one does not need the network by memory. It
 * sets the same two choices as the dropdowns beside it, which stay for the keyboard
 * and for anyone who knows the code. The dashed ring is the distance past which the
 * page warns that the reference tilts East, North and Up.
 *
 * There is no tile server: the land is a file in the bundle (coastline.json), so the
 * map works on the office network alone and tells nobody where the stations are.
 * Plain wheel scrolling is left to the page, as on the plot.
 *
 * With `field`, each station's velocity is drawn over its marker: an arrow with its
 * 95% ellipse, or its vertical rate as a circle. An arrow's length is in screen
 * pixels per mm/yr and does not grow with the zoom, so it is redrawn after each zoom.
 * A station whose rate is not a velocity (withheld) gets a hollow marker and no arrow.
 */
export default function StationMap({ positions, distances, reference, station, warnDeg, onReference, onStation, field }: {
  positions: Record<string, LatLon>; distances: Record<string, number>; reference: string; station: string
  warnDeg: number; onReference: (code: string) => void; onStation: (code: string) => void; field?: FieldLayer | null
}) {
  const host = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const marks = useRef<L.LayerGroup | null>(null)
  const vectors = useRef<L.LayerGroup | null>(null)
  const [mode, setMode] = useState<Mode>(reference ? 'station' : 'reference')
  // Handlers change every render; the markers read the current ones through here.
  const click = useRef<(code: string) => void>(() => {})
  click.current = (code) => {
    if (mode === 'reference') { onReference(code); setMode('station') }
    else onStation(code)
  }
  // However the reference was chosen, the dropdown included, the next click is for a
  // station: gps3 has no default, so this is how the page opens.
  useEffect(() => setMode(reference ? 'station' : 'reference'), [reference])
  const opened = useRef(false)
  const [noLand, setNoLand] = useState(false)

  const bounds = (codes: string[]) => L.latLngBounds(codes.map((c) => [positions[c].lat, positions[c].lon] as [number, number]))
  const fit = (codes: string[]) => { if (codes.length) map.current?.fitBounds(bounds(codes), { padding: [24, 24], maxZoom: 9 }) }

  useEffect(() => {
    if (!host.current) return
    const m = L.map(host.current, { attributionControl: false, scrollWheelZoom: false, zoomSnap: 0.5 })
    map.current = m
    vectors.current = L.layerGroup().addTo(m)
    marks.current = L.layerGroup().addTo(m)
    m.on('zoomend', () => draw.current())
    m.setView([12, 122], 5)
    let gone = false
    const ink = getComputedStyle(document.documentElement).getPropertyValue('--faint').trim() || '#7A827C'
    void import('../coastline.json').then((land) => {
      if (!gone) L.geoJSON(land.default as never, {
        // Leaflet's line simplifying wiped out whole coasts at this zoom; the file is small.
        style: { color: ink, weight: 1, fill: false, smoothFactor: 0 } as L.PolylineOptions, interactive: false,
      }).addTo(m).bringToBack()
    }).catch(() => { if (!gone) setNoLand(true) })
    // opened too: StrictMode's second mount is a new map that has not been fitted.
    return () => { gone = true; m.remove(); map.current = null; marks.current = null; vectors.current = null; opened.current = false }
  }, [])

  // Open on the network once it is known; later choices leave the view alone.
  useEffect(() => {
    if (opened.current || Object.keys(positions).length === 0) return
    opened.current = true
    fit(coreStations(positions))
  }, [positions])

  useEffect(() => {
    const group = marks.current
    if (!group) return
    group.clearLayers()
    const css = getComputedStyle(document.documentElement)
    const token = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback
    const accent = token('--accent', '#1F5E8C')
    const ink = token('--ink', '#1A1F1C')
    const far = token('--failed', '#E8833A')
    const here = positions[reference]
    if (here) {
      L.circle([here.lat, here.lon], {
        radius: warnDeg * METRES_PER_DEGREE, color: far, weight: 1.5, dashArray: '6 6', fill: false, interactive: false,
      }).addTo(group)
    }
    const faint = token('--faint', '#7A827C')
    const inField = new Map((field?.stations ?? []).map((s) => [s.station, s]))
    for (const [code, p] of Object.entries(positions)) {
      const isRef = code === reference
      const isOn = code === station
      const d = distances[code]
      const beyond = d !== undefined && d > warnDeg
      const entry = inField.get(code)
      const held = entry ? withheld(entry) : null
      const mark = L.circleMarker([p.lat, p.lon], {
        radius: isRef || isOn ? 8 : 5,
        color: isRef ? ink : isOn ? accent : held ? faint : '#fff',
        weight: isRef || isOn ? 3 : held ? 1.5 : 1,
        fillColor: isRef ? ink : held ? faint : beyond ? far : accent,
        fillOpacity: held && !isOn ? 0.1 : 0.95,
      })
      let label = isRef ? `${code}, reference` : d === undefined ? code : `${code}, ${d.toFixed(1)}° from ${reference}`
      if (entry && held) label += ` · no velocity: ${held}`
      else if (entry) {
        const v = entry.velocity.velocity_mm_yr
        const sg = entry.velocity.sigma_mm_yr
        label += field?.layer === 'vertical'
          ? ` · up ${v.u.toFixed(1)} ± ${sg.u.toFixed(1)} mm/yr`
          : ` · ${speed(entry).toFixed(1)} mm/yr toward ${compass(azimuth(v.e, v.n))} (E ${v.e.toFixed(1)} ± ${sg.e.toFixed(1)}, N ${v.n.toFixed(1)} ± ${sg.n.toFixed(1)})`
      }
      mark.bindTooltip(label, { permanent: isRef || isOn, direction: 'top', offset: [0, -6] })
      mark.on('click', () => click.current(code))
      mark.addTo(group)
    }
  }, [positions, distances, reference, station, warnDeg, field])

  // The velocities themselves. Lengths are pixels at the current zoom: each shape is
  // laid out around the station's screen position and turned back into coordinates.
  const draw = useRef(() => {})
  draw.current = () => {
    const group = vectors.current
    const m = map.current
    if (!group || !m) return
    group.clearLayers()
    if (!field) return
    const css = getComputedStyle(document.documentElement)
    const token = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback
    const ink = token('--ink', '#1B2420')
    const soft = token('--muted', '#4F5953')
    for (const s of field.stations) {
      if (withheld(s) || s.station === reference) continue
      const at: [number, number] = [s.lat, s.lon]
      const v = s.velocity.velocity_mm_yr
      const sg = s.velocity.sigma_mm_yr
      if (field.layer === 'vertical') {
        const colour = v.u >= 0 ? token('--up', '#B8382A') : token('--down', '#2563A8')
        L.circleMarker(at, {
          radius: verticalRadius(v.u), color: colour, weight: 2, fillColor: colour,
          fillOpacity: verticalClear(v.u, sg.u) ? 0.55 : 0, interactive: false,
        }).addTo(group)
        continue
      }
      const origin = m.latLngToContainerPoint(at)
      const place = (p: XY): [number, number] => {
        const ll = m.containerPointToLatLng([origin.x + p.x, origin.y + p.y])
        return [ll.lat, ll.lng]
      }
      const end = tip(v.e, v.n, field.pxPerMm)
      L.polygon(ellipse(end, sg.e, sg.n, field.pxPerMm).map(place), { color: soft, weight: 1, fill: false, interactive: false }).addTo(group)
      L.polyline([at, place(end)], { color: ink, weight: 2, interactive: false }).addTo(group)
      const head = arrowHead({ x: 0, y: 0 }, end)
      if (head.length) L.polygon(head.map(place), { color: ink, weight: 1, fillColor: ink, fillOpacity: 1, interactive: false }).addTo(group)
    }
  }
  useEffect(() => draw.current(), [field, reference, positions])
  // The map is taller with the field on. Leaflet only draws the size it last
  // measured, so tell it, or the new strip at the bottom stays empty.
  const tall = Boolean(field)
  useEffect(() => { map.current?.invalidateSize() }, [tall])

  const bar = field && field.layer === 'horizontal' ? scaleBar(field.pxPerMm) : null

  return (
    <section aria-label="Map of the stations" className="panel pad stack" style={{ gap: 8 }}>
      <div className="row" style={{ justifyContent: 'space-between', fontSize: 13 }}>
        <div className="seg" role="group" aria-label="A click on the map sets">
          <span className="muted">A click sets the</span>
          <button type="button" aria-pressed={mode === 'station'} onClick={() => setMode('station')}>Station</button>
          <button type="button" aria-pressed={mode === 'reference'} onClick={() => setMode('reference')}>Reference</button>
        </div>
        <div className="seg" role="group" aria-label="Show on the map">
          <button type="button" onClick={() => fit(coreStations(positions))}>The network</button>
          <button type="button" onClick={() => fit(Object.keys(positions))}>All stations</button>
        </div>
      </div>
      <div style={{ position: 'relative' }}>
        <div ref={host} data-testid="station-map" style={{ height: field ? 460 : 340, background: 'var(--panel)', borderRadius: 4 }} />
        {field && (
          <div data-testid="field-legend" style={{ position: 'absolute', left: 8, bottom: 8, zIndex: 1000, pointerEvents: 'none', padding: '6px 8px', borderRadius: 4, fontSize: 12, background: 'var(--panel)', border: '1px solid var(--line)', color: 'var(--ink)' }}>
            {bar ? (
              <>
                <svg width={bar.px + 2} height={10} aria-hidden="true" style={{ display: 'block' }}>
                  <line x1={0} y1={5} x2={bar.px - 6} y2={5} stroke="currentColor" strokeWidth={2} />
                  <polygon points={`${bar.px},5 ${bar.px - 8},1.5 ${bar.px - 8},8.5`} fill="currentColor" />
                </svg>
                {bar.mm} mm/yr · ellipses 95% ({ELLIPSE_95}σ)
              </>
            ) : (
              <>
                <span style={{ color: 'var(--up)' }}>●</span> up <span style={{ color: 'var(--down)' }}>●</span> down · hollow: under 2σ
              </>
            )}
          </div>
        )}
      </div>
      <p className="muted" style={{ fontSize: 12, margin: 0 }}>
        Orange stations are over {warnDeg}° from the reference, outside the dashed ring: East, North and Up are the reference's axes, so that far away they are tilted.
        {noLand && <strong> The coastline did not load: reload the page.</strong>}
      </p>
    </section>
  )
}
