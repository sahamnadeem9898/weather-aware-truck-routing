import { AnimatePresence, motion } from 'motion/react'

interface Props {
  id: string
  value: number
  onChange: (value: number) => void
}

const TRACK_MAX = 80_000 // US federal gross weight limit; heavier loads can be typed
const INPUT_MAX = 200_000
const STEP = 1_000

/** The brief's two load thresholds split the scale into three zones. */
const ZONES = [
  { upTo: 30_000, name: 'Standard', rule: 'Only the standard wind bands apply.' },
  { upTo: 40_000, name: 'Heavy', rule: 'Wind of 45 mph or more means No Travel.' },
  { upTo: TRACK_MAX, name: 'Very heavy', rule: '35+ mph wind is Severe; 45+ mph is No Travel.' },
]
const MARKS = [0, 30_000, 40_000, TRACK_MAX]

const clamp = (value: number) => Math.min(Math.max(Math.round(value), 0), INPUT_MAX)
const percent = (value: number) => (Math.min(value, TRACK_MAX) / TRACK_MAX) * 100

/** Load weight: a typed value with steppers, on a scale that shows the rule zones. */
export default function LoadInput({ id, value, onChange }: Props) {
  const zoneIndex = value > 40_000 ? 2 : value > 30_000 ? 1 : 0
  const zone = ZONES[zoneIndex]

  return (
    <div className="load">
      <div className="load__readout">
        <button
          type="button"
          aria-label={`Decrease load by ${STEP.toLocaleString('en-US')} lb`}
          disabled={value <= 0}
          onClick={() => onChange(clamp(value - STEP))}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <path d="M6 12h12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
          </svg>
        </button>
        <label className="load__value" htmlFor={id}>
          <input
            id={id}
            type="text"
            inputMode="numeric"
            autoComplete="off"
            value={value.toLocaleString('en-US')}
            // Width follows the number so "lb" sits right next to it.
            style={{ width: `${value.toLocaleString('en-US').length}ch` }}
            onChange={(event) => onChange(clamp(Number(event.target.value.replace(/\D/g, '')) || 0))}
            onKeyDown={(event) => {
              if (event.key === 'ArrowUp') onChange(clamp(value + STEP))
              if (event.key === 'ArrowDown') onChange(clamp(value - STEP))
            }}
          />
          <span>lb</span>
        </label>
        <button
          type="button"
          aria-label={`Increase load by ${STEP.toLocaleString('en-US')} lb`}
          disabled={value >= INPUT_MAX}
          onClick={() => onChange(clamp(value + STEP))}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <path d="M6 12h12M12 6v12" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
          </svg>
        </button>
      </div>

      <div className="load__scale">
        <div className="load__zones" aria-hidden>
          {ZONES.map((item, i) => {
            const from = i === 0 ? 0 : ZONES[i - 1].upTo
            const filled = Math.min(Math.max((value - from) / (item.upTo - from), 0), 1)
            return (
              <span key={item.name} data-active={i === zoneIndex} style={{ flexGrow: item.upTo - from }}>
                <i style={{ width: `${filled * 100}%` }} />
              </span>
            )
          })}
        </div>
        <input
          type="range"
          className="load__range"
          min={0}
          max={TRACK_MAX}
          step={500}
          value={Math.min(value, TRACK_MAX)}
          aria-label="Load weight"
          aria-valuetext={`${value.toLocaleString('en-US')} pounds, ${zone.name}`}
          onChange={(event) => onChange(Number(event.target.value))}
        />
        <div className="load__marks" aria-hidden>
          {MARKS.map((mark) => (
            <span key={mark} style={{ left: `${percent(mark)}%` }}>
              {mark === 0 ? '0' : `${mark / 1000}k`}
            </span>
          ))}
        </div>
      </div>

      <div className="load__rule">
        <AnimatePresence mode="wait" initial={false}>
          <motion.p
            key={zone.name}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
          >
            <b>{zone.name}.</b> {zone.rule}
          </motion.p>
        </AnimatePresence>
      </div>
    </div>
  )
}
