import { useApi } from '../lib'

export default function TimeSeries({ campaign }: { campaign: string }) {
  const { error } = useApi<unknown>(`/api/campaigns/${campaign}/time-series/ALL`)
  return (
    <>
      <div className="stack">
        <h1>Time series · {campaign} <span className="stub">stage 5 · not connected</span></h1>
        <p className="muted" style={{ maxWidth: '80ch' }}>
          East, north and up per station, with offsets from the offsets catalogue marked by type (EQ earthquake, CE equipment change, VE volcanic, UK unknown), replacing <span className="mono">plot_v2.py</span> and <span className="mono">vel_line_v8.m</span>. Statistical outliers arrive flagged by the timeseries package; a person confirms or overrides each, and the decision is recorded with their name.
        </p>
      </div>
      <div className="banner idle" role="status">
        <strong>Not connected.</strong>
        <span>{error ?? 'This panel waits on a read-only status endpoint from the timeseries package.'}</span>
      </div>
      <p className="faint" style={{ fontSize: 13 }}>Open team decision, shown here once it is made: whether a confirmed outlier is excluded from the velocity fit, or only recorded.</p>
    </>
  )
}
