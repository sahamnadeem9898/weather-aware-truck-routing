"""Shared builders for tests: straight-line routes and constant forecasts."""

from datetime import UTC, datetime

from planner.services.geo import cumulative_miles
from planner.services.routing import Route
from planner.services.weather import Sample

DEPARTURE = datetime(2026, 11, 13, 14, 0, tzinfo=UTC)


def straight_route(miles: float, mph: float = 50.0, lat: float = 35.0, points: int = 50) -> Route:
    """An east-west route of roughly `miles` at a constant speed."""
    degrees = miles / 56.66  # one degree of longitude at 35 N is about 56.66 miles
    coords = [(-100.0 + degrees * i / points, lat) for i in range(points + 1)]
    cum = cumulative_miles(coords)
    return Route(coords, cum, [m / mph * 3600 for m in cum], provider="test")


def sample(wind: float = 0.0, rain: float = 0.0, snow: float = 0.0) -> Sample:
    return Sample(
        wind_mph=wind, wind_speed_mph=wind, gust_mph=wind, rain_in_hr=rain, snow_in_hr=snow
    )


class FakeForecast:
    """Forecast whose weather is decided by a function of (lat, lon, when)."""

    def __init__(self, fn=None):
        self._fn = fn or (lambda lat, lon, when: sample())
        self.calls: list[tuple[float, float, datetime]] = []

    def at(self, lat: float, lon: float, when: datetime) -> Sample:
        self.calls.append((lat, lon, when))
        return self._fn(lat, lon, when)
