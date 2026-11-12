"""Small geometry helpers. Coordinates are (lon, lat) pairs, as in GeoJSON."""

import math
from bisect import bisect_right

LonLat = tuple[float, float]

EARTH_RADIUS_MI = 3958.7613
MILES_PER_DEGREE_LAT = 69.172


def haversine_miles(a: LonLat, b: LonLat) -> float:
    lon1, lat1, lon2, lat2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(h))


def flat_miles(a: LonLat, b: LonLat) -> float:
    """Fast equirectangular distance; accurate enough for points < ~200 mi apart."""
    mean_lat = math.radians((a[1] + b[1]) / 2)
    dx = (b[0] - a[0]) * math.cos(mean_lat)
    dy = b[1] - a[1]
    return MILES_PER_DEGREE_LAT * math.hypot(dx, dy)


def cumulative_miles(coords: list[LonLat]) -> list[float]:
    """Distance from the first point to every point along the line."""
    total = 0.0
    out = [0.0]
    for prev, cur in zip(coords, coords[1:], strict=False):
        total += haversine_miles(prev, cur)
        out.append(total)
    return out


def interpolate_along(
    coords: list[LonLat], cumulative: list[float], target: float
) -> tuple[LonLat, int, float]:
    """Point at `target` along the line.

    Returns the point, the index of the segment it lies on, and the fraction
    (0..1) of the way through that segment.
    """
    target = min(max(target, 0.0), cumulative[-1])
    i = min(bisect_right(cumulative, target) - 1, len(coords) - 2)
    span = cumulative[i + 1] - cumulative[i]
    t = 0.0 if span <= 0 else (target - cumulative[i]) / span
    (lon1, lat1), (lon2, lat2) = coords[i], coords[i + 1]
    return (lon1 + (lon2 - lon1) * t, lat1 + (lat2 - lat1) * t), i, t


def decode_polyline(encoded: str, precision: int = 6) -> list[LonLat]:
    """Decode a Google-style encoded polyline into (lon, lat) pairs."""
    factor = 10**precision
    coords: list[LonLat] = []
    index = lat = lon = 0
    length = len(encoded)
    while index < length:
        deltas = []
        for _ in range(2):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            deltas.append(~(result >> 1) if result & 1 else result >> 1)
        lat += deltas[0]
        lon += deltas[1]
        coords.append((lon / factor, lat / factor))
    return coords


def simplify(coords: list[LonLat], tolerance_deg: float) -> list[LonLat]:
    """Ramer-Douglas-Peucker line simplification (iterative, no recursion limit)."""
    if len(coords) < 3:
        return list(coords)
    keep = [False] * len(coords)
    keep[0] = keep[-1] = True
    stack = [(0, len(coords) - 1)]
    while stack:
        start, end = stack.pop()
        (x1, y1), (x2, y2) = coords[start], coords[end]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        worst, worst_i = 0.0, -1
        for i in range(start + 1, end):
            x, y = coords[i]
            if norm == 0:
                dist = math.hypot(x - x1, y - y1)
            else:
                dist = abs(dy * (x - x1) - dx * (y - y1)) / norm
            if dist > worst:
                worst, worst_i = dist, i
        if worst > tolerance_deg:
            keep[worst_i] = True
            stack.append((start, worst_i))
            stack.append((worst_i, end))
    return [c for c, k in zip(coords, keep, strict=False) if k]


def thin(coords: list[LonLat], min_gap_miles: float) -> list[LonLat]:
    """Keep points at least `min_gap_miles` apart (always keeps both ends)."""
    if not coords:
        return []
    out = [coords[0]]
    for c in coords[1:-1]:
        if flat_miles(out[-1], c) >= min_gap_miles:
            out.append(c)
    if len(coords) > 1:
        out.append(coords[-1])
    return out


def offset_perpendicular(start: LonLat, end: LonLat, anchor: LonLat, miles: float) -> LonLat:
    """Move `anchor` sideways (perpendicular to start->end) by `miles`.

    Positive values go to the left of the direction of travel.
    """
    cos_lat = math.cos(math.radians(anchor[1]))
    dx = (end[0] - start[0]) * cos_lat
    dy = end[1] - start[1]
    norm = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / norm, dx / norm
    return (
        anchor[0] + nx * miles / (MILES_PER_DEGREE_LAT * max(cos_lat, 0.01)),
        anchor[1] + ny * miles / MILES_PER_DEGREE_LAT,
    )
