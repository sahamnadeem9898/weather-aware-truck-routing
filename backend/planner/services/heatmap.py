"""Weather heatmap along the trip corridor, precomputed for every slider hour.

The grid is built once per plan and every hour's values ship in the plan
response, so moving the slider never triggers a network call.
"""

import math
from datetime import datetime, timedelta

from .geo import MILES_PER_DEGREE_LAT, LonLat, flat_miles, thin
from .risk import overall_level
from .simulation import StormForecast
from .weather import Forecast

HEATMAP_HOURS = 48
CORRIDOR_HALF_WIDTH_MI = 40.0
MAX_POINTS = 240
# Longitude spacing options, finest first; the first that fits MAX_POINTS wins.
STEP_OPTIONS_DEG = [0.2, 0.25, 0.3, 0.4, 0.5, 0.65, 0.8, 1.0, 1.3, 1.7, 2.2, 3.0]


def corridor_grid(routes: list[list[LonLat]]) -> tuple[list[LonLat], float]:
    """Evenly spaced points within CORRIDOR_HALF_WIDTH_MI of any route.

    Returns the points and the longitude step in degrees. Latitude spacing is
    shrunk by cos(latitude) so cells are square on a Web Mercator map.
    """
    all_points = [p for coords in routes for p in coords]
    mid_lat = (min(p[1] for p in all_points) + max(p[1] for p in all_points)) / 2
    cos_lat = max(math.cos(math.radians(mid_lat)), 0.2)

    for step in STEP_OPTIONS_DEG:
        lat_step = step * cos_lat
        cell_miles = lat_step * MILES_PER_DEGREE_LAT
        reach = math.ceil(CORRIDOR_HALF_WIDTH_MI / cell_miles)
        cells: set[tuple[int, int]] = set()
        for coords in routes:
            for lon, lat in thin(coords, max(cell_miles / 2, 5.0)):
                ci, cj = round(lon / step), round(lat / lat_step)
                for di in range(-reach, reach + 1):
                    for dj in range(-reach, reach + 1):
                        cell = (ci + di, cj + dj)
                        if cell in cells:
                            continue
                        center = (cell[0] * step, cell[1] * lat_step)
                        if flat_miles((lon, lat), center) <= CORRIDOR_HALF_WIDTH_MI:
                            cells.add(cell)
            if len(cells) > MAX_POINTS:
                break
        if len(cells) <= MAX_POINTS:
            break

    points = [(round(i * step, 4), round(j * lat_step, 4)) for i, j in sorted(cells)]
    return points, step


def build_frames(
    points: list[LonLat], forecast: Forecast | StormForecast, start: datetime, load_lb: float
) -> dict[str, list[list[float]]]:
    """Per-hour arrays (one value per grid point) for hours 0..HEATMAP_HOURS."""
    frames: dict[str, list[list[float]]] = {"wind": [], "rain": [], "snow": [], "level": []}
    for hour in range(HEATMAP_HOURS + 1):
        when = start + timedelta(hours=hour)
        wind, rain, snow, level = [], [], [], []
        for lon, lat in points:
            sample = forecast.at(lat, lon, when)
            wind.append(round(sample.wind_mph, 1))
            rain.append(round(sample.rain_in_hr, 3))
            snow.append(round(sample.snow_in_hr, 2))
            level.append(
                int(overall_level(sample.wind_mph, sample.rain_in_hr, sample.snow_in_hr, load_lb))
            )
        frames["wind"].append(wind)
        frames["rain"].append(rain)
        frames["snow"].append(snow)
        frames["level"].append(level)
    return frames
