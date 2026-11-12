import { AnimatePresence, motion } from 'motion/react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { ApiError, planTrip } from './api'
import CheckpointList from './components/CheckpointList'
import LoadingOverlay from './components/LoadingOverlay'
import MapView from './components/MapView'
import Recommendation from './components/Recommendation'
import RouteCard from './components/RouteCard'
import RulesCard from './components/RulesCard'
import TimelineDock from './components/TimelineDock'
import TripFormPanel from './components/TripFormPanel'
import { useMediaQuery } from './hooks/useMediaQuery'
import { useTheme } from './hooks/useTheme'
import { formatDayTime, formatLoad, nextHourLocal, zoneAbbreviation } from './lib/format'
import type { CheckpointRef, HeatMode, Plan, TripForm } from './types'

const INITIAL_FORM: TripForm = {
  origin: { text: '' },
  destination: { text: '' },
  departure: nextHourLocal(),
  loadLb: 42_000,
  intervalMi: 25,
  simulateStorm: false,
}

export default function App() {
  const [form, setForm] = useState<TripForm>(INITIAL_FORM)
  const [plan, setPlan] = useState<Plan | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [editing, setEditing] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hour, setHour] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [mode, setMode] = useState<HeatMode>('risk')
  const [focus, setFocus] = useState<CheckpointRef | null>(null)
  const [hoverId, setHoverId] = useState<string | null>(null)
  const [showRules, setShowRules] = useState(false)
  const [theme, toggleTheme] = useTheme()

  const wide = useMediaQuery('(min-width: 1180px)')
  const compact = useMediaQuery('(max-width: 820px)')
  const request = useRef<AbortController | null>(null)

  // When the free weather API asks us to wait, count down and retry once.
  const [retryIn, setRetryIn] = useState<number | null>(null)
  const lastRequest = useRef<TripForm | null>(null)
  const errorBox = useRef<HTMLDivElement>(null)

  // The error sits under the form. Once it has opened, scroll the form, and
  // only the form, so it can't be missed. (scrollIntoView would also scroll
  // the panel itself and push its header out of view.)
  const revealError = useCallback(() => {
    const box = errorBox.current
    const scroller = box?.closest<HTMLElement>('.panel__scroll')
    if (!box || !scroller) return
    const hidden = box.getBoundingClientRect().bottom - scroller.getBoundingClientRect().bottom
    if (hidden > 0) scroller.scrollBy({ top: hidden + 16, behavior: 'smooth' })
  }, [])

  const submit = useCallback(async (values: TripForm, isAutoRetry = false) => {
    request.current?.abort()
    const controller = new AbortController()
    request.current = controller
    lastRequest.current = values
    setLoading(true)
    setError(null)
    setRetryIn(null)
    setPlaying(false)
    try {
      const result = await planTrip(values, controller.signal)
      setPlan(result)
      // With no safe route there is no pick; show the least bad one for inspection.
      const leastBad = result.routes.find((route) => route.rank === 1)
      setSelectedId(result.recommendation.route_id ?? leastBad?.id ?? null)
      setHoverId(null)
      setHour(0)
      setFocus(null)
      setEditing(false)
      // Keep the resolved names and coordinates so re-planning skips geocoding.
      setForm({
        ...values,
        origin: { text: result.origin.label, lat: result.origin.lat, lon: result.origin.lon },
        destination: {
          text: result.destination.label,
          lat: result.destination.lat,
          lon: result.destination.lon,
        },
      })
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.')
      if (err instanceof ApiError && err.retryAfter && !isAutoRetry) setRetryIn(err.retryAfter)
    } finally {
      if (request.current === controller) setLoading(false)
    }
  }, [])

  useEffect(() => () => request.current?.abort(), [])

  useEffect(() => {
    if (retryIn === null) return
    const timer = window.setTimeout(() => {
      if (retryIn > 1) setRetryIn(retryIn - 1)
      else if (lastRequest.current) void submit(lastRequest.current, true)
    }, 1000)
    return () => window.clearTimeout(timer)
  }, [retryIn, submit])

  // Re-plan the same trip leaving later (the "wait" actions on closed routes).
  const formRef = useRef(form)
  useEffect(() => {
    formRef.current = form
  }, [form])
  const stormAnchor = useRef<string | null>(null)
  useEffect(() => {
    stormAnchor.current = plan?.storm_anchor ?? null
  }, [plan])
  const delayDeparture = useCallback(
    (departureLocal: string) =>
      // Keep a simulated storm where it is: only the truck leaves later.
      submit({ ...formRef.current, departure: departureLocal, stormAnchor: stormAnchor.current }),
    [submit],
  )
  // A plan submitted from the form is a fresh trip, with a fresh storm drill.
  const submitForm = useCallback(
    (values: TripForm) => submit({ ...values, stormAnchor: null }),
    [submit],
  )

  const jumpToHour = useCallback((value: number) => {
    setPlaying(false)
    setHour(value)
  }, [])

  useEffect(() => {
    if (!showRules) return
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setShowRules(false)
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [showRules])

  const selected = plan?.routes.find((route) => route.id === selectedId) ?? null
  const ranked = useMemo(
    () => (plan ? [...plan.routes].sort((a, b) => a.rank - b.rank) : []),
    [plan],
  )

  // Space the floating panels take, so the map frames routes in what's left.
  const padding = useMemo(
    () =>
      compact
        ? { top: 150, bottom: Math.round(window.innerHeight * 0.5) + 30, left: 40, right: 40 }
        : { top: 70, bottom: 230, left: 470, right: wide ? 410 : 60 },
    [compact, wide],
  )

  return (
    <div className="app" data-has-plan={plan !== null}>
      <MapView
        plan={plan}
        selectedId={selectedId}
        hoverId={hoverId}
        hour={hour}
        mode={mode}
        focus={focus}
        padding={padding}
        theme={theme}
        onSelect={setSelectedId}
      />
      <div className="vignette" aria-hidden />

      <AnimatePresence>
        {!plan && !loading && !compact && (
          <motion.div
            key="hero"
            className="hero"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.6, delay: 0.2 }}
          >
            <h2>
              Know the weather <span>before the road does.</span>
            </h2>
            <ul>
              <li>
                Up to <b>3</b> truck routes
              </li>
              <li>
                <b>ETA</b> matched forecasts
              </li>
              <li>
                <b>48 h</b> corridor heatmap
              </li>
            </ul>
          </motion.div>
        )}
      </AnimatePresence>

      <aside className="panel glass">
        <header className="brand">
          <svg className="brand__mark" viewBox="0 0 32 32" width="34" height="34" aria-hidden>
            <rect width="32" height="32" rx="9" />
            <path d="M7 23c5 0 5-6 9-6s4-8 9-8" fill="none" strokeWidth="2.6" strokeLinecap="round" />
            <circle cx="7" cy="23" r="2.4" />
            <circle cx="25" cy="9" r="2.4" />
          </svg>
          <div>
            <h1>Stormline</h1>
            <p>Weather-aware truck routing</p>
          </div>
          <div className="brand__actions">
            <button type="button" className="ghost" onClick={() => setShowRules(true)}>
              Rules
            </button>
            <button
              type="button"
              className="ghost ghost--icon"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
              title={theme === 'dark' ? 'Light mode' : 'Dark mode'}
            >
              <AnimatePresence mode="popLayout" initial={false}>
                <motion.svg
                  key={theme}
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  aria-hidden
                  initial={{ rotate: -90, scale: 0.3, opacity: 0 }}
                  animate={{ rotate: 0, scale: 1, opacity: 1 }}
                  exit={{ rotate: 90, scale: 0.3, opacity: 0 }}
                  transition={{ type: 'spring', stiffness: 300, damping: 20 }}
                >
                  {theme === 'dark' ? (
                    <g fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                      <circle cx="12" cy="12" r="4" />
                      <path d="M12 2.5v2.2M12 19.3v2.2M2.5 12h2.2M19.3 12h2.2M5.3 5.3l1.5 1.5M17.2 17.2l1.5 1.5M5.3 18.7l1.5-1.5M17.2 6.8l1.5-1.5" />
                    </g>
                  ) : (
                    <path
                      d="M20 14.2A8.2 8.2 0 0 1 9.8 4a8.2 8.2 0 1 0 10.2 10.2Z"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.8"
                      strokeLinejoin="round"
                    />
                  )}
                </motion.svg>
              </AnimatePresence>
            </button>
          </div>
        </header>

        <div className="panel__scroll">
          <AnimatePresence mode="popLayout" initial={false}>
            {editing || !plan ? (
              <motion.div
                key="form"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
              >
                {!plan && (
                  <p className="intro">
                    Three routes, scored by the wind, rain and snow your truck will meet at the hour
                    it gets there.
                  </p>
                )}
                <TripFormPanel form={form} loading={loading} onChange={setForm} onSubmit={submitForm} />
              </motion.div>
            ) : (
              <motion.button
                key="summary"
                type="button"
                className="trip-summary"
                onClick={() => setEditing(true)}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                transition={{ duration: 0.2 }}
              >
                <span className="trip-summary__route">
                  <strong>{plan.origin.label.split(',')[0]}</strong>
                  <i aria-hidden>→</i>
                  <strong>{plan.destination.label.split(',')[0]}</strong>
                </span>
                <span className="trip-summary__meta">
                  {formatDayTime(plan.departure, plan.timezone)}{' '}
                  {zoneAbbreviation(plan.departure, plan.timezone)} · {formatLoad(plan.load_lb)} ·
                  every {plan.interval_mi} mi
                </span>
                <span className="trip-summary__edit">Edit</span>
              </motion.button>
            )}
          </AnimatePresence>

          <AnimatePresence>
            {error && (
              <motion.div
                ref={errorBox}
                className="error"
                role="alert"
                initial={{ opacity: 0, height: 0 }}
                // A short shake draws the eye without a modal.
                animate={{ opacity: 1, height: 'auto', x: [0, -6, 6, -4, 4, 0] }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ x: { duration: 0.4, delay: 0.1 } }}
                onAnimationComplete={revealError}
              >
                <div>
                  <strong>Couldn’t plan that trip</strong>
                  <span>{error}</span>
                  {retryIn !== null && (
                    <span className="error__retry">
                      Trying again automatically in {retryIn} s.{' '}
                      <button type="button" onClick={() => setRetryIn(null)}>
                        Cancel
                      </button>
                    </span>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>

          {plan && (
            <div className="results" key={plan.departure + plan.load_lb + plan.interval_mi + plan.simulated}>
              {plan.simulated && (
                <p className="sim-banner">
                  Storm drill on: a simulated storm is added to the real forecast.
                </p>
              )}
              <Recommendation plan={plan} loading={loading} onDelay={delayDeparture} />
              {ranked.map((route, index) => (
                <RouteCard
                  key={route.id}
                  route={route}
                  index={index}
                  timezone={plan.timezone}
                  recommended={route.id === plan.recommendation.route_id}
                  selected={route.id === selectedId}
                  loading={loading}
                  onSelect={setSelectedId}
                  onHover={setHoverId}
                  onDelay={delayDeparture}
                />
              ))}
              {!wide && selected && <CheckpointList plan={plan} route={selected} onFocus={setFocus} onJump={jumpToHour} />}
              <p className="footnote">
                Routes: {plan.routing_provider === 'valhalla-truck' ? 'Valhalla truck profile' : 'OSRM, truck speed cap'} ·
                Weather: Open-Meteo · Wind uses {plan.wind_field === 'gust' ? 'gusts' : 'sustained speed'}
              </p>
            </div>
          )}
        </div>
      </aside>

      <AnimatePresence>
        {plan && wide && selected && (
          <motion.aside
            key="checkpoints"
            className="panel panel--right glass"
            initial={{ opacity: 0, x: 40 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: 40 }}
            transition={{ type: 'spring', stiffness: 240, damping: 28, delay: 0.3 }}
          >
            <CheckpointList plan={plan} route={selected} onFocus={setFocus} onJump={jumpToHour} />
          </motion.aside>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {plan && (
          <TimelineDock
            key="dock"
            plan={plan}
            hour={hour}
            playing={playing}
            mode={mode}
            selectedId={selectedId}
            onHour={setHour}
            onPlaying={setPlaying}
            onMode={setMode}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>{loading && <LoadingOverlay key="loading" />}</AnimatePresence>
      <AnimatePresence>
        {showRules && <RulesCard key="rules" onClose={() => setShowRules(false)} />}
      </AnimatePresence>
    </div>
  )
}
