import { animate } from 'motion'
import { useEffect, useRef } from 'react'

interface Props {
  value: number
  format: (value: number) => string
  delay?: number
}

/** A number that counts up to its value, and glides when the value changes. */
export default function AnimatedNumber({ value, format, delay = 0 }: Props) {
  const node = useRef<HTMLSpanElement>(null)
  const shown = useRef(0)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      shown.current = value
      if (node.current) node.current.textContent = format(value)
      return
    }
    const controls = animate(shown.current, value, {
      duration: 0.9,
      delay,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (latest) => {
        shown.current = latest
        if (node.current) node.current.textContent = format(latest)
      },
    })
    return () => controls.stop()
  }, [value, format, delay])

  // Rendered once at zero; the effect then owns the text, so parent re-renders
  // never interrupt the count.
  return <span ref={node}>{format(0)}</span>
}
