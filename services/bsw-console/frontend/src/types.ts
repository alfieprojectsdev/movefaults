// Shapes of the console API (services/bsw-console/src/bsw_console). Kept by hand:
// a field renamed there must be renamed here.

export type DayInfo = { year: number; doy: number; date: string; gps_week: number; gps_day: number; session: string }
export type DayState = 'fixed' | 'float' | 'failed' | 'running' | 'queued' | 'excluded' | 'none'

export type Session = { user: string | null; accounts: string; version: string; actions_enabled: boolean; can_act: boolean; campaigns: string[] }
export type Lock = {
  held: boolean
  holder: string
  last_holder: string
  run: { campaign: string; year: number; run: string; doys: number[]; done: number; total: number; started: number } | null
}

export type RunSummary = {
  run: string
  started: number
  ended: number | null
  host?: string
  doys: number[]
  banked?: number[]
  config?: string | null
  state: string
  halt: string | null
  status_lines?: string[]
}
export type CampaignCard = {
  name: string
  pcf: string
  float_pcf: string
  prefix: string
  years: { year: number; fixed: number; float: number; failed: number; not_run: number }[]
  last_run: (RunSummary & { year: number }) | null
}
export type Activity = { ts: number; who: string; campaign: string; year: number; doy: number | null; event: string; text: string }

export type Calendar = {
  campaign: string
  year: number
  counts: Record<DayState, number>
  days: (DayInfo & { state: DayState; note: string })[]
}

export type RunRow = DayInfo & { outcome: string; error: string; note: string; pid: number | null; cells: string[]; seconds: number | null }
export type RunDetail = {
  campaign: string
  year: number
  run: RunSummary | null
  runs: RunSummary[]
  groups?: { key: string; name: string }[]
  rows?: RunRow[]
  breaker?: { identical: number; identical_limit: number; any: number; any_limit: number; last_error: string }
  median_seconds?: number | null
}

export type Attempt = {
  run: string
  doy: number
  session: string
  started: number
  ended: number | null
  outcome: string
  seconds: number | null
  error: string
  note: string
  stations: number | null
  config?: string | null
  host?: string
}
export type ResultFile = { name: string; v52: string; folder: string; what: string; size: number | null; written: number | null; path: string | null }
export type DayDetail = DayInfo & {
  campaign: string
  state: DayState
  attempts: Attempt[]
  results: ResultFile[]
  present: number
  quality: { stations: number | null; dropped: string[]; helmert_rms_mm: number | null; ambiguity_rate: number | null; sources: Record<string, string> }
  provenance: Record<string, string | null>
}
export type FileText = { name: string; lines: string[]; truncated: boolean; total: number }

export type KBEntry = {
  emitter: string
  message: string
  scope: string
  status: string
  diagnosis: string
  remedy: string
  source: string
  confirm: string | null
  number: number
}
export type Failure = DayInfo & {
  campaign: string
  attempt: Attempt
  attempt_number: number
  label: string
  file: string | null
  pid: number | null
  script: string | null
  program: string | null
  cause: { emitter: string; emitter_type: string; program: string | null; headline: string; kind: string; detail: string[]; params: Record<string, string>; line: number } | null
  lines: string[]
  first_current_line: number
  entry: KBEntry | null
  verdict: { kind: string; text: string; detail: string }
}
export type KnownErrors = {
  path: string
  days: number
  entries: (KBEntry & { fired: number; last: { campaign: string; year: number; doy: number; ts: number } | null })[]
  unknown: { campaign: string; year: number; doy: number; ts: number; label: string }[]
}

export type Check = { level: 'ok' | 'bad' | 'info'; title: string; detail: string }
export type Plan = {
  campaign: string
  year: number
  pcf: string
  from: DayInfo
  to: DayInfo
  todo: number[]
  busiest: number | null
  excluded: { doy: number; reason: string; detail: string }[]
  maxpar: Record<string, number | null>
  label: string
  sources: string[]
  groups: { index: number; key: string; name: string; pids: string[] }[]
  skipped: number[]
  rnxgra: string
  rnxgra_presets: Record<string, string>
  checks: Check[]
  can_start: boolean
  start_blocked_because: string[]
  pcfs: string[]
}
export type SavedPlan = { id: string; saved: string; by: string; name?: string; campaign: string; year: number; from: number; to: number; pcf: string; skipped: number[] }

export type Redo = DayInfo & { campaign: string; from: string; to: string; files: ResultFile[]; lock: Lock }

export type StationFiles = {
  campaign: string
  refdir: string
  files: Record<string, { name: string; present: boolean }>
  columns: string[]
  rows: { station: string; cells: Record<string, number>; notes: string[] }[]
}
