/** Shapes returned by the Django API (see backend/planner/services/planner.py). */

export type Level = 0 | 1 | 2 | 3 | 4

export interface Place {
  label: string
  lat: number
  lon: number
}

export interface Checkpoint {
  mile: number
  lat: number
  lon: number
  elapsed_s: number
  eta: string
  wind_mph: number
  gust_mph: number | null
  rain_in_hr: number
  snow_in_hr: number
  level: Level
  load_rule_applied: boolean
  reason: string
}

export interface Segment {
  from_mile: number
  to_mile: number
  level: Level
}

/** When a closed route becomes drivable again. */
export interface Wait {
  hours: number
  departure: string // UTC instant
  departure_local: string // wall-clock time at the origin, ready for the form
}

export interface RoutePlan {
  id: string
  rank: number
  tags: string[]
  distance_mi: number
  duration_s: number
  arrival: string
  miles_by_level: number[]
  avg_risk: number
  worst_level: Level
  /** Any No Travel miles: the route is closed and must not be driven. */
  has_no_travel: boolean
  wait: Wait | null
  geometry: [number, number][]
  checkpoints: Checkpoint[]
  segments: Segment[]
}

export interface Heatmap {
  points: [number, number][]
  step_deg: number
  hours: number
  wind: number[][]
  rain: number[][]
  snow: number[][]
  level: number[][]
}

export interface Plan {
  origin: Place
  destination: Place
  departure: string
  timezone: string
  load_lb: number
  interval_mi: number
  wind_field: 'speed' | 'gust'
  routing_provider: string
  simulated: boolean
  /** Departure the storm drill is timed against (origin wall-clock), if simulated */
  storm_anchor: string | null
  recommendation: {
    /** null when every route is closed */
    route_id: string | null
    reasons: string[]
    no_safe_route: boolean
    /** Shortest wait for any route to open; only set when every route is closed */
    wait: (Wait & { route_id: string }) | null
  }
  routes: RoutePlan[]
  heatmap: Heatmap
}

export interface PlaceInput {
  text: string
  lat?: number
  lon?: number
}

export interface TripForm {
  origin: PlaceInput
  destination: PlaceInput
  departure: string
  loadLb: number
  intervalMi: 10 | 25 | 50
  simulateStorm: boolean
  /** Set only when re-planning a storm drill for a later departure */
  stormAnchor?: string | null
}

export type HeatMode = 'risk' | 'wind' | 'rain' | 'snow'

export interface CheckpointRef {
  routeId: string
  index: number
}
