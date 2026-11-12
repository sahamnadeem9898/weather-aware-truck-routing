import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'

interface Props {
  id: string
  /** "YYYY-MM-DDTHH:MM" wall-clock time, the same format the API takes */
  value: string
  onChange: (value: string) => void
}

/** Weather forecasts, and so the API, only reach this far ahead. */
const MAX_DAYS_AHEAD = 12
const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa']
const WEEKDAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
] // prettier-ignore
const HOURS = [12, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
const MINUTES = [0, 15, 30, 45]

const pad = (n: number) => String(n).padStart(2, '0')
const dateKey = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
const startOfDay = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate())
const addDays = (d: Date, days: number) => new Date(d.getFullYear(), d.getMonth(), d.getDate() + days)
const monthIndex = (d: Date) => d.getFullYear() * 12 + d.getMonth()

function clockLabel(hours: number, minutes: number): string {
  return `${hours % 12 === 0 ? 12 : hours % 12}:${pad(minutes)} ${hours < 12 ? 'AM' : 'PM'}`
}

/** The weeks of a month as rows of seven cells; null pads the first and last week. */
function monthGrid(year: number, month: number): (Date | null)[] {
  const first = new Date(year, month, 1)
  const days = new Date(year, month + 1, 0).getDate()
  const cells: (Date | null)[] = Array.from({ length: first.getDay() }, () => null)
  for (let day = 1; day <= days; day++) cells.push(new Date(year, month, day))
  while (cells.length % 7 !== 0) cells.push(null)
  return cells
}

