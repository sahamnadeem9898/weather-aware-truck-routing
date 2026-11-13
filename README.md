# Stormline · Weather-aware truck routing

A React + Django app that helps a truck driver pick the safest of three routes,
based on the wind, rain and snow the truck will meet **at the hour it reaches
each point**, the load weight, and travel time.

- **Live app:** https://stormline-z3hi.onrender.com (free tier: the first visit after a quiet spell takes about a minute to wake up)
- **Walkthrough:** _add the Loom link here_

## What it does

1. The driver enters origin, destination, departure date and time, and load
   weight.
2. The API gets **3 route options** from a truck routing engine.
3. It drops a **checkpoint every 10, 25 or 50 miles** on each route and works
   out the truck's **arrival time** at each one.
4. It reads the forecast for each checkpoint **at that arrival time** and
   classifies it with the risk and load rules below.
5. It **ranks the routes** and explains the pick in one sentence per rival.
   A route with any No Travel miles is **closed**: it is never recommended,
   and the app says how many hours to wait before it opens, with a one-tap
   re-plan for that later departure.
6. The map shows all routes coloured by risk, every checkpoint (hover for ETA,
   wind, rain, snow, level and reason), route summaries, and a **weather
   heatmap of the trip corridor with a 0–48 hour slider**. Moving the slider
   also moves a truck along the selected route to where it would be at that
   hour; on a closed route the truck stops before the No Travel stretch.

No API keys or configuration are needed. Optional settings are listed in
[`.env.example`](.env.example). The app has a light and a dark theme; it follows
the system setting until the toggle in the header is used.

## Run it locally

Needs Python 3.12+, Node 22+ and `make`.

```bash
make install     # backend virtualenv + frontend packages
make serve       # builds the frontend, serves everything on http://localhost:8000
make test        # backend test suite (no network needed)
```

For development with hot reload, run `make dev-api` and `make dev-web` in two
terminals and open http://localhost:5173. `make lint` runs ruff, oxlint and
the TypeScript compiler.

## Deploy to Render

The repo ships a `Dockerfile` and a `render.yaml` blueprint: one web service
runs both the API and the built frontend, so there is a single URL and no CORS
setup.

1. Push the repo to GitHub.
2. In Render: **New → Blueprint**, pick the repo, **Apply**.
3. Set up the weather proxy below, then open the service URL.

### Weather proxy (needed on Render)

Open-Meteo's free tier is limited per IP address, and Render shares its
outbound IP addresses between many customers, so other people's apps can use
up the quota first (Open-Meteo's terms warn about exactly this for Render,
Vercel and Netlify). Requests that come through a Cloudflare Worker are limited
per Cloudflare account instead, which is the fix Open-Meteo recommends.

1. In a free Cloudflare account: **Workers & Pages → Create → Hello World**,
   then **Edit code**, paste [`deploy/open-meteo-worker.js`](deploy/open-meteo-worker.js)
   and **Deploy**.
2. In the Render service's **Environment**, set both `OPEN_METEO_URL` and
   `OPEN_METEO_GEOCODING_URL` to the Worker's URL (for example
   `https://open-meteo-proxy.<account>.workers.dev`).

The Worker forwards only the forecast and place-search endpoints and gives a
failed upstream call one more try. If the Worker itself has trouble, the server
falls back to calling Open-Meteo directly (see below). Locally, no proxy is
needed.

**Keeping the free instance awake (optional).** Render's free plan stops a
service after 15 minutes without traffic, and the next visitor waits about a
minute while it starts again. The same Worker can prevent that: in its
**Settings**, add a variable `KEEP_WARM_URL` set to
`https://<your-service>.onrender.com/api/health/`, and a **Cron Trigger** that
runs every 10 minutes. An always-on free service uses about 730 of the 750
free instance hours Render gives each workspace per month, so do this only for
one free service.

### Running on Render's free tier

The free instance has 512 MB of memory and a fraction of a CPU, sleeps after
15 idle minutes, and shares its outbound IP address with other services. The
app is set up for that:

