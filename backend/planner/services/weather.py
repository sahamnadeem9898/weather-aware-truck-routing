"""Hourly forecasts from Open-Meteo, in the units the risk table uses.

Requests ask for mph and inches directly, so there is no unit conversion
anywhere else in the code. Open-Meteo's hourly rain/snow values are totals
for the hour, i.e. already in/hr.

Locations are snapped to a 0.1 degree cell (about 7 miles). Forecast models
are no finer than that, and it lets nearby checkpoints, overlapping routes
and repeat requests share one cached forecast.
"""

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from django.conf import settings
from django.core.cache import cache

from .errors import RateLimited, UpstreamError
from .http import request_json

Cell = tuple[float, float]  # (lat, lon), rounded to CELL_DECIMALS
HourlyValues = tuple[float, float | None, float, float]  # wind, gust, rain, snow

CELL_DECIMALS = 1
CELLS_PER_REQUEST = 100
SECONDS_PER_HOUR = 3600
HOURLY_FIELDS = "wind_speed_10m,wind_gusts_10m,rain,showers,snowfall"
# Open-Meteo's free tier counts every location as one call, with per-minute,
# per-hour and per-day caps. Only the per-minute one is worth waiting out.
MINUTE_LIMIT_RETRY_SECONDS = 60


@dataclass(frozen=True)
class Sample:
    """Weather for one cell and hour."""

    wind_mph: float  # the value the risk table is applied to (see settings.WIND_FIELD)
    wind_speed_mph: float
    gust_mph: float | None
    rain_in_hr: float
    snow_in_hr: float


class ForecastUnavailable(UpstreamError):
    code = "forecast_unavailable"

    def __init__(self, when: datetime):
        super().__init__(
            "weather",
            f"No forecast is available for {when:%b %d, %H:%M} UTC. "
            "Pick a departure closer to today.",
        )


def cell_for(lat: float, lon: float) -> Cell:
    return (round(lat, CELL_DECIMALS), round(lon, CELL_DECIMALS))


def nearest_hour(when: datetime) -> int:
    """Unix timestamp of the forecast hour closest to `when`."""
    return int(round(when.timestamp() / SECONDS_PER_HOUR)) * SECONDS_PER_HOUR


class Forecast:
    """Lookup of hourly weather by cell and time."""

    def __init__(self, hours_by_cell: dict[Cell, dict[int, HourlyValues]]):
        self._hours = hours_by_cell

    def at(self, lat: float, lon: float, when: datetime) -> Sample:
        """Weather at the forecast hour nearest to `when`."""
        values = self._hours.get(cell_for(lat, lon), {}).get(nearest_hour(when))
        if values is None:
            raise ForecastUnavailable(when)
        speed, gust, rain, snow = values
        use_gust = settings.WIND_FIELD == "gust" and gust is not None
        return Sample(
            wind_mph=gust if use_gust else speed,  # type: ignore[arg-type]
            wind_speed_mph=speed,
            gust_mph=gust,
            rain_in_hr=rain,
            snow_in_hr=snow,
        )


def load_forecast(cells: Iterable[Cell], start: datetime, end: datetime) -> Forecast:
    """Forecast for every cell covering [start, end]. Cached per cell and UTC day."""
    cells = sorted(set(cells))
    days = _days_between(start, end)

    keys = {(cell, day): _cache_key(cell, day) for cell in cells for day in days}
    cached = cache.get_many(keys.values())
    missing = [cell for cell in cells if any(keys[(cell, day)] not in cached for day in days)]

    fresh: dict[str, dict[int, HourlyValues]] = {}
    if missing:
        chunks = [
            missing[i : i + CELLS_PER_REQUEST] for i in range(0, len(missing), CELLS_PER_REQUEST)
        ]
        errors: list[UpstreamError] = []
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(_fetch, chunk, days): chunk for chunk in chunks}
            for future in as_completed(futures):
                try:
                    hours_per_cell = future.result()
                except UpstreamError as exc:
                    errors.append(exc)
                    continue
                # Cache each batch as it lands: if another batch fails, a retry
                # only asks for what is still missing and spends no extra quota.
                batch = {
                    keys[(cell, day)]: _hours_on(hours, day)
                    for cell, hours in zip(futures[future], hours_per_cell, strict=True)
                    for day in days
                }
                cache.set_many(batch, settings.WEATHER_CACHE_SECONDS)
                fresh.update(batch)
        if errors:
            raise next((e for e in errors if isinstance(e, RateLimited)), errors[0])

    stored = {**cached, **fresh}
    hours_by_cell: dict[Cell, dict[int, HourlyValues]] = {}
    for cell in cells:
        merged: dict[int, HourlyValues] = {}
        for day in days:
            merged.update(stored.get(keys[(cell, day)], {}))
        hours_by_cell[cell] = merged
    return Forecast(hours_by_cell)


