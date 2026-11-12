import { AnimatePresence, motion } from 'motion/react'
import { useEffect, useId, useRef, useState } from 'react'

import { suggestPlaces } from '../api'
import type { Place, PlaceInput as PlaceValue } from '../types'

interface Props {
  label: string
  kind: 'origin' | 'destination'
  placeholder: string
  value: PlaceValue
  onChange: (value: PlaceValue) => void
}

const DEBOUNCE_MS = 220

/** Text field with place suggestions. Free text is allowed: the server geocodes it. */
export default function PlaceInput({ label, kind, placeholder, value, onChange }: Props) {
  const id = useId()
  const [open, setOpen] = useState(false)
  const [results, setResults] = useState<Place[]>([])
  const [active, setActive] = useState(0)
  const typed = useRef(false) // only search after the user types, not on programmatic fills

  useEffect(() => {
    if (!typed.current || value.text.trim().length < 2) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      suggestPlaces(value.text, controller.signal)
        .then((places) => {
          setResults(places)
          setActive(0)
          setOpen(places.length > 0)
        })
        .catch(() => {}) // suggestions are a convenience; typing still works
    }, DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [value.text])

  const pick = (place: Place) => {
    typed.current = false
    onChange({ text: place.label, lat: place.lat, lon: place.lon })
    setOpen(false)
  }

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (!open) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => (i + 1) % results.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => (i - 1 + results.length) % results.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      pick(results[active])
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="place">
      <span className={`place__marker place__marker--${kind}`} aria-hidden />
      <div className="place__field">
        <label htmlFor={id}>{label}</label>
        <input
          id={id}
          type="text"
          autoComplete="off"
          spellCheck={false}
          placeholder={placeholder}
          value={value.text}
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id}-list`}
          aria-autocomplete="list"
          onChange={(event) => {
            typed.current = true
            onChange({ text: event.target.value }) // typing discards picked coordinates
          }}
          onFocus={() => setOpen(typed.current && results.length > 0)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
          required
        />
      </div>
      <AnimatePresence>
        {open && (
          <motion.ul
            id={`${id}-list`}
            role="listbox"
            className="place__list"
            initial={{ opacity: 0, y: -6, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.14 }}
          >
            {results.map((place, i) => {
              const [name, ...rest] = place.label.split(', ')
              return (
                <li
                  key={`${place.lat},${place.lon}`}
                  role="option"
                  aria-selected={i === active}
                  data-active={i === active}
                  // mousedown fires before the input's blur closes the list
                  onMouseDown={(event) => {
                    event.preventDefault()
                    pick(place)
                  }}
                  onMouseEnter={() => setActive(i)}
                >
                  <strong>{name}</strong>
                  <span>{rest.join(', ')}</span>
                </li>
              )
            })}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  )
}
