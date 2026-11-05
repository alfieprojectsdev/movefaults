// Shapes of the console API (services/bsw-console/src/bsw_console). Kept by hand:
// a field renamed there must be renamed here.

export type DayInfo = { year: number; doy: number; date: string; gps_week: number; gps_day: number; session: string }
export type DayState = 'fixed' | 'float' | 'failed' | 'running' | 'queued' | 'excluded' | 'none'

export type Session = { user: string | null; version: string; actions_enabled: boolean; can_act: boolean; campaigns: string[] }
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
  provenance?: RunProvenance
}
/** What an attempt's run_start recorded (#318). recorded is false for a run
 *  written before then: its fields are null and the page says so. */
export type RunProvenance = {
  recorded: boolean; started_by: string | null; command: string | null; code_version: string | null
  pcf: string | null; products: string | null; product_tier: string | null; config_hash: string | null
}
export type ResultFile = { name: string; v52: string; folder: string; what: string; size: number | null; written: number | null; path: string | null }
export type DayDetail = DayInfo & {
  campaign: string
  state: DayState
  attempts: Attempt[]
  results: ResultFile[]
  present: number
  quality: { stations: number | null; dropped: string[]; helmert_rms_mm: number | null; ambiguity_rate: number | null; sources: Record<string, string> }
  provenance: {
    pcf: string; ambiguities: string; campaign_dir: string
    /** The latest attempt's run; its run_start is what the fields below come from. */
    run: string | null; recorded: boolean
    started_by: string | null; command: string | null; code_version: string | null
    products: string | null; product_tier: string | null; config_hash: string | null
  }
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

/** pogf_geodetic_suite.timeseries.status, as the console serves it (bsw_console/timeseries.py). */
export type Enu = { e: number; n: number; u: number }
export type TsNotConfigured = { configured: false; missing: string[]; message: string }
export type TsUnavailable = {
  configured: true; available: false; message: string; crd_dirs: string[]; reference: string | null; default_reference: string | null
  offsets_path: string; station?: string; all_stations?: string[]; campaign?: string
  positions?: Record<string, { lat: number; lon: number }>; distances?: Record<string, number>; reference_warn_deg?: number
}
export type TsSummary =
  | TsNotConfigured
  | TsUnavailable
  | {
      configured: true; available: true; crd_dirs: string[]; reference: string | null; default_reference: string | null
      positions?: Record<string, { lat: number; lon: number }>; distances?: Record<string, number>; reference_warn_deg?: number
      offsets_path: string; all_stations: string[]; stations: string[]; outlier_mode: string; message?: string
      campaign: string
    }
export type TsSegment = {
  index: number; t_start: number; t_end: number; span_yr: number; n_epochs: number; n_fit: number; n_outliers: number
  velocity_mm_yr: Enu; sigma_mm_yr: Enu; r2: Enu; short_span: boolean
  /** The fitted line at the segment's two ends, in the same millimetre frame as `series`. */
  line?: { t: [number, number]; e_mm: [number, number]; n_mm: [number, number]; u_mm: [number, number] }
}
/** Columnar, index-aligned per epoch: what a chart takes as it is. */
export type TsSeries = {
  t: number[]; e_mm: number[]; n_mm: number[]; u_mm: number[]
  outlier: boolean[]; in_fit: boolean[]; segment: (number | null)[]; excluded?: boolean[]
}
export type TsStation =
  | TsNotConfigured
  | TsUnavailable
  | {
      configured: true; available: true; schema: string; station: string; reference: string | null
      offsets_catalog: { path: string; sha256: string } | null
      outlier_rule: { method: string; factor: number; scope: string; on: string; mode: string }
      series: TsSeries
      offsets: { t: number; type: string; label: string; within_span: boolean }[]
      segments: TsSegment[]
      velocity: { segment: number; velocity_mm_yr: Enu; sigma_mm_yr: Enu; span_yr: number; short_span: boolean; covers_latest_epoch: boolean }
      min_span_years: number; warnings: string[]
      reference_distance_deg: number; reference_warning: string | null
      decisions?: TsDecision[]
      decided_fit?: TsDecidedFit | null
    }
/** One epoch's current outlier decision (bsw_console/outliers.py). */
export type TsDecision = {
  epoch: string; decision: 'outlier' | 'not_outlier'; by: string; ts: string; reason: string
  reference: string; auto_flag: boolean; history: number; superseded: boolean; other_reference: boolean
}
/** The fit with confirmed outliers left out: shown beside the published one, never instead. */
export type TsDecidedFit =
  | { available: false; message: string; excluded: string[] }
  | {
      available: true; excluded: string[]
      velocity: { segment: number; velocity_mm_yr: Enu; sigma_mm_yr: Enu; span_yr: number; short_span: boolean; covers_latest_epoch: boolean }
      segments: Pick<TsSegment, 'index' | 'n_fit' | 'velocity_mm_yr' | 'sigma_mm_yr' | 'line'>[]
    }
/** bernese-check-equipment's report, as the console serves it (bsw_console/equipment.py). */
export type EquipmentField = { sta: string; source: string; status: string; source_igs: string | null; note: string }
export type EquipmentCurrent = {
  station: string; category: string; sta_name: string; sta_line: number | null; sta_from: string; sta_to: string
  fields: Partial<Record<'receiver' | 'antenna' | 'radome', EquipmentField>>; note: string
}
export type EquipmentVisit = {
  station: string; visit_date: string; visit_time: string; visit_time_source: string; equipment_changed: boolean
  before_status: string; before_fields: Partial<Record<'receiver' | 'antenna', EquipmentField>>; before_row_line: number | null
  after_status: string | null; after_fields: Record<string, string>; after_row_line: number | null; after_row_from: string; note: string
}
export type EquipmentAbout =
  | { configured: false; message: string }
  | { configured: true; available: false; message: string }
  | {
      configured: true; available: true; written: number; sta: { path: string; rows: number; codes: number }
      exported_at: string | null; export_counts: Record<string, number> | null; equipment_csv: string | null
      current_equipment_from: string | null
    }
export type EquipmentReport = EquipmentAbout & { summary?: Record<string, number> }
export type StationEquipment = EquipmentAbout & {
  station: string; current?: EquipmentCurrent[]; visits?: EquipmentVisit[]; names?: { station: string; problem: string; sta_names: string[] }[]
}
