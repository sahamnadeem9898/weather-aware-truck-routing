import { motion } from 'motion/react'

import { LEVEL_LABELS } from '../lib/risk'

const ROWS = [
  { name: 'Wind (mph)', bands: ['< 25', '25 – 34', '35 – 44', '45 – 54', '≥ 55'] },
  { name: 'Rain (in/hr)', bands: ['< 0.10', '0.10 – 0.25', '0.25 – 0.50', '0.50 – 1.00', '> 1.00'] },
  { name: 'Snow (in/hr)', bands: ['< 0.5', '0.5 – 1.0', '1.0 – 2.0', '2.0 – 3.0', '> 3.0'] },
]

/** The scoring rules, so a driver can see exactly how a level was reached. */
export default function RulesCard({ onClose }: { onClose: () => void }) {
  return (
    <motion.div
      className="rules-backdrop"
      onClick={onClose}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        className="rules glass"
        role="dialog"
        aria-modal="true"
        aria-label="How risk is scored"
        onClick={(event) => event.stopPropagation()}
        initial={{ opacity: 0, y: 24, scale: 0.96 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 16, scale: 0.97 }}
        transition={{ type: 'spring', stiffness: 300, damping: 28 }}
      >
        <header>
          <h2>How risk is scored</h2>
          <button type="button" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>

        <table>
          <thead>
            <tr>
              <th />
              {LEVEL_LABELS.map((label, level) => (
                <th key={label} data-level={level}>
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => (
              <tr key={row.name}>
                <th>{row.name}</th>
                {row.bands.map((band) => (
                  <td key={band}>{band}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>

        <div className="rules__grid">
          <section>
            <h3>Load rules</h3>
            <ul>
              <li>Wind ≥ 55 mph: No Travel for any load</li>
              <li>Wind 45 – 54 mph and load over 30,000 lb: No Travel</li>
              <li>Wind 35 – 44 mph and load over 40,000 lb: Severe</li>
            </ul>
          </section>
          <section>
            <h3>Ranking, in order</h3>
            <ol>
              <li>Fewest Severe miles (No Travel miles count first)</li>
              <li>Fewest High miles</li>
              <li>Lowest average risk</li>
              <li>Shortest travel time</li>
            </ol>
          </section>
        </div>
        <p className="rules__note">
          Weather is read at each checkpoint for the hour the truck arrives there, not the departure
          hour. A checkpoint takes the worst of its wind, rain and snow levels, and the miles between
          two checkpoints take the worse of the two.
        </p>
      </motion.div>
    </motion.div>
  )
}
