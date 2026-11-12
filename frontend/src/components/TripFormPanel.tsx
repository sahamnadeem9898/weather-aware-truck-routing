import { motion } from 'motion/react'

import type { PlaceInput as PlaceValue, TripForm } from '../types'
import DateTimePicker from './DateTimePicker'
import LoadInput from './LoadInput'
import PlaceInput from './PlaceInput'

interface Props {
  form: TripForm
  loading: boolean
  onChange: (form: TripForm) => void
  onSubmit: (form: TripForm) => void
}

const INTERVALS = [10, 25, 50] as const
const DEMO_TRIPS: { name: string; origin: PlaceValue; destination: PlaceValue }[] = [
  {
    name: 'Dallas → Denver',
    origin: { text: 'Dallas, Texas, US', lat: 32.78306, lon: -96.80667 },
    destination: { text: 'Denver, Colorado, US', lat: 39.73915, lon: -104.9847 },
  },
  {
    name: 'Chicago → Atlanta',
    origin: { text: 'Chicago, Illinois, US', lat: 41.85003, lon: -87.65005 },
    destination: { text: 'Atlanta, Georgia, US', lat: 33.749, lon: -84.38798 },
  },
  {
    name: 'Seattle → Salt Lake City',
    origin: { text: 'Seattle, Washington, US', lat: 47.60621, lon: -122.33207 },
    destination: { text: 'Salt Lake City, Utah, US', lat: 40.76078, lon: -111.89105 },
  },
]

export default function TripFormPanel({ form, loading, onChange, onSubmit }: Props) {
  const set = <K extends keyof TripForm>(key: K, value: TripForm[K]) =>
    onChange({ ...form, [key]: value })

  return (
    <form
      className="trip-form"
      onSubmit={(event) => {
        event.preventDefault()
        onSubmit(form)
      }}
    >
      <div className="places">
        <PlaceInput
          label="Origin"
          kind="origin"
          placeholder="City or address"
          value={form.origin}
          onChange={(value) => set('origin', value)}
        />
        <PlaceInput
          label="Destination"
          kind="destination"
          placeholder="City or address"
          value={form.destination}
          onChange={(value) => set('destination', value)}
        />
        <button
          type="button"
          className="places__swap"
          aria-label="Swap origin and destination"
          onClick={() => onChange({ ...form, origin: form.destination, destination: form.origin })}
        >
          <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden>
            <path
              d="M8 4v15m0 0-3.5-3.5M8 19l3.5-3.5M16 20V5m0 0-3.5 3.5M16 5l3.5 3.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>

      <div className="demo-trips">
        {DEMO_TRIPS.map((trip) => (
          <button
            key={trip.name}
            type="button"
            onClick={() => onChange({ ...form, origin: trip.origin, destination: trip.destination })}
          >
            {trip.name}
          </button>
        ))}
      </div>

      <div className="field">
        <label htmlFor="departure">
          Departure <span>local time at origin</span>
        </label>
        <DateTimePicker
          id="departure"
          value={form.departure}
          onChange={(value) => set('departure', value)}
        />
      </div>

      <div className="field">
        <label htmlFor="load">Load weight</label>
        <LoadInput id="load" value={form.loadLb} onChange={(value) => set('loadLb', value)} />
      </div>

      <div className="field">
        <span className="field__label">
          Weather checkpoint every <span>miles</span>
        </span>
        <div className="segmented" role="radiogroup" aria-label="Checkpoint interval in miles">
          {INTERVALS.map((interval) => (
            <button
              key={interval}
              type="button"
              role="radio"
              aria-checked={form.intervalMi === interval}
              onClick={() => set('intervalMi', interval)}
            >
              {form.intervalMi === interval && (
                <motion.span layoutId="interval-thumb" className="segmented__thumb" />
              )}
              <span>{interval} mi</span>
            </button>
          ))}
        </div>
      </div>

      <label className="drill">
        <input
          type="checkbox"
          checked={form.simulateStorm}
          onChange={(event) => set('simulateStorm', event.target.checked)}
        />
        <span className="drill__switch" aria-hidden />
        <span className="drill__text">
          <strong>Storm drill</strong>
          <span>Add a simulated storm to Route A to see the rules react</span>
        </span>
      </label>

      <button type="submit" className="cta" disabled={loading}>
        {loading ? (
          <>
            <span className="spinner" aria-hidden /> Reading the sky…
          </>
        ) : (
          <>
            Find the safest route
            <svg viewBox="0 0 24 24" width="18" height="18" aria-hidden>
              <path
                d="M5 12h14m0 0-5.5-5.5M19 12l-5.5 5.5"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </>
        )}
      </button>
    </form>
  )
}
