import { motion } from 'motion/react'
import { useEffect, useState } from 'react'

const STEPS = [
  'Locating origin and destination',
  'Requesting truck route options',
  'Dropping checkpoints along each route',
  'Reading the forecast at each arrival time',
  'Scoring risk and ranking routes',
]
const STEP_MS = 1100

/** Radar sweep shown while a plan is being computed. */
export default function LoadingOverlay() {
  const [step, setStep] = useState(0)
  useEffect(() => {
    const timer = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), STEP_MS)
    return () => clearInterval(timer)
  }, [])

  return (
    <motion.div
      className="loading"
      role="status"
      aria-live="polite"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.25 }}
    >
      <div className="radar" aria-hidden>
        <span className="radar__sweep" />
        <span className="radar__ring" />
        <span className="radar__ring" />
        <span className="radar__ring" />
        <span className="radar__core" />
      </div>
      <motion.p key={step} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
        {STEPS[step]}…
      </motion.p>
    </motion.div>
  )
}
