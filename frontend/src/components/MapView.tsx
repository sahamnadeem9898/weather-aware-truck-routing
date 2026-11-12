import type { Feature, FeatureCollection } from 'geojson'
import {
  type ExpressionSpecification,
  type GeoJSONSource,
  LngLatBounds,
  Map as MapLibreMap,
  type MapLayerMouseEvent,
  Marker,
  type PaddingOptions,
  Popup,
  setWorkerUrl,
} from 'maplibre-gl'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { memo, useEffect, useMemo, useRef, useState } from 'react'

import { formatDayTime, formatDuration, zoneAbbreviation } from '../lib/format'
import { cumulativeMiles, interpolate, type LonLat, pointAtMile, sliceLine } from '../lib/geo'
import type { Theme } from '../hooks/useTheme'
import { cssVar, heatWeights, levelLabel, riskPalette, stopPoint } from '../lib/risk'
import type { CheckpointRef, HeatMode, Plan, RoutePlan } from '../types'

setWorkerUrl(workerUrl)

const BASEMAPS: Record<Theme, string> = {
  dark: 'https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
  light: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',
}
const USA_CENTER: LonLat = [-97.5, 39.2]
const DRAW_MS = 1600
const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

// Dash patterns that, played in order, make a dashed line appear to move forward.
const FLOW_DASHES = [
  [0, 4, 3], [0.5, 4, 2.5], [1, 4, 2], [1.5, 4, 1.5], [2, 4, 1], [2.5, 4, 0.5], [3, 4, 0],
  [0, 0.5, 3, 3.5], [0, 1, 3, 3], [0, 1.5, 3, 2.5], [0, 2, 3, 2], [0, 2.5, 3, 1.5],
  [0, 3, 3, 1], [0, 3.5, 3, 0.5],
] // prettier-ignore
const FLOW_STEP_MS = 70

