import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useRef } from 'react'

import { formatDayTime, zoneAbbreviation } from '../lib/format'
import { LEVEL_LABELS, stopPoint, THRESHOLDS, UNITS } from '../lib/risk'
import type { HeatMode, Plan } from '../types'

interface Props {
  plan: Plan
  hour: number
  playing: boolean
  mode: HeatMode
  selectedId: string | null
  onHour: (hour: number) => void
  onPlaying: (playing: boolean) => void
  onMode: (mode: HeatMode) => void
}

const MODES: { id: HeatMode; label: string }[] = [
  { id: 'risk', label: 'Risk' },
  { id: 'wind', label: 'Wind' },
  { id: 'rain', label: 'Rain' },
  { id: 'snow', label: 'Snow' },
]
const HOURS_PER_SECOND = 2.5

/** Forecast scrubber: moves the heatmap and the trucks through the next 48 hours. */
export default function TimelineDock(props: Props) {
  const { plan, hour, playing, mode, selectedId, onHour, onPlaying, onMode } = props
  const max = plan.heatmap.hours

  // Playback: advance the hour every animation frame.
  const hourRef = useRef(hour)
  useEffect(() => {
    hourRef.current = hour
  }, [hour])
  useEffect(() => {
    if (!playing) return
    let frame = 0
    let previous = performance.now()
    const tick = (now: number) => {
      const next = hourRef.current + ((now - previous) / 1000) * HOURS_PER_SECOND
      previous = now
      if (next >= max) {
        onHour(max)
        onPlaying(false)
        return
      }
      hourRef.current = next
      onHour(next)
      frame = requestAnimationFrame(tick)
    }
    frame = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(frame)
  }, [playing, max, onHour, onPlaying])

  const when = new Date(new Date(plan.departure).getTime() + hour * 3_600_000)
  const zone = zoneAbbreviation(when, plan.timezone)

  return (
    <motion.section
      className="dock"
      aria-label="Forecast timeline"
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 30 }}
      transition={{ type: 'spring', stiffness: 240, damping: 28, delay: 0.35 }}
    >
      <div className="dock__top">
        <button
          type="button"
          className="dock__play"
          aria-label={playing ? 'Pause forecast' : 'Play forecast'}
          onClick={() => {
            if (!playing && hour >= max) onHour(0)
            onPlaying(!playing)
          }}
        >
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.svg
              key={playing ? 'pause' : 'play'}
              viewBox="0 0 24 24"
              width="18"
              height="18"
              aria-hidden
              initial={{ scale: 0.4, opacity: 0, rotate: -30 }}
              animate={{ scale: 1, opacity: 1, rotate: 0 }}
              exit={{ scale: 0.4, opacity: 0, rotate: 30 }}
              transition={{ duration: 0.16 }}
            >
              {playing ? (
                <path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" />
              ) : (
                <path d="M8 5.2v13.6a.6.6 0 0 0 .92.5l10.4-6.8a.6.6 0 0 0 0-1L8.92 4.7A.6.6 0 0 0 8 5.2Z" fill="currentColor" />
              )}
            </motion.svg>
          </AnimatePresence>
        </button>
        <div className="dock__time">
          <strong>
            {formatDayTime(when, plan.timezone)} <span>{zone}</span>
          </strong>
          <span>{hour < 0.05 ? 'Departure' : `+${hour.toFixed(hour % 1 < 0.05 ? 0 : 1)} h after departure`}</span>
        </div>
        <div className="segmented segmented--small" role="radiogroup" aria-label="Heatmap layer">
          {MODES.map((item) => (
            <button
              key={item.id}
              type="button"
              role="radio"
              aria-checked={mode === item.id}
              onClick={() => onMode(item.id)}
            >
              {mode === item.id && <motion.span layoutId="mode-thumb" className="segmented__thumb" />}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="scrub">
        <div className="scrub__arrivals">
          {arrivalMarks(plan, max).map(({ id, left, hour: arrival, stopped }) => (
            <button
              key={id}
              type="button"
              data-selected={id === selectedId}
              data-stopped={stopped}
              style={{ left: `${left}%` }}
              title={
                stopped
                  ? `Route ${id} has to stop here: No Travel ahead. Click to jump there.`
                  : `Route ${id} arrives. Click to jump there.`
              }
              aria-label={stopped ? `Jump to where route ${id} stops` : `Jump to route ${id} arrival`}
              onClick={() => {
                onPlaying(false)
                onHour(arrival)
              }}
            >
              {id}
            </button>
          ))}
        </div>
        <input
          type="range"
          min={0}
          max={max}
          step={0.25}
          value={hour}
          aria-label="Hours after departure"
          aria-valuetext={`${hour.toFixed(1)} hours after departure`}
          style={{ '--fill': `${(hour / max) * 100}%` } as React.CSSProperties}
          onChange={(event) => {
            onPlaying(false)
            onHour(Number(event.target.value))
          }}
        />
        <div className="scrub__marks" aria-hidden>
          {[0, 0.25, 0.5, 0.75, 1].map((share) => share * max).map((tick) => (
            <span key={tick} style={{ left: `${(tick / max) * 100}%` }}>
              {tick === 0 ? 'Depart' : `+${tick}h`}
            </span>
          ))}
        </div>
      </div>

      <Legend mode={mode} simulated={plan.simulated} />
    </motion.section>
  )
}

const MIN_MARK_GAP = 4 // percent of the track, so arrival badges never overlap

interface Mark {
  id: string
  left: number
  hour: number
  stopped: boolean
}

/**
 * One badge per route on the track: where it arrives, or, for a closed route,
 * where the truck has to stop. Badges are nudged apart if they collide.
 */
function arrivalMarks(plan: Plan, maxHours: number): Mark[] {
  const marks = plan.routes
    .map((route) => {
      const stop = stopPoint(route)
      const hour = stop ? stop.hour : route.duration_s / 3600
      return { id: route.id, hour, left: (hour / maxHours) * 100, stopped: stop !== null }
    })
    .filter((mark) => mark.hour <= maxHours)
    .sort((a, b) => a.left - b.left)
  for (let i = 1; i < marks.length; i++) {
    marks[i].left = Math.max(marks[i].left, marks[i - 1].left + MIN_MARK_GAP)
  }
  return marks
}

function Legend({ mode, simulated }: { mode: HeatMode; simulated: boolean }) {
  const labels =
    mode === 'risk'
      ? [...LEVEL_LABELS]
      : ['0', ...THRESHOLDS[mode].map((value) => `${value}`)]
  return (
    <div className="legend">
      <span className="legend__name">
        {mode === 'risk' ? 'Risk level' : `${mode[0].toUpperCase()}${mode.slice(1)} (${UNITS[mode]})`}
      </span>
      <div className="legend__scale">
        <div className="legend__bar" />
        <div className="legend__labels">
          {labels.map((label, i) => (
            <span key={label} style={{ left: `${i * 25}%` }}>
              {label}
            </span>
          ))}
        </div>
      </div>
      {simulated && <span className="legend__sim">Simulated storm</span>}
    </div>
  )
}
