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
;(globalThis as any).__leaflet = { markers: [], circles: [], fits: [] }
vi.mock('leaflet', () => {
  const state = () => (globalThis as any).__leaflet
  const layer = () => ({
    addTo() { return this }, bringToBack() { return this },
  })
  const L = {
    map: () => ({
      setView() { return this },
      fitBounds(b: unknown) { state().fits.push(b); return this },
      remove() {},
    }),
    layerGroup: () => ({
      addTo() { return this },
      clearLayers() { state().markers.length = 0; state().circles.length = 0 },
    }),
    latLngBounds: (points: unknown) => points,
    geoJSON: layer,
    circle: (at: unknown, opts: unknown) => { state().circles.push({ at, opts }); return layer() },
    circleMarker: (at: unknown, opts: unknown) => {
      const m: any = { at, opts, ...layer(), label: '', permanent: false, handlers: {} as Record<string, () => void> }
      m.bindTooltip = (label: string, o: { permanent: boolean }) => { m.label = label; m.permanent = o.permanent; return m }
      m.on = (name: string, fn: () => void) => { m.handlers[name] = fn; return m }
      state().markers.push(m)
      return m
    },
  }
  return { default: L }
})
vi.mock('leaflet/dist/leaflet.css', () => ({}))