- **Memory.** One gunicorn worker with 4 threads. Route geometry (1–4 MB per
  trip) lives in its own cache capped at 24 trips; forecasts are cached per
  0.1° cell and day.
- **CPU.** A new 800-mile trip needs about half a second of CPU; re-planning
  the same trip (another load or checkpoint interval) comes from cache.
- **Weather quota.** Open-Meteo's free tier counts every location as a call
  (600 a minute, 5,000 an hour, 10,000 a day) and a plan uses 150–500. The
  weather proxy above keeps that quota to this app alone. Each batch is cached
  as soon as it arrives, so a retry only asks for what is missing. If the
  per-minute limit is hit, the UI counts down and retries once on its own.
- **Flaky networks.** Every Open-Meteo call has a 5-second connect timeout.
  A dropped connection or a 5xx from the Worker is retried against Open-Meteo
  directly, and the Worker is then tried last for two minutes, so one bad path
  never stalls a plan. If both paths fail, the API returns `retry_after: 5` and
  the app retries once without showing an error. Rate limits (429) are never
  routed around.
- **Abuse.** At most 12 plans a minute per client and 30 a minute overall.
- **Health check.** `/api/health/` answers before host validation, so Render's
  internal health checks pass.
- **Cold start.** After a sleep, the first request takes about a minute,
  unless the Worker's keep-awake ping above is on.

## Architecture

```
React (Vite, TypeScript, MapLibre GL)          Django + DRF
┌──────────────────────────────┐   POST    ┌──────────────────────────────────┐
│ form: places, time, load     │ /api/plan │ geocoding.py   text -> lat/lon   │ -> Open-Meteo geocoder, Nominatim
│ map: routes, checkpoints,    │ ────────► │ routing.py     3 distinct routes │ -> Valhalla (truck), OSRM fallback
│      heatmap, truck          │           │ checkpoints.py point every N mi  │
│ route cards + reasons        │ ◄──────── │ weather.py     hourly forecast   │ -> Open-Meteo (batched, cached)
│ 0–48 h slider (no requests)  │  one JSON │ risk.py        level + load rule │
└──────────────────────────────┘           │ recommend.py   ranking + reasons │
                                           │ delay.py       wait until open   │
                                           │ heatmap.py     corridor grid x49 │
                                           │ planner.py     orchestrates      │
                                           └──────────────────────────────────┘
```

All routing, weather and risk logic lives in Django so it is testable in plain
Python; React only collects inputs and draws the answer.

| Endpoint | Purpose |
| --- | --- |
| `POST /api/plan/` | Plan a trip. Body: `origin`, `destination` (`{text, lat?, lon?}`), `departure` (`YYYY-MM-DDTHH:MM`, local time at origin), `load_lb`, `interval_mi` (10, 25 or 50), optional `simulate_storm` and `storm_anchor` (see Storm drill) |
| `GET /api/geocode/?q=` | Place suggestions for the autocomplete |
| `GET /api/health/` | Health check |

Errors always look like `{"code": "...", "detail": "readable message"}`:

| Code | Status | When |
| --- | --- | --- |
| `invalid_input`, `invalid_trip` | 400, 422 | Bad field, or a departure outside the forecast window |
| `place_not_found` | 422 | Neither geocoder knows the address |
| `no_route` | 422 | No drivable route between the two places |
| `upstream_error` | 502 | A routing, geocoding or weather service failed; `retry_after` is set when a quick retry should work |
| `rate_limited` | 503 | The free weather quota is used up; `retry_after` says when to retry, if waiting helps |
| `throttled` | 429 | Too many plans from this client |
| `server_error` | 500 | Anything unexpected (logged on the server) |

The UI shows the message as written.

## How the map stays smooth

- **One request per plan.** `POST /api/plan/` returns the routes, checkpoints,
  ranking and all 49 hourly heatmap frames, about 35–45 KB gzipped for an
  800-mile trip. Nothing is fetched while the slider moves.
