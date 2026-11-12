"""Three route options between two places.

Primary provider: Valhalla (FOSSGIS public server) with the `truck` costing
model and built-in alternates. It refuses trips over ~930 miles, so the
fallback is the public OSRM server (car profile, speeds capped at a truck's).

Neither API guarantees three alternatives. When fewer come back, extra
options are produced by routing through "via" points pushed sideways off the
main route, keeping only results that are genuinely different roads.
"""

import logging
import math
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from django.conf import settings
from django.core.cache import caches

from .errors import NoRouteFound, UpstreamError
from .geo import (
    LonLat,
    cumulative_miles,
    decode_polyline,
    flat_miles,
    haversine_miles,
    interpolate_along,
    offset_perpendicular,
    thin,
)
from .http import request_json

logger = logging.getLogger(__name__)

ROUTE_COUNT = 3
TRUCK_MAX_MPH = 65.0  # cap applied to OSRM's car speeds
SECONDS_PER_HOUR = 3600.0

# Two routes are "the same" if this share of one lies within OVERLAP_MILES of the other.
MAX_OVERLAP_SHARE = 0.8
OVERLAP_MILES = 3.0
# A via-point route is rejected if it is this much worse than the best one.
MAX_DETOUR_FACTOR = 1.6
# (position along the main route, sideways offset as a share of trip length)
VIA_CANDIDATES = [(0.5, 0.15), (0.5, -0.15), (0.5, 0.3), (0.5, -0.3), (0.33, 0.2), (0.66, -0.2)]

Provider = Callable[[list[LonLat], int], list["Route"]]


@dataclass(frozen=True)
class Route:
    """A drivable line with distance and driving time known at every vertex."""

    coords: list[LonLat]
    cum_miles: list[float]
    cum_seconds: list[float]
    provider: str

    @property
    def distance_mi(self) -> float:
        return self.cum_miles[-1]

    @property
    def duration_s(self) -> float:
        return self.cum_seconds[-1]

    def position_at(self, mile: float) -> tuple[LonLat, float]:
        """Location and elapsed driving seconds at `mile` along the route."""
        point, i, t = interpolate_along(self.coords, self.cum_miles, mile)
        elapsed = self.cum_seconds[i] + (self.cum_seconds[i + 1] - self.cum_seconds[i]) * t
        return point, elapsed


def find_routes(origin: LonLat, destination: LonLat) -> list[Route]:
    """Up to three distinct routes, in the order the routing API prefers them."""
    key = "routes:{:.4f},{:.4f}:{:.4f},{:.4f}".format(*origin, *destination)
    route_cache = caches["routes"]
    if (cached := route_cache.get(key)) is not None:
        return cached

    if haversine_miles(origin, destination) < 1.0:
        raise NoRouteFound("Origin and destination are the same place.")

    provider, routes = _first_working_provider(origin, destination)
    routes = _distinct(routes)
    if len(routes) < ROUTE_COUNT:
        routes = _add_via_routes(provider, origin, destination, routes)

    routes = routes[:ROUTE_COUNT]
    route_cache.set(key, routes, settings.ROUTE_CACHE_SECONDS)
    return routes


def _first_working_provider(origin: LonLat, destination: LonLat) -> tuple[Provider, list[Route]]:
    last_error: Exception | None = None
    for provider in (_valhalla, _osrm):
        try:
            routes = provider([origin, destination], ROUTE_COUNT - 1)
        except NoRouteFound as exc:
            last_error = exc
            continue
        except UpstreamError as exc:
            logger.warning("Routing provider %s failed: %s", provider.__name__, exc)
            last_error = last_error or exc
            continue
        if routes:
            return provider, routes
    if isinstance(last_error, NoRouteFound):
        raise last_error
    raise UpstreamError("routing", "Routing services are unavailable right now. Try again shortly.")


# --- Making sure we have three different roads ------------------------------


def _overlap_share(candidate: Route, existing: Route) -> float:
    """Share of `candidate` that runs within OVERLAP_MILES of `existing`."""
    samples = 60
    reference = thin(existing.coords, 1.0)
    near = 0
    for k in range(samples + 1):
        point, _, _ = interpolate_along(
            candidate.coords, candidate.cum_miles, candidate.distance_mi * k / samples
        )
        if any(
            abs(point[1] - ref[1]) < 0.1 and flat_miles(point, ref) <= OVERLAP_MILES
            for ref in reference
        ):
            near += 1
    return near / (samples + 1)


def _is_new(candidate: Route, accepted: list[Route]) -> bool:
    return all(_overlap_share(candidate, route) < MAX_OVERLAP_SHARE for route in accepted)


def _distinct(routes: list[Route]) -> list[Route]:
    accepted: list[Route] = []
    for route in routes:
        if _is_new(route, accepted):
            accepted.append(route)
    return accepted


