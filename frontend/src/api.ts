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
    let retryAfter = typeof body?.retry_after === 'number' ? body.retry_after : null
    // No JSON body means the host answered, not the app (e.g. mid-restart).
    if (body === null && GATEWAY_ERRORS.has(response.status)) retryAfter = 3
    throw new ApiError(body?.code ?? 'server_error', body?.detail ?? fallback, retryAfter)
  }
  return body as T
}

const GATEWAY_ERRORS = new Set([502, 503, 504])
// A server-suggested wait up to this long is a brief hiccup: retry once
// without showing an error. Longer waits (rate limits) are left to the caller.
const QUIET_RETRY_MAX_SECONDS = 10

function wait(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      window.clearTimeout(timer)
      reject(new DOMException('Aborted', 'AbortError'))
    }
    const timer = window.setTimeout(() => {
      signal?.removeEventListener('abort', abort)
      resolve()
    }, ms)
    if (signal?.aborted) abort()
    else signal?.addEventListener('abort', abort, { once: true })
  })
}

export async function planTrip(form: TripForm, signal?: AbortSignal): Promise<Plan> {
  try {
    return await requestPlan(form, signal)
  } catch (error) {
    const seconds = error instanceof ApiError ? error.retryAfter : null
    if (seconds === null || seconds > QUIET_RETRY_MAX_SECONDS) throw error
    await wait(seconds * 1000, signal)
    return requestPlan(form, signal)
  }
}

function requestPlan(form: TripForm, signal?: AbortSignal): Promise<Plan> {
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