- **Blended frames.** The slider moves in quarter hours; the browser blends the
  two forecast hours on either side, so the heatmap changes continuously.
- **GPU layers.** Routes, checkpoints and the heatmap are MapLibre layers drawn
  by WebGL, not DOM elements. A slider step updates about 240 heatmap points.
- **Small geometry.** Route lines are simplified on the server (40 m
  tolerance), cutting ~10,000 points per route to about 1,000 with no visible
  change.
- **Reduced motion.** Animations are skipped when the system asks for reduced
  motion.

## Risk rules

Thresholds from the brief, implemented in [`backend/planner/services/risk.py`](backend/planner/services/risk.py):

| Condition | Low | Moderate | High | Severe | No Travel |
| --- | --- | --- | --- | --- | --- |
| Wind (mph) | < 25 | 25–34 | 35–44 | 45–54 | ≥ 55 |
| Rain (in/hr) | < 0.10 | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | > 1.00 |
| Snow (in/hr) | < 0.5 | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | > 3.0 |

Load rules: ≥ 55 mph is No Travel for any load; 45–54 mph with more than
30,000 lb is No Travel; 35–44 mph with more than 40,000 lb is Severe.

Ranking ([`recommend.py`](backend/planner/services/recommend.py)): routes with
No Travel miles last, then fewest Severe miles → fewest High miles → lowest
average risk → shortest travel time.

## Assumptions

Where the brief leaves room, this is what the code does:

| Topic | Decision |
| --- | --- |
| **Boundary values** | A value exactly on a boundary goes to the higher band (25 mph is Moderate, 0.25 in/hr rain is High). The exception is the top of rain and snow, which the brief writes as `> 1.00` and `> 3.0`: exactly 1.00 in/hr is Severe. |
| **Checkpoint level** | The worst of its wind (after load rules), rain and snow levels. |
| **Miles per level** | The road between two checkpoints takes the **worse** level of the two. If either end is dangerous, those miles count as dangerous. |
| **No Travel** | The brief ranks by Severe miles but doesn't say what No Travel means for a route. Here any No Travel miles **close the route**: it sorts last, is marked "Do not travel" and can't be recommended. On the map its truck drives as far as the last checkpoint before the No Travel stretch and stops there. If all three are closed there is no recommendation, only "Do not depart". |
| **Wait time** | For a closed route, the same route is re-scored with the departure pushed back one hour at a time (up to 48) until no checkpoint is No Travel. That delay is offered as "Leave at … instead". Severe conditions do not close a route. |
| **Average risk** | Mile-weighted mean of segment levels (Low 0 … No Travel 4). |
| **Near ties** | Compared at 0.1 mile, 0.01 average risk and 1 minute, so float noise can't decide a ranking. |
| **ETA** | Departure plus the routing engine's own driving time to that point on the route (not distance ÷ an average speed). No rest or fuel stops are added. |
| **Forecast hour** | The forecast hour nearest to the ETA. |
| **Wind** | Sustained 10 m wind speed. Gusts are shown in each checkpoint popup; set `WIND_FIELD=gust` to classify on gusts instead. |
| **Rain** | Open-Meteo `rain` + `showers` (large-scale plus convective), in inches for the hour. |
| **Units** | The weather API is asked for mph and inches directly, so nothing is converted in code. |
| **Times** | Departure is local time at the origin; all times are shown in the origin's timezone. |
| **Heatmap** | A grid of up to 240 points within 40 miles of any route. Hour 0 is departure. The "Risk" layer includes the load rules; Wind, Rain and Snow show the raw forecast on the same colour scale. |

## API choices

