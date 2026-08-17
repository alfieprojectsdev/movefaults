/**
 * Great-circle distance between two WGS-84 points, in metres.
 *
 * Haversine rather than a projected approximation: the Philippines spans
 * 5°–21°N and the sites run from Batanes to Tawi-Tawi, so a flat-earth
 * approximation tuned to one latitude drifts badly at the other end of the
 * network. At the ranges this is used for — a few kilometres — haversine on a
 * spherical earth is accurate to well under a metre, which is far finer than
 * the phone's own fix.
 */

const EARTH_RADIUS_M = 6_371_008.8; // IUGG mean radius

export interface LatLon {
  latitude: number;
  longitude: number;
}

export function distanceMetres(a: LatLon, b: LatLon): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;

  const dLat = toRad(b.latitude - a.latitude);
  const dLon = toRad(b.longitude - a.longitude);
  const lat1 = toRad(a.latitude);
  const lat2 = toRad(b.latitude);

  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;

  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(h));
}

/**
 * Distance for a person reading a phone in the sun, not for a report.
 *
 * Under a kilometre the useful question is "is it the one I am standing at?",
 * so metres rounded to 10. Past that, one decimal of a kilometre is as much
 * precision as a handset fix deserves.
 */
export function formatDistance(metres: number): string {
  if (metres < 1000) return `${Math.round(metres / 10) * 10} m`;
  if (metres < 10_000) return `${(metres / 1000).toFixed(1)} km`;
  return `${Math.round(metres / 1000)} km`;
}
