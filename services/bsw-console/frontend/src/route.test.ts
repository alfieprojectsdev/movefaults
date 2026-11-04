import { href, parse } from './route'
import { dayLabel, lineClass, pad3 } from './lib'

describe('routes', () => {
  it('names the campaign in the URL, so two tabs can show two campaigns', () => {
    expect(parse('#/c/luzon/2026/day/45')).toEqual({ page: 'day', campaign: 'LUZON', year: 2026, doy: 45 })
    expect(parse('#/c/PHREF/2025/day/210/failure')).toEqual({ page: 'failure', campaign: 'PHREF', year: 2025, doy: 210 })
    expect(parse('#/c/LUZON/2026/plan?from=71&to=100')).toEqual({ page: 'plan', campaign: 'LUZON', year: 2026, from: 71, to: 100 })
    expect(parse('#/known-errors')).toEqual({ page: 'known-errors' })
    expect(parse('')).toEqual({ page: 'campaigns' })
  })
  it('round-trips every link it makes', () => {
    expect(parse(href.redo('LUZON', 2026, 45))).toEqual({ page: 'redo', campaign: 'LUZON', year: 2026, doy: 45 })
    expect(parse(href.run('LUZON', 2026, 'c2ff9ab5'))).toEqual({ page: 'run', campaign: 'LUZON', year: 2026, run: 'c2ff9ab5' })
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
