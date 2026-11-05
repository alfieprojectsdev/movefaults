import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { coreStations, METRES_PER_DEGREE, type LatLon } from '../stationMap'

type Mode = 'station' | 'reference'

/**
 * Where the stations are, so choosing one does not need the network by memory. It
 * sets the same two choices as the dropdowns beside it, which stay for the keyboard
 * and for anyone who knows the code. The dashed ring is the distance past which the
 * page warns that the reference tilts East, North and Up.
 *
 * There is no tile server: the land is a file in the bundle (coastline.json), so the
 * map works on the office network alone and tells nobody where the stations are.
 * Plain wheel scrolling is left to the page, as on the plot.
 */
export default function StationMap({ positions, distances, reference, station, warnDeg, onReference, onStation }: {
  positions: Record<string, LatLon>; distances: Record<string, number>; reference: string; station: string
  warnDeg: number; onReference: (code: string) => void; onStation: (code: string) => void
}) {
  const host = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const marks = useRef<L.LayerGroup | null>(null)
  const [mode, setMode] = useState<Mode>(reference ? 'station' : 'reference')
  // Handlers change every render; the markers read the current ones through here.
  const click = useRef<(code: string) => void>(() => {})
  click.current = (code) => {
    if (mode === 'reference') { onReference(code); setMode('station') }
    else if (code !== reference) onStation(code)
  }

  const bounds = (codes: string[]) => L.latLngBounds(codes.map((c) => [positions[c].lat, positions[c].lon] as [number, number]))
  const fit = (codes: string[]) => { if (codes.length) map.current?.fitBounds(bounds(codes), { padding: [24, 24], maxZoom: 9 }) }

  useEffect(() => {
    if (!host.current) return
    const m = L.map(host.current, { attributionControl: false, scrollWheelZoom: false, zoomSnap: 0.5 })
    map.current = m
    marks.current = L.layerGroup().addTo(m)
    m.setView([12, 122], 5)
    let gone = false
    const ink = getComputedStyle(document.documentElement).getPropertyValue('--faint').trim() || '#7A827C'
    void import('../coastline.json').then((land) => {
      if (!gone) L.geoJSON(land.default as never, {
        // Leaflet's line simplifying wiped out whole coasts at this zoom; the file is small.
        style: { color: ink, weight: 1, fill: false, smoothFactor: 0 } as L.PolylineOptions, interactive: false,
      }).addTo(m).bringToBack()
    })
    return () => { gone = true; m.remove(); map.current = null; marks.current = null }
  }, [])

  // Open on the network once it is known; later choices leave the view alone.
  const opened = useRef(false)
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
    for (const [code, p] of Object.entries(positions)) {
      const isRef = code === reference
      const isOn = code === station
      const d = distances[code]
      const beyond = d !== undefined && d > warnDeg
      const mark = L.circleMarker([p.lat, p.lon], {
        radius: isRef || isOn ? 8 : 5,
        color: isRef ? ink : isOn ? accent : '#fff',
        weight: isRef || isOn ? 3 : 1,
        fillColor: isRef ? ink : beyond ? far : accent,
        fillOpacity: 0.95,
      })
      const label = isRef ? `${code}, reference` : d === undefined ? code : `${code}, ${d.toFixed(1)}° from ${reference}`
      mark.bindTooltip(label, { permanent: isRef || isOn, direction: 'top', offset: [0, -6] })
      mark.on('click', () => click.current(code))
      mark.addTo(group)
    }
  }, [positions, distances, reference, station, warnDeg])

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
      <div ref={host} data-testid="station-map" style={{ height: 340, background: 'var(--panel)', borderRadius: 4 }} />
      <p className="muted" style={{ fontSize: 12, margin: 0 }}>
        Orange stations are over {warnDeg}° from the reference, outside the dashed ring: East, North and Up are the reference's axes, so that far away they are tilted.
      </p>
    </section>
  )
}
