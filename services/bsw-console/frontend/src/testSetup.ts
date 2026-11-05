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
    valToPos(v: number) { return v }
    posToVal(v: number) { return v }
    destroy() { this.destroyed = true }
  }
  return { default: FakeUPlot }
})
vi.mock('uplot/dist/uPlot.min.css', () => ({}))