/** "#rrggbb" + alpha -> "rgba(r, g, b, a)" */
function withAlpha(hex: string, alpha: number): string {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${n >> 16}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`
}

/** Line and circle colour by risk level, from the current theme's palette. */
function levelColorExpression(palette: string[]): ExpressionSpecification {
  return [
    'match', ['get', 'level'],
    0, palette[0],
    1, palette[1],
    2, palette[2],
    3, palette[3],
    palette[4],
  ] // prettier-ignore
}

/** Heatmap ramp. Density 0..1 maps onto the level scale: 0.25 = Moderate, 0.5 = High, ... */
function heatColorExpression(palette: string[]): ExpressionSpecification {
  return [
    'interpolate', ['linear'], ['heatmap-density'],
    0, withAlpha(palette[0], 0),
    0.04, withAlpha(palette[0], 0.06),
    0.2, withAlpha(palette[0], 0.36),
    0.3, withAlpha(palette[1], 0.54),
    0.5, withAlpha(palette[2], 0.64),
    0.75, withAlpha(palette[3], 0.72),
    1, withAlpha(palette[4], 0.8),
  ] // prettier-ignore
}

interface Props {
  plan: Plan | null
  selectedId: string | null
  /** Route whose card is hovered: previewed on the map without selecting it. */
  hoverId: string | null
  hour: number
  mode: HeatMode
  focus: CheckpointRef | null
  padding: PaddingOptions
  theme: Theme
  onSelect: (routeId: string) => void
}

/** Route geometry with the distance to every vertex, computed once per plan. */
interface Track {
  route: RoutePlan
  cum: number[]
}

function MapView(props: Props) {
  const { plan, selectedId, hoverId, hour, mode, focus, padding, theme, onSelect } = props
  const container = useRef<HTMLDivElement>(null)
  const mapRef = useRef<MapLibreMap | null>(null)
  const popupRef = useRef<Popup | null>(null)
  const drawProgress = useRef(1)
  // Counts basemap loads. Changing theme swaps the basemap, which drops our
  // layers; each new epoch tells the data effects to put them back.
  const [styleEpoch, setStyleEpoch] = useState(0)
  const ready = styleEpoch > 0
  const initialTheme = useRef(theme)
  const appliedTheme = useRef(theme)

  // Latest values for code that must not re-run when they change: map event
  // handlers (registered once), the route-drawing animation and the camera.
  const live = useRef({ plan, onSelect, selectedId, padding })
  useEffect(() => {
    live.current = { plan, onSelect, selectedId, padding }
  })

  const tracks = useMemo<Track[]>(
    () =>
      plan?.routes.map((route) => ({
        route,
        cum: cumulativeMiles(route.geometry, route.distance_mi),
      })) ?? [],
    [plan],
  )
  const weights = useMemo(() => (plan ? heatWeights(plan.heatmap, mode) : null), [plan, mode])

  // --- Create the map once -------------------------------------------------
  useEffect(() => {
    const map = new MapLibreMap({
      container: container.current!,
      style: BASEMAPS[initialTheme.current],
      center: USA_CENTER,
      zoom: 3.4,
      maxZoom: 12,
      attributionControl: { compact: true },
      dragRotate: false,
      pitchWithRotate: false,
    })
    mapRef.current = map
    popupRef.current = new Popup({
      closeButton: false,
      closeOnClick: false,
      offset: 14,
      maxWidth: '300px',
      className: 'cp-popup',
    })

    map.on('style.load', () => {
      addLayers(map)
      setStyleEpoch((epoch) => epoch + 1)
    })

    const pointer = () => (map.getCanvas().style.cursor = 'pointer')
    const reset = () => (map.getCanvas().style.cursor = '')
    const select = (event: MapLayerMouseEvent) => {
      const routeId = event.features?.[0]?.properties?.route
      if (routeId) live.current.onSelect(routeId)
    }
    for (const layer of ['route-hit', 'checkpoint-dot']) {
      map.on('mouseenter', layer, pointer)
      map.on('mouseleave', layer, reset)
      map.on('click', layer, select)
    }
    map.on('mousemove', 'checkpoint-dot', (event) => {
      const props = event.features?.[0]?.properties
      const current = live.current.plan
      if (props && current) showPopup(map, popupRef.current!, current, props.route, props.index)
    })
    map.on('mouseleave', 'checkpoint-dot', () => popupRef.current?.remove())

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // --- Theme change: swap the basemap (layers are re-added on style.load) ---
  useEffect(() => {
    const map = mapRef.current
    if (!map || appliedTheme.current === theme) return
    appliedTheme.current = theme
    map.setStyle(BASEMAPS[theme], { diff: false })
  }, [theme])

  // --- New plan: frame the trip and draw the routes in ---------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    popupRef.current?.remove()
    if (!plan) {
      for (const id of ['routes', 'flow', 'checkpoints']) setSource(map, id, EMPTY)
      return
    }

    const bounds = new LngLatBounds()
    for (const route of plan.routes) for (const point of route.geometry) bounds.extend(point)
    // Padding is read now rather than tracked: a later layout change (such as
    // resizing the window) shouldn't re-frame the map under the user.
    map.fitBounds(bounds, {
      padding: live.current.padding,
      duration: 1400,
      maxZoom: 9,
      essential: true,
    })

    const markers = [
      endpointMarker('origin', plan.origin.label).setLngLat([plan.origin.lon, plan.origin.lat]),
      endpointMarker('destination', plan.destination.label).setLngLat([
        plan.destination.lon,
        plan.destination.lat,
      ]),
    ]
    markers.forEach((marker) => marker.addTo(map))

    drawProgress.current = 0
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const started = performance.now()
    let frame = 0
    const tick = (now: number) => {
      const t = reduceMotion ? 1 : Math.min((now - started) / DRAW_MS, 1)
      drawProgress.current = 1 - (1 - t) ** 3 // ease-out
      drawRoutes(map, tracks, live.current.selectedId, null, drawProgress.current)
      if (t < 1) frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(frame)
      markers.forEach((marker) => marker.remove())
    }
  }, [plan, tracks, ready])

  // --- Selection changes: restyle without replaying the animation ----------
  useEffect(() => {
    const map = mapRef.current
    if (map && ready && tracks.length) {
      drawRoutes(map, tracks, selectedId, hoverId, drawProgress.current)
    }
  }, [selectedId, hoverId, tracks, ready, styleEpoch])

  // --- Marching dashes on the selected route show the direction of travel --
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !plan) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    let step = 0
    const timer = window.setInterval(() => {
      if (!map.getLayer('route-flow')) return
      step = (step + 1) % FLOW_DASHES.length
      map.setPaintProperty('route-flow', 'line-dasharray', FLOW_DASHES[step])
    }, FLOW_STEP_MS)
    return () => window.clearInterval(timer)
  }, [plan, ready, styleEpoch])

  // --- Route letter badges -------------------------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !plan) return
    const spots = [0.3, 0.5, 0.7]
    const markers = tracks.map(({ route, cum }, i) => {
      const el = document.createElement('button')
      el.type = 'button'
      el.className = 'route-badge'
      el.dataset.selected = String(route.id === selectedId)
      el.dataset.best = String(route.id === plan.recommendation.route_id)
      el.dataset.closed = String(route.has_no_travel)
      // The letter sits in a child so hover/press can scale it: MapLibre owns
      // the transform on the marker element itself.
      const face = document.createElement('span')
      face.textContent = route.id
      el.append(face)
      el.setAttribute(
        'aria-label',
        `Select route ${route.id}${route.has_no_travel ? ' (closed: do not travel)' : ''}`,
      )
      el.addEventListener('click', () => live.current.onSelect(route.id))
      const at = pointAtMile(route.geometry, cum, route.distance_mi * spots[i % spots.length])
      return new Marker({ element: el }).setLngLat(at).addTo(map)
    })
    return () => markers.forEach((marker) => marker.remove())
  }, [plan, tracks, selectedId, ready])

  // --- Heatmap: blend the two forecast hours around the slider position ----
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !map.getLayer('heat')) return
    if (!plan || !weights) {
      setSource(map, 'heat', EMPTY)
      return
    }
    const { points, step_deg, hours } = plan.heatmap
    const h0 = Math.min(Math.floor(hour), hours)
    const h1 = Math.min(h0 + 1, hours)
    const t = hour - h0
    const features: Feature[] = points.map((point, i) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: point },
      properties: { w: weights[h0][i] * (1 - t) + weights[h1][i] * t },
    }))
    setSource(map, 'heat', { type: 'FeatureCollection', features })

    // Radius = two grid cells, in pixels, at every zoom: neighbours blend into
    // a continuous surface whose density equals the local weight.
    const radiusAtZoom0 = (2 * step_deg * 512) / 360
    map.setPaintProperty('heat', 'heatmap-radius', [
      'interpolate', ['exponential', 2], ['zoom'],
      0, radiusAtZoom0,
      14, radiusAtZoom0 * 2 ** 14,
    ]) // prettier-ignore
  }, [plan, weights, hour, ready, styleEpoch])

  // --- Truck: where the selected route's truck is at the slider time --------
  // Only the selected route has a truck, so one thing moves when you press play.
  const trucks = useRef<Map<string, Marker>>(new Map())
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    const markers = trucks.current
    for (const [id, marker] of markers) {
      if (id !== selectedId || !tracks.some((track) => track.route.id === id)) {
        marker.remove()
        markers.delete(id)
      }
    }
    for (const { route, cum } of tracks) {
      if (route.id !== selectedId) continue
      const elapsed = hour * 3600
      // On a closed route the truck drives up to the No Travel stretch and waits there.
      const stop = stopPoint(route)
      const driven = interpolate(
        route.checkpoints.map((c) => c.elapsed_s),
        route.checkpoints.map((c) => c.mile),
        elapsed,
      )
      const mile = stop ? Math.min(driven, stop.mile) : driven
      const stopped = stop !== null && driven >= stop.mile
      let marker = markers.get(route.id)
      if (!marker) {
        const el = document.createElement('div')
        el.className = 'truck'
        el.dataset.selected = 'true'
        el.innerHTML =
          '<span class="truck__pulse"></span><span class="truck__dot"></span>' +
          '<span class="truck__label">Stopped: No Travel ahead</span>'
        marker = new Marker({ element: el }).setLngLat(route.geometry[0]).addTo(map)
        markers.set(route.id, marker)
      }
      const el = marker.getElement()
      el.dataset.arrived = String(!stop && elapsed >= route.duration_s)
      el.dataset.stopped = String(stopped)
      marker.setLngLat(pointAtMile(route.geometry, cum, mile))
    }
  }, [tracks, hour, selectedId, ready])

  // --- Checkpoint hovered in the side list ---------------------------------
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !plan) return
    if (focus) showPopup(map, popupRef.current!, plan, focus.routeId, focus.index)
    else popupRef.current?.remove()
  }, [focus, plan, ready])

  return <div ref={container} className="map" aria-label="Map of route options" role="region" />
}

export default memo(MapView)

// ---------------------------------------------------------------------------

function setSource(map: MapLibreMap, id: string, data: FeatureCollection) {
  ;(map.getSource(id) as GeoJSONSource | undefined)?.setData(data)
}

/** Our sources and layers, coloured from the current theme's CSS variables. */
function addLayers(map: MapLibreMap) {
  const palette = riskPalette()
  const levelColor = levelColorExpression(palette)
  const casing = cssVar('--map-casing')
  for (const id of ['heat', 'routes', 'flow', 'checkpoints']) {
    map.addSource(id, { type: 'geojson', data: EMPTY })
  }
  // The heatmap goes under the basemap's labels so place names stay readable.
  const firstLabel = map.getStyle().layers.find((layer) => layer.type === 'symbol')?.id

  map.addLayer(
    {
      id: 'heat',
      type: 'heatmap',
      source: 'heat',
      paint: {
        'heatmap-weight': ['get', 'w'],
        'heatmap-intensity': 0.9,
        'heatmap-color': heatColorExpression(palette),
        'heatmap-radius': 30,
        'heatmap-opacity': 0.9,
      },
    },
    firstLabel,
  )

  const selected: ExpressionSpecification = ['==', ['get', 'selected'], true]
  const line = { 'line-cap': 'round', 'line-join': 'round' } as const
  map.addLayer({
    id: 'route-other',
    type: 'line',
    source: 'routes',
    filter: ['!', selected],
    layout: line,
    paint: {
      'line-color': levelColor,
      'line-width': ['case', ['get', 'hover'], 5, 3],
      'line-opacity': ['case', ['get', 'hover'], 0.95, 0.5],
    },
  })
  map.addLayer({
    id: 'route-casing',
    type: 'line',
    source: 'routes',
    filter: selected,
    layout: line,
    paint: { 'line-color': casing, 'line-width': 9 },
  })
  map.addLayer({
    id: 'route-selected',
    type: 'line',
    source: 'routes',
    filter: selected,
    layout: line,
    paint: { 'line-color': levelColor, 'line-width': 5 },
  })
  map.addLayer({
    id: 'route-flow',
    type: 'line',
    source: 'flow',
    paint: {
      'line-color': '#ffffff',
      'line-width': 1.6,
      'line-opacity': 0.6,
      'line-dasharray': FLOW_DASHES[0],
    },
  })
  // Invisible, wide line so routes are easy to click.
  map.addLayer({
    id: 'route-hit',
    type: 'line',
    source: 'routes',
    paint: { 'line-color': '#000', 'line-width': 22, 'line-opacity': 0 },
  })
  map.addLayer({
    id: 'checkpoint-dot',
    type: 'circle',
    source: 'checkpoints',
    paint: {
      'circle-radius': ['case', selected, 5.5, 3.2],
      'circle-color': levelColor,
      'circle-stroke-color': casing,
      'circle-stroke-width': ['case', selected, 2, 1],
      'circle-opacity': ['case', selected, 1, 0.6],
      'circle-stroke-opacity': ['case', selected, 1, 0.6],
    },
  })
}

/** Routes as level-coloured segments, revealed up to `progress` (0..1). */
function drawRoutes(
  map: MapLibreMap,
  tracks: Track[],
  selectedId: string | null,
  hoverId: string | null,
  progress: number,
) {
  const lines: Feature[] = []
  const dots: Feature[] = []
  // Selected route last so it is drawn on top.
  const ordered = [...tracks].sort(
    (a, b) => Number(a.route.id === selectedId) - Number(b.route.id === selectedId),
  )
  for (const { route, cum } of ordered) {
    const selected = route.id === selectedId
    const limit = route.distance_mi * progress
    for (const segment of route.segments) {
      if (segment.from_mile >= limit) break
      lines.push({
        type: 'Feature',
        geometry: {
          type: 'LineString',
          coordinates: sliceLine(route.geometry, cum, segment.from_mile, Math.min(segment.to_mile, limit)),
        },
        properties: { route: route.id, level: segment.level, selected, hover: route.id === hoverId },
      })
    }
    route.checkpoints.forEach((checkpoint, index) => {
      if (checkpoint.mile > limit) return
      dots.push({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [checkpoint.lon, checkpoint.lat] },
        properties: { route: route.id, index, level: checkpoint.level, selected },
      })
    })
  }
  // Direction-of-travel dashes: one unbroken line along the selected route,
  // unless it is closed (nothing travels a closed route).
  const active = tracks.find((track) => track.route.id === selectedId)
  const flow: Feature[] =
    active && !active.route.has_no_travel && progress > 0
      ? [
          {
            type: 'Feature',
            geometry: {
              type: 'LineString',
              coordinates: sliceLine(active.route.geometry, active.cum, 0, active.route.distance_mi * progress),
            },
            properties: {},
          },
        ]
      : []
  setSource(map, 'flow', { type: 'FeatureCollection', features: flow })
  setSource(map, 'routes', { type: 'FeatureCollection', features: lines })
  setSource(map, 'checkpoints', { type: 'FeatureCollection', features: dots })
}

function endpointMarker(kind: 'origin' | 'destination', label: string): Marker {
  const el = document.createElement('div')
  el.className = `endpoint endpoint--${kind}`
  const pin = document.createElement('span')
  pin.className = 'endpoint__pin'
  const text = document.createElement('span')
  text.className = 'endpoint__label'
  text.textContent = label.split(',')[0]
  el.append(pin, text)
  return new Marker({ element: el, anchor: 'center' })
}

function showPopup(map: MapLibreMap, popup: Popup, plan: Plan, routeId: string, index: number) {
  const route = plan.routes.find((r) => r.id === routeId)
  const cp = route?.checkpoints[index]
  if (!route || !cp) return

  const isFirst = index === 0
  const isLast = index === route.checkpoints.length - 1
  const where = isFirst ? 'Origin' : isLast ? 'Destination' : `Mile ${Math.round(cp.mile)}`
  const zone = zoneAbbreviation(cp.eta, plan.timezone)
  const gust = cp.gust_mph === null ? '' : `<small>gusts ${Math.round(cp.gust_mph)}</small>`

  const root = document.createElement('div')
  root.className = 'cp'
  root.innerHTML = `
    <div class="cp__head">
      <span class="cp__title">Route ${route.id} · ${where}</span>
      <span class="pill" data-level="${cp.level}">${levelLabel(cp.level)}</span>
    </div>
    <div class="cp__eta">ETA ${formatDayTime(cp.eta, plan.timezone)} ${zone}
      <span>${isFirst ? 'departure' : `${formatDuration(cp.elapsed_s)} in`}</span></div>
    <dl class="cp__grid">
      <div><dt>Wind</dt><dd>${Math.round(cp.wind_mph)}<i>mph</i>${gust}</dd></div>
      <div><dt>Rain</dt><dd>${cp.rain_in_hr.toFixed(2)}<i>in/hr</i></dd></div>
      <div><dt>Snow</dt><dd>${cp.snow_in_hr.toFixed(1)}<i>in/hr</i></dd></div>
    </dl>`
  const reason = document.createElement('p')
  reason.className = 'cp__reason'
  reason.textContent = cp.reason
  root.append(reason)

  popup.setLngLat([cp.lon, cp.lat]).setDOMContent(root).addTo(map)
}