def timezone_name(lat: float, lon: float) -> str:
    """IANA timezone at a location (Open-Meteo resolves it from coordinates)."""
    key = f"tz:{lat:.2f},{lon:.2f}"
    if (name := cache.get(key)) is None:
        data = _open_meteo(
            {
                "latitude": lat,
                "longitude": lon,
                "timezone": "auto",
                "forecast_days": 1,
                "daily": "weather_code",
            }
        )
        name = data.get("timezone") or "UTC"
        cache.set(key, name, settings.GEOCODE_CACHE_SECONDS)
    return name


def _days_between(start: datetime, end: datetime) -> list[date]:
    first = start.astimezone(UTC).date()
    last = end.astimezone(UTC).date()
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _cache_key(cell: Cell, day: date) -> str:
    return f"wx:{settings.WIND_FIELD}:{cell[0]}:{cell[1]}:{day.isoformat()}"


def _hours_on(hours: dict[int, HourlyValues], day: date) -> dict[int, HourlyValues]:
    start = int(datetime(day.year, day.month, day.day, tzinfo=UTC).timestamp())
    return {ts: v for ts, v in hours.items() if start <= ts < start + 24 * SECONDS_PER_HOUR}


def _fetch(cells: list[Cell], days: list[date]) -> list[dict[int, HourlyValues]]:
    """One batched Open-Meteo call: hourly values for every cell in `cells`."""
    data = _open_meteo(
        {
            "latitude": ",".join(str(lat) for lat, _ in cells),
            "longitude": ",".join(str(lon) for _, lon in cells),
            "hourly": HOURLY_FIELDS,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_date": days[0].isoformat(),
            "end_date": days[-1].isoformat(),
        },
        timeout=40.0,
    )
    locations = data if isinstance(data, list) else [data]
    if len(locations) != len(cells):
        raise UpstreamError("weather", "The weather service returned an incomplete forecast.")
    return [_parse_hourly(location["hourly"]) for location in locations]


def _open_meteo(params: dict, timeout: float = 25.0):
    """Call the forecast API, turning its errors into messages a driver can act on."""
    try:
        return request_json(
            "weather",
            "GET",
            f"{settings.OPEN_METEO_URL}/v1/forecast",
            params=params,
            timeout=timeout,
        )
    except UpstreamError as exc:
        if exc.http_status == 429:
            if "minut" in str(exc).lower():
                raise RateLimited(
                    "weather",
                    "The free weather service is rate limiting requests. "
                    "Wait a minute and try again.",
                    retry_after=MINUTE_LIMIT_RETRY_SECONDS,
                ) from exc
            window = "daily" if "daily" in str(exc).lower() else "hourly"
            raise RateLimited(
                "weather",
                f"The free weather service's {window} limit has been reached. Try again later.",
            ) from exc
        if exc.http_status == 400:
            raise UpstreamError(
                "weather",
                "The weather service has no forecast for those dates. "
                "Pick a departure within the next 12 days.",
                http_status=400,
            ) from exc
        raise


def _parse_hourly(hourly: dict) -> dict[int, HourlyValues]:
    """Hour timestamp -> (wind, gust, rain, snow). Hours with gaps are left out."""
    out: dict[int, HourlyValues] = {}
    rows = zip(
        hourly["time"],
        hourly["wind_speed_10m"],
        hourly["wind_gusts_10m"],
        hourly["rain"],
        hourly["showers"],
        hourly["snowfall"],
        strict=False,
    )
    for ts, wind, gust, rain, showers, snow in rows:
        if wind is None or rain is None or snow is None:
            continue
        # Liquid precipitation = large-scale rain + convective showers.
        out[int(ts)] = (float(wind), gust, float(rain) + float(showers or 0.0), float(snow))
    return out
