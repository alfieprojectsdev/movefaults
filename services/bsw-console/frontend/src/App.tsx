import { useApi, pad3 } from './lib'
import { href, useRoute, type Route } from './route'
import type { Lock, Session } from './types'
import Campaigns from './pages/Campaigns'
import Calendar from './pages/Calendar'
import Run from './pages/Run'
import Day from './pages/Day'
import Failure from './pages/Failure'
import Plan from './pages/Plan'
import Redo from './pages/Redo'
import KnownErrors from './pages/KnownErrors'
import StationFiles from './pages/StationFiles'
import Inventory from './pages/Inventory'
import TimeSeries from './pages/TimeSeries'
import { BackToTop } from './pages/common'

const thisYear = new Date().getFullYear()

function campaignOf(r: Route, fallback: string): string {
  return 'campaign' in r ? r.campaign : fallback
}
function yearOf(r: Route): number {
  return 'year' in r ? r.year : thisYear
}

export function LockPill({ lock }: { lock: Lock | null }) {
  if (!lock) return null
  const run = lock.run
  if (lock.held && run) {
    return (
      <a className="lockpill" href={href.run(run.campaign, run.year, run.run, 'running')} title="Open this run at the days now running">
        <span aria-hidden="true" className="dot-live" />
        <span>
          BPE lock held · <strong>{run.campaign} {run.year} · DOY {pad3(run.doys[0])}–{pad3(run.doys[1])}</strong> · {run.done} of {run.total} days
        </span>
      </a>
    )
  }
  if (lock.held) {
    return (
      <span className="lockpill" title={lock.holder}>
        <span aria-hidden="true" className="dot-live" />
        <span>BPE lock held · {lock.holder}</span>
      </span>
    )
  }
  return (
    <span className="lockpill" title={lock.last_holder ? `Last holder: ${lock.last_holder}` : ''}>
      <span aria-hidden="true" className="dot-idle" />
      <span>BPE lock free</span>
    </span>
  )
}

export default function App() {
  const route = useRoute()
  const session = useApi<Session>('/api/session')
  const lock = useApi<Lock>('/api/lock')
  const campaigns = session.data?.campaigns ?? []
  const campaign = campaignOf(route, campaigns[0] ?? 'LUZON')
  const year = yearOf(route)

  const nav: [string, string, Route['page'][]][] = [
    ['Campaigns', href.campaigns(), ['campaigns']],
    ['Inventory', href.inventory(campaign, year), ['inventory']],
    ['Calendar', href.calendar(campaign, year), ['calendar', 'day', 'failure', 'redo']],
    ['Runs', href.run(campaign, year), ['run']],
    ['Plan', href.plan(campaign, year), ['plan']],
    ['Known errors', href.knownErrors(), ['known-errors']],
    ['Station files', href.stations(campaign, year), ['stations']],
    ['Time series', href.timeSeries(campaign, year), ['time-series']],
  ]

  const switchCampaign = (c: string) => {
    if ('campaign' in route) window.location.hash = window.location.hash.replace(`/c/${route.campaign}`, `/c/${c}`)
    else window.location.hash = href.calendar(c, year)
  }

  let page
  switch (route.page) {
    case 'campaigns': page = <Campaigns />; break
    case 'calendar': page = <Calendar campaign={route.campaign} year={route.year} />; break
    case 'run': page = <Run key={`${route.campaign}/${route.year}/${route.run ?? ''}/${route.at ?? ''}`} campaign={route.campaign} year={route.year} run={route.run} at={route.at} />; break
    case 'day': page = <Day campaign={route.campaign} year={route.year} doy={route.doy} />; break
    case 'failure': page = <Failure campaign={route.campaign} year={route.year} doy={route.doy} />; break
    case 'redo': page = <Redo campaign={route.campaign} year={route.year} doy={route.doy} lock={lock.data} />; break
    case 'plan': page = <Plan campaign={route.campaign} year={route.year} from={route.from} to={route.to} />; break
    case 'known-errors': page = <KnownErrors />; break
    case 'stations': page = <StationFiles campaign={route.campaign} year={route.year} />; break
    case 'inventory': page = <Inventory campaign={route.campaign} year={route.year} />; break
    case 'time-series': page = <TimeSeries key={route.campaign} campaign={route.campaign} />; break
  }

  return (
    <>
      <header className="hdr">
        <a className="brand" href={href.campaigns()}>gps3 · BSW 5.4 console</a>
        <label>
          Campaign
          <select value={campaign} onChange={(e) => switchCampaign(e.target.value)}>
            {campaigns.map((c) => <option key={c}>{c}</option>)}
          </select>
        </label>
        <nav aria-label="Main">
          {nav.map(([label, h, pages]) => (
            <a key={label} className="nav" href={h} aria-current={pages.includes(route.page) ? 'page' : undefined}>{label}</a>
          ))}
        </nav>
        <LockPill lock={lock.data} />
        <span className="who">
          {session.data?.user ?? 'Not signed in'}
        </span>
      </header>
      <main>{page}</main>
      <BackToTop />
    </>
  )
}
