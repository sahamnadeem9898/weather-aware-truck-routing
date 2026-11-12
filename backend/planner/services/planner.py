"""Orchestrates one trip plan: routes -> checkpoints -> weather -> risk -> ranking."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings

from . import delay, heatmap, recommend, routing, simulation, weather
from .checkpoints import Checkpoint, build_checkpoints
from .errors import InvalidTrip
from .geo import simplify
from .geocoding import Place
from .risk import Assessment, assess

MAX_PAST = timedelta(hours=24)
MAX_AHEAD = timedelta(days=12)
ROUTE_IDS = "ABC"
ForecastSource = weather.Forecast | simulation.StormForecast
# ~40 m: invisible on the map, and sends the browser about 15 times fewer points.
GEOMETRY_TOLERANCE_DEG = 0.0004


@dataclass(frozen=True)
class TripRequest:
    origin: Place
    destination: Place
    departure_local: datetime  # naive wall-clock time at the origin
    load_lb: int
    interval_mi: int
    simulate_storm: bool = False
    # The departure the storm drill is timed against. Kept fixed when the driver
    # re-plans with a later departure, so the storm does not move with them.
    storm_anchor_local: datetime | None = None


def plan_trip(trip: TripRequest, now: datetime | None = None) -> dict:
    """Everything the map needs for one trip, as a JSON-ready dict."""
    now = now or datetime.now(UTC)
    zone = _zone(weather.timezone_name(trip.origin.lat, trip.origin.lon))
    departure = _to_utc(trip.departure_local, zone)
    if departure < now - MAX_PAST:
        raise InvalidTrip("Departure is more than a day in the past. Pick a later time.")
    if departure > now + MAX_AHEAD:
        raise InvalidTrip("Forecasts only reach about two weeks out. Depart within 12 days.")

    routes = routing.find_routes(
        (trip.origin.lon, trip.origin.lat), (trip.destination.lon, trip.destination.lat)
    )
    checkpoints = [build_checkpoints(route, trip.interval_mi) for route in routes]
    grid, grid_step = heatmap.corridor_grid([route.coords for route in routes])

    cells = {weather.cell_for(lat, lon) for lon, lat in grid}
    cells |= {weather.cell_for(cp.lat, cp.lon) for cps in checkpoints for cp in cps}
    if len(cells) > settings.MAX_WEATHER_CELLS:
        raise InvalidTrip(
            f"This trip needs weather at {len(cells)} locations, more than the free "
            "forecast service allows per request. Use a wider checkpoint interval."
        )

    # Enough forecast for the 48 h heatmap and for testing delayed departures.
    longest = max(route.duration_s for route in routes)
    horizon = max(heatmap.HEATMAP_HOURS, delay.MAX_WAIT_HOURS) * 3600 + longest
    forecast = weather.load_forecast(
        cells,
        start=departure - timedelta(hours=1),
        end=departure + timedelta(seconds=horizon) + timedelta(hours=1),
    )

    if trip.simulate_storm:
        anchor = _to_utc(trip.storm_anchor_local or trip.departure_local, zone)
        if abs(anchor - departure) > MAX_AHEAD:
            raise InvalidTrip("The storm drill's reference time is out of range.")
        forecast = simulation.storm_on_route(forecast, routes[0], anchor)

    route_payloads = []
    summaries = []
    for route_id, route, cps in zip(ROUTE_IDS, routes, checkpoints, strict=False):
        payload, summary = _score_route(route_id, route, cps, forecast, departure, trip.load_lb)
        route_payloads.append(payload)
        summaries.append(summary)

    # A route with any No Travel miles is closed. For each closed route, work
    # out how long the driver would have to wait for it to open.
    waits = {}
    for payload, summary, cps in zip(route_payloads, summaries, checkpoints):
        if summary.has_no_travel:
            hours = delay.hours_until_clear(cps, forecast, departure, trip.load_lb)
            payload["wait"] = waits[summary.route_id] = _wait(trip, departure, hours)

    ranked = recommend.rank(summaries)
    for position, summary in enumerate(ranked, start=1):
        next(p for p in route_payloads if p["id"] == summary.route_id)["rank"] = position
    _tag(route_payloads)

    # Only an open route can be recommended. If every route is closed there is
    # no pick, just the shortest wait.
    best = ranked[0] if not ranked[0].has_no_travel else None
    shortest_wait = min(
        ((route_id, wait) for route_id, wait in waits.items() if wait),
        key=lambda item: item[1]["hours"],
        default=None,
    )

    return {
        "origin": _place(trip.origin),
        "destination": _place(trip.destination),
        "departure": _iso(departure),
        "timezone": zone.key,
        "load_lb": trip.load_lb,
        "interval_mi": trip.interval_mi,
        "wind_field": settings.WIND_FIELD,
        "routing_provider": routes[0].provider,
        "simulated": trip.simulate_storm,
        "storm_anchor": (trip.storm_anchor_local or trip.departure_local).strftime("%Y-%m-%dT%H:%M")
        if trip.simulate_storm
        else None,
        "recommendation": {
            "route_id": best.route_id if best else None,
            "reasons": [recommend.explain(best, other) for other in ranked[1:]] if best else [],
            "no_safe_route": best is None,
            "wait": {"route_id": shortest_wait[0], **shortest_wait[1]}
            if best is None and shortest_wait
            else None,
        },
        "routes": route_payloads,
        "heatmap": {
            "points": grid,
            "step_deg": grid_step,
            "hours": heatmap.HEATMAP_HOURS,
            **heatmap.build_frames(grid, forecast, departure, trip.load_lb),
        },
    }


def _score_route(
    route_id: str,
    route: routing.Route,
    checkpoints: list[Checkpoint],
    forecast: ForecastSource,
    departure: datetime,
    load_lb: int,
) -> tuple[dict, recommend.RouteSummary]:
    rows = []
    assessments: list[Assessment] = []
    for cp in checkpoints:
        # The whole point: weather is read at the truck's arrival time here.
        eta = departure + timedelta(seconds=cp.elapsed_s)
        sample = forecast.at(cp.lat, cp.lon, eta)
        result = assess(sample.wind_mph, sample.rain_in_hr, sample.snow_in_hr, load_lb)
        assessments.append(result)
        rows.append(
            {
                "mile": round(cp.mile, 1),
                "lat": round(cp.lat, 5),
                "lon": round(cp.lon, 5),
                "elapsed_s": round(cp.elapsed_s),
                "eta": _iso(eta),
                "wind_mph": round(sample.wind_speed_mph, 1),
                "gust_mph": None if sample.gust_mph is None else round(sample.gust_mph, 1),
                "rain_in_hr": round(sample.rain_in_hr, 3),
                "snow_in_hr": round(sample.snow_in_hr, 2),
                "level": int(result.level),
                "load_rule_applied": result.load_rule_applied,
                "reason": result.reason,
            }
        )

    segments = recommend.build_segments(
        [cp.mile for cp in checkpoints], [a.level for a in assessments]
    )
    summary = recommend.summarize(route_id, route.duration_s, segments)
    payload = {
        "id": route_id,
        "rank": 0,
        "tags": [],
        "distance_mi": round(route.distance_mi, 1),
        "duration_s": round(route.duration_s),
        "arrival": _iso(departure + timedelta(seconds=route.duration_s)),
        "miles_by_level": [round(m, 1) for m in summary.miles_by_level],
        "avg_risk": round(summary.avg_risk, 2),
        "worst_level": int(summary.worst_level),
        "has_no_travel": summary.has_no_travel,
        "wait": None,
        "geometry": [
            [round(lon, 5), round(lat, 5)]
            for lon, lat in simplify(route.coords, GEOMETRY_TOLERANCE_DEG)
        ],
        "checkpoints": rows,
        "segments": [
            {
                "from_mile": round(s.from_mile, 1),
                "to_mile": round(s.to_mile, 1),
                "level": int(s.level),
            }
            for s in segments
        ],
    }
    return payload, summary


def _wait(trip: TripRequest, departure: datetime, hours: int | None) -> dict | None:
    """When a closed route opens, as both a UTC instant and origin wall-clock time."""
    if hours is None:
        return None
    return {
        "hours": hours,
        "departure": _iso(departure + timedelta(hours=hours)),
        "departure_local": (trip.departure_local + timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M"
        ),
    }


def _tag(routes: list[dict]) -> None:
    min(routes, key=lambda r: r["duration_s"])["tags"].append("Fastest")
    min(routes, key=lambda r: r["distance_mi"])["tags"].append("Shortest")


def _zone(name: str) -> ZoneInfo:
    """The origin's timezone, or UTC if this server doesn't know the name."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _to_utc(local: datetime, zone: ZoneInfo) -> datetime:
    try:
        return local.replace(tzinfo=zone).astimezone(UTC)
    except OverflowError as exc:
        raise InvalidTrip("That departure date is out of range.") from exc


def _iso(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _place(place: Place) -> dict:
    return {"label": place.label, "lat": place.lat, "lon": place.lon}