/** Departure picker: a month calendar and a tap-to-set clock. */
export default function DateTimePicker({ id, value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)
  const panelId = useId()

  const [datePart, timePart = '08:00'] = value.split('T')
  const [hours, minutes] = timePart.split(':').map(Number)
  const selected = new Date(`${datePart}T00:00`)

  // Selectable range: today through the end of the forecast.
  const [today] = useState(() => startOfDay(new Date()))
  const lastDay = addDays(today, MAX_DAYS_AHEAD)

  // Month on screen, and which way the last change went (for the slide).
  const [view, setView] = useState(() => ({ year: selected.getFullYear(), month: selected.getMonth() }))
  const [direction, setDirection] = useState(1)
  const viewIndex = view.year * 12 + view.month
  const canGoBack = viewIndex > monthIndex(today)
  const canGoForward = viewIndex < monthIndex(lastDay)
  const shiftMonth = (by: number) => {
    const next = new Date(view.year, view.month + by, 1)
    setDirection(by)
    setView({ year: next.getFullYear(), month: next.getMonth() })
  }

  const setDate = (date: Date) => {
    onChange(`${dateKey(date)}T${timePart}`)
    setView({ year: date.getFullYear(), month: date.getMonth() })
  }
  const setTime = (nextHours: number, nextMinutes: number) =>
    onChange(`${datePart}T${pad(nextHours)}:${pad(nextMinutes)}`)

  const isPm = hours >= 12
  const hour12 = hours % 12 === 0 ? 12 : hours % 12
  const to24 = (hour: number, pm: boolean) => (hour % 12) + (pm ? 12 : 0)

  // Each preset is worked out when clicked, so "In 1 hour" is always from now.
  const presets = [
    { label: 'In 1 hour', at: () => new Date(Math.ceil((Date.now() + 3_600_000) / 3_600_000) * 3_600_000) },
    { label: 'Tomorrow 6 AM', at: () => new Date(addDays(today, 1).setHours(6)) },
    { label: 'Tomorrow 6 PM', at: () => new Date(addDays(today, 1).setHours(18)) },
  ]
  const applyPreset = (at: Date) => {
    onChange(`${dateKey(at)}T${pad(at.getHours())}:${pad(at.getMinutes())}`)
    setView({ year: at.getFullYear(), month: at.getMonth() })
  }

  // Close on outside click or Escape.
  useEffect(() => {
    if (!open) return
    const onPointer = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const onKey = (event: KeyboardEvent) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', onPointer)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('pointerdown', onPointer)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const offset = Math.round((selected.getTime() - today.getTime()) / 86_400_000)
  const dayLabel =
    offset === 0
      ? 'Today'
      : offset === 1
        ? 'Tomorrow'
        : `${WEEKDAY_NAMES[selected.getDay()]}, ${MONTHS[selected.getMonth()].slice(0, 3)} ${selected.getDate()}`

  return (
    <div className="dtp" ref={root} data-open={open}>
      <button
        id={id}
        type="button"
        className="dtp__field"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => {
          // Always open on the month of the chosen date.
          setView({ year: selected.getFullYear(), month: selected.getMonth() })
          setOpen((current) => !current)
        }}
      >
        <svg viewBox="0 0 24 24" width="17" height="17" aria-hidden>
          <rect x="3.5" y="5" width="17" height="15.5" rx="3" fill="none" stroke="currentColor" strokeWidth="1.7" />
          <path d="M3.5 10h17M8 3v4M16 3v4" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
        </svg>
        <span className="dtp__day">{dayLabel}</span>
        <span className="dtp__time">{clockLabel(hours, minutes)}</span>
        <svg className="dtp__chevron" viewBox="0 0 24 24" width="16" height="16" aria-hidden>
          <path d="m6 9 6 6 6-6" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            id={panelId}
            className="dtp__panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: 'spring', stiffness: 380, damping: 36 }}
          >
            <div className="dtp__card">
              <div className="dtp__presets">
                {presets.map((preset) => (
                  <button key={preset.label} type="button" onClick={() => applyPreset(preset.at())}>
                    {preset.label}
                  </button>
                ))}
              </div>

              {/* --- Calendar --- */}
              <div className="dtp__month">
                <strong aria-live="polite">
                  {MONTHS[view.month]} <span>{view.year}</span>
                </strong>
                <button type="button" aria-label="Previous month" disabled={!canGoBack} onClick={() => shiftMonth(-1)}>
                  <Chevron direction="left" />
                </button>
                <button type="button" aria-label="Next month" disabled={!canGoForward} onClick={() => shiftMonth(1)}>
                  <Chevron direction="right" />
                </button>
              </div>
              <div className="dtp__weekdays" aria-hidden>
                {WEEKDAYS.map((day) => (
                  <span key={day}>{day}</span>
                ))}
              </div>
              <div className="dtp__grid-clip">
                <AnimatePresence mode="popLayout" initial={false} custom={direction}>
                  <motion.div
                    key={viewIndex}
                    className="dtp__grid"
                    role="grid"
                    aria-label={`${MONTHS[view.month]} ${view.year}`}
                    custom={direction}
                    variants={{
                      enter: (dir: number) => ({ x: dir * 40, opacity: 0 }),
                      center: { x: 0, opacity: 1 },
                      exit: (dir: number) => ({ x: dir * -40, opacity: 0 }),
                    }}
                    initial="enter"
                    animate="center"
                    exit="exit"
                    transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
                  >
                    {monthGrid(view.year, view.month).map((date, i) => {
                      if (!date) return <span key={`pad-${i}`} />
                      const key = dateKey(date)
                      const outOfRange = date < today || date > lastDay
                      return (
                        <button
                          key={key}
                          type="button"
                          role="gridcell"
                          aria-selected={key === datePart}
                          aria-label={`${WEEKDAY_NAMES[date.getDay()]}, ${MONTHS[date.getMonth()]} ${date.getDate()}`}
                          data-today={key === dateKey(today)}
                          disabled={outOfRange}
                          onClick={() => setDate(date)}
                        >
                          {key === datePart && <motion.i layoutId="dtp-selected" className="dtp__thumb" />}
                          <span>{date.getDate()}</span>
                        </button>
                      )
                    })}
                  </motion.div>
                </AnimatePresence>
              </div>
              <p className="dtp__note">Forecasts reach {MAX_DAYS_AHEAD} days ahead, so later dates can’t be planned.</p>

              {/* --- Time --- */}
              <div className="dtp__clock">
                <div className="dtp__clock-head">
                  <span>Time</span>
                  <strong>{clockLabel(hours, minutes)}</strong>
                  <div className="dtp__ampm" role="radiogroup" aria-label="AM or PM">
                    {['AM', 'PM'].map((half) => {
                      const active = (half === 'PM') === isPm
                      return (
                        <button
                          key={half}
                          type="button"
                          role="radio"
                          aria-checked={active}
                          onClick={() => setTime(to24(hour12, half === 'PM'), minutes)}
                        >
                          {active && <motion.i layoutId="dtp-ampm" className="dtp__thumb" />}
                          <span>{half}</span>
                        </button>
                      )
                    })}
                  </div>
                </div>
                <div className="dtp__hours" role="radiogroup" aria-label="Hour">
                  {HOURS.map((hour) => (
                    <button
                      key={hour}
                      type="button"
                      role="radio"
                      aria-checked={hour === hour12}
                      onClick={() => setTime(to24(hour, isPm), minutes)}
                    >
                      {hour === hour12 && <motion.i layoutId="dtp-hour" className="dtp__thumb" />}
                      <span>{hour}</span>
                    </button>
                  ))}
                </div>
                <div className="dtp__minutes" role="radiogroup" aria-label="Minutes">
                  {MINUTES.map((minute) => (
                    <button
                      key={minute}
                      type="button"
                      role="radio"
                      aria-checked={minute === minutes}
                      onClick={() => setTime(hours, minute)}
                    >
                      {minute === minutes && <motion.i layoutId="dtp-minute" className="dtp__thumb" />}
                      <span>:{pad(minute)}</span>
                    </button>
                  ))}
                </div>
              </div>

              <button type="button" className="dtp__done" onClick={() => setOpen(false)}>
                Done
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function Chevron({ direction }: { direction: 'left' | 'right' }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
      <path
        d={direction === 'left' ? 'm14.5 6-6 6 6 6' : 'm9.5 6 6 6-6 6'}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}
