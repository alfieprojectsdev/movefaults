import { useApi, pad3 } from '../lib'
import { href } from '../route'
import type { Activity, CampaignCard } from '../types'
import { Failed, Loading, When } from './common'

function RunState({ c }: { c: CampaignCard }) {
  const r = c.last_run
  if (!r) return <div className="banner idle">No run recorded by the service</div>
  const span = r.doys.length ? `${r.year} DOY ${pad3(Math.min(...r.doys))}–${pad3(Math.max(...r.doys))}` : `${r.year}`
  if (r.state === 'running' || r.state === 'slow' || r.state === 'unknown')
    return <div className="banner info"><span aria-hidden="true" className="dot-live" /> Running · {span}{r.state === 'slow' ? ' · slower than usual' : ''}</div>
  if (r.state === 'halted' || r.state === 'dead')
    return (
      <div className="banner warn">
        <strong aria-hidden="true">!</strong>
        <span>{r.state === 'dead' ? 'Driver gone' : 'Halted'} · {span} · {r.halt ?? 'no run_end recorded'}</span>
      </div>
    )
  return <div className="banner idle">Idle · last run {span} finished</div>
}

export default function Campaigns() {
  const { data, error } = useApi<{ campaigns: CampaignCard[]; activity: Activity[] }>('/api/campaigns')
  if (error) return <Failed error={error} />
  if (!data) return <Loading what="campaigns" />
  return (
    <>
      <div className="titlebar">
        <div>
          <h1>Campaigns</h1>
          <p className="muted">BSW 5.4 processing campaigns on gps3. Results are archived in SAVEDISK; the DATAPOOL is the input of record.</p>
        </div>
        <a className="btn" href={href.plan(data.campaigns[0]?.name ?? 'LUZON', new Date().getFullYear())}>Plan a run</a>
      </div>
      <section className="cards" aria-label="Campaigns">
        {data.campaigns.map((c) => {
          const latest = c.years[0]?.year ?? new Date().getFullYear()
          return (
            <article key={c.name} className="panel pad stack">
              <div className="row" style={{ justifyContent: 'space-between' }}>
                <h2 style={{ fontSize: 18 }}>{c.name}</h2>
                <span className="muted" style={{ fontSize: 12 }}>PCF {c.pcf}{c.float_pcf ? ` · float ${c.float_pcf}` : ''}</span>
                {c.allow_header_mismatches && <span className="stub" title="RINEX header and STA disagreements are written to the log and the day still runs, as bernese-run-year --allow-header-mismatches does">header mismatches allowed</span>}
              </div>
              <RunState c={c} />
              <table className="t">
                <thead><tr><th scope="col">Year</th><th scope="col">Fixed</th><th scope="col">Float</th><th scope="col">Failed</th><th scope="col">Not run</th></tr></thead>
                <tbody>
                  {c.years.map((y) => (
                    <tr key={y.year}>
                      <td><a href={href.calendar(c.name, y.year)}>{y.year}</a></td>
                      <td className="num">{y.fixed}</td><td className="num">{y.float}</td><td className="num">{y.failed}</td><td className="num">{y.not_run}</td>
                    </tr>
                  ))}
                  {!c.years.length && <tr><td colSpan={5} className="muted">No results directory yet</td></tr>}
                </tbody>
              </table>
              <div className="row" style={{ fontSize: 13 }}>
                <a href={href.calendar(c.name, latest)}>Calendar</a>
                {c.last_run && <a href={href.run(c.name, c.last_run.year, c.last_run.run)}>{c.last_run.ended ? 'Last run' : 'Current run'}</a>}
              </div>
            </article>
          )
        })}
      </section>
      <section aria-labelledby="recent" className="stack">
        <h2 id="recent">Recent activity</h2>
        <div className="panel scroll">
          <table className="t">
            <thead><tr><th scope="col">When (local)</th><th scope="col">Where</th><th scope="col">Campaign</th><th scope="col">Event</th></tr></thead>
            <tbody>
              {data.activity.map((a, i) => (
                <tr key={i}>
                  <td><When ts={a.ts} /></td>
                  <td>{a.who}</td>
                  <td>{a.campaign} {a.year}</td>
                  <td>
                    {a.text}{' '}
                    {a.event === 'attempt_end' && a.doy && <a href={href.failure(a.campaign, a.year, a.doy)}>Diagnosis</a>}
                  </td>
                </tr>
              ))}
              {!data.activity.length && <tr><td colSpan={4} className="muted">No runs recorded yet</td></tr>}
            </tbody>
          </table>
        </div>
        <p className="faint" style={{ fontSize: 12 }}>From the service's run records. Runs started through scripts/ before the cutover are not in them.</p>
      </section>
    </>
  )
}
