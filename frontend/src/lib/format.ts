export function formatDuration(seconds: number): string {
  const minutes = Math.round(seconds / 60)
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return h > 0 ? `${h} h ${String(m).padStart(2, '0')} min` : `${m} min`
}

export const formatMiles = (miles: number): string =>
  `${Math.round(miles).toLocaleString('en-US')} mi`

export const formatLoad = (lb: number): string => `${lb.toLocaleString('en-US')} lb`

const formatters = new Map<string, Intl.DateTimeFormat>()

function formatter(timeZone: string, options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  const key = timeZone + JSON.stringify(options)
  let fmt = formatters.get(key)
  if (!fmt) {
    fmt = new Intl.DateTimeFormat('en-US', { timeZone, ...options })
    formatters.set(key, fmt)
  }
  return fmt
}

/** "Fri 2:10 PM" in the trip's timezone. */
export function formatDayTime(when: Date | string, timeZone: string): string {
  return formatter(timeZone, { weekday: 'short', hour: 'numeric', minute: '2-digit' }).format(
    new Date(when),
  )
}

/** "Fri, Nov 13" in the trip's timezone. */
export function formatDate(when: Date | string, timeZone: string): string {
  return formatter(timeZone, { weekday: 'short', month: 'short', day: 'numeric' }).format(
    new Date(when),
  )
}

/** "2:10 PM" in the trip's timezone. */
export function formatClock(when: Date | string, timeZone: string): string {
  return formatter(timeZone, { hour: 'numeric', minute: '2-digit' }).format(new Date(when))
}

/** Short zone name such as "CST". */
export function zoneAbbreviation(when: Date | string, timeZone: string): string {
  const parts = formatter(timeZone, { hour: 'numeric', timeZoneName: 'short' }).formatToParts(
    new Date(when),
  )
  return parts.find((part) => part.type === 'timeZoneName')?.value ?? ''
}

/** Default departure ("YYYY-MM-DDTHH:MM"): the next full hour on the user's clock. */
export function nextHourLocal(): string {
  const d = new Date(Date.now() + 60 * 60 * 1000)
  d.setMinutes(0, 0, 0)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}
