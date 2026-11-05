import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { COMPONENTS, panelData, sessionDate, zoomRange } from '../tsPlot'
import type { TsSegment, TsSeries } from '../types'

type Offset = { t: number; type: string; label: string; within_span: boolean }

/**
 * East, North and Up stacked on one time axis, the layout tsview and the
 * EarthScope / NGL station plots use. Zoom like a waveform editor: the mouse
 * wheel zooms time around the cursor, dragging selects a span, double-click
 * shows everything. The three panels share their cursor and their time range.
 *
 * Marks: epochs in the fit (dots), epochs the outlier rule flagged (larger,
 * orange), epochs not in the fit for any other reason (hollow), the package's
 * fitted line per segment, and the catalogue's offsets as dashed verticals.
 */
export default function TsPlot({ series, segments, offsets, station }: {
  series: TsSeries; segments: TsSegment[]; offsets: Offset[]; station: string
}) {
  const host = useRef<HTMLDivElement>(null)
  const [hover, setHover] = useState<string>('')

  useEffect(() => {
    const el = host.current
    if (!el || series.t.length === 0) return
    const css = getComputedStyle(document.documentElement)
    const color = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback
    const ink = color('--ink2', '#3A433E')
    const grid = color('--line2', '#E6E9E4')
    const accent = color('--accent', '#1F5E8C')
    const flag = color('--failed', '#E8833A')
    const eq = color('--eq', '#C2570C')
    const faint = color('--faint', '#7A827C')

    const lo = series.t[0]
    const hi = series.t[series.t.length - 1]
    const pad = Math.max((hi - lo) * 0.01, 1 / 365.25)
    const charts: uPlot[] = []
    let syncing = false
    const syncKey = `ts-${station}-${Math.random().toString(36).slice(2)}`
    const width = () => Math.max(el.clientWidth || 800, 320)

    const offsetLines: uPlot.Plugin = {
      hooks: {
        draw: (u) => {
          const { ctx, bbox } = u
          ctx.save()
          ctx.strokeStyle = eq
          ctx.lineWidth = 1.5 * devicePixelRatio
          ctx.setLineDash([6 * devicePixelRatio, 4 * devicePixelRatio])
          for (const o of offsets) {
            const x = Math.round(u.valToPos(o.t, 'x', true))
            if (x < bbox.left || x > bbox.left + bbox.width) continue
            ctx.beginPath()
            ctx.moveTo(x, bbox.top)
            ctx.lineTo(x, bbox.top + bbox.height)
            ctx.stroke()
          }
          ctx.restore()
        },
      },
    }

    const wheelZoom: uPlot.Plugin = {
      hooks: {
        ready: (u) => {
          u.over.addEventListener('wheel', (e: WheelEvent) => {
            e.preventDefault()
            const { min, max } = u.scales.x
            if (min == null || max == null) return
            const center = u.posToVal(e.offsetX, 'x')
            const [nmin, nmax] = zoomRange(min, max, center, e.deltaY < 0 ? 0.8 : 1.25, lo - pad, hi + pad)
            u.setScale('x', { min: nmin, max: nmax })
          }, { passive: false })
        },
      },
    }

    COMPONENTS.forEach(({ key, label }, k) => {
      const d = panelData(series, segments, key)
      const div = document.createElement('div')
      el.appendChild(div)
      const last = k === COMPONENTS.length - 1
      const opts: uPlot.Options = {
        width: width(),
        height: 190,
        legend: { show: false },
        cursor: {
          sync: { key: syncKey, setSeries: false },
          drag: { x: true, y: false, setScale: true },
          points: { show: false },
        },
        scales: { x: { time: false, min: lo - pad, max: hi + pad } },
        axes: [
          { stroke: ink, grid: { stroke: grid }, ticks: { stroke: grid }, show: true, size: last ? 40 : 24,
            values: last ? (_u, vals) => vals.map((v) => v.toFixed(2)) : (_u, vals) => vals.map(() => '') },
          { stroke: ink, grid: { stroke: grid }, ticks: { stroke: grid }, label, labelSize: 18, size: 60 },
        ],
        series: [
          {},
          { label: 'in fit', stroke: accent, width: 0, points: { show: true, size: 3, fill: accent, stroke: accent } },
          { label: 'flagged', stroke: flag, width: 0, points: { show: true, size: 6, fill: flag, stroke: flag } },
          { label: 'not in fit', stroke: faint, width: 0, points: { show: true, size: 5, fill: 'transparent', stroke: faint } },
          { label: 'fit', stroke: ink, width: 1.5, points: { show: false }, spanGaps: false },
        ],
        hooks: {
          setScale: [
            (u, scaleKey) => {
              if (scaleKey !== 'x' || syncing) return
              syncing = true
              const { min, max } = u.scales.x
              for (const other of charts) if (other !== u) other.setScale('x', { min: min!, max: max! })
              syncing = false
            },
          ],
          setCursor: [
            (u) => {
              const i = u.cursor.idx
              if (i == null || k !== 0) return
              const parts = COMPONENTS.map(({ key: c }) => `${c.toUpperCase()} ${series[`${c}_mm`][i].toFixed(1)}`)
              const tag = series.outlier[i] ? ' · flagged' : series.in_fit[i] ? '' : ' · not in fit'
              setHover(`${sessionDate(series.t[i])} (${series.t[i].toFixed(4)}) · ${parts.join(' · ')} mm${tag}`)
            },
          ],
        },
        plugins: [offsetLines, wheelZoom],
      }
      charts.push(new uPlot(opts, [d.t, d.kept, d.flagged, d.left, d.fit] as uPlot.AlignedData, div))
    })

    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
      for (const c of charts) c.setSize({ width: width(), height: 190 })
    })
    ro?.observe(el)
    return () => {
      ro?.disconnect()
      for (const c of charts) c.destroy()
      el.replaceChildren()
    }
  }, [series, segments, offsets, station])

  return (
    <section aria-labelledby="ts-plot" className="panel pad stack">
      <h2 id="ts-plot">{station} · east, north, up</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        Mouse wheel zooms time around the cursor; drag to select a span; double-click shows everything. Dots are in the fit, orange marks were flagged by the outlier rule, hollow marks are not in the fit, the line is the fitted velocity per segment, and dashed lines are the catalogue's offsets.
      </p>
      <div ref={host} data-testid="ts-plot" />
      <p className="mono" style={{ fontSize: 12, minHeight: '1.4em' }} aria-live="polite">{hover}</p>
    </section>
  )
}
