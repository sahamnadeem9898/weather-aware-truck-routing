/**
 * Cloudflare Worker that forwards the app's weather and place-search requests
 * to Open-Meteo, and can keep a free Render service awake.
 *
 * Why: Open-Meteo's free tier limits requests per IP address. Hosts such as
 * Render share their outbound IP addresses between many customers, so the
 * quota can be used up by others before this app makes a single request.
 * For requests that come from a Worker, Open-Meteo applies the limit per
 * Cloudflare account instead, which is what its terms of use recommend.
 *
 * Deploy: Cloudflare dashboard -> Workers & Pages -> Create -> "Hello World"
 * Worker -> Edit code -> paste this file -> Deploy. Then set OPEN_METEO_URL
 * and OPEN_METEO_GEOCODING_URL on the server to the Worker's URL.
 *
 * Optional keep-awake: Render's free plan stops a service after 15 minutes
 * without traffic, and the next visitor waits about a minute for it to start.
 * Give the Worker a variable KEEP_WARM_URL (e.g.
 * https://<app>.onrender.com/api/health/) and a cron trigger that runs every
 * 10 minutes, and it will ping the app on that schedule.
 */

// Only these two endpoints are forwarded; everything else gets a 404.
const UPSTREAM = {
  '/v1/forecast': 'https://api.open-meteo.com',
  '/v1/search': 'https://geocoding-api.open-meteo.com',
}

// Open-Meteo answers in about a second. A dropped connection or a 5xx is
// usually gone a moment later, so each request gets one more try.
const ATTEMPTS = 2
const RETRY_PAUSE_MS = 300

export default {
  async fetch(request) {
    const url = new URL(request.url)
    const origin = UPSTREAM[url.pathname]
    if (request.method !== 'GET' || !origin) {
      return new Response('Not found', { status: 404 })
    }
    const target = origin + url.pathname + url.search
    const headers = { 'User-Agent': request.headers.get('User-Agent') ?? 'stormline-worker' }

    for (let attempt = 1; ; attempt++) {
      try {
        const response = await fetch(target, { headers })
        if (response.status < 500 || attempt === ATTEMPTS) return response
      } catch {
        if (attempt === ATTEMPTS) {
          return Response.json({ error: true, reason: 'Upstream unreachable' }, { status: 502 })
        }
      }
      await new Promise((resolve) => setTimeout(resolve, RETRY_PAUSE_MS))
    }
  },

  async scheduled(_event, env, ctx) {
    if (env.KEEP_WARM_URL) {
      ctx.waitUntil(fetch(env.KEEP_WARM_URL, { headers: { 'User-Agent': 'stormline-keep-warm' } }))
    }
  },
}
