// jsdom has no canvas and no matchMedia, both of which uPlot needs at import.
// The chart library is replaced by a stand-in that records what it was given,
// so tests check the data and options the page hands it, not the pixels.
import { vi } from 'vitest'

export type FakeChart = { opts: any; data: any[]; destroyed: boolean; scales: Record<string, { min?: number; max?: number }> }
;(globalThis as any).__uplots = [] as FakeChart[]

vi.mock('uplot', () => {
  class FakeUPlot {
    opts: any
    data: any[]
    destroyed = false
    scales: Record<string, { min?: number; max?: number }>
    over = document.createElement('div')
    cursor = { idx: null as number | null }
    constructor(opts: any, data: any[], target: HTMLElement) {
      this.opts = opts
      this.data = data
      this.scales = { x: { min: opts.scales?.x?.min, max: opts.scales?.x?.max } }
      target.appendChild(document.createElement('canvas'))
      ;(globalThis as any).__uplots.push(this)
      for (const p of opts.plugins ?? []) p.hooks?.ready?.(this)
    }
    setScale(key: string, r: { min: number; max: number }) {
      this.scales[key] = r
      for (const h of this.opts.hooks?.setScale ?? []) h(this, key)
    }
    setSize() {}
    redraw() {}
    valToPos(v: number) { return v }
    posToVal(v: number) { return v }
    destroy() { this.destroyed = true }
  }
  return { default: FakeUPlot }
})
vi.mock('uplot/dist/uPlot.min.css', () => ({}))

// The map library is replaced the same way: jsdom has no layout for it to measure.
;(globalThis as any).__leaflet = { markers: [], circles: [], lines: [], polygons: [], fits: [], handlers: {}, resized: 0 }
vi.mock('leaflet', () => {
  const state = () => (globalThis as any).__leaflet
  const kinds = ['markers', 'circles', 'lines', 'polygons'] as const
  // A layer remembers the group it was added to, so clearing one group leaves the others' layers.
  const layer = (extra: object = {}) => ({
    group: null as unknown,
    addTo(target: unknown) { this.group = target; return this }, bringToBack() { return this },
    ...extra,
  })
  const L = {
    // A flat, fixed projection: 100 px per degree, north up.
    map: () => ({
      groups: [] as { clearLayers(): void }[],
      setView() { return this },
      fitBounds(b: unknown) { state().fits.push(b); return this },
      on(name: string, fn: () => void) { state().handlers[name] = fn; return this },
      invalidateSize() { state().resized += 1; return this },
      latLngToContainerPoint: ([lat, lon]: [number, number]) => ({ x: lon * 100, y: -lat * 100 }),
      containerPointToLatLng: ([x, y]: [number, number]) => ({ lat: -y / 100, lng: x / 100 }),
      // Removing a map takes its layers with it.
      remove() { for (const g of this.groups) g.clearLayers() },
    }),
    layerGroup: () => {
      const group = {
        addTo(m: { groups: unknown[] }) { m.groups.push(group); return group },
        clearLayers() {
          for (const k of kinds) state()[k] = state()[k].filter((l: { group: unknown }) => l.group !== group)
        },
      }
      return group
    },
    latLngBounds: (points: unknown) => points,
    geoJSON: () => layer(),
    circle: (at: unknown, opts: unknown) => { const c = layer({ at, opts }); state().circles.push(c); return c },
    polyline: (points: unknown, opts: unknown) => { const l = layer({ points, opts }); state().lines.push(l); return l },
    polygon: (points: unknown, opts: unknown) => { const l = layer({ points, opts }); state().polygons.push(l); return l },
    circleMarker: (at: unknown, opts: unknown) => {
      const m: any = layer({ at, opts, label: '', permanent: false, handlers: {} as Record<string, () => void> })
      m.bindTooltip = (label: string, o: { permanent: boolean }) => { m.label = label; m.permanent = o.permanent; return m }
      m.on = (name: string, fn: () => void) => { m.handlers[name] = fn; return m }
      state().markers.push(m)
      return m
    },
  }
  return { default: L }
})
vi.mock('leaflet/dist/leaflet.css', () => ({}))
