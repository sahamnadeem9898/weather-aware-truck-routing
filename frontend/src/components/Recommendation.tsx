import { motion } from 'motion/react'

import { formatDayTime, zoneAbbreviation } from '../lib/format'
import type { Plan } from '../types'

interface Props {
  plan: Plan
  loading: boolean
  onDelay: (departureLocal: string) => void
}

/** The pick and the rule that decided it, or a stop sign when nothing is drivable. */
export default function Recommendation({ plan, loading, onDelay }: Props) {
  const { route_id, reasons, no_safe_route, wait } = plan.recommendation
  const routes = plan.routes.length

  if (no_safe_route) {
    const zone = zoneAbbreviation(plan.departure, plan.timezone)
    return (
      <motion.div
        className="verdict verdict--stop"
        role="alert"
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.1 }}
      >
        <StopIcon />
        <span className="verdict__eyebrow">Do not depart</span>
        <h2>No route is safe to drive</h2>
        <p>
          {routes === 1 ? 'The only route crosses' : `All ${routes} routes cross`} No Travel
          conditions at the time the truck would be there.
          {wait
            ? ` Route ${wait.route_id} is the first to open.`
            : ' None of them opens in the next 48 hours.'}
        </p>
        {wait && (
          <motion.button
            type="button"
            className="verdict__action"
            disabled={loading}
            onClick={() => onDelay(wait.departure_local)}
            whileTap={{ scale: 0.97 }}
          >
            <span>
              Wait {wait.hours} h
              <small>
                leave {formatDayTime(wait.departure, plan.timezone)} {zone}
              </small>
            </span>
            <b>Re-plan</b>
          </motion.button>
        )}
      </motion.div>
    )
  }

  return (
    <motion.div
      className="verdict"
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: 'spring', stiffness: 260, damping: 24, delay: 0.1 }}
    >
      <CheckIcon />
      <span className="verdict__eyebrow">Recommended</span>
      <h2>Take Route {route_id}</h2>
      <ul>
        {reasons.map((reason, i) => (
          <motion.li
            key={reason}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: 0.45 + i * 0.1 }}
          >
            {reason}
          </motion.li>
        ))}
      </ul>
    </motion.div>
  )
}

/** Tick that draws itself. */
function CheckIcon() {
  return (
    <svg className="verdict__icon" viewBox="0 0 28 28" width="28" height="28" aria-hidden>
      <motion.circle
        cx="14"
        cy="14"
        r="12"
        fill="none"
        strokeWidth="2"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.5, delay: 0.25 }}
      />
      <motion.path
        d="M8.5 14.5l3.8 3.8 7.2-8"
        fill="none"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0 }}
        animate={{ pathLength: 1 }}
        transition={{ duration: 0.35, delay: 0.65 }}
      />
    </svg>
  )
}

function StopIcon() {
  return (
    <motion.svg
      className="verdict__icon"
      viewBox="0 0 28 28"
      width="28"
      height="28"
      aria-hidden
      initial={{ rotate: -20, scale: 0.6 }}
      animate={{ rotate: 0, scale: 1 }}
      transition={{ type: 'spring', stiffness: 320, damping: 12, delay: 0.25 }}
    >
      <circle cx="14" cy="14" r="12" fill="none" strokeWidth="2" />
      <path d="M8 14h12" fill="none" strokeWidth="2.8" strokeLinecap="round" />
    </motion.svg>
  )
}
