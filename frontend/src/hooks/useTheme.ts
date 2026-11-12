import { useCallback, useState } from 'react'

export type Theme = 'light' | 'dark'

const STORAGE_KEY = 'stormline-theme'
const SWITCH_MS = 400

/** The theme index.html already applied to <html> before React started. */
function currentTheme(): Theme {
  return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark'
}

/**
 * Light/dark theme. The choice lives on <html data-theme>, where the CSS
 * tokens and the map (which reads its colours from those tokens) pick it up.
 */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(currentTheme)

  const toggle = useCallback(() => {
    const next: Theme = currentTheme() === 'dark' ? 'light' : 'dark'
    // Set the attribute first so anything reading CSS variables sees the new theme.
    const root = document.documentElement
    root.dataset.theme = next
    // Cross-fade colours for this one change only (see .theme-switching in index.css).
    root.classList.add('theme-switching')
    window.setTimeout(() => root.classList.remove('theme-switching'), SWITCH_MS)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Private browsing: the choice just won't be remembered.
    }
    setTheme(next)
  }, [])

  return [theme, toggle]
}