| Need | Service | Why |
| --- | --- | --- |
| Routing | **Valhalla** on the FOSSGIS public server, `truck` costing, 2 alternates | A real truck profile and built-in alternatives, no key |
| Routing fallback | **OSRM** public server | Valhalla's public server refuses trips over about 930 miles; OSRM has no such limit. It is a car profile, so each segment's speed is capped at 65 mph |
| Third route | Via-point routing | Neither engine guarantees 3 alternatives. When fewer come back, the app routes through points pushed sideways off the main route and keeps results that overlap existing routes by less than 80% and are at most 1.6× as long |
| Weather | **Open-Meteo** forecast API | Hourly wind, gusts, rain, snowfall in mph/inches; up to 100 locations per call |
| Geocoding | **Open-Meteo** geocoder, then **Nominatim** | Fast prefix search for suggestions; Nominatim covers street addresses |
| Basemap | CARTO Dark Matter and Positron vector tiles | Keyless, one per theme, rendered on the GPU with MapLibre |

**Caching** (Django in-memory cache): routes for 1 hour, forecasts for 30
minutes per 0.1° cell and UTC day, geocoding for a day. Changing only the load
weight or the checkpoint interval re-plans from cache in well under a second.

## Storm drill

Real weather is calm most days, so every route scores Low and the rules have
nothing to show. The **Storm drill** switch layers a simulated storm on Route
A, timed for when the truck gets there. The response is flagged `simulated`
and the UI labels it. It is off by default and never affects a normal plan.
When a drill is re-planned for a later departure, the storm stays where it was
(`storm_anchor`), so waiting it out works as it would with real weather.
Code: [`simulation.py`](backend/planner/services/simulation.py).

## Tests

`make test` runs the backend suite (107 tests) in about a second, with no
network access:

- `test_risk.py`: every band edge for wind, rain and snow; each load rule on both sides of its weight limit
- `test_recommend.py`: each ranking tie-break in turn, No Travel ordering, reason text
- `test_delay.py`: wait until a closed route opens, at the delayed arrival times, with load rules
- `test_checkpoints.py`: spacing for 10/25/50 miles, ETA from route time
- `test_weather.py`: units requested, nearest-hour lookup, batching, caching, missing data
- `test_heatmap.py`: corridor grid bounds, one frame per hour, load rules in frames
- `test_routing.py`: duplicate removal, via-point fill, detour rejection, provider fallback, response parsing
- `test_simulation.py`: storm drill placement in space and time, rain vs snow
- `test_geo.py`: distances, polyline decoding, interpolation, line simplification
- `test_http.py`: outbound error messages keep only readable text from third-party responses; an outage on the weather proxy falls back to Open-Meteo, while rate limits and bad requests are not retried
- `test_api.py`: full plan through the HTTP API, including "a storm that arrives after the truck has passed doesn't count", load changing the level, closed routes and wait times, every error code, the health check and out-of-range dates

## Known limits

- **Trip length.** Trips are limited by the weather API's free tier (about 560
  forecast cells per plan). Coast-to-coast works at 50-mile checkpoints; at 10
  miles the app asks for a wider interval.
- **Departure window.** From 24 hours ago to 12 days ahead, the range the
  forecast covers.
- **Long trips use car routing.** Over about 930 miles the OSRM fallback is a
  car profile with a truck speed cap, so it ignores truck restrictions.
- **No hours-of-service breaks.** ETAs assume continuous driving.
- **Public demo servers.** Valhalla, OSRM and Nominatim are shared community
  servers with fair-use limits, and Open-Meteo's free quota is per IP address;
  on a host with a shared outbound IP, other users count against it. A
  production app would self-host or use paid plans.
- **In-memory cache.** One process, cleared on restart. Redis would be the
  next step for more than one server.

## Project layout

```
backend/
  config/                 Django settings, URLs, WSGI
  planner/
    services/             one module per job (see Architecture)
    serializers.py        request validation
    views.py              three thin API views + error format
    tests/
frontend/
  src/
    App.tsx               state and layout
    api.ts, types.ts      API client and response types
    components/           MapView, TripFormPanel, RouteCard, CheckpointList, TimelineDock, …
    lib/                  geometry, formatting, risk scale
    index.css             theme tokens (light + dark); the map reads its colours from these
deploy/open-meteo-worker.js  Cloudflare Worker for the weather quota (see Deploy)
Dockerfile, render.yaml   single-service deploy
```
