/**
 * Cloudflare Worker that forwards the app's weather and place-search requests
 * to Open-Meteo.
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
 */

// Only these two endpoints are forwarded; everything else gets a 404.
const UPSTREAM = {
  '/v1/forecast': 'https://api.open-meteo.com',
  '/v1/search': 'https://geocoding-api.open-meteo.com',
}

// Successful responses are cached at the edge for 15 minutes, so repeated
// identical requests cost no quota. Errors are never cached.
const CACHE_SECONDS = 15 * 60

export default {
  async fetch(request) {
    const url = new URL(request.url)
    const origin = UPSTREAM[url.pathname]
    if (request.method !== 'GET' || !origin) {
      return new Response('Not found', { status: 404 })
    }
    return fetch(origin + url.pathname + url.search, {
      headers: { 'User-Agent': request.headers.get('User-Agent') ?? 'stormline-worker' },
      cf: { cacheEverything: true, cacheTtlByStatus: { '200-299': CACHE_SECONDS, '300-599': 0 } },
    })
  },
}
