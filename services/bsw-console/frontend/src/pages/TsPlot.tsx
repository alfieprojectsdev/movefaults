import { useEffect, useRef, useState } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'
import { COMPONENTS, decisionMarks, lineAt, panRange, panelData, sessionDate, axisDigits, yearRange, yearsIn, zoomRange } from '../tsPlot'
import type { TsDecidedFit, TsDecision, TsSegment, TsSeries } from '../types'

type Offset = { t: number; type: string; label: string; within_span: boolean }

/**
 * East, North and Up stacked on one time axis, the layout tsview and the
 * EarthScope / NGL station plots use. Zoom like a waveform editor: Ctrl (or
 * Cmd) with the mouse wheel, or a trackpad pinch, zooms time around the cursor;
 * Shift with the wheel pans; dragging selects a span; double-click shows
 * everything. A plain wheel still scrolls the page: the three panels fill most
 * of the screen, and taking the plain wheel would trap the reader in them.
 * The panels share their cursor and their time range. The year buttons jump to
 * one calendar year; the velocities below still come from the whole series. A
 * rebuild (a decision recorded, a colour scheme change) keeps the range in view.
 *
 * Marks: epochs in the fit (dots), epochs the outlier rule flagged (larger,
 * orange), epochs not in the fit for any other reason (hollow), the package's
 * fitted line per segment, and the catalogue's offsets as dashed verticals.
 * Rings mark epochs a person decided on (confirmed outlier, or a flag overridden
 * as real), and a dashed line is the fit without the confirmed outliers, which
 * is not published. A click (not a drag) on a panel picks the nearest epoch.
 */
