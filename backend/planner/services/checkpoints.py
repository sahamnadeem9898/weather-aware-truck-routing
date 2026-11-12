"""Checkpoints along a route, each with the truck's elapsed time on arrival."""

from dataclasses import dataclass

from .routing import Route

# A trailing stub shorter than this is merged into the destination checkpoint.
MIN_TAIL_MILES = 0.5


@dataclass(frozen=True)
class Checkpoint:
    mile: float
    lon: float
    lat: float
    elapsed_s: float  # driving time from departure to this point


def build_checkpoints(route: Route, interval_mi: float) -> list[Checkpoint]:
    """Origin, one point every `interval_mi` miles, and the destination."""
    total = route.distance_mi
    miles = [0.0]
    next_mile = interval_mi
    while next_mile < total - MIN_TAIL_MILES:
        miles.append(next_mile)
        next_mile += interval_mi
    if total > 0:
        miles.append(total)

    checkpoints = []
    for mile in miles:
        (lon, lat), elapsed = route.position_at(mile)
        checkpoints.append(Checkpoint(mile=mile, lon=lon, lat=lat, elapsed_s=elapsed))
    return checkpoints
