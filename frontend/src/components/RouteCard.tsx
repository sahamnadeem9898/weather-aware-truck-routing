import { motion } from 'motion/react'
import { memo, useCallback } from 'react'

import { formatDayTime, formatDuration, formatMiles, zoneAbbreviation } from '../lib/format'
import { levelLabel, NO_TRAVEL, riskVar } from '../lib/risk'
import type { RoutePlan } from '../types'
import AnimatedNumber from './AnimatedNumber'

interface Props {
  route: RoutePlan
  timezone: string
  recommended: boolean
  selected: boolean
  loading: boolean
  index: number
  onSelect: (routeId: string) => void
  onHover: (routeId: string | null) => void
  onDelay: (departureLocal: string) => void
}

function RouteCard(props: Props) {
  const { route, timezone, recommended, selected, loading, index, onSelect, onHover, onDelay } = props
  const closed = route.has_no_travel
  const riskyLevels = [4, 3, 2, 1].filter((level) => route.miles_by_level[level] > 0)
  const enterDelay = 0.25 + index * 0.09
  const formatRisk = useCallback((value: number) => value.toFixed(2), [])

  return (
    // A div, not a button: a closed route's card contains its own "Re-plan" button.
    <motion.div
      role="button"
      tabIndex={0}
      className="route-card"
      data-selected={selected}
      data-recommended={recommended}
      data-closed={closed}
      aria-pressed={selected}
      aria-label={`Route ${route.id}${closed ? ', closed: do not travel' : ''}`}
      onClick={() => onSelect(route.id)}
      onKeyDown={(event) => {
        if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault()
          onSelect(route.id)
        }
      }}
      onHoverStart={() => onHover(route.id)}
      onHoverEnd={() => onHover(null)}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: enterDelay, type: 'spring', stiffness: 260, damping: 26 }}
      whileHover={{ y: -2, transition: { type: 'spring', stiffness: 400, damping: 24 } }}
      whileTap={{ scale: 0.985 }}
    >
      {/* One ring shared by all cards, so it glides to whichever is selected. */}
      {selected && (
        <motion.span
          layoutId="route-selection"
          className="route-card__ring"
          transition={{ type: 'spring', stiffness: 380, damping: 32 }}
        />
      )}

      <div className="route-card__head">
        <span className="route-card__letter">{route.id}</span>
        <div className="route-card__title">
          <strong>Route {route.id}</strong>
          <span>
            {recommended && <em className="tag tag--best">Recommended</em>}
            {closed && <em className="tag tag--closed">Do not travel</em>}
            {!closed &&
              route.tags.map((tag) => (
                <em key={tag} className="tag">
                  {tag}
                </em>
              ))}
          </span>
        </div>
        <span className="pill" data-level={route.worst_level}>
          {closed ? 'Closed' : route.worst_level === 0 ? 'All clear' : `Peak ${levelLabel(route.worst_level)}`}
        </span>
      </div>

      <div className="route-card__stats">
        <div>
          <dt>Drive time</dt>
          <dd>{formatDuration(route.duration_s)}</dd>
        </div>
        <div>
          <dt>Distance</dt>
          <dd>
            <AnimatedNumber value={route.distance_mi} format={formatMiles} delay={enterDelay} />
          </dd>
        </div>
        <div>
          <dt>{closed ? 'Would arrive' : 'Arrives'}</dt>
          <dd>{formatDayTime(route.arrival, timezone)}</dd>
        </div>
        <div>
          <dt>Avg risk</dt>
          <dd>
            <AnimatedNumber value={route.avg_risk} format={formatRisk} delay={enterDelay} />
            <small>/ 4</small>
          </dd>
        </div>
      </div>

      {/* Risk along the route, origin on the left, destination on the right. */}
      <div className="ribbon" role="img" aria-label="Risk level along the route">
        {route.segments.map((segment, i) => (
          <motion.span
            key={i}
            title={`Mile ${Math.round(segment.from_mile)}–${Math.round(segment.to_mile)}: ${levelLabel(segment.level)}`}
            style={{
              flexGrow: segment.to_mile - segment.from_mile,
              background: riskVar(segment.level),
            }}
            initial={{ scaleY: 0.2, opacity: 0 }}
            animate={{ scaleY: 1, opacity: 1 }}
            transition={{ delay: enterDelay + 0.2 + (i / route.segments.length) * 0.5, duration: 0.3 }}
          />
        ))}
      </div>

      <div className="route-card__miles">
        {riskyLevels.length === 0 ? (
          <span className="miles miles--clear">Low risk for all {formatMiles(route.distance_mi)}</span>
        ) : (
          riskyLevels.map((level) => (
            <span key={level} className="miles" data-level={level}>
              <i />
              {levelLabel(level)} <b>{formatMiles(route.miles_by_level[level])}</b>
            </span>
          ))
        )}
      </div>

      {closed && <ClosedNotice route={route} timezone={timezone} loading={loading} onDelay={onDelay} />}
    </motion.div>
  )
}

/** Why the route is closed and when it opens, with a one-tap re-plan. */
function ClosedNotice({
  route,
  timezone,
  loading,
  onDelay,
}: Pick<Props, 'route' | 'timezone' | 'loading' | 'onDelay'>) {
  const first = route.checkpoints.find((cp) => cp.level === NO_TRAVEL)
  const zone = zoneAbbreviation(route.arrival, timezone)
  const wait = route.wait
  return (
    <motion.div
      className="closed"
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: 'auto' }}
      transition={{ delay: 0.6, duration: 0.3 }}
    >
      <p>
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden>
          <path d="M10 2.5 18.5 17h-17L10 2.5Z" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
          <path d="M10 8v4.2M10 14.6v.2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
        </svg>
        <span>
          {first && (
            <>
              No Travel conditions from mile {Math.round(first.mile)}, reached{' '}
              {formatDayTime(first.eta, timezone)} {zone}.{' '}
            </>
          )}
          {wait ? `Opens if you leave ${wait.hours} h later.` : 'Stays closed for the next 48 hours.'}
        </span>
      </p>
      {wait && (
        <button
          type="button"
          disabled={loading}
          onClick={(event) => {
            event.stopPropagation()
            onDelay(wait.departure_local)
          }}
        >
          Leave {formatDayTime(wait.departure, timezone)} instead
        </button>
      )}
    </motion.div>
  )
}

export default memo(RouteCard)