export default function TsPlot({ series, segments, offsets, station, decisions, decidedFit, onPick }: {
  series: TsSeries; segments: TsSegment[]; offsets: Offset[]; station: string
  decisions?: TsDecision[]; decidedFit?: TsDecidedFit | null; onPick?: (index: number) => void
}) {
  const host = useRef<HTMLDivElement>(null)
  // Kept in a ref so a new callback does not rebuild the charts.
  const pick = useRef(onPick)
  pick.current = onPick
  const [hover, setHover] = useState<string>('')
  const chartsRef = useRef<uPlot[]>([])
  const view = useRef<[number, number] | null>(null)
  // Canvas colours are read from the CSS tokens when the charts are built, so a
  // switch between light and dark rebuilds them.
  const [scheme, setScheme] = useState(0)
  useEffect(() => {
    const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null
    const bump = () => setScheme((n) => n + 1)
    mq?.addEventListener?.('change', bump)
    return () => mq?.removeEventListener?.('change', bump)
  }, [])

  useEffect(() => {
    const el = host.current
    if (!el || series.t.length === 0) return
    const css = getComputedStyle(document.documentElement)
    const color = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback
    const ink = color('--ink2', '#3A433E')
    const grid = color('--line2', '#E6E9E4')
    const accent = color('--accent', '#1F5E8C')
    const flag = color('--failed', '#E8833A')
    const decided = color('--warn-strong', '#7A3300')
    const eq = color('--eq', '#C2570C')
    const faint = color('--faint', '#7A827C')

    const lo = series.t[0]
    const hi = series.t[series.t.length - 1]
    const pad = Math.max((hi - lo) * 0.01, 1 / 365.25)
    const charts: uPlot[] = []
    const restore = view.current
    let syncing = false
    let built = false // uPlot sets its scales while it is built: that is not the reader's range
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
            // Browsers report a trackpad pinch as a wheel event with ctrlKey set.
            const zoom = e.ctrlKey || e.metaKey
            const pan = e.shiftKey || Math.abs(e.deltaX) > Math.abs(e.deltaY)
            if (!zoom && !pan) return // a plain wheel scrolls the page
            e.preventDefault()
            const { min, max } = u.scales.x
            if (min == null || max == null) return
            if (zoom) {
              const center = u.posToVal(e.offsetX, 'x')
              const [nmin, nmax] = zoomRange(min, max, center, e.deltaY < 0 ? 0.8 : 1.25, lo - pad, hi + pad)
              u.setScale('x', { min: nmin, max: nmax })
            } else {
              const d = e.shiftKey ? e.deltaY : e.deltaX
              const [nmin, nmax] = panRange(min, max, Math.sign(d) * 0.1, lo - pad, hi + pad)
              u.setScale('x', { min: nmin, max: nmax })
            }
          }, { passive: false })
        },
      },
    }

    // A click picks the nearest epoch; a drag (zoom select) does not.
    const clickPick: uPlot.Plugin = {
      hooks: {
        ready: (u) => {
          let down: [number, number] | null = null
          u.over.addEventListener('mousedown', (e: MouseEvent) => { down = [e.clientX, e.clientY] })
          u.over.addEventListener('click', (e: MouseEvent) => {
            const moved = down ? Math.hypot(e.clientX - down[0], e.clientY - down[1]) : 0
            down = null
            const i = u.cursor.idx
            if (moved < 4 && i != null && i >= 0 && i < series.t.length) pick.current?.(i)
          })
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
            values: last ? (_u, vals, _axis, _space, incr) => vals.map((v) => v.toFixed(axisDigits(incr))) : (_u, vals) => vals.map(() => '') },
          { stroke: ink, grid: { stroke: grid }, ticks: { stroke: grid }, label, labelSize: 18, size: 60 },
        ],
        series: [
          {},
          { label: 'in fit', stroke: accent, width: 0, points: { show: true, size: 3, fill: accent, stroke: accent } },
          { label: 'flagged', stroke: flag, width: 0, points: { show: true, size: 6, fill: flag, stroke: flag } },
          { label: 'not in fit', stroke: faint, width: 0, points: { show: true, size: 5, fill: 'transparent', stroke: faint } },
          { label: 'fit', stroke: ink, width: 1.5, points: { show: false }, spanGaps: false },
          { label: 'confirmed outlier', stroke: decided, width: 0, points: { show: true, size: 12, width: 2, fill: 'transparent', stroke: decided } },
          { label: 'kept by decision', stroke: accent, width: 0, points: { show: true, size: 12, width: 2, fill: 'transparent', stroke: accent } },
          { label: 'fit without confirmed outliers (not published)', stroke: decided, width: 1.5, dash: [6, 4], points: { show: false }, spanGaps: false },
        ],
        hooks: {
          setScale: [
            (u, scaleKey) => {
              if (scaleKey !== 'x' || syncing) return
              syncing = true
              const { min, max } = u.scales.x
              if (built) view.current = [min!, max!]
              for (const other of charts) if (other !== u) other.setScale('x', { min: min!, max: max! })
              syncing = false
            },
          ],
          setCursor: [
            (u) => {
              const i = u.cursor.idx
              if (k !== 0) return
              if (i == null || i < 0 || i >= series.t.length) { setHover(''); return }
              const parts = COMPONENTS.map(({ key: c }) => `${c.toUpperCase()} ${series[`${c}_mm`][i].toFixed(1)}`)
              const tag = series.outlier[i] ? ' · flagged' : series.in_fit[i] ? '' : ' · not in fit'
              setHover(`${sessionDate(series.t[i])} (${series.t[i].toFixed(4)}) · ${parts.join(' · ')} mm${tag}`)
            },
          ],
        },
        plugins: [offsetLines, wheelZoom, clickPick],
      }
      const m = decisionMarks(series, decisions, key)
      const alt = decidedFit && decidedFit.available ? lineAt(series, decidedFit.segments, key) : series.t.map(() => null)
      charts.push(new uPlot(opts, [d.t, d.kept, d.flagged, d.left, d.fit, m.confirmed, m.overridden, alt] as uPlot.AlignedData, div))
    })

    chartsRef.current = charts
    built = true
    if (restore) charts[0]?.setScale('x', { min: restore[0], max: restore[1] })

    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(() => {
      for (const c of charts) c.setSize({ width: width(), height: 190 })
    })
    ro?.observe(el)
    return () => {
      ro?.disconnect()
      chartsRef.current = []
      for (const c of charts) c.destroy()
      el.replaceChildren()
    }
  }, [series, segments, offsets, station, scheme, decisions, decidedFit])

  const years = yearsIn(series.t)
  const lo = series.t[0]
  const hi = series.t[series.t.length - 1]
  const show = (min: number, max: number) => chartsRef.current[0]?.setScale('x', { min, max })

  return (
    <section aria-labelledby="ts-plot" className="panel pad stack">
      <h2 id="ts-plot">{station} · east, north, up</h2>
      <p className="muted" style={{ fontSize: 13 }}>
        Ctrl + mouse wheel (or pinch) zooms time around the cursor; Shift + wheel pans; drag to select a span; double-click shows everything. Dots are in the fit, orange marks were flagged by the outlier rule, hollow marks are not in the fit, the line is the fitted velocity per segment, and dashed vertical lines are the catalogue's offsets. Click an epoch to record a decision on it: rings mark decided epochs, and a dashed line is the fit without the confirmed outliers (not published).
      </p>
      {years.length > 1 && (
        <div className="seg" role="group" aria-label="Show on the plot">
          <button type="button" onClick={() => show(lo, hi)}>All years</button>
          {years.map((y) => {
            const [a, b] = yearRange(y, lo, hi)
            return <button key={y} type="button" onClick={() => show(a, b)}>{y}</button>
          })}
        </div>
      )}
      <div ref={host} data-testid="ts-plot" />
      <p className="mono" style={{ fontSize: 12, minHeight: '1.4em' }} aria-live="polite">{hover}</p>
    </section>
  )
}