def _add_via_routes(
    provider: Provider, origin: LonLat, destination: LonLat, routes: list[Route]
) -> list[Route]:
    main = routes[0]
    trip_miles = haversine_miles(origin, destination)
    vias = []
    for position, offset in VIA_CANDIDATES:
        anchor, _, _ = interpolate_along(main.coords, main.cum_miles, main.distance_mi * position)
        vias.append(offset_perpendicular(origin, destination, anchor, offset * trip_miles))

    def attempt(via: LonLat) -> Route | None:
        try:
            found = provider([origin, via, destination], 0)
        except (UpstreamError, NoRouteFound):
            return None
        return found[0] if found else None

    with ThreadPoolExecutor(max_workers=3) as pool:
        candidates = list(pool.map(attempt, vias))

    best_time = min(r.duration_s for r in routes)
    best_dist = min(r.distance_mi for r in routes)
    routes = list(routes)
    for candidate in candidates:
        if len(routes) >= ROUTE_COUNT:
            break
        if candidate is None:
            continue
        too_long = (
            candidate.duration_s > best_time * MAX_DETOUR_FACTOR
            or candidate.distance_mi > best_dist * MAX_DETOUR_FACTOR
        )
        if not too_long and _is_new(candidate, routes):
            routes.append(candidate)
    return routes


# --- Valhalla ---------------------------------------------------------------


def _valhalla(points: list[LonLat], alternates: int) -> list[Route]:
    locations = []
    for i, (lon, lat) in enumerate(points):
        is_end = i in (0, len(points) - 1)
        # "through" = pass by without stopping or U-turning.
        locations.append({"lon": lon, "lat": lat, "type": "break" if is_end else "through"})
    body: dict = {"locations": locations, "costing": "truck", "units": "miles"}
    if alternates and len(points) == 2:
        body["alternates"] = alternates

    try:
        data = request_json("routing", "POST", f"{settings.VALHALLA_URL}/route", json=body)
    except UpstreamError as exc:
        # 442 = "No path could be found for input", 171 = no suitable edges near location
        if exc.http_status == 400 and ("No path" in str(exc) or "No suitable edges" in str(exc)):
            raise NoRouteFound("No drivable truck route was found between those places.") from exc
        raise

    trips = [data["trip"], *(alt["trip"] for alt in data.get("alternates", []))]
    return [_valhalla_trip_to_route(trip) for trip in trips]


def _valhalla_trip_to_route(trip: dict) -> Route:
    coords: list[LonLat] = []
    seconds: list[float] = []
    elapsed = 0.0
    for leg in trip["legs"]:
        shape = decode_polyline(leg["shape"], precision=6)
        miles = cumulative_miles(shape)
        leg_seconds = [0.0] * len(shape)
        # Each maneuver covers a span of shape points and has a driving time;
        # spread that time across the span in proportion to distance.
        for man in leg["maneuvers"]:
            start, end = man["begin_shape_index"], man["end_shape_index"]
            span = miles[end] - miles[start]
            for i in range(start, end + 1):
                share = (miles[i] - miles[start]) / span if span > 0 else 1.0
                leg_seconds[i] = elapsed + man["time"] * share
            elapsed += man["time"]
        skip = 1 if coords else 0  # legs share their joining point
        coords.extend(shape[skip:])
        seconds.extend(leg_seconds[skip:])
    return Route(coords, cumulative_miles(coords), seconds, provider="valhalla-truck")


# --- OSRM -------------------------------------------------------------------


def _osrm(points: list[LonLat], alternates: int) -> list[Route]:
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in points)
    params = {
        "overview": "full",
        "geometries": "polyline6",
        "annotations": "duration,distance",
        "alternatives": alternates if len(points) == 2 and alternates else "false",
        "continue_straight": "true",
    }
    try:
        data = request_json(
            "routing", "GET", f"{settings.OSRM_URL}/route/v1/driving/{path}", params=params
        )
    except UpstreamError as exc:
        if exc.http_status == 400 and ("NoRoute" in str(exc) or "NoSegment" in str(exc)):
            raise NoRouteFound("No drivable route was found between those places.") from exc
        raise
    if data.get("code") != "Ok":
        raise NoRouteFound("No drivable route was found between those places.")
    return [_osrm_route_to_route(route) for route in data["routes"]]


def _osrm_route_to_route(raw: dict) -> Route:
    coords = decode_polyline(raw["geometry"], precision=6)
    miles = cumulative_miles(coords)
    durations = [d for leg in raw["legs"] for d in leg["annotation"]["duration"]]
    seconds = [0.0]
    if len(durations) == len(coords) - 1:
        # Per-segment car times, slowed where they exceed a truck's top speed.
        for i, car_seconds in enumerate(durations):
            truck_seconds = (miles[i + 1] - miles[i]) / TRUCK_MAX_MPH * SECONDS_PER_HOUR
            seconds.append(seconds[-1] + max(car_seconds, truck_seconds))
    else:
        # Annotation doesn't line up with the geometry: spread time by distance.
        total = max(raw["duration"], miles[-1] / TRUCK_MAX_MPH * SECONDS_PER_HOUR)
        seconds = [total * m / miles[-1] if miles[-1] else 0.0 for m in miles]
    if not all(math.isfinite(s) for s in seconds):
        raise UpstreamError("routing", "The routing service returned invalid travel times.")
    return Route(coords, miles, seconds, provider="osrm")
