"""Optional "storm drill": a synthetic storm layered on the real forecast.

Real weather is calm most days, which makes every route Low risk and hides
the risk and ranking logic. When the driver turns the drill on, a storm is
placed on the first route so the rules can be seen working. The response is
flagged `simulated` and the UI labels it clearly.
"""

import math
from dataclasses import replace
from datetime import datetime, timedelta

from .geo import flat_miles
from .routing import Route
from .weather import Forecast, Sample

STORM_POSITION = 0.45  # how far along the first route the storm sits
STORM_RADIUS_MI = 110.0
STORM_HALF_LIFE_H = 7.0
PEAK_WIND_MPH = 50.0
PEAK_GUST_MPH = 66.0
PEAK_RAIN_IN_HR = 0.7
PEAK_SNOW_IN_HR = 2.4
SNOW_ABOVE_LAT = 41.0  # the storm falls as snow north of this latitude


class StormForecast:
    """Wraps a Forecast, adding a storm centred in space and time."""

    def __init__(self, base: Forecast, center: tuple[float, float], peak: datetime):
        self._base = base
        self._center = center
        self._peak = peak

    def at(self, lat: float, lon: float, when: datetime) -> Sample:
        sample = self._base.at(lat, lon, when)
        strength = self._strength(lat, lon, when)
        if strength < 0.01:
            return sample
        snowing = lat >= SNOW_ABOVE_LAT
        return replace(
            sample,
            wind_mph=max(sample.wind_mph, PEAK_WIND_MPH * strength),
            wind_speed_mph=max(sample.wind_speed_mph, PEAK_WIND_MPH * strength),
            gust_mph=max(sample.gust_mph or 0.0, PEAK_GUST_MPH * strength),
            rain_in_hr=sample.rain_in_hr
            if snowing
            else max(sample.rain_in_hr, PEAK_RAIN_IN_HR * strength),
            snow_in_hr=max(sample.snow_in_hr, PEAK_SNOW_IN_HR * strength)
            if snowing
            else sample.snow_in_hr,
        )

    def _strength(self, lat: float, lon: float, when: datetime) -> float:
        """0..1: a bell curve in distance from the centre and in time from the peak."""
        miles = flat_miles((lon, lat), self._center)
        hours = abs((when - self._peak) / timedelta(hours=1))
        return math.exp(-((miles / STORM_RADIUS_MI) ** 2)) * math.exp(
            -((hours / STORM_HALF_LIFE_H) ** 2)
        )


def storm_on_route(base: Forecast, route: Route, departure: datetime) -> StormForecast:
    """A storm that peaks where and when the truck is 45% of the way along `route`."""
    center, elapsed = route.position_at(route.distance_mi * STORM_POSITION)
    return StormForecast(base, center, departure + timedelta(seconds=elapsed))
