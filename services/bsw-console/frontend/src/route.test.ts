import { href, parse } from './route'
import { dayLabel, jumpTargets, lineClass, pad3, resolveAt } from './lib'

describe('routes', () => {
  it('names the campaign in the URL, so two tabs can show two campaigns', () => {
    expect(parse('#/c/luzon/2026/day/45')).toEqual({ page: 'day', campaign: 'LUZON', year: 2026, doy: 45 })
    expect(parse('#/c/PHREF/2025/day/210/failure')).toEqual({ page: 'failure', campaign: 'PHREF', year: 2025, doy: 210 })
    expect(parse('#/c/LUZON/2026/plan?from=71&to=100')).toEqual({ page: 'plan', campaign: 'LUZON', year: 2026, from: 71, to: 100 })
    expect(parse('#/known-errors')).toEqual({ page: 'known-errors' })
    // the year-less time-series link from before years were in it opens this year
    expect(parse('#/c/luzon/time-series')).toEqual({ page: 'time-series', campaign: 'LUZON', year: new Date().getFullYear() })
    expect(parse('')).toEqual({ page: 'campaigns' })
  })
  it('round-trips every link it makes', () => {
    expect(parse(href.redo('LUZON', 2026, 45))).toEqual({ page: 'redo', campaign: 'LUZON', year: 2026, doy: 45 })
    expect(parse(href.run('LUZON', 2026, 'c2ff9ab5'))).toEqual({ page: 'run', campaign: 'LUZON', year: 2026, run: 'c2ff9ab5' })
    expect(parse(href.timeSeries('PHREF', 2025))).toEqual({ page: 'time-series', campaign: 'PHREF', year: 2025 })
    expect(parse(href.run('PHSUP', 2025, 'b2c7a582', 'running'))).toEqual({ page: 'run', campaign: 'PHSUP', year: 2025, run: 'b2c7a582', at: 'running' })
    expect(parse(href.run('PHSUP', 2025, undefined, 292))).toEqual({ page: 'run', campaign: 'PHSUP', year: 2025, at: '292' })
    expect(href.run('PHSUP', 2025)).toBe('#/c/PHSUP/2025/run')
  })
})

describe('jump links on the run page', () => {
  const rows = [
    { doy: 69, outcome: 'already solved' },
    { doy: 70, outcome: 'failed' },
    { doy: 292, outcome: 'running' },
    { doy: 303, outcome: 'running' },
    { doy: 304, outcome: 'queued' },
    { doy: 305, outcome: 'not started (halted)' },
  ]
  it('finds the first day of each kind and the running block', () => {
    expect(jumpTargets(rows)).toEqual({ running: [292, 303], failed: 70, queued: 304, solved: 69 })
    expect(jumpTargets([])).toEqual({ running: null, failed: null, queued: null, solved: null })
  })
  it('reads at= as a DOY or as a kind of day', () => {
    const t = jumpTargets(rows)
    expect(resolveAt('running', t)).toBe(292)
    expect(resolveAt('failed', t)).toBe(70)
    expect(resolveAt('300', t)).toBe(300)
    expect(resolveAt('nonsense', t)).toBeNull()
    expect(resolveAt(undefined, t)).toBeNull()
  })
})

describe('BSW text', () => {
  it('marks *** errors, ### warnings and ERR status lines', () => {
    expect(lineClass(' *** SR HELMR1: NO REDUNDANCY')).toBe('err')
    expect(lineClass(' ### SR RXOSTA: Station name different')).toBe('warn')
    expect(lineClass(' 26-OCT-2026  09:31:03  ERR HELMR1    ERROR IN MAIN PROGRAM')).toBe('warn')
    expect(lineClass(' |   4 | DARW 50134M001 |', 'darw')).toBe('hit')
  })
  it('always gives the DOY with the date', () => {
    expect(pad3(5)).toBe('005')
    expect(dayLabel('2026-02-14', 45)).toBe('2026-02-14, DOY 045')
  })
})
