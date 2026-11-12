import type { Place, Plan, TripForm } from './types'

export class ApiError extends Error {
  code: string
  /** Seconds to wait before retrying, when the server says waiting will help. */
  retryAfter: number | null

  constructor(code: string, message: string, retryAfter: number | null = null) {
    super(message)
    this.code = code
    this.retryAfter = retryAfter
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, init)
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError('network', 'Could not reach the server. Check your connection and try again.')
  }
  const body = await response.json().catch(() => null)
  if (!response.ok) {
    const fallback =
      response.status === 429
        ? 'Too many requests. Wait a moment and try again.'
        : 'Something went wrong on the server. Try again.'
    const retryAfter = typeof body?.retry_after === 'number' ? body.retry_after : null
    throw new ApiError(body?.code ?? 'server_error', body?.detail ?? fallback, retryAfter)
  }
  return body as T
}

export function planTrip(form: TripForm, signal?: AbortSignal): Promise<Plan> {
  return request<Plan>('/api/plan/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    signal,
    body: JSON.stringify({
      origin: form.origin,
      destination: form.destination,
      departure: form.departure,
      load_lb: form.loadLb,
      interval_mi: form.intervalMi,
      simulate_storm: form.simulateStorm,
      storm_anchor: form.stormAnchor ?? null,
    }),
  })
}

export async function suggestPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const data = await request<{ results: Place[] }>(
    `/api/geocode/?q=${encodeURIComponent(query)}`,
    { signal },
  )
  return data.results
}
