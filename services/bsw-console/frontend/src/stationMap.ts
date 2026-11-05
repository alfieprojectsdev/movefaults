/** Pure helpers for the Time series page's station map. */

export type LatLon = { lat: number; lon: number }

/** Metres of a degree of arc: the ring's radius, the distance the page warns at. */
export const METRES_PER_DEGREE = 111_195

const median = (v: number[]) => {
  const s = [...v].sort((a, b) => a - b)
  return s[Math.floor(s.length / 2)]
}

/** The stations the map opens on: those near the middle of the network. IGS
 * fiducials are thousands of km away, and including them would shrink the campaign's
 * own stations to a smudge. The median is what they cannot pull. */
export function coreStations(positions: Record<string, LatLon>, withinDeg = 10): string[] {
  const codes = Object.keys(positions)
  if (codes.length === 0) return []
  const lat = median(codes.map((c) => positions[c].lat))
  const lon = median(codes.map((c) => positions[c].lon))
  const near = codes.filter((c) => Math.hypot(positions[c].lat - lat, positions[c].lon - lon) <= withinDeg)
  return near.length > 0 ? near : codes
}
