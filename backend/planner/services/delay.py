"""How long to wait before a closed route becomes drivable. Pure logic, no I/O.

A route with any No Travel checkpoint is closed: the truck must not take it.
The useful follow-up is "when can I go?", so this replays the same route with
the departure pushed back an hour at a time until no checkpoint is No Travel.
"""

from datetime import datetime, timedelta

from .checkpoints import Checkpoint
from .risk import Level, overall_level
from .simulation import StormForecast
from .weather import Forecast, ForecastUnavailable

MAX_WAIT_HOURS = 48


def hours_until_clear(
    checkpoints: list[Checkpoint],
    forecast: Forecast | StormForecast,
    departure: datetime,
    load_lb: float,
) -> int | None:
    """Smallest whole-hour delay after which the route has no No Travel checkpoint.

    Returns None if it stays closed for MAX_WAIT_HOURS or the forecast runs out.
    """
    for hours in range(1, MAX_WAIT_HOURS + 1):
        start = departure + timedelta(hours=hours)
        try:
            if all(_passable(cp, forecast, start, load_lb) for cp in checkpoints):
                return hours
        except ForecastUnavailable:
            return None
    return None


def _passable(
    cp: Checkpoint, forecast: Forecast | StormForecast, start: datetime, load_lb: float
) -> bool:
    sample = forecast.at(cp.lat, cp.lon, start + timedelta(seconds=cp.elapsed_s))
    return (
        overall_level(sample.wind_mph, sample.rain_in_hr, sample.snow_in_hr, load_lb)
        < Level.NO_TRAVEL
    )
