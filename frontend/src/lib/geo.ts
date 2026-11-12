export type LonLat = [number, number]

const EARTH_RADIUS_MI = 3958.7613
const toRad = (deg: number) => (deg * Math.PI) / 180

function haversineMiles(a: LonLat, b: LonLat): number {
  const dLat = toRad(b[1] - a[1])
  const dLon = toRad(b[0] - a[0])
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_RADIUS_MI * Math.asin(Math.sqrt(h))
}

/**
 * Distance from the start to every vertex, rescaled so the last value equals
 * `totalMiles`. The geometry sent to the browser is simplified, so its own
 * length is slightly shorter than the real route.
 */
export function cumulativeMiles(coords: LonLat[], totalMiles: number): number[] {
  const out = [0]
  for (let i = 1; i < coords.length; i++) out.push(out[i - 1] + haversineMiles(coords[i - 1], coords[i]))
  const scale = out[out.length - 1] > 0 ? totalMiles / out[out.length - 1] : 1
  return out.map((d) => d * scale)
}

/** Index of the last vertex at or before `mile`. */
function segmentIndex(cum: number[], mile: number): number {
  let lo = 0
  let hi = cum.length - 1
  while (lo < hi - 1) {
    const mid = (lo + hi) >> 1
    if (cum[mid] <= mile) lo = mid
    else hi = mid
  }
  return lo
}

export function pointAtMile(coords: LonLat[], cum: number[], mile: number): LonLat {
  const m = Math.min(Math.max(mile, 0), cum[cum.length - 1])
  const i = segmentIndex(cum, m)
  const span = cum[i + 1] - cum[i]
  const t = span > 0 ? (m - cum[i]) / span : 0
  return [
    coords[i][0] + (coords[i + 1][0] - coords[i][0]) * t,
    coords[i][1] + (coords[i + 1][1] - coords[i][1]) * t,
  ]
}

/** The part of the line between two mile marks, with exact end points. */
export function sliceLine(coords: LonLat[], cum: number[], from: number, to: number): LonLat[] {
  const start = segmentIndex(cum, from)
  const end = segmentIndex(cum, to)
  const out: LonLat[] = [pointAtMile(coords, cum, from)]
  for (let i = start + 1; i <= end; i++) out.push(coords[i])
  out.push(pointAtMile(coords, cum, to))
  return out
}

/** Linear interpolation of y at x over sorted (x, y) pairs, clamped at both ends. */
export function interpolate(xs: number[], ys: number[], x: number): number {
  if (x <= xs[0]) return ys[0]
  const last = xs.length - 1
  if (x >= xs[last]) return ys[last]
  const i = segmentIndex(xs, x)
  const span = xs[i + 1] - xs[i]
  return span > 0 ? ys[i] + ((ys[i + 1] - ys[i]) * (x - xs[i])) / span : ys[i]
}
