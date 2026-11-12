import type { Heatmap, HeatMode, Level, RoutePlan } from '../types'

export const LEVEL_LABELS = ['Low', 'Moderate', 'High', 'Severe', 'No Travel'] as const

export const levelLabel = (level: Level | number): string => LEVEL_LABELS[level]

/**
 * Risk colours are defined once, in index.css, as --risk-0 … --risk-4 (with a
 * light and a dark value). Components reference the variable; the map, which
 * needs real colour values, reads them with `riskPalette()`.
 */
export const riskVar = (level: Level | number): string => `var(--risk-${level})`

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

export const riskPalette = (): string[] => LEVEL_LABELS.map((_, level) => cssVar(`--risk-${level}`))

export const NO_TRAVEL = 4

/**
 * Where a truck on a closed route has to stop: the last checkpoint before the
 * first No Travel stretch. Null if the route is open.
 */
export function stopPoint(route: RoutePlan): { mile: number; hour: number } | null {
  const blocked = route.segments.find((segment) => segment.level === NO_TRAVEL)
  if (!blocked) return null
  const checkpoint = route.checkpoints.find((cp) => cp.mile >= blocked.from_mile - 0.05)
  return { mile: blocked.from_mile, hour: (checkpoint?.elapsed_s ?? 0) / 3600 }
}

/** Lower bound of Moderate, High, Severe and No Travel for each condition. */
export const THRESHOLDS = {
  wind: [25, 35, 45, 55],
  rain: [0.1, 0.25, 0.5, 1.0],
  snow: [0.5, 1.0, 2.0, 3.0],
} as const

export const UNITS = { wind: 'mph', rain: 'in/hr', snow: 'in/hr' } as const

/**
 * Position of a value on the 0..4 level scale, with a fraction for how far
 * through its band it is. Only used to shade the heatmap smoothly: the actual
 * risk levels are computed by the backend.
 */
function continuousLevel(value: number, thresholds: readonly number[]): number {
  if (value <= 0) return 0
  let lower = 0
  for (let i = 0; i < thresholds.length; i++) {
    if (value < thresholds[i]) return i + (value - lower) / (thresholds[i] - lower)
    lower = thresholds[i]
  }
  return thresholds.length
}

/** Heatmap weight (0..1) of every grid point, for every hour, in one mode. */
export function heatWeights(heatmap: Heatmap, mode: HeatMode): Float32Array[] {
  const count = heatmap.points.length
  return heatmap.level.map((levels, hour) => {
    const weights = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      const wind = continuousLevel(heatmap.wind[hour][i], THRESHOLDS.wind)
      const rain = continuousLevel(heatmap.rain[hour][i], THRESHOLDS.rain)
      const snow = continuousLevel(heatmap.snow[hour][i], THRESHOLDS.snow)
      const value =
        mode === 'wind'
          ? wind
          : mode === 'rain'
            ? rain
            : mode === 'snow'
              ? snow
              : // The backend level includes the load rules, so it can exceed raw wind.
                Math.max(wind, rain, snow, levels[i])
      weights[i] = Math.min(value / 4, 1)
    }
    return weights
  })
}
