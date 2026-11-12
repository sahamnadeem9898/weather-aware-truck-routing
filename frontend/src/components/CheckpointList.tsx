import { motion } from 'motion/react'
import { memo } from 'react'

import { formatClock, formatDate, zoneAbbreviation } from '../lib/format'
import { levelLabel } from '../lib/risk'
import type { CheckpointRef, Plan, RoutePlan } from '../types'

interface Props {
  plan: Plan
  route: RoutePlan
  onFocus: (ref: CheckpointRef | null) => void
  /** Move the forecast slider to the moment the truck reaches a checkpoint. */
  onJump: (hour: number) => void
}


/** Every checkpoint on the selected route: arrival time, weather and level. */
function CheckpointList({ plan, route, onFocus, onJump }: Props) {
  const zone = zoneAbbreviation(plan.departure, plan.timezone)
  const last = route.checkpoints.length - 1

  return (
    <section className="checkpoints" aria-label={`Checkpoints on route ${route.id}`}>
      <header>
        <h2>
          Route {route.id} checkpoints
          <span>
            every {plan.interval_mi} mi · times in {zone}
          </span>
        </h2>
        <div className="checkpoints__cols" aria-hidden>
          <span>Mile · ETA</span>
          <span>Wind</span>
          <span>Rain</span>
          <span>Snow</span>
        </div>
      </header>
      <ol onMouseLeave={() => onFocus(null)}>
        {route.checkpoints.map((cp, index) => {
          const newDay =
            index === 0 ||
            formatDate(cp.eta, plan.timezone) !== formatDate(route.checkpoints[index - 1].eta, plan.timezone)
          return (
            <motion.li
              key={`${route.id}-${index}`}
              tabIndex={0}
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(index * 0.015, 0.4), duration: 0.25 }}
              onClick={() => onJump(Math.min(cp.elapsed_s / 3600, plan.heatmap.hours))}
              onKeyDown={(event) => {
                if (event.key === 'Enter') onJump(Math.min(cp.elapsed_s / 3600, plan.heatmap.hours))
              }}
              data-level={cp.level}
              onMouseEnter={() => onFocus({ routeId: route.id, index })}
              onFocus={() => onFocus({ routeId: route.id, index })}
              onBlur={() => onFocus(null)}
              title={`${cp.reason} Click to move the forecast to this time.`}
            >
              {newDay && <div className="checkpoints__day">{formatDate(cp.eta, plan.timezone)}</div>}
              <div className="checkpoints__row">
                <span className="checkpoints__dot" aria-label={levelLabel(cp.level)} />
                <span className="checkpoints__where">
                  <strong>
                    {index === 0 ? 'Origin' : index === last ? 'Destination' : `Mile ${Math.round(cp.mile)}`}
                  </strong>
                  <span>{formatClock(cp.eta, plan.timezone)}</span>
                </span>
                <span className="num">{Math.round(cp.wind_mph)}</span>
                <span className="num">{cp.rain_in_hr.toFixed(2)}</span>
                <span className="num">{cp.snow_in_hr.toFixed(1)}</span>
              </div>
              {cp.level > 0 && <p className="checkpoints__reason">{cp.reason}</p>}
            </motion.li>
          )
        })}
      </ol>
    </section>
  )
}

export default memo(CheckpointList)
